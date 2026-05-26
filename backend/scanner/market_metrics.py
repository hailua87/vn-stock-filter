"""
MARKET METRICS — Beta & Historical Multiples
================================================================================
Tính các metric cần cho định giá từ OHLCV cache + financial data:

  1. Beta 2Y       : regression returns vs VN-Index
  2. Historical P/E: từ price history × EPS history
  3. Historical P/B: từ price history × BVPS history

Tận dụng parquet cache đã có của data_fetcher (KHÔNG re-fetch).
"""
from __future__ import annotations
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Cache OHLCV ở cùng nơi với data_fetcher
OHLCV_CACHE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'cache'
VNINDEX_CACHE = Path(__file__).resolve().parent.parent / 'data' / 'vnindex_cache.parquet'


# ============================================================================
# BETA CALCULATION
# ============================================================================

def _load_ohlcv_from_cache(ticker: str, lookback_days: int = 730) -> Optional[pd.DataFrame]:
    """Đọc OHLCV từ parquet cache. Fallback _adj → _raw."""
    for suffix in ('_adj', '_raw'):
        cache_file = OHLCV_CACHE_DIR / f'{ticker}{suffix}.parquet'
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                df['Date'] = pd.to_datetime(df['Date'])
                cutoff = datetime.now() - timedelta(days=lookback_days)
                df = df[df['Date'] >= cutoff].sort_values('Date').reset_index(drop=True)
                if len(df) >= 50:  # Cần ít nhất ~10 tuần data
                    return df
            except Exception as e:
                log.debug(f"  {ticker} cache read failed: {e}")
    return None


def _load_vnindex(lookback_days: int = 730) -> Optional[pd.DataFrame]:
    """Đọc VN-Index từ cache hoặc fetch fresh."""
    if VNINDEX_CACHE.exists():
        try:
            df = pd.read_parquet(VNINDEX_CACHE)
            df['Date'] = pd.to_datetime(df['Date'])
            cutoff = datetime.now() - timedelta(days=lookback_days)
            df = df[df['Date'] >= cutoff].sort_values('Date').reset_index(drop=True)
            if len(df) >= 50:
                return df
        except Exception as e:
            log.debug(f"  VN-Index cache read failed: {e}")

    # Fallback: fetch fresh
    from .data_fetcher import fetch_vnindex
    df = fetch_vnindex(lookback_days=lookback_days)
    if df is not None and not df.empty:
        try:
            VNINDEX_CACHE.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(VNINDEX_CACHE, index=False)
        except Exception:
            pass
    return df


def calculate_beta(ticker: str, lookback_days: int = 730,
                   min_observations: int = 100) -> Dict[str, Any]:
    """
    Tính beta 2 năm bằng OLS regression của weekly returns vs VN-Index.

    Dùng WEEKLY returns thay vì daily vì:
      1. Daily noise quá lớn cho stocks thanh khoản thấp
      2. Bid-ask bounce làm daily returns biased
      3. Weekly cho beta ổn định hơn cho định giá dài hạn

    Returns:
        {
            'beta': float,               # hệ số beta
            'beta_raw': float,           # raw beta trước khi adjust
            'beta_adjusted': float,      # Blume-adjusted: 0.67*raw + 0.33*1.0
            'r_squared': float,          # độ phù hợp regression
            'observations': int,
            'lookback_days': int,
            'method': str,
            'fallback': bool,            # True nếu phải dùng default
        }
    """
    default_result = {
        'beta': 1.0,
        'beta_raw': 1.0,
        'beta_adjusted': 1.0,
        'r_squared': 0.0,
        'observations': 0,
        'lookback_days': lookback_days,
        'method': 'default_no_data',
        'fallback': True,
    }

    stock_df = _load_ohlcv_from_cache(ticker, lookback_days)
    if stock_df is None or len(stock_df) < min_observations:
        log.debug(f"  {ticker} beta: insufficient data → fallback to 1.0")
        return default_result

    index_df = _load_vnindex(lookback_days)
    if index_df is None or len(index_df) < min_observations:
        log.warning(f"  Beta calc: VN-Index unavailable → fallback to 1.0")
        return default_result

    # Merge on Date — chỉ giữ ngày cả stock và index đều có
    stock_df = stock_df[['Date', 'Close']].rename(columns={'Close': 'stock'})
    index_df = index_df[['Date', 'Close']].rename(columns={'Close': 'index'})
    merged = stock_df.merge(index_df, on='Date', how='inner').sort_values('Date')

    if len(merged) < min_observations:
        log.debug(f"  {ticker} beta: only {len(merged)} matched days → fallback")
        return default_result

    # Resample sang WEEKLY (lấy giá đóng cửa cuối tuần)
    merged = merged.set_index('Date')
    weekly = merged.resample('W-FRI').last().dropna()

    if len(weekly) < 30:  # Cần ít nhất 30 tuần (~7 tháng)
        return default_result

    # Calculate log returns (more robust than simple returns for regression)
    weekly['stock_ret'] = np.log(weekly['stock'] / weekly['stock'].shift(1))
    weekly['index_ret'] = np.log(weekly['index'] / weekly['index'].shift(1))
    weekly = weekly.dropna()

    if len(weekly) < 30:
        return default_result

    # OLS: stock_ret = α + β × index_ret + ε
    x = weekly['index_ret'].values
    y = weekly['stock_ret'].values

    # Loại bỏ outliers cực trị (>3σ) để tránh distortion
    y_std = np.std(y)
    y_mean = np.mean(y)
    mask = np.abs(y - y_mean) <= 3 * y_std
    x_clean = x[mask]
    y_clean = y[mask]

    if len(x_clean) < 30:
        return default_result

    # Compute beta via covariance/variance
    cov = np.cov(x_clean, y_clean)[0, 1]
    var_x = np.var(x_clean, ddof=1)
    if var_x < 1e-10:
        return default_result

    beta_raw = cov / var_x

    # R-squared
    correlation = np.corrcoef(x_clean, y_clean)[0, 1]
    r_squared = correlation ** 2 if not np.isnan(correlation) else 0.0

    # Blume adjustment: shrink toward 1.0
    # Lý do: regression beta có bias → mean reversion theo thời gian
    # Empirical: beta_future ≈ 0.67 × beta_raw + 0.33 × 1.0
    beta_adjusted = 0.67 * beta_raw + 0.33 * 1.0

    # Sanity cap: VN small-caps có thể có beta extreme
    if beta_adjusted < 0.2:
        beta_adjusted = 0.2
    if beta_adjusted > 2.5:
        beta_adjusted = 2.5

    return {
        'beta': round(beta_adjusted, 3),
        'beta_raw': round(beta_raw, 3),
        'beta_adjusted': round(beta_adjusted, 3),
        'r_squared': round(r_squared, 3),
        'observations': len(x_clean),
        'lookback_days': lookback_days,
        'method': 'weekly_log_returns_blume_adjusted',
        'fallback': False,
    }


