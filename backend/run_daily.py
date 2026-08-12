#!/usr/bin/env python3
"""
Daily multi-strategy scan runner.

Runs 3 different scanning strategies and writes JSON for each:
  - Pre-Breakout      → web/data/latest.json + archive/
  - Golden Cross      → web/data/golden_cross/latest.json + archive/
  - Ichimoku          → web/data/ichimoku/latest.json + archive/
"""
import argparse
import json
import os
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import BreakoutScanner
from scanner.exporter import to_excel, to_json, to_html, write_json
from scanner.data_fetcher import get_ticker_universe, fetch_universe, fetch_vnindex
from scanner.corporate_actions import apply_event_filter
from scanner.market_regime import (
    compute_regime, compute_breadth, compute_relative_strength, annotate_results,
)
from scanner.strategies import golden_cross, ichimoku

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('daily')


def is_intraday_run() -> bool:
    """
    Bản quét 12:00 ICT chạy giữa phiên (phiên chiều chưa đóng).

    Khối lượng lúc đó mới đạt ~40-50% cả ngày nên các tiêu chí dựa trên volume
    (vol_surge, pocket_pivot, volume_confirm) bị thiên lệch âm có hệ thống.
    Dữ liệu này vẫn hữu ích để theo dõi trong ngày, nhưng KHÔNG được ghi vào
    archive — nếu ghi, lịch sử dùng cho backtest sẽ lẫn dữ liệu nửa phiên và
    mọi thống kê sau này đều sai.
    """
    return os.environ.get('SCAN_RUN_TYPE', '').lower() == 'intraday'


