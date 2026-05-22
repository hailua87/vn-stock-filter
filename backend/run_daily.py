#!/usr/bin/env python3
"""
Daily scan runner. Designed to be invoked by cron or GitHub Actions
at ~16:00 ICT every trading day (after market close at 15:00).

Usage:
    python backend/run_daily.py [--min-score 6] [--exchanges HOSE,HNX,UPCOM]
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure backend/ is on path so `scanner` can be imported when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import BreakoutScanner
from scanner.exporter import to_excel, to_json, to_html

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('daily')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-score', type=int, default=6,
                        help='Minimum composite score to include (0-10)')
    parser.add_argument('--exchanges', type=str, default='HOSE,HNX,UPCOM',
                        help='Comma-separated exchanges')
    parser.add_argument('--lookback', type=int, default=180,
                        help='Days of history to fetch')
    parser.add_argument('--output-dir', type=str, default='backend/data/results',
                        help='Where to write output files')
    parser.add_argument('--web-data-dir', type=str, default='web/data',
                        help='Directory to publish JSON for the web app')
    args = parser.parse_args()

    exchanges = tuple(args.exchanges.split(','))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    web_dir = Path(args.web_data_dir)
    web_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime('%Y-%m-%d')

    log.info(f"🇻🇳 VN Breakout Scanner — Daily Run {today}")
    log.info(f"Exchanges: {exchanges}, min_score={args.min_score}")

    scanner = BreakoutScanner(exchanges=exchanges)
    df_all = scanner.scan_live(lookback_days=args.lookback)

    if df_all.empty:
        log.error("No signals detected (or fetch failed)")
        sys.exit(1)

    df = df_all[df_all['total_score'] >= args.min_score].copy()
    log.info(f"✅ Found {len(df)} signals with score >= {args.min_score}")

    # 1) Excel for analysts
    excel_path = out_dir / f'signals_{today}.xlsx'
    to_excel(df, excel_path)
    log.info(f"  Wrote {excel_path}")

    # 2) JSON for web (latest = always-up-to-date pointer)
    json_path = out_dir / f'signals_{today}.json'
    to_json(df, json_path, metadata={
        'min_score': args.min_score,
        'exchanges': list(exchanges),
        'total_scanned': len(df_all),
    })
    log.info(f"  Wrote {json_path}")

    # Copy to web data directory — latest pointer
    latest_json = web_dir / 'latest.json'
    to_json(df, latest_json, metadata={
        'min_score': args.min_score,
        'exchanges': list(exchanges),
        'total_scanned': len(df_all),
    })
    log.info(f"  Wrote {latest_json} (for web app)")

    # Archive by date — for the date picker in the web UI
    web_archive = web_dir / 'archive'
    web_archive.mkdir(exist_ok=True)
    archive_json = web_archive / f'{today}.json'
    to_json(df, archive_json, metadata={
        'min_score': args.min_score,
        'exchanges': list(exchanges),
        'total_scanned': len(df_all),
    })
    log.info(f"  Wrote {archive_json} (archive)")

    # Rebuild index.json listing all available dates
    available_dates = sorted([
        f.stem for f in web_archive.glob('*.json')
        if f.stem != 'index'
    ], reverse=True)
    index_data = {
        'latest': today,
        'dates': available_dates[:90],  # keep last 90 trading days available
        'count': len(available_dates),
    }
    import json as _json
    with open(web_archive / 'index.json', 'w') as f:
        _json.dump(index_data, f, indent=2)
    log.info(f"  Updated archive index ({len(available_dates)} dates available)")

    # 3) HTML report
    html_path = out_dir / f'signals_{today}.html'
    to_html(df, html_path, title=f'VN Pre-Breakout Signals — {today}')
    log.info(f"  Wrote {html_path}")

    # Print top 10 to stdout
    log.info("\nTOP 10 SIGNALS:")
    cols = ['ticker', 'exchange', 'close', 'rating', 'total_score',
            'm_vol_ratio', 'm_dist_to_high20_pct']
    available = [c for c in cols if c in df.columns]
    print(df[available].head(10).to_string(index=False))


if __name__ == '__main__':
    main()
