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
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

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


# Việt Nam ở UTC+7 và không có DST từ 1975, nên offset cố định là chính xác và
# không phụ thuộc gói tzdata của máy chạy. `datetime.now()` trần KHÔNG dùng được:
# runner của GitHub Actions chạy giờ UTC, nên nó vừa lệch 7 tiếng vừa đặt sai tên
# file archive mỗi khi bản EOD chạy qua nửa đêm ICT.
ICT = timezone(timedelta(hours=7), name='ICT')

# Vì sao 15:15 ICT: HOSE khớp ATC lúc 14:45, nhưng khối lượng chỉ chốt hẳn sau đó
# ~20-25 phút (thoả thuận + báo cáo muộn). Đo trên 223 quan sát tháng 7-8/2026,
# so khối lượng trong archive với khối lượng lấy về sau cùng phiên:
#     ghi lúc 14:45 → 72% số mã còn thiếu, trung vị 0,905
#     ghi lúc 14:59 → 44% còn thiếu
#     ghi lúc 15:08 trở đi → 0% thiếu, khớp 100%
# 15:15 là mốc chốt đó cộng biên an toàn.
ARCHIVE_CUTOFF_ICT = dtime(15, 15)


def now_ict() -> datetime:
    """Giờ ICT tại THỜI ĐIỂM GỌI — không phải nhãn dán lúc job khởi động."""
    return datetime.now(timezone.utc).astimezone(ICT)


def get_run_type() -> str:
    """
    Nhãn ca chạy do workflow dán (`SCAN_RUN_TYPE`), chỉ để GHI LẠI.

    Nhãn này được tính bằng giờ UTC lúc job KHỞI ĐỘNG rồi đóng băng, trong khi
    bước ghi file diễn ra sau đó 30-60 phút. Dùng nó làm cổng chặn thì sai cả hai
    chiều: bản khởi động 12:00 ICT mà ghi lúc 15:40 vẫn mang nhãn 'intraday' dù
    khối lượng đã chốt (vứt oan dữ liệu tốt), còn `workflow_dispatch` chọn tay
    'eod' lúc 12:00 thì mở toang cổng cho dữ liệu nửa phiên. Cổng thật đo đồng hồ
    tại lúc ghi — xem archive_decision().
    """
    return os.environ.get('SCAN_RUN_TYPE', '').strip().lower() or 'unknown'


def session_date_from_data(df_all: pd.DataFrame) -> Optional[str]:
    """
    Ngày phiên lấy từ CHÍNH dữ liệu, không lấy từ đồng hồ của máy chạy.

    Trước đây tên file archive là `datetime.now()` của runner (giờ UTC): bản EOD
    chạy 23:00 ICT tức 16:00 UTC, chỉ cần quét quá 60 phút là qua 17:00 UTC và
    ngày UTC lệch một ngày so với ngày phiên. `df['Date'].max()` không có vấn đề
    đó vì nó là ngày của chính cây nến cuối cùng.
    """
    if df_all is None or len(df_all) == 0 or 'Date' not in df_all.columns:
        return None
    last = pd.to_datetime(df_all['Date']).max()
    return None if pd.isna(last) else pd.Timestamp(last).strftime('%Y-%m-%d')


def session_completeness(by_ticker: dict) -> Optional[float]:
    """
    Trung vị chéo của (KL phiên cuối / trung vị KL 20 phiên trước đó).

    Phiên trọn vẹn cho ~1,0; ảnh chụp giữa phiên chiều cho ~0,64 (đo tháng 8/2026
    trên 63 quan sát). Đây là CỜ THÔNG TIN, cố ý KHÔNG dùng để chặn: chỉ số này
    cũng tụt trong phiên thật sự trầm lắng, nên tự nó không phân biệt được "chưa
    đóng cửa" với "thanh khoản thấp". Cổng chặn là đồng hồ; số này để hậu kiểm.
    """
    ratios = []
    for d in (by_ticker or {}).values():
        if d is None or len(d) < 21 or 'Volume' not in d.columns:
            continue
        base = float(d['Volume'].iloc[-21:-1].median())
        if base > 0:
            ratios.append(float(d['Volume'].iloc[-1]) / base)
    if not ratios:
        return None
    return round(float(pd.Series(ratios).median()), 3)