# ============================================================================
# HISTORICAL MULTIPLES (P/E, P/B)
# ============================================================================

def _extract_eps_bvps_history(fundamentals_raw: Dict) -> List[Dict]:
    """
    Trích historical EPS và BVPS theo năm từ raw fundamentals.
    Returns list of {'period': str, 'eps': float, 'bvps': float}, oldest first.

    vnstock ratio table thường có column 'eps' và 'bvps' cho mỗi năm.
    """
    ratio_records = fundamentals_raw.get('ratio', [])
    if not ratio_records:
        return []

    out = []
    # ratio_records từ vnstock: latest first → reverse cho chronological
    for i, r in enumerate(reversed(ratio_records)):
        # Try multiple keys for period identifier
        period = (r.get('year') or r.get('period') or r.get('yearReport')
                  or f'period_{i}')
        eps = r.get('eps') or r.get('earnings_per_share') or r.get('basic_eps')
        bvps = r.get('bvps') or r.get('book_value_per_share')

        if eps is not None or bvps is not None:
            out.append({
                'period': str(period),
                'eps': float(eps) if eps is not None else None,
                'bvps': float(bvps) if bvps is not None else None,
            })
    return out


def _get_price_at_or_near(price_df: pd.DataFrame, target_date: pd.Timestamp,
                          window_days: int = 30) -> Optional[float]:
    """Tìm giá đóng cửa gần target_date nhất (trong cửa sổ ±window_days)."""
    lo = target_date - timedelta(days=window_days)
    hi = target_date + timedelta(days=window_days)
    window = price_df[(price_df['Date'] >= lo) & (price_df['Date'] <= hi)]
    if window.empty:
        return None
    # Lấy ngày gần target nhất
    window = window.copy()
    window['delta'] = (window['Date'] - target_date).abs()
    closest = window.sort_values('delta').iloc[0]
    return float(closest['Close'])


