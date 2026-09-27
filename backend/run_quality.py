#!/usr/bin/env python3
"""
Module B — chấm chất lượng watchlist dài hạn (blueprint v4 §8–§10).

    python backend/run_quality.py --limit 100

Đầu ra:
    web/data/quality/latest.json            điểm 4 chiều, chỉ tiêu, độ phủ, cờ, veto, trạng thái, lý do
    web/data/quality/archive/<ngày>.json    snapshot đã chuẩn hóa (blueprint §5.2.3, audit F3)
    web/data/quality/archive/index.json

Universe = cùng lời gọi `get_ticker_universe` với weekly valuation (§8.1, D10),
nên chạy NGAY SAU run_valuation.py trong cùng job: BCTC năm lấy từ cache mà
run_valuation vừa ghi, chỉ BCTC quý là gọi mạng.

Percentile là thứ hạng TRONG universe này, không phải toàn thị trường.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from time import monotonic
from typing import Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.publish_gate import may_publish
from scanner.quality import adapter, governance, metrics, scoring
from scanner.quality import config as C
from scanner.quality.status import DIMS, classify, model_for, sharp_drops, valuation_band
from scanner.strategies.valuation.industry_classifier import IndustryClassifier

log = logging.getLogger('run_quality')

QUALITY_SCHEMA = 1

# Trần thời gian cho vòng lấy dữ liệu, giây. 100 phút — cố ý thấp hơn
# `timeout-minutes: 120` của workflow 20 phút, cùng tỷ lệ với `run_daily`.
#
# NÂNG 70 -> 100 ngày 28/09/2026, từ số đo: lượt 27/09 14:59 chạm trần 70 phút
# ở đúng 165/200 mã = 25,45s mỗi mã, nên trọn rổ cần ~85 phút. Trần cũ không đủ,
# và hậu quả không phải job đỏ mà là TUẦN NÀO CŨNG công bố điểm tính trên 82%
# rổ — percentile lệch mà con số trông vẫn bình thường.
#
# Vì sao cần (thêm 27/09/2026): trước đây script này KHÔNG có ngân sách nội bộ,
# nên chạm trần là bị runner giết giữa vòng lấy dữ liệu — tức chết TRƯỚC bước
# ghi file, mất sạch mọi thứ đã chấm. Đúng chuyện đã xảy ra ngày 27/09: bước
# chấm chất lượng chạm trần 45 phút và không để lại gì.
#
# Tự dừng sớm thì phần percentile, quản trị, veto và ghi JSON vẫn còn thời gian.
FETCH_BUDGET_S = int(os.environ.get('QUALITY_FETCH_BUDGET_S', 100 * 60))

# Dưới độ phủ này thì KHÔNG ghi đè `latest.json` đang có. Xem chú thích cùng tên
# trong run_valuation.py; ở đây còn một lý do riêng: điểm là PERCENTILE TRONG
# UNIVERSE. Cắt đuôi rổ (rổ xếp theo thanh khoản giảm dần) nghĩa là mọi mã bị
# xếp hạng so với riêng nhóm vốn hoá lớn — điểm đổi mà không ai đổi gì cả.
MIN_COVERAGE_TO_PUBLISH = float(os.environ.get('QUALITY_MIN_COVERAGE', 0.8))


def _round(v, nd=4):
    return round(v, nd) if isinstance(v, float) else v


def load_delisted(path: Path) -> set:
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return set()
    return {l.split('#')[0].strip().upper() for l in lines if l.split('#')[0].strip()}


def load_valuation_signals(path: Path) -> Dict[str, dict]:
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {s['ticker']: s for s in d.get('signals', [])}


def load_previous_dims(path: Path) -> Dict[str, dict]:
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {it['ticker']: {k: (v or {}).get('score') for k, v in it.get('dims', {}).items()}
            for it in d.get('items', [])}


def build_quality(tickers, fetch_year: Callable[[str], Optional[dict]],
                  fetch_quarter: Callable[[str], Optional[dict]],
                  valuation_signals: Dict[str, dict], as_of: date,
                  delisted: set, previous: Dict[str, dict],
                  on_fetched: Optional[Callable[[dict], None]] = None,
                  fetch_bank_ratio: Optional[Callable] = None,
                  should_stop: Optional[Callable[[], bool]] = None) -> dict:
    """
    Chấm cả universe. Không gọi mạng trực tiếp — mọi dữ liệu qua fetch_year/fetch_quarter.

    `should_stop` được hỏi TRƯỚC mỗi mã: trả True thì bỏ phần rổ còn lại và đi
    thẳng sang chấm điểm. Hàm này không biết gì về đồng hồ — `main` truyền vào
    một closure đọc ngân sách thời gian, còn test truyền một bộ đếm.
    """
    classifier = IndustryClassifier()
    rows: Dict[str, dict] = {}
    failures = []
    stop_reason = None
    attempted = 0

    # ── 1. Dữ liệu + chỉ tiêu từng mã ────────────────────────────────────
    for t in tickers:
        # Hỏi TRƯỚC khi gọi mạng: một lượt fetch có thể mất tới ~20s khi nguồn
        # timeout và retry, nên hỏi sau nghĩa là vẫn vượt trần.
        if should_stop and should_stop():
            stop_reason = f'hết ngân sách lấy dữ liệu sau {attempted}/{len(tickers)} mã'
            break
        attempted += 1
        raw_y = fetch_year(t)
        if not raw_y:
            failures.append({'ticker': t, 'reason': 'Không lấy được BCTC năm'})
            continue
        raw_q = fetch_quarter(t)
        if on_fetched:
            for raw in (raw_y, raw_q):
                if raw:
                    on_fetched(raw)
        industry = classifier.classify(t, raw_y.get('overview') or {}).valuation_industry.value
        model = model_for(industry)
        annual = adapter.annual_schema(raw_y)
        # NIM chỉ có ở nguồn KBS và chỉ dùng cho mô hình BANK — gọi thêm một
        # lượt API cho ~18 mã, không phải cả rổ 200.
        if model == 'BANK' and fetch_bank_ratio:
            adapter.attach_bank_ratios(annual, fetch_bank_ratio(t))
        rows[t] = {
            'industry': industry,
            'model': model,
            'active': model in C.ACTIVE_MODELS,
            'annual': annual,
            'gov_inputs': adapter.governance_inputs(annual, raw_q),
            'metrics': metrics.compute(model, annual) if model in C.ACTIVE_MODELS else {},
            'has_quarter': bool(raw_q),
        }

    # ── 2. Percentile trong từng mô hình ─────────────────────────────────
    scored: Dict[str, dict] = {}
    for model in C.ACTIVE_MODELS:
        group = {t: r['metrics'] for t, r in rows.items() if r['model'] == model}
        if group:
            scored.update(scoring.score_group(model, group))

    # ── 3. Quản trị, veto, định giá, trạng thái ──────────────────────────
    items = []
    for t, r in rows.items():
        s = scored.get(t, {})
        gov = governance.score(r['gov_inputs'], as_of)
        veto = governance.veto(t, r['gov_inputs'], as_of, delisted)
        dims = {
            'quality': s.get('quality'),
            'growth': s.get('growth'),
            'resilience': s.get('resilience'),
            'governance': {'score': gov['score'], 'coverage': gov['coverage'],
                           'missing': gov['missing']},
        }
        dim_scores = {d: (dims[d] or {}).get('score') for d in DIMS}
        band = valuation_band(valuation_signals.get(t))
        if t not in valuation_signals:
            band['reason'] = 'Không có trong đầu ra định giá tuần này'
        status = classify(dim_scores, band, veto_reason=veto, model_active=r['active'],
                          model=r['model'])
        periods = [p for p in r['annual']['period_end'] if p]
        lq = r['gov_inputs']['latest_quarter_end']
        items.append({
            'ticker': t,
            'industry': r['industry'],
            'model': r['model'],
            'status': status['status'],
            'status_label': status['label'],
            'reason': status['reason'],
            'dims': dims,
            'governance_flags': gov['flags'],
            'veto': veto,
            'valuation': {k: band.get(k) for k in ('band', 'label', 'upside_pct', 'confidence',
                                                    'method', 'reason')},
            'metrics': {k: _round(v) for k, v in r['metrics'].items()},
            'percentiles': s.get('percentiles', {}),
            'latest_annual': periods[-1] if periods else None,
            'latest_quarter': lq.isoformat() if lq else None,
            'sharp_drops': sharp_drops(dim_scores, previous.get(t)),
        })

    order = {'QUAL': 0, 'MON': 1, 'REV': 2, 'RES': 3, 'EXC': 4}
    items.sort(key=lambda it: (order.get(it['status'], 9),
                               -((it['dims']['quality'] or {}).get('score') or -1)))

    def _count(key):
        out = {}
        for it in items:
            out[it[key]] = out.get(it[key], 0) + 1
        return out

    return {
        'schema': QUALITY_SCHEMA,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'as_of': as_of.isoformat(),
        'metadata': {
            'universe_size': len(tickers),
            'attempted': attempted,
            'fetch_coverage': round(attempted / len(tickers), 3) if tickers else 0.0,
            # None khi vòng lấy dữ liệu chạy trọn. Khác None nghĩa là percentile
            # được tính trên phần rổ đã bị cắt đuôi, không phải cả universe.
            'fetch_stop_reason': stop_reason,
            'scored': len(items),
            'failures': failures,
            'status_counts': _count('status'),
            'model_counts': _count('model'),
            'active_models': sorted(C.ACTIVE_MODELS),
            'thresholds': {'qualify': C.QUALIFY, 'review_below': C.REVIEW_BELOW,
                           'coverage_min': C.COVERAGE_MIN, 'min_peer_group': C.MIN_PEER_GROUP},
            # Web đọc cấu hình từ đây thay vì chép lại (blueprint v4: không đổi
            # ngưỡng, trọng số chỉ trên giao diện).
            'model_specs': {m: {dim: [{'key': k, 'weight': w, 'higher_better': h}
                                      for k, w, h in specs]
                                for dim, specs in C.MODELS[m].items()}
                            for m in sorted(C.ACTIVE_MODELS)},
            'governance_penalty': C.PENALTY,
            # Yeu to ĐÃ CAN NHAC va KHONG danh gia duoc vi khong co nguon
            # (§14.2). Giao dien phai noi ra, neu khong nguoi doc mac dinh
            # diem Quan tri da xet het moi thu.
            'bank_not_evaluated': C.BANK_NOT_EVALUATED,
            # Mo hinh chua bat va VI SAO. Khong co cho nay thi man hinh chi noi
            # "Mo hinh nganh chua kich hoat" — nghe nhu sap lam den noi, trong
            # khi that ra la khong lam duoc voi ro nay.
            'inactive_model_reason': C.INACTIVE_MODEL_REASON,
            'governance_not_evaluated': C.GOVERNANCE_NOT_EVALUATED,
            'veto_not_evaluated': C.VETO_NOT_EVALUATED,
            'note': ('Percentile là thứ hạng trong universe Module B (top thanh khoản), '
                     'không phải toàn thị trường. Ngưỡng là mặc định cấu hình, chưa backtest. '
                     'Không phải khuyến nghị đầu tư.'),
        },
        'items': items,
    }


def write_outputs(payload: dict, web_dir: Path) -> None:
    qdir = web_dir / 'quality'
    archive = qdir / 'archive'
    archive.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    (qdir / 'latest.json').write_text(text, encoding='utf-8')
    (archive / f"{payload['as_of']}.json").write_text(text, encoding='utf-8')
    dates = sorted((p.stem for p in archive.glob('*.json') if p.stem != 'index'), reverse=True)
    (archive / 'index.json').write_text(
        json.dumps({'latest': payload['as_of'], 'dates': dates[:90], 'count': len(dates)}, indent=2),
        encoding='utf-8')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--exchanges', default='HOSE,HNX')
    ap.add_argument('--limit', type=int, default=100,
                    help='Phải bằng --limit của run_valuation (cùng universe, §8.1)')
    ap.add_argument('--web-data-dir', default='web/data')
    ap.add_argument('--as-of', default=None, help='YYYY-MM-DD, mặc định hôm nay')
    ap.add_argument('--snapshot-registry',
                    default=str(Path(__file__).resolve().parent / 'data' / 'snapshots'
                                / 'fundamentals_registry.json'),
                    help='Sổ point-in-time BCTC; "" để tắt')
    ap.add_argument('--fetch-budget', type=int, default=FETCH_BUDGET_S,
                    help='Trần thời gian cho vòng lấy dữ liệu, giây (0 = bỏ trần). '
                         'Mặc định %(default)s, cố ý thấp hơn timeout-minutes của '
                         'workflow để bước chấm điểm và ghi file còn kịp chạy.')
    ap.add_argument('--min-coverage', type=float, default=MIN_COVERAGE_TO_PUBLISH,
                    help='Độ phủ tối thiểu để ghi đè latest.json đang có (0 = luôn '
                         'ghi). Mặc định %(default)s.')
    args = ap.parse_args(argv)
    # Mốc tính ngân sách là lúc TIẾN TRÌNH bắt đầu, không phải lúc vào vòng lặp:
    # `timeout-minutes` của workflow đếm từ đây, và `get_ticker_universe` phía
    # dưới cũng gọi mạng. Đặt mốc sau nó nghĩa là ngân sách âm thầm dài thêm
    # đúng bằng thời gian xếp hạng thanh khoản.
    started = monotonic()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S')

    from scanner.data_fetcher import get_ticker_universe, setup_api_key
    from scanner.financial_fetcher import fetch_bank_ratios, fetch_fundamentals, fetch_quarterly_statements
    from scanner.snapshots import record_snapshot
    setup_api_key()

    web = Path(args.web_data_dir)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    tickers = get_ticker_universe(tuple(args.exchanges.split(',')), limit=args.limit)['ticker'].tolist()
    log.info(f"Universe: {len(tickers)} mã ({args.exchanges}, limit={args.limit})")

    registry = Path(args.snapshot_registry) if args.snapshot_registry else None

    def on_fetched(raw):
        if registry:
            record_snapshot(raw, registry, today=str(raw.get('fetched_at', ''))[:10] or None)

    payload = build_quality(
        tickers,
        fetch_year=lambda t: fetch_fundamentals(t, period='year'),
        fetch_quarter=fetch_quarterly_statements,
        fetch_bank_ratio=fetch_bank_ratios,
        valuation_signals=load_valuation_signals(web / 'valuation' / 'latest.json'),
        as_of=as_of,
        delisted=load_delisted(Path(__file__).resolve().parent / 'data' / 'delisted_tickers.txt'),
        previous=load_previous_dims(web / 'quality' / 'latest.json'),
        on_fetched=on_fetched,
        should_stop=(lambda: monotonic() - started > args.fetch_budget)
                    if args.fetch_budget else None,
    )

    m = payload['metadata']
    latest = web / 'quality' / 'latest.json'
    if m['fetch_stop_reason']:
        log.warning(f"DỪNG SỚM: {m['fetch_stop_reason']}")
    # Trả mã lỗi khi không công bố, để job đỏ và ci-alert mở issue.
    ok, why = may_publish(m['fetch_coverage'], args.min_coverage, latest)
    if not ok:
        log.error(f"KHÔNG công bố: {why}")
        return 1
    if why:
        log.warning(why)
    write_outputs(payload, web)

    # health.json KHÔNG cập nhật ở đây — xem backend/refresh_health.py.
    # Tóm tắt: định giá và chấm chất lượng là hai bước riêng; đặt lời gọi ở đây
    # nghĩa là bước này chết thì phần của bước ĐỊNH GIÁ cũng không ai cập nhật.
    # Đã xảy ra ngày 27/09/2026.

    log.info(f"Chấm {m['scored']}/{m['universe_size']} mã | trạng thái {m['status_counts']} "
             f"| mô hình {m['model_counts']} | lỗi {len(m['failures'])}")
    return 0 if payload['items'] else 1


if __name__ == '__main__':
    sys.exit(main())
