"""
PEER DATABASE — Peer Comparable Analysis
================================================================================
Lưu trữ và tính peer median multiples theo ICB classification.

Logic:
  1. Khi chạy run_valuation.py cho universe (100+ mã), thu thập multiples
     của TỪNG mã sau khi fetch fundamentals
  2. Group theo ValuationIndustry → tính median, P25, P75, count
  3. Lưu vào JSON cache để các lần chạy sau dùng làm peer reference
  4. Trong định giá, dùng peer median THAY CHO VN-Index proxy

Schema cache (peer_multiples.json):
{
    "updated_at": "2026-05-26",
    "industries": {
        "Banking": {
            "ticker_count": 18,
            "tickers": ["VCB", "BID", "CTG", ...],
            "pe": {"median": 9.5, "p25": 7.2, "p75": 12.1, "mean": 9.8},
            "pb": {"median": 1.5, "p25": 1.1, "p75": 2.0, "mean": 1.6},
            "ev_ebitda": null,           # không áp dụng cho banking
            "roe": {"median": 0.18, "p25": 0.14, "p75": 0.22}
        },
        "Consumer_Staples": {...}
    }
}
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np

log = logging.getLogger(__name__)

PEER_DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'peer_multiples.json'


# Methods nào áp dụng cho mỗi ngành (peer median nào có ý nghĩa)
INDUSTRY_RELEVANT_METRICS = {
    'Banking':                  ['pe', 'pb', 'roe', 'npl_ratio'],
    'Securities':               ['pe', 'pb', 'roe'],
    'Insurance':                ['pe', 'pb', 'roe'],
    'Real_Estate':              ['pe', 'pb', 'roe'],
    'Construction':             ['pe', 'pb', 'ev_ebitda'],
    'Consumer_Staples':         ['pe', 'pb', 'ev_ebitda', 'roe'],
    'Consumer_Discretionary':   ['pe', 'pb', 'ev_ebitda', 'roe'],
    'Steel_Metals':             ['pb', 'ev_ebitda', 'roe'],     # P/E không tin cậy cho cyclical
    'Chemicals':                ['pb', 'ev_ebitda', 'roe'],
    'Oil_Gas':                  ['pb', 'ev_ebitda'],
    'Utilities':                ['pe', 'ev_ebitda', 'roe'],
    'Technology':               ['pe', 'pb', 'ev_ebitda', 'roe'],
    'Telecom':                  ['pe', 'ev_ebitda'],
    'Industrial_Manufacturing': ['pe', 'pb', 'ev_ebitda'],
    'Logistics_Transport':      ['pe', 'pb', 'ev_ebitda'],
    'Healthcare':               ['pe', 'pb', 'ev_ebitda', 'roe'],
    'Agriculture_Livestock':    ['pb', 'ev_ebitda'],            # cyclical
    'Diversified_Holding':      ['pe', 'pb', 'ev_ebitda'],
    'Unknown':                  ['pe', 'pb'],
}


# Trần "có nghĩa" cho MỘT quan sát EV/EBITDA trước khi nó được đếm vào rổ peer.
#
# 60,0 KHÔNG phải số chọn cho đẹp. EV/EBITDA là EV chia cho một mẫu số có thể
# tiến về 0: khi EBITDA ≈ 0 thì tỷ lệ nói về MẪU SỐ BỊ HỎNG, không nói gì về
# giá thị trường trả cho mỗi đồng EBITDA. Đo trên rổ thật 200 mã (13/10/2026,
# 196 quan sát), phân vị của toàn bộ quan sát:
#
#     p50=9,7  p75=20,5  p90=35,9  p95=48,5  p97=55,4  p98=126,7  p99=308,8
#     max=2.723,9  (UNI: EV 351 tỷ / EBITDA 0,13 tỷ)
#
# Đuôi vỡ ở đâu thì đọc được bằng mắt trên dãy đã xếp: ... 48,3  49,0  49,4
# 49,5  53,0 │ 69,3  117,2  212,3  307,8  328,0  2.723,9. Dưới 53x là một dải
# liên tục; từ 69x trở lên là các mã có EBITDA/EV < 1,5% — tức EBITDA gần 0.
# 60,0 nằm trong khe đó (tương đương đòi EBITDA/EV >= 1,67%) và bỏ 6/196 quan
# sát = 3,1%. Hai ngưỡng khác đều tệ hơn, và đây là lý do KHÔNG chọn chúng:
#   · 40x bỏ 19/196 = 9,7% — cắt vào giữa dải liên tục, nơi không có khe nào.
#     Nó đổi bội số mục tiêu của 8/13 ngành, tức đổi kết luận bằng một hằng số.
#   · 100x bỏ 5/196 = 2,6% — vẫn để VC9 (117x, EBITDA 1,14 tỷ) vào rổ.
#
# Đổi ngưỡng này là đổi kết luận. Phải ĐO LẠI trên rổ thật, không chỉnh cho đẹp.
MAX_MEANINGFUL_EV_EBITDA = 60.0

# Trần theo từng metric. Chỉ ev_ebitda có mẫu số tiến về 0; pe đã bị chặn bởi
# `v > 0` trong _compute_stats (lỗ EPS → pe <= 0 → loại), pb/roe/npl_ratio
# không có dạng vỡ này.
METRIC_MAX_MEANINGFUL = {
    'ev_ebitda': MAX_MEANINGFUL_EV_EBITDA,
}


def loc_quan_sat_co_nghia(metric: str, values: List[float]) -> List[float]:
    """Bỏ các quan sát mà bản thân con số là tạo tác của phép chia, không phải
    một bội số thị trường. Trả về nguyên list với metric không có trần."""
    tran = METRIC_MAX_MEANINGFUL.get(metric)
    if tran is None:
        return list(values)
    return [v for v in values if v is not None and v <= tran]


def _trim_outliers(values: List[float], q_low: float = 0.10, q_high: float = 0.90) -> List[float]:
    """Loại bỏ top/bottom 10% để giảm noise (cyclical extremes, data errors).

    LƯU Ý ĐÃ ĐO: hàm này KHÔNG cứu được rổ nhỏ, và nới `len < 5` cũng không.
    Rổ Technology thật [8,0 · 9,2 · 46,8 · 2.723,9] cắt 10/90 ở n=4 chỉ còn
    [9,2 · 46,8] — rơi xuống dưới min_count nên nhánh `trimmed = cleaned` dưới
    đây trả lại nguyên rổ chưa cắt, và trung vị vẫn là 28,0. Trung vị của rổ 4
    mã nằm GIỮA hai giá trị giữa, nên nó không bị "một giá trị rác kéo đi" —
    nó bị rác ĐẨY THỨ HẠNG. Vì vậy bản sửa nằm ở `loc_quan_sat_co_nghia`
    (lọc trước khi đếm), không ở đây.
    """
    if len(values) < 5:
        return values
    arr = np.array(values)
    lo = np.percentile(arr, q_low * 100)
    hi = np.percentile(arr, q_high * 100)
    return [v for v in values if lo <= v <= hi]


def _compute_stats(values: List[float], min_count: int = 3) -> Optional[Dict[str, float]]:
    """Tính median, P25, P75, mean cho list of values."""
    cleaned = [v for v in values if v is not None and v > 0
               and not (isinstance(v, float) and (np.isnan(v) or np.isinf(v)))]
    if len(cleaned) < min_count:
        return None
    trimmed = _trim_outliers(cleaned)
    if len(trimmed) < min_count:
        trimmed = cleaned  # too few — fall back to original

    return {
        'median': round(float(np.median(trimmed)), 2),
        'p25': round(float(np.percentile(trimmed, 25)), 2),
        'p75': round(float(np.percentile(trimmed, 75)), 2),
        'mean': round(float(np.mean(trimmed)), 2),
        'n': len(trimmed),
    }


def build_peer_database(valuation_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Xây peer database từ list of normalized valuation inputs.

    Args:
        valuation_inputs: List của dicts có schema:
            {
                'ticker': str,
                'industry': ValuationIndustry.value (str),
                'pe': float, 'pb': float, 'ev_ebitda': float,
                'roe': float, 'npl_ratio': float,
            }

    Returns:
        Peer database dict (sẽ save vào JSON)
    """
    # Group by industry
    by_industry: Dict[str, List[Dict]] = {}
    for v in valuation_inputs:
        ind = v.get('industry', 'Unknown')
        by_industry.setdefault(ind, []).append(v)

    industries_out = {}
    for industry, records in by_industry.items():
        relevant = INDUSTRY_RELEVANT_METRICS.get(industry, ['pe', 'pb'])
        industry_data = {
            'ticker_count': len(records),
            'tickers': [r['ticker'] for r in records],
        }

        for metric in ['pe', 'pb', 'ev_ebitda', 'roe', 'npl_ratio']:
            if metric not in relevant:
                industry_data[metric] = None
                continue
            values = [r.get(metric) for r in records if r.get(metric) is not None]
            # Lọc TRƯỚC khi đếm: một quan sát rác không chỉ kéo mean/p75, nó
            # chiếm một suất trong rổ và đẩy thứ hạng của trung vị.
            values = loc_quan_sat_co_nghia(metric, values)
            stats = _compute_stats(values)
            industry_data[metric] = stats

        industries_out[industry] = industry_data

    return {
        'updated_at': datetime.now().isoformat(),
        'total_tickers': len(valuation_inputs),
        'industries': industries_out,
    }