def calculate_historical_multiples(ticker: str, fundamentals_raw: Dict,
                                    lookback_years: int = 5) -> Dict[str, Any]:
    """
    Tính historical P/E và P/B percentiles thực sự (không phải proxy ±20%).

    Logic:
      1. Lấy EPS, BVPS cho mỗi năm từ ratio history (vnstock)
      2. Với mỗi cuối năm, lookup giá đóng cửa từ OHLCV cache
      3. Tính P/E = price / EPS, P/B = price / BVPS cho mỗi năm
      4. Thêm giá trị hiện tại (TTM)
      5. Trả về median, P25, P75

    Returns:
        {
            'pe_5y_median': float,
            'pe_5y_p25': float,
            'pe_5y_p75': float,
            'pe_history': [{'period': '2020', 'pe': 8.5}, ...],
            'pb_5y_median': float,
            'pb_5y_p25': float,
            'pb_5y_p75': float,
            'pb_history': [...],
            'observations': int,
            'fallback': bool,
        }
    """
    fallback_result = {
        'pe_5y_median': None,
        'pe_5y_p25': None,
        'pe_5y_p75': None,
        'pe_history': [],
        'pb_5y_median': None,
        'pb_5y_p25': None,
        'pb_5y_p75': None,
        'pb_history': [],
        'observations': 0,
        'fallback': True,
        'reason': '',
    }

    history = _extract_eps_bvps_history(fundamentals_raw)
    if not history:
        return {**fallback_result, 'reason': 'no_ratio_history'}

    price_df = _load_ohlcv_from_cache(ticker, lookback_days=lookback_years * 365 + 100)
    if price_df is None:
        return {**fallback_result, 'reason': 'no_ohlcv_cache'}

    pe_points = []
    pb_points = []

    for record in history:
        period = record['period']
        eps = record['eps']
        bvps = record['bvps']

        # Parse year từ period (e.g., '2024', '2024-Q4', '2024-12-31')
        year = None
        for part in str(period).replace('-', ' ').split():
            if part.isdigit() and 2000 <= int(part) <= 2100:
                year = int(part)
                break
        if year is None:
            continue

        # Lookup giá ở cuối năm (31/12) hoặc gần nhất
        year_end = pd.Timestamp(year=year, month=12, day=31)
        price = _get_price_at_or_near(price_df, year_end, window_days=45)
        if price is None:
            continue

        if eps and eps > 0:
            pe = price / eps
            if 0.5 < pe < 200:  # Sanity filter
                pe_points.append({'period': str(year), 'price': price,
                                  'eps': eps, 'pe': round(pe, 2)})
        if bvps and bvps > 0:
            pb = price / bvps
            if 0.1 < pb < 20:  # Sanity filter
                pb_points.append({'period': str(year), 'price': price,
                                  'bvps': bvps, 'pb': round(pb, 2)})

    # Thêm điểm hiện tại (TTM) để median phản ánh cả giá hiện tại
    current_price = float(price_df['Close'].iloc[-1])
    current_eps = fundamentals_raw.get('ratio', [{}])[0].get('eps')
    current_bvps = fundamentals_raw.get('ratio', [{}])[0].get('bvps')

    if current_eps and current_eps > 0:
        pe_now = current_price / float(current_eps)
        if 0.5 < pe_now < 200:
            pe_points.append({'period': 'current', 'price': current_price,
                              'eps': float(current_eps), 'pe': round(pe_now, 2)})
    if current_bvps and current_bvps > 0:
        pb_now = current_price / float(current_bvps)
        if 0.1 < pb_now < 20:
            pb_points.append({'period': 'current', 'price': current_price,
                              'bvps': float(current_bvps), 'pb': round(pb_now, 2)})

    result = {
        'pe_history': pe_points,
        'pb_history': pb_points,
        'observations': max(len(pe_points), len(pb_points)),
        'fallback': False,
        'reason': '',
    }

    if len(pe_points) >= 3:
        pe_vals = [p['pe'] for p in pe_points]
        result['pe_5y_median'] = round(float(np.median(pe_vals)), 2)
        result['pe_5y_p25'] = round(float(np.percentile(pe_vals, 25)), 2)
        result['pe_5y_p75'] = round(float(np.percentile(pe_vals, 75)), 2)
    else:
        result['pe_5y_median'] = None

    if len(pb_points) >= 3:
        pb_vals = [p['pb'] for p in pb_points]
        result['pb_5y_median'] = round(float(np.median(pb_vals)), 2)
        result['pb_5y_p25'] = round(float(np.percentile(pb_vals, 25)), 2)
        result['pb_5y_p75'] = round(float(np.percentile(pb_vals, 75)), 2)
    else:
        result['pb_5y_median'] = None

    if result.get('pe_5y_median') is None and result.get('pb_5y_median') is None:
        result['fallback'] = True
        result['reason'] = 'insufficient_points'

    return result


# ============================================================================
# CONVENIENCE: enrich fundamentals dict in-place
# ============================================================================

def enrich_with_market_metrics(ticker: str, fundamentals_raw: Dict) -> Dict:
    """
    Thêm beta + historical multiples vào fundamentals_raw để normalizer dùng.

    Sau khi gọi function này, fundamentals_raw sẽ có thêm:
      - 'beta_info': dict từ calculate_beta()
      - 'historical_multiples': dict từ calculate_historical_multiples()

    Đây là điểm tích hợp chính: gọi giữa fetch và normalize.
    """
    beta_info = calculate_beta(ticker)
    fundamentals_raw['beta_info'] = beta_info

    hist_mults = calculate_historical_multiples(ticker, fundamentals_raw)
    fundamentals_raw['historical_multiples'] = hist_mults

    return fundamentals_raw
