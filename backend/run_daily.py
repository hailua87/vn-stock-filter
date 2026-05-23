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
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import BreakoutScanner
from scanner.exporter import to_excel, to_json, to_html
from scanner.data_fetcher import get_ticker_universe, fetch_universe
from scanner.strategies import golden_cross, ichimoku

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('daily')


def write_strategy_outputs(results, web_subdir, today, min_score,
                           exchanges, total_scanned, strategy_label):
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
        },
        'signals': signals,
    }

    latest = web_subdir / 'latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  [{strategy_label}] {len(signals)} signals → {latest}")

    archive_file = archive_dir / f'{today}.json'
    with open(archive_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

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

    # -------- Pre-Breakout --------
    log.info("Running Pre-Breakout strategy...")
    scanner = BreakoutScanner(exchanges=exchanges)
    df_pb = scanner.scan_from_dataframe(df_all_raw)
    if not df_pb.empty:
        pb_signals = df_pb[df_pb['total_score'] >= args.min_score].copy()
        log.info(f"  Pre-Breakout: {len(pb_signals)} signals")

        to_json(pb_signals, web_dir / 'latest.json', metadata={
            'min_score': args.min_score,
            'exchanges': list(exchanges),
            'total_scanned': total_scanned,
        })
        archive = web_dir / 'archive'
        archive.mkdir(exist_ok=True)
        to_json(pb_signals, archive / f'{today}.json', metadata={
            'min_score': args.min_score,
            'exchanges': list(exchanges),
            'total_scanned': total_scanned,
        })
        available = sorted([f.stem for f in archive.glob('*.json') if f.stem != 'index'],
                           reverse=True)
        with open(archive / 'index.json', 'w') as f:
            json.dump({'latest': today, 'dates': available[:90],
                       'count': len(available)}, f, indent=2)
        if not pb_signals.empty:
            try:
                to_excel(pb_signals, out_dir / f'signals_{today}.xlsx')
            except Exception as e:
                log.warning(f"  Excel export failed: {e}")

    # -------- Golden Cross — LONG preset (MA50 × MA200) --------
    log.info("Running Golden Cross strategy (LONG: MA50×MA200)...")
    gc_long_results = []
    for ticker in df_all_raw['Ticker'].unique():
        df_t = df_all_raw[df_all_raw['Ticker'] == ticker].sort_values('Date').reset_index(drop=True)
        try:
            res = golden_cross.evaluate(df_t, ticker, preset='long')
            if res:
                gc_long_results.append(res)
        except Exception as e:
            log.debug(f"  GC-long {ticker}: {e}")
    log.info(f"  Golden Cross LONG: {len(gc_long_results)} candidates")
    write_strategy_outputs(gc_long_results, web_dir / 'golden_cross_long', today,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_long')

    # -------- Golden Cross — SHORT preset (MA10 × MA20) --------
    log.info("Running Golden Cross strategy (SHORT: MA10×MA20)...")
    gc_short_results = []
    for ticker in df_all_raw['Ticker'].unique():
        df_t = df_all_raw[df_all_raw['Ticker'] == ticker].sort_values('Date').reset_index(drop=True)
        try:
            res = golden_cross.evaluate(df_t, ticker, preset='short')
            if res:
                gc_short_results.append(res)
        except Exception as e:
            log.debug(f"  GC-short {ticker}: {e}")
    log.info(f"  Golden Cross SHORT: {len(gc_short_results)} candidates")
    write_strategy_outputs(gc_short_results, web_dir / 'golden_cross_short', today,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_short')

    # -------- Ichimoku --------
    log.info("Running Ichimoku strategy...")
    ich_results = []
    for ticker in df_all_raw['Ticker'].unique():
        df_t = df_all_raw[df_all_raw['Ticker'] == ticker].sort_values('Date').reset_index(drop=True)
        try:
            res = ichimoku.evaluate(df_t, ticker)
            if res:
                ich_results.append(res)
        except Exception as e:
            log.debug(f"  Ichimoku {ticker}: {e}")
    log.info(f"  Ichimoku: {len(ich_results)} candidates")
    write_strategy_outputs(ich_results, web_dir / 'ichimoku', today,
                           args.min_score_ichimoku, exchanges, total_scanned,
                           'ichimoku')

    log.info(f"All strategies complete for {today}")


if __name__ == '__main__':
    main()
