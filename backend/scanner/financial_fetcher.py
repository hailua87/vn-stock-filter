"""
Financial data fetcher for Vietnam stocks — vnstock 4.x compatible.

Lấy financial statements (BS/IS/CF) + ratios + company overview cho định giá.
Tái sử dụng pattern từ data_fetcher.py: API key setup, sys.exit patch, retry,
parquet cache.

Khác data_fetcher (chuyên OHLCV) ở chỗ:
  - Chu kỳ refresh dài hơn (quý/năm thay vì ngày)
  - Cache key gồm cả period (year/quarter)
  - Format trả về dict thay vì DataFrame (vì có nhiều bảng)

Usage:
    from scanner.financial_fetcher import fetch_fundamentals
    data = fetch_fundamentals('VIB', period='year')
    # → {'overview': {...}, 'balance_sheet': df, 'income': df, ...}
"""
from __future__ import annotations
import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

# Tái sử dụng monkey-patch và setup từ data_fetcher
from .data_fetcher import (
    setup_api_key,
    RateLimitError,
    patch_sys_exit,
)

log = logging.getLogger(__name__)

# Cache directory riêng cho fundamentals (refresh thưa hơn OHLCV)
CACHE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'fundamentals_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Fundamental data refresh interval: 7 days
# BCTC quý ra ~30 ngày sau cuối quý, không cần fetch hàng ngày
DEFAULT_CACHE_TTL_DAYS = 7


def _cache_path(ticker: str, period: str) -> Path:
    """Cache file path for fundamentals."""
    return CACHE_DIR / f"{ticker}_{period}.json"


def _is_cache_fresh(cache_path: Path, ttl_days: int = DEFAULT_CACHE_TTL_DAYS) -> bool:
    """Check if cache file exists and is fresh enough."""
    if not cache_path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
    return age < timedelta(days=ttl_days)


def fetch_company_overview(ticker: str, source: str = 'vci') -> Optional[Dict[str, Any]]:
    """
    Fetch company overview (industry, sector, listed date, etc.).
    Returns dict or None on error.
    """
    setup_api_key()
    try:
        from vnstock.api.company import Company
    except ImportError:
        log.error("vnstock not installed")
        return None

    try:
        c = Company(symbol=ticker, source=source)
        df = c.overview()
        if df is None or df.empty:
            return None
        # vnstock 4.x trả về DataFrame 1 hàng; convert thành dict
        row = df.iloc[0].to_dict()
        # Normalize keys (vnstock có thể đổi tên cột giữa versions)
        return {
            'ticker': ticker,
            'industry': row.get('icb_name2') or row.get('industry') or row.get('industry_en'),
            'sector': row.get('icb_name3') or row.get('sector'),
            'subsector': row.get('icb_name4') or row.get('subsector'),
            'company_name': row.get('short_name') or row.get('company_name'),
            'established_year': row.get('established_year'),
            'listed_date': row.get('listed_date'),
            'outstanding_share': row.get('outstanding_share') or row.get('issue_share'),
            'foreign_percent': row.get('foreign_percent'),
            '_raw': row,
        }
    except RateLimitError:
        log.warning(f"  {ticker} overview rate-limited")
        return None
    except Exception as e:
        log.warning(f"  {ticker} overview failed: {type(e).__name__}: {str(e)[:120]}")
        return None


def fetch_financial_statements(ticker: str, source: str = 'vci',
                                period: str = 'year') -> Optional[Dict[str, pd.DataFrame]]:
    """
    Fetch balance sheet + income statement + cash flow.

    Args:
        period: 'year' or 'quarter'
    Returns:
        {'balance_sheet': df, 'income': df, 'cash_flow': df, 'ratio': df}
        Each DataFrame has rows = periods (latest first), columns = line items.
    """
    setup_api_key()
    try:
        from vnstock.api.finance import Finance
    except ImportError:
        log.error("vnstock not installed")
        return None

    results = {}
    fin = Finance(symbol=ticker, source=source)

    fetchers = {
        'balance_sheet': lambda: fin.balance_sheet(period=period, lang='en'),
        'income': lambda: fin.income_statement(period=period, lang='en'),
        'cash_flow': lambda: fin.cash_flow(period=period, lang='en'),
        'ratio': lambda: fin.ratio(period=period, lang='en'),
    }

    for name, fn in fetchers.items():
        for attempt in range(3):
            try:
                df = fn()
                if df is not None and not df.empty:
                    results[name] = df
                break
            except RateLimitError:
                log.warning(f"  {ticker} {name} rate-limited, waiting 65s")
                time.sleep(65)
            except Exception as e:
                err_str = str(e).lower()
                if 'rate' in err_str or '429' in err_str:
                    time.sleep(60)
                else:
                    log.warning(f"  {ticker} {name} attempt {attempt+1}: {type(e).__name__}: {str(e)[:120]}")
                    time.sleep(2 + attempt * 2)

    return results if results else None