def write_strategy_outputs(results, web_subdir, today, min_score,
                           exchanges, total_scanned, strategy_label,
                           market_context=None):
    """Write latest.json + archive/<date>.json + archive/index.json for one strategy."""
    web_subdir.mkdir(parents=True, exist_ok=True)
    archive_dir = web_subdir / 'archive'
    archive_dir.mkdir(exist_ok=True)

    signals = []
    for r in results:
        if r is None: continue
        if r.total_score >= min_score:
            signals.append(r.to_dict())
    signals.sort(key=lambda s: -s['total_score'])

    payload = {
        'generated_at': datetime.now().isoformat(),
        'strategy': strategy_label,
        'total': len(signals),
        'metadata': {
            'min_score': min_score,
            'exchanges': list(exchanges),
            'total_scanned': total_scanned,
            'market_context': market_context or {},
            'intraday': is_intraday_run(),
        },
        'signals': signals,
    }

    latest = web_subdir / 'latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  [{strategy_label}] {len(signals)} signals → {latest}")

    if is_intraday_run():
        log.info(f"  [{strategy_label}] bỏ qua archive (bản quét giữa phiên)")
        return

    # compact=True: archive chỉ máy đọc, giảm ~35% dung lượng repo
    write_json(payload, archive_dir / f'{today}.json', compact=True)

    available_dates = sorted([
        f.stem for f in archive_dir.glob('*.json') if f.stem != 'index'
    ], reverse=True)
    with open(archive_dir / 'index.json', 'w') as f:
        json.dump({'latest': today, 'dates': available_dates[:90],
                   'count': len(available_dates)}, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-score', type=int, default=5,
                        help='Pre-breakout min score (0-10)')
    parser.add_argument('--min-score-goldencross', type=int, default=2,
                        help='Golden Cross min score (0-5)')
    parser.add_argument('--min-score-ichimoku', type=int, default=3,
                        help='Ichimoku min score (3-4, flexible mode)')
    parser.add_argument('--exchanges', type=str, default='HOSE,HNX,UPCOM')
    parser.add_argument('--lookback', type=int, default=400)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--web-data-dir', type=str, default='web/data')
    parser.add_argument('--output-dir', type=str, default='backend/data/results')
    parser.add_argument('--no-corporate-actions', action='store_true',
                        help='Bỏ qua bộ lọc sự kiện quyền (nhanh hơn, dùng khi test)')
    args = parser.parse_args()

    exchanges = tuple(args.exchanges.split(','))
    web_dir = Path(args.web_data_dir)
    web_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime('%Y-%m-%d')
    log.info(f"VN Multi-Strategy Scanner -- Daily Run {today}")
    log.info(f"  Exchanges: {exchanges}, limit={args.limit}")

    universe = get_ticker_universe(exchanges, limit=args.limit)
    log.info(f"  Universe: {len(universe)} tickers")

    df_all_raw = fetch_universe(universe, lookback_days=args.lookback)
    if df_all_raw.empty:
        log.error("No data fetched from vnstock")
        sys.exit(1)

    total_scanned = df_all_raw['Ticker'].nunique()
    log.info(f"  Fetched data for {total_scanned} tickers")

    # -------- Bối cảnh thị trường (regime + breadth + relative strength) -----
    # Trước đây `fetch_vnindex` được import nhưng không dùng ở đâu: hệ thống bắn
    # tín hiệu mua giống hệt nhau trong uptrend lẫn downtrend, và không có
    # relative strength — yếu tố dự báo mạnh nhất trong momentum.
    log.info("Đánh giá bối cảnh thị trường (VN-Index)...")
    index_df = fetch_vnindex(lookback_days=max(args.lookback, 400))
    regime = compute_regime(index_df)
    log.info(f"  Regime: {regime.get('regime')} — {regime.get('label')}")

    # Cắt DataFrame theo mã MỘT LẦN rồi tái sử dụng cho mọi strategy.
    # Trước đây mỗi strategy tự lọc `df_all_raw[df_all_raw['Ticker'] == t]` trong
    # vòng lặp → quét lại toàn bộ frame 3 × N lần.
    by_ticker = {tk: g.sort_values('Date').reset_index(drop=True)
                 for tk, g in df_all_raw.groupby('Ticker', sort=False)}

    breadth = compute_breadth(by_ticker)
    rs_map = compute_relative_strength(by_ticker, index_df)
    log.info(f"  Breadth: {breadth.get('pct_above_ma50')}% số mã trên MA50 "
             f"(n={breadth.get('sample_size')}) | RS tính cho {len(rs_map)} mã")

    market_context = {**regime, 'breadth': breadth}

    # -------- Pre-Breakout --------
    log.info("Running Pre-Breakout strategy...")
    scanner = BreakoutScanner(exchanges=exchanges,
                              fetch_corporate_actions=not args.no_corporate_actions)
    df_pb = scanner.scan_from_dataframe(df_all_raw)
    if not df_pb.empty:
        # Gắn RS vào bảng kết quả Pre-Breakout (scanner trả về DataFrame)
        if rs_map:
            df_pb['m_rs_score'] = df_pb['ticker'].map(
                lambda t: (rs_map.get(t) or {}).get('rs_score'))
            df_pb['m_rs_rank'] = df_pb['ticker'].map(
                lambda t: (rs_map.get(t) or {}).get('rs_rank'))

        pb_signals = df_pb[df_pb['total_score'] >= args.min_score].copy()
        log.info(f"  Pre-Breakout: {len(pb_signals)} signals")

        pb_meta = {
            'min_score': args.min_score,
            'exchanges': list(exchanges),
            'total_scanned': total_scanned,
            'market_context': market_context,
            'intraday': is_intraday_run(),
        }
        to_json(pb_signals, web_dir / 'latest.json', metadata=pb_meta)

        # Bản quét giữa phiên KHÔNG ghi archive — xem is_intraday_run()
        if not is_intraday_run():
            archive = web_dir / 'archive'
            archive.mkdir(exist_ok=True)
            to_json(pb_signals, archive / f'{today}.json', metadata=pb_meta,
                    compact=True)
            available = sorted([f.stem for f in archive.glob('*.json') if f.stem != 'index'],
                               reverse=True)
            with open(archive / 'index.json', 'w') as f:
                json.dump({'latest': today, 'dates': available[:90],
                           'count': len(available)}, f, indent=2)
        else:
            log.info("  [pre_breakout] bỏ qua archive (bản quét giữa phiên)")

        if not pb_signals.empty:
            try:
                to_excel(pb_signals, out_dir / f'signals_{today}.xlsx')
            except Exception as e:
                log.warning(f"  Excel export failed: {e}")

    def run_strategy(label, fn):
        """Chấm điểm toàn bộ mã → gắn RS → áp bộ lọc sự kiện quyền."""
        results = []
        for ticker, df_t in by_ticker.items():
            try:
                res = fn(df_t, ticker)
                if res:
                    results.append(res)
            except Exception as e:
                log.debug(f"  {label} {ticker}: {e}")
        log.info(f"  {label}: {len(results)} candidates")
        annotate_results(results, rs_map)
        if not args.no_corporate_actions:
            results = apply_event_filter(results)
        return results

    # -------- Golden Cross — LONG preset (MA50 × MA200) --------
    log.info("Running Golden Cross strategy (LONG: MA50×MA200)...")
    gc_long_results = run_strategy(
        'GC-long', lambda df_t, tk: golden_cross.evaluate(df_t, tk, preset='long'))
    write_strategy_outputs(gc_long_results, web_dir / 'golden_cross_long', today,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_long', market_context)

    # -------- Golden Cross — SHORT preset (MA10 × MA20) --------
    log.info("Running Golden Cross strategy (SHORT: MA10×MA20)...")
    gc_short_results = run_strategy(
        'GC-short', lambda df_t, tk: golden_cross.evaluate(df_t, tk, preset='short'))
    write_strategy_outputs(gc_short_results, web_dir / 'golden_cross_short', today,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_short', market_context)

    # -------- Ichimoku --------
    log.info("Running Ichimoku strategy...")
    ich_results = run_strategy('Ichimoku', lambda df_t, tk: ichimoku.evaluate(df_t, tk))
    write_strategy_outputs(ich_results, web_dir / 'ichimoku', today,
                           args.min_score_ichimoku, exchanges, total_scanned,
                           'ichimoku', market_context)

    log.info(f"All strategies complete for {today}")


if __name__ == '__main__':
    main()
