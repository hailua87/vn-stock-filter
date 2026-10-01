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
import os
import sys
from datetime import datetime
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.data_fetcher import get_ticker_universe, setup_api_key
from scanner.financial_fetcher import fetch_bank_asset_quality, fetch_fundamentals
from scanner.strategies.valuation import value_ticker
from scanner.snapshots import record_snapshot
from scanner.publish_gate import may_publish
from scanner.sources import http as SOURCE
from scanner.quality.status import valuation_band

# Trần thời gian cho PASS 1 (vòng gọi mạng), giây. 120 phút — cố ý thấp hơn
# `timeout-minutes: 150` của workflow 30 phút.
#
# Vì sao cần (thêm 27/09/2026): trước đây script này KHÔNG có ngân sách nội bộ.
# Chạm trần nghĩa là runner giết tiến trình giữa lúc đang fetch — tức chết
# TRƯỚC mọi bước ghi file, nên toàn bộ BCTC đã tải về và mọi thứ đã tính không
# thành cái gì cả. Đúng kiểu hỏng của 17-20/08/2026 mà `run_daily` đã có
# FETCH_BUDGET_S để chặn; hai script hằng tuần thì chưa.
#
# Tự dừng sớm thì PASS 2 (thuần tính toán trên dữ liệu đã có), peer DB và ghi
# JSON vẫn còn thời gian — hỏng có kiểm soát thay vì bị chặt ngang.
#
# Con số: nguồn Vietcap/KBS ~6,2s mỗi lượt gọi, BCTC cần ~3 lượt mỗi mã, nên
# 200 mã với cache lạnh vào khoảng 62 phút. 120 phút cho gần gấp đôi mức đó.
FETCH_BUDGET_S = int(os.environ.get('VALUATION_FETCH_BUDGET_S', 120 * 60))

# Dưới độ phủ này thì KHÔNG ghi đè `latest.json` đang có.
#
# Universe xếp theo thanh khoản giảm dần, nên dừng sớm cắt mất đuôi — phần còn
# lại thiên về mã lớn, và peer median của mỗi ngành tính trên nhóm lệch đó.
# Một tệp mỏng còn tệ hơn tệp tuần trước: định giá dựa trên BCTC (ra theo quý),
# một tuần cũ gần như không mất gì, còn mã biến mất khỏi web thì người đọc thấy
# ngay. Đây đúng là điều chú thích trong weekly-valuation.yml đã hứa: "hỏng
# theo hướng an toàn — dữ liệu tuần trước còn nguyên".
MIN_COVERAGE_TO_PUBLISH = float(os.environ.get('VALUATION_MIN_COVERAGE', 0.8))

# Fair value lệch khỏi giá quá mức này gần như luôn do phương pháp không hợp
# với doanh nghiệp (vd. EV/EBITDA khi EBITDA năm đáy < nợ ròng → BAF −97%),
# không phải cơ hội thật. Không công bố làm tín hiệu; ghi vào metadata.
MIN_PUBLISHED_UPSIDE = -0.80
MAX_PUBLISHED_UPSIDE = 2.00


def signals_with_bands(reports) -> tuple[list, dict]:
    """
    to_dict() của từng report + `valuation_band` (blueprint §9: Hấp dẫn / Hợp lý
    / Đắt / Chưa có) và số mã theo mức. Web chỉ hiển thị mức này, KHÔNG hiển
    thị verdict mua/bán của engine (§9, §16); `verdict` vẫn giữ cho backtest.py.
    """
    signals, counts = [], {}
    for r in reports:
        sig = r.to_dict()
        sig['valuation_band'] = valuation_band(sig)
        band = sig['valuation_band']['band']
        counts[band] = counts.get(band, 0) + 1
        signals.append(sig)
    return signals, counts


def outlier_reason(upside: float) -> str | None:
    """Lý do loại khỏi latest.json, hoặc None nếu được công bố."""
    if upside < MIN_PUBLISHED_UPSIDE:
        return f"upside {upside:+.0%} < {MIN_PUBLISHED_UPSIDE:+.0%}"
    if upside > MAX_PUBLISHED_UPSIDE:
        return f"upside {upside:+.0%} > {MAX_PUBLISHED_UPSIDE:+.0%}"
    return None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('valuation')