def fetch_current_price(ticker: str, source: str = 'vci') -> Optional[float]:
    """
    Giá đóng cửa gần nhất, trả về theo **VND/cp** (đã nhân 1.000).

    vnstock trả giá theo nghìn VND (ACB = 24.30) trong khi EPS/BVPS của bảng
    ratio theo VND (EPS = 3.500). Toàn bộ valuation engine làm việc bằng VND nên
    quy đổi phải xảy ra ở đây — xem `scanner/price_units.py`.
    """
    from .data_fetcher import fetch_ohlcv
    from .price_units import quote_to_vnd
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    df = fetch_ohlcv(ticker, start, end, source=source)
    if df is None or df.empty:
        return None
    return quote_to_vnd(float(df['Close'].iloc[-1]))


def fetch_fundamentals(ticker: str, period: str = 'year',
                       use_cache: bool = True,
                       cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS) -> Optional[Dict[str, Any]]:
    """
    Lấy tổng hợp dữ liệu cơ bản cho định giá.

    Returns:
        {
            'ticker': str,
            'fetched_at': iso datetime,
            'current_price': float,
            'overview': dict,
            'balance_sheet': list of dicts (latest first),
            'income': list of dicts,
            'cash_flow': list of dicts,
            'ratio': list of dicts,
        }
    """
    cache_path = _cache_path(ticker, period)

    if use_cache and _is_cache_fresh(cache_path, cache_ttl_days):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            log.debug(f"  {ticker} fundamentals from cache")
            # Always re-fetch current price (cheap, changes daily)
            price = fetch_current_price(ticker)
            if price:
                data['current_price'] = price
            return data
        except Exception as e:
            log.warning(f"  {ticker} cache read failed: {e}")

    overview = fetch_company_overview(ticker)
    statements = fetch_financial_statements(ticker, period=period)
    price = fetch_current_price(ticker)

    if not statements:
        log.warning(f"  {ticker}: no financial statements available")
        return None

    result = {
        'ticker': ticker,
        'fetched_at': datetime.now().isoformat(),
        'period': period,
        'current_price': price,
        'overview': overview or {},
    }

    # Convert DataFrames to list of dicts (JSON-serializable)
    for key, df in statements.items():
        # Limit to latest 5 periods to keep cache file small
        df_limited = df.head(5) if len(df) > 5 else df
        # Convert all values to native Python (avoid numpy types in JSON)
        records = df_limited.to_dict(orient='records')
        result[key] = records

    if use_cache:
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            log.warning(f"  {ticker} cache write failed: {e}")

    return result


def fetch_fundamentals_batch(tickers: list, period: str = 'year',
                              use_cache: bool = True,
                              max_failures: int = 50) -> Dict[str, Dict]:
    """
    Fetch fundamentals cho nhiều tickers với rate-limit awareness.
    Trả về dict {ticker: data}.
    """
    results = {}
    failures = 0
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        if i % 10 == 0:
            log.info(f"  Fetching fundamentals: {i}/{total} ({len(results)} ok, {failures} failed)")

        try:
            data = fetch_fundamentals(ticker, period=period, use_cache=use_cache)
            if data:
                results[ticker] = data
            else:
                failures += 1

            if failures >= max_failures:
                log.error(f"  Too many failures ({failures}), stopping batch")
                break
        except Exception as e:
            failures += 1
            log.warning(f"  {ticker} unexpected error: {e}")

    log.info(f"  Fundamentals batch complete: {len(results)}/{total} successful")
    return results