def archive_decision(force: bool = False, now: Optional[datetime] = None) -> dict:
    """
    Có được ghi archive không — quyết định bằng ĐỒNG HỒ TẠI LÚC GHI.

    Ba đường vào đều đi qua đúng cổng này:
      - chạy theo lịch  → chỉ giờ ICT mới mở được cổng
      - `workflow_dispatch` chọn tay 'eod' → KHÔNG mở được cổng, phải thêm cờ
      - thiếu `SCAN_RUN_TYPE` (chạy tay, script khác) → cũng KHÔNG mở được cổng

    Điểm cuối cùng là thay đổi quan trọng nhất về mặt an toàn: bản cũ hỏi
    `env == 'intraday'`, nên thiếu biến sẽ trả False và archive được ghi vô điều
    kiện — hỏng theo hướng MỞ. Nay thiếu thông tin thì đóng.
    """
    now = now or now_ict()
    run_type = get_run_type()
    after_cutoff = now.time() >= ARCHIVE_CUTOFF_ICT
    cutoff_str = ARCHIVE_CUTOFF_ICT.strftime('%H:%M')

    if after_cutoff:
        return {'write': True, 'forced': False, 'run_type': run_type,
                'written_at_ict': now.strftime('%Y-%m-%d %H:%M:%S%z'),
                'reason': f'{now:%H:%M} ICT >= {cutoff_str} — khối lượng đã chốt'}
    if force:
        return {'write': True, 'forced': True, 'run_type': run_type,
                'written_at_ict': now.strftime('%Y-%m-%d %H:%M:%S%z'),
                'reason': f'{now:%H:%M} ICT < {cutoff_str} nhưng có --force-archive'}
    return {'write': False, 'forced': False, 'run_type': run_type,
            'written_at_ict': now.strftime('%Y-%m-%d %H:%M:%S%z'),
            'reason': f'{now:%H:%M} ICT < {cutoff_str} — khối lượng chưa chốt'}


def build_metadata(min_score, exchanges, total_scanned, market_context,
                   session_date, decision, completeness) -> dict:
    """
    Metadata dùng chung cho latest.json VÀ file archive.

    Trước đây `run_type` chỉ được bước jq của workflow vá vào 4 file latest.json,
    không vá bản archive — nên nhìn một file archive không cách nào biết nó là
    bản giữa phiên hay bản chính thức, phải suy ngược từ `generated_at`. Nay ba
    trường bằng chứng đi kèm mọi file.
    """
    return {
        'min_score': min_score,
        'exchanges': list(exchanges),
        'total_scanned': total_scanned,
        'market_context': market_context or {},
        'session_date': session_date,
        'written_at_ict': decision['written_at_ict'],
        'run_type': decision['run_type'],
        'session_complete': completeness,
        'archive_written': decision['write'],
        'archive_forced': decision['forced'],
        'archive_gate': decision['reason'],
        # Giữ khoá cũ: web/app.js:373 đọc `metadata.intraday` làm nguồn dự phòng
        # khi thiếu `run_type`.
        'intraday': decision['run_type'] == 'intraday',
    }


