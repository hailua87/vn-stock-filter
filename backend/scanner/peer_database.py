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


def _trim_outliers(values: List[float], q_low: float = 0.10, q_high: float = 0.90) -> List[float]:
    """Loại bỏ top/bottom 10% để giảm noise (cyclical extremes, data errors)."""
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
