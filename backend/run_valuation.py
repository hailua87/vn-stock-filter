#!/usr/bin/env python3
"""
Daily valuation runner.

Chạy định giá đa phương pháp cho universe cổ phiếu VN, output JSON cho web.
Khác với run_daily.py (chuyên technical signals), file này dùng financial data
(BCTC, ratios) thay vì OHLCV.

Lịch khuyến nghị: chạy 1 lần/tuần (BCTC ra hàng quý, không cần daily).

Usage:
    # Chạy với 100 mã liquid nhất
    python run_valuation.py --limit 100

    # Chỉ định nghĩa danh sách cụ thể
    python run_valuation.py --tickers VIB,PAN,DBC,FPT,HPG

    # Lọc theo verdict
    python run_valuation.py --min-upside 15  # chỉ giữ upside >= 15%
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.data_fetcher import get_ticker_universe, setup_api_key
from scanner.financial_fetcher import fetch_fundamentals
from scanner.strategies.valuation import value_ticker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('valuation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', type=str, default=None,
                        help='Comma-separated tickers (e.g., VIB,PAN,DBC). Nếu set thì bỏ qua --limit/--exchanges')
    parser.add_argument('--exchanges', type=str, default='HOSE,HNX',
                        help='Sàn cần định giá (UPCOM thường thanh khoản thấp)')
    parser.add_argument('--limit', type=int, default=100,
                        help='Số mã tối đa (sort by liquidity)')
    parser.add_argument('--min-upside', type=float, default=-100,
                        help='Lọc theo upside % tối thiểu (default: hiển thị tất cả)')
    parser.add_argument('--min-confidence', type=float, default=0.30,
                        help='Lọc theo confidence tối thiểu (0-1)')
    parser.add_argument('--web-data-dir', type=str, default='web/data')
    parser.add_argument('--period', type=str, default='year', choices=['year', 'quarter'])
    parser.add_argument('--no-cache', action='store_true', help='Bỏ qua cache, fetch lại tất cả')
    args = parser.parse_args()

    setup_api_key()
    today = datetime.now().strftime('%Y-%m-%d')
    log.info(f"VN Valuation Runner -- {today}")

    # === Build ticker list ===
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
        log.info(f"  Custom list: {len(tickers)} tickers")
    else:
        exchanges = tuple(args.exchanges.split(','))
        universe = get_ticker_universe(exchanges, limit=args.limit)
        tickers = universe['ticker'].tolist()
        log.info(f"  Universe ({exchanges}): {len(tickers)} tickers")

    # === Run valuation ===
    from scanner.strategies.valuation.normalizer import normalize_fundamentals
    from scanner.strategies.valuation.industry_classifier import IndustryClassifier
    from scanner.peer_database import (
        build_peer_database, save_peer_database, extract_peer_input,
    )
    from scanner.market_metrics import enrich_with_market_metrics

    # ────────────────────────────────────────────────────────────────────
    # PASS 1: Fetch fundamentals + enrich + extract metrics cho peer DB
    # ────────────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("PASS 1/2: Fetch + Enrich + Build Peer Database")
    log.info("=" * 60)

    cached_raw = {}        # ticker → raw_fundamentals (đã enrich)
    cached_normalized = {} # ticker → normalized data với _industry
    peer_inputs = []
    classifier = IndustryClassifier()
    failures = []

    for i, ticker in enumerate(tickers, 1):
        if i % 20 == 0:
            log.info(f"  Pass 1 progress: {i}/{len(tickers)}")

        try:
            raw = fetch_fundamentals(ticker, period=args.period,
                                     use_cache=not args.no_cache)
            if raw is None:
                failures.append({'ticker': ticker, 'reason': 'no_fundamentals'})
                continue

            # Enrich với beta + historical multiples thực
            raw = enrich_with_market_metrics(ticker, raw)
            cached_raw[ticker] = raw

            # Normalize + classify để biết industry
            data = normalize_fundamentals(raw)
            if data is None:
                failures.append({'ticker': ticker, 'reason': 'normalize_failed'})
                continue

            classification = classifier.classify(ticker, data.get('overview', {}))
            data['_industry'] = classification.valuation_industry.value
            cached_normalized[ticker] = data

            # Contribute vào peer DB
            peer_input = extract_peer_input(data)
            if peer_input:
                peer_inputs.append(peer_input)

        except Exception as e:
            log.warning(f"  {ticker} pass-1 failed: {type(e).__name__}: {str(e)[:100]}")
            failures.append({'ticker': ticker, 'reason': str(e)[:100]})

    log.info(f"  Pass 1 complete: {len(cached_raw)} fetched, {len(peer_inputs)} contributed to peer DB")

    # Build & save peer database
    peer_db = build_peer_database(peer_inputs)
    save_peer_database(peer_db)
    log.info(f"  Peer DB: {len(peer_db['industries'])} industries")
    for ind, stats in peer_db['industries'].items():
        pe_med = (stats.get('pe') or {}).get('median', '—')
        pb_med = (stats.get('pb') or {}).get('median', '—')
        log.info(f"    {ind:<28} n={stats['ticker_count']:>3}  P/E={pe_med}  P/B={pb_med}")

    # ────────────────────────────────────────────────────────────────────
    # PASS 2: Run valuation engine (giờ có peer DB)
    # ────────────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("PASS 2/2: Run Valuation Engine")
    log.info("=" * 60)

    reports = []
    for i, ticker in enumerate(cached_raw.keys(), 1):
        if i % 20 == 0:
            log.info(f"  Pass 2 progress: {i}/{len(cached_raw)} (valid={len(reports)})")

        try:
            report = value_ticker(ticker, raw_fundamentals=cached_raw[ticker])
            if report is None:
                continue

            # Apply filters
            if report.upside_pct * 100 < args.min_upside:
                continue
            if report.confidence < args.min_confidence:
                continue

            reports.append(report)
        except Exception as e:
            log.warning(f"  {ticker} pass-2 failed: {type(e).__name__}: {str(e)[:100]}")

    log.info(f"  Pass 2 complete: {len(reports)} valid signals after filters")

    # === Write outputs ===
    web_dir = Path(args.web_data_dir) / 'valuation'
    web_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = web_dir / 'archive'
    archive_dir.mkdir(exist_ok=True)

    # Sort: STRONG BUY first, then by upside
    verdict_order = {'STRONG BUY': 0, 'BUY': 1, 'HOLD': 2, 'SELL': 3, 'STRONG SELL': 4}
    reports.sort(key=lambda r: (verdict_order.get(r.verdict, 99), -r.upside_pct))

    # Group by verdict for summary
    verdict_counts = {}
    for r in reports:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

    payload = {
        'generated_at': datetime.now().isoformat(),
        'strategy': 'multi_method_valuation',
        'total': len(reports),
        'metadata': {
            'period': args.period,
            'min_upside': args.min_upside,
            'min_confidence': args.min_confidence,
            'total_attempted': len(tickers),
            'failures': len(failures),
            'verdict_counts': verdict_counts,
        },
        'signals': [r.to_dict() for r in reports],
    }

    # Write latest.json
    latest = web_dir / 'latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  Latest: {latest}")

    # Write archive
    archive_file = archive_dir / f'{today}.json'
    with open(archive_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    # Update archive index
    available_dates = sorted([
        f.stem for f in archive_dir.glob('*.json') if f.stem != 'index'
    ], reverse=True)
    with open(archive_dir / 'index.json', 'w') as f:
        json.dump({'latest': today, 'dates': available_dates[:90],
                   'count': len(available_dates)}, f, indent=2)

    log.info(f"Valuation run complete: {len(reports)} signals saved")
    log.info(f"  Verdict breakdown: {verdict_counts}")


if __name__ == '__main__':
    main()