def write_strategy_outputs(results, web_subdir, session_date, min_score,
                           exchanges, total_scanned, strategy_label,
                           market_context=None, decision=None, completeness=None):
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
        'metadata': build_metadata(min_score, exchanges, total_scanned,
                                   market_context, session_date, decision,
                                   completeness),
        'signals': signals,
    }

    latest = web_subdir / 'latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  [{strategy_label}] {len(signals)} signals → {latest}")

    if not decision['write']:
        log.warning(f"  [{strategy_label}] KHÔNG ghi archive — {decision['reason']}")
        return
    if session_date is None:
        log.warning(f"  [{strategy_label}] KHÔNG ghi archive — không xác định được "
                    f"ngày phiên từ dữ liệu")
        return

    # compact=True: archive chỉ máy đọc, giảm ~35% dung lượng repo
    write_json(payload, archive_dir / f'{session_date}.json', compact=True)

    available_dates = sorted([
        f.stem for f in archive_dir.glob('*.json') if f.stem != 'index'
    ], reverse=True)
    with open(archive_dir / 'index.json', 'w') as f:
        json.dump({'latest': session_date, 'dates': available_dates[:90],
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
    parser.add_argument('--force-archive', action='store_true',
                        help='Ghi archive kể cả khi chưa qua %s ICT. Chỉ dùng khi '
                             'biết rõ dữ liệu đã đủ; lần ghi đè sẽ được đánh dấu '
                             'archive_forced=true trong metadata.'
                             % ARCHIVE_CUTOFF_ICT.strftime('%H:%M'))
    args = parser.parse_args()

    exchanges = tuple(args.exchanges.split(','))
    web_dir = Path(args.web_data_dir)
    web_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"VN Multi-Strategy Scanner -- Daily Run "
             f"{now_ict():%Y-%m-%d %H:%M} ICT")
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

    # -------- Cổng archive: quyết định bằng đồng hồ TẠI LÚC GHI --------
    session_date = session_date_from_data(df_all_raw)
    completeness = session_completeness(by_ticker)
    decision = archive_decision(force=args.force_archive)
    log.info(f"  Ngày phiên (từ dữ liệu): {session_date}")
    log.info(f"  Độ trọn vẹn phiên: {completeness} "
             f"(cờ thông tin, không dùng để chặn)")
    if decision['write']:
        log.info(f"  Archive: GHI — {decision['reason']}")
        if decision['forced']:
            log.warning("  Archive bị ép ghi bằng --force-archive; "
                        "metadata.archive_forced = true")
    else:
        log.warning(f"  Archive: BỎ QUA — {decision['reason']}")

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

        pb_meta = build_metadata(args.min_score, exchanges, total_scanned,
                                 market_context, session_date, decision,
                                 completeness)
        to_json(pb_signals, web_dir / 'latest.json', metadata=pb_meta)

        if decision['write'] and session_date is not None:
            archive = web_dir / 'archive'
            archive.mkdir(exist_ok=True)
            to_json(pb_signals, archive / f'{session_date}.json', metadata=pb_meta,
                    compact=True)
            available = sorted([f.stem for f in archive.glob('*.json') if f.stem != 'index'],
                               reverse=True)
            with open(archive / 'index.json', 'w') as f:
                json.dump({'latest': session_date, 'dates': available[:90],
                           'count': len(available)}, f, indent=2)
        else:
            log.warning(f"  [pre_breakout] KHÔNG ghi archive — "
                        f"{decision['reason'] if session_date else 'thiếu ngày phiên'}")

        if not pb_signals.empty:
            try:
                to_excel(pb_signals, out_dir / f'signals_{session_date}.xlsx')
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
    write_strategy_outputs(gc_long_results, web_dir / 'golden_cross_long', session_date,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_long', market_context, decision, completeness)

    # -------- Golden Cross — SHORT preset (MA10 × MA20) --------
    log.info("Running Golden Cross strategy (SHORT: MA10×MA20)...")
    gc_short_results = run_strategy(
        'GC-short', lambda df_t, tk: golden_cross.evaluate(df_t, tk, preset='short'))
    write_strategy_outputs(gc_short_results, web_dir / 'golden_cross_short', session_date,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_short', market_context, decision, completeness)

    # -------- Ichimoku --------
    log.info("Running Ichimoku strategy...")
    ich_results = run_strategy('Ichimoku', lambda df_t, tk: ichimoku.evaluate(df_t, tk))
    write_strategy_outputs(ich_results, web_dir / 'ichimoku', session_date,
                           args.min_score_ichimoku, exchanges, total_scanned,
                           'ichimoku', market_context, decision, completeness)

    log.info(f"All strategies complete for session {session_date}")


if __name__ == '__main__':
    main()