def main(argv=None, clock=monotonic):
    """`clock` chỉ để test bơm đồng hồ giả — chạy thật luôn dùng `monotonic`."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', type=str, default=None,
                        help='Comma-separated tickers (e.g., VIB,PAN,DBC). Nếu set thì bỏ qua --limit/--exchanges')
    parser.add_argument('--exchanges', type=str, default='HOSE,HNX',
                        help='Sàn cần định giá (UPCOM thường thanh khoản thấp)')
    parser.add_argument('--limit', type=int, default=100,
                        help='Số mã tối đa (sort by liquidity)')
    parser.add_argument('--min-upside', type=float, default=-100,
                        # `%%` chứ không phải `%`: argparse chạy chuỗi help qua phép định dạng `%`,
                        # nên một dấu % trần làm `--help` NỔ. Vẫn nổ từ trước 27/09/2026;
                        # thấy khi thêm --fetch-budget. backend/tests/test_weekly_budget.py chốt lại.
                        help='Lọc theo upside %% tối thiểu (default: hiển thị tất cả)')
    parser.add_argument('--min-confidence', type=float, default=0.30,
                        help='Lọc theo confidence tối thiểu (0-1)')
    parser.add_argument('--web-data-dir', type=str, default='web/data')
    parser.add_argument('--period', type=str, default='year', choices=['year', 'quarter'])
    parser.add_argument('--no-cache', action='store_true', help='Bỏ qua cache, fetch lại tất cả')
    parser.add_argument('--snapshot-registry', type=str,
                        default=str(Path(__file__).resolve().parent / 'data' / 'snapshots'
                                    / 'fundamentals_registry.json'),
                        help='Sổ point-in-time của BCTC (audit F3); "" để tắt')
    parser.add_argument('--fetch-budget', type=int, default=FETCH_BUDGET_S,
                        help='Trần thời gian cho PASS 1, giây (0 = bỏ trần). Mặc '
                             'định %(default)s, cố ý thấp hơn timeout-minutes của '
                             'workflow để PASS 2 và bước ghi file còn kịp chạy.')
    parser.add_argument('--min-coverage', type=float, default=MIN_COVERAGE_TO_PUBLISH,
                        help='Độ phủ PASS 1 tối thiểu để ghi đè latest.json đang có '
                             '(0 = luôn ghi). Mặc định %(default)s.')
    args = parser.parse_args(argv)
    started = clock()
    SOURCE.reset_stats()

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
    snapshot_stats = {'new': 0, 'revised': 0}
    stop_reason = None
    attempted = 0

    for i, ticker in enumerate(tickers, 1):
        # Kiểm TRƯỚC khi gọi mạng, không phải sau: một lượt fetch có thể mất tới
        # ~20s khi nguồn timeout và retry, nên kiểm sau nghĩa là vẫn vượt trần.
        if args.fetch_budget and clock() - started > args.fetch_budget:
            stop_reason = (f'hết ngân sách PASS 1 ({args.fetch_budget}s) '
                           f'sau {attempted}/{len(tickers)} mã')
            log.warning(f"  DỪNG SỚM: {stop_reason}")
            break
        attempted = i

        if i % 20 == 0:
            log.info(f"  Pass 1 progress: {i}/{len(tickers)}")

        try:
            raw = fetch_fundamentals(ticker, period=args.period,
                                     use_cache=not args.no_cache)
            if raw is None:
                failures.append({'ticker': ticker, 'reason': 'no_fundamentals'})
                continue

            if args.snapshot_registry:
                # Ngày = ngày lấy dữ liệu thật (fetched_at), kể cả khi đọc từ cache
                snap = record_snapshot(raw, Path(args.snapshot_registry),
                                       today=str(raw.get('fetched_at', ''))[:10] or None)
                snapshot_stats['new'] += snap['new']
                snapshot_stats['revised'] += snap['revised']

            # Ngân hàng: lấy nợ xấu + CAR từ thuyết minh BCTC TRƯỚC khi
            # normalize, vì normalizer đọc chúng để điều chỉnh P/B mục tiêu.
            # Phân ngành suy từ `overview` nên không cần normalize trước.
            #
            # Một lượt gọi thêm cho ~17 ngân hàng, không phải cả rổ 200.
            if classifier.classify(ticker, raw.get('overview') or {})                     .valuation_industry.value == 'Banking':
                raw['bank_asset_quality'] = fetch_bank_asset_quality(ticker)

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

    coverage = round(attempted / len(tickers), 3) if tickers else 0.0
    log.info(f"  Pass 1 complete: {len(cached_raw)} fetched, {len(peer_inputs)} contributed to peer DB")
    log.info(f"  Độ phủ PASS 1: {attempted}/{len(tickers)} = {coverage:.0%}")
    log.info(f"  Snapshot registry: {snapshot_stats['new']} kỳ mới, "
             f"{snapshot_stats['revised']} kỳ bị sửa số liệu")

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
    outliers = []
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
            reason = outlier_reason(report.upside_pct)
            if reason:
                outliers.append({'ticker': ticker, 'fair_value': round(report.fair_value),
                                 'current_price': report.current_price, 'reason': reason})
                continue

            reports.append(report)
        except Exception as e:
            log.warning(f"  {ticker} pass-2 failed: {type(e).__name__}: {str(e)[:100]}")

    log.info(f"  Pass 2 complete: {len(reports)} valid signals after filters")
    if outliers:
        log.warning(f"  Excluded {len(outliers)} outliers: " + ", ".join(o['ticker'] for o in outliers))

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

    signals_out, band_counts = signals_with_bands(reports)

    payload = {
        'generated_at': datetime.now().isoformat(),
        'strategy': 'multi_method_valuation',
        'total': len(reports),
        'metadata': {
            'period': args.period,
            'min_upside': args.min_upside,
            'min_confidence': args.min_confidence,
            'total_attempted': attempted,
            'universe_size': len(tickers),
            'fetch_coverage': coverage,
            # None khi PASS 1 chạy trọn. Khác None nghĩa là peer median của mỗi
            # ngành tính trên nhóm đã bị cắt đuôi, không phải cả rổ.
            'fetch_stop_reason': stop_reason,
            # Nguồn tử tế hay dở chứng trong CHÍNH lượt này. Xem chú thích
            # trong scanner/sources/http.py về việc vì sao đếm tỷ lệ treo chứ
            # không đo thời gian chạy.
            'source_stats': SOURCE.stats(),
            'failures': len(failures),
            'verdict_counts': verdict_counts,
            'band_counts': band_counts,
            'excluded_outliers': outliers,
        },
        'signals': signals_out,
    }

    # Trả mã lỗi khi không công bố, để job đỏ và ci-alert mở issue: một lượt
    # phải bỏ công bố là chuyện cần người biết, không phải chuyện im cho qua.
    latest = web_dir / 'latest.json'
    ok, why = may_publish(coverage, args.min_coverage, latest)
    if not ok:
        log.error(f"KHÔNG công bố: {why} ({stop_reason or 'nhiều mã hỏng'})")
        return 1
    if why:
        log.warning(why)

    # Write latest.json
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