def save_peer_database(db: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Lưu peer database ra JSON."""
    target = path or PEER_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  Peer database saved: {target} "
             f"({len(db['industries'])} industries, {db['total_tickers']} tickers)")


def load_peer_database(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Đọc peer database từ JSON. None nếu chưa tồn tại."""
    target = path or PEER_DB_PATH
    if not target.exists():
        return None
    try:
        with open(target, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"  Peer DB read failed: {e}")
        return None


def get_peer_median(industry: str, metric: str = 'pe',
                    peer_db: Optional[Dict] = None) -> Optional[float]:
    """
    Lookup peer median cho 1 industry và metric.

    Args:
        industry: ValuationIndustry value (e.g., 'Banking')
        metric: 'pe' | 'pb' | 'ev_ebitda' | 'roe'
        peer_db: Pre-loaded db. Nếu None, sẽ load từ file.

    Returns:
        Median value hoặc None nếu không có peer data.
    """
    if peer_db is None:
        peer_db = load_peer_database()
    if peer_db is None:
        return None

    industry_data = peer_db.get('industries', {}).get(industry)
    if not industry_data:
        return None

    metric_stats = industry_data.get(metric)
    if not metric_stats:
        return None

    return metric_stats.get('median')


def get_peer_band(industry: str, metric: str = 'pe',
                  peer_db: Optional[Dict] = None) -> Optional[Dict[str, float]]:
    """
    Lookup full peer band (median, P25, P75, n) cho 1 metric.
    Returns None nếu không có data.
    """
    if peer_db is None:
        peer_db = load_peer_database()
    if peer_db is None:
        return None

    industry_data = peer_db.get('industries', {}).get(industry)
    if not industry_data:
        return None

    return industry_data.get(metric)


def extract_peer_input(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Trích các metric từ normalized data để contribute vào peer database.

    Args:
        data: Output từ normalize_fundamentals()
    """
    ticker = data.get('ticker')
    if not ticker:
        return None

    ratios = data.get('ratios', {})
    asset_quality = data.get('asset_quality', {})

    # Industry phải được set trước (qua classifier)
    industry = data.get('_industry')  # set bởi engine sau classification
    if not industry:
        return None

    return {
        'ticker': ticker,
        'industry': industry,
        'pe': ratios.get('pe_ttm'),
        'pb': ratios.get('pb_current'),
        'ev_ebitda': ratios.get('ev_ebitda'),  # nếu có
        'roe': ratios.get('roe_ttm'),
        'npl_ratio': asset_quality.get('npl_ratio'),
    }
