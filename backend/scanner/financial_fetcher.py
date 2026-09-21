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
from .snapshots import vnstock_version
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

# Tăng khi đổi định dạng record trong cache; cache khác schema bị bỏ qua.
# 2: mỗi record là một kỳ, khóa theo item_id, BCTC theo tỷ đồng.
# 3: overview có industry (ICB cấp 2) và icb_code_lv2/lv4 cho vnstock 4.0.7.
# 4: giữ 8 kỳ thay vì 5.
CACHE_SCHEMA = 4

# Số kỳ giữ lại. CAGR 5 năm cần 6 điểm (audit F2); bản cộng đồng của vnstock
# trả tối đa 8 kỳ, nên giữ hết. Normalizer tự cắt phần nó cần.
MAX_PERIODS = 8

# vnstock 4.x trả BCTC theo đồng; normalizer làm việc bằng tỷ đồng
# (vd. eps = net_profit * 1e9 / shares).
VND_PER_BN = 1_000_000_000

# Bảng ratio cũ hơn kỳ BCTC mới nhất quá số năm này thì bỏ — bản cộng đồng
# của vnstock 4.0.7 chỉ trả các quý 2018 cho bảng ratio.
MAX_RATIO_LAG_YEARS = 1

_ITEM_COLS = ('item', 'item_en', 'item_id')


def _period_sort_key(label: str) -> tuple:
    """'2025' → (2025, 5); '2026-Q2' → (2026, 2). Kỳ năm xếp sau Q4 cùng năm."""
    year, _, q = str(label).partition('-Q')
    try:
        return (int(year[:4]), int(q) if q else 5)
    except ValueError:
        return (0, 0)


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def statement_to_records(df: pd.DataFrame, scale: float = VND_PER_BN,
                         max_periods: int = MAX_PERIODS) -> list:
    """
    Chuyển bảng BCTC dạng dài của vnstock 4.x thành list record theo kỳ.

    Đầu vào: mỗi dòng một khoản mục (`item`, `item_en`, `item_id`), mỗi cột
    còn lại một kỳ ('2025' hoặc '2026-Q2').
    Đầu ra: [{'period': '2025', 'total_assets': 88141.99, ...}, ...], kỳ mới
    nhất trước, giá trị chia cho `scale`. item_id trùng lặp (vd. SSI có hai
    dòng short_term_borrowings) lấy giá trị khác rỗng đầu tiên.
    """
    if df is None or df.empty or 'item_id' not in df.columns:
        return []
    ids = df['item_id'].astype(str).tolist()
    periods = [(i, str(c)) for i, c in enumerate(df.columns) if c not in _ITEM_COLS]
    periods.sort(key=lambda p: _period_sort_key(p[1]), reverse=True)

    records = []
    for pos, label in periods[:max_periods]:
        rec = {'period': label}
        for item_id, v in zip(ids, df.iloc[:, pos].tolist()):
            f = _num(v)
            if f is not None and item_id not in rec:
                rec[item_id] = f / scale
        records.append(rec)
    return records


def ratio_to_records(df: pd.DataFrame, latest_statement_year: Optional[int],
                     max_periods: int = MAX_PERIODS) -> list:
    """
    Chuyển bảng ratio dạng dài thành list record theo kỳ, mới nhất trước.

    Kỳ đọc từ hai dòng `year`/`quarter` (tên cột không tin được: bản 4.0.7
    trả 16 cột cùng tên '2018'). Giữ nguyên giá trị (tỷ lệ, VND/cp).
    Trả [] nếu kỳ mới nhất cũ hơn BCTC quá MAX_RATIO_LAG_YEARS — để normalizer
    tự tính từ BCTC thay vì dùng P/E, ROE của nhiều năm trước.
    """
    if df is None or df.empty or 'item_id' not in df.columns:
        return []
    ids = df['item_id'].astype(str).tolist()
    by_period = {}
    for pos, c in enumerate(df.columns):
        if c in _ITEM_COLS:
            continue
        rec = {}
        for item_id, v in zip(ids, df.iloc[:, pos].tolist()):
            f = _num(v)
            if f is not None and item_id not in rec:
                rec[item_id] = f
        year, quarter = int(rec.get('year') or 0), int(rec.get('quarter') or 0)
        if year:
            by_period.setdefault((year, quarter), rec)

    ordered = [by_period[k] for k in sorted(by_period, reverse=True)]
    if not ordered:
        return []
    newest = int(ordered[0]['year'])
    if latest_statement_year and newest < latest_statement_year - MAX_RATIO_LAG_YEARS:
        log.warning(f"  ratio table stale (latest {newest}, statements {latest_statement_year}) — dropped")
        return []
    return ordered[:max_periods]


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
        # Normalize keys (vnstock có thể đổi tên cột giữa versions).
        # vnstock 4.0.7 (VCI) không còn icb_name2..4: cột `sector` là tên ngành
        # ICB cấp 2 tiếng Anh ('Banks', 'Real Estate') kèm icb_code_lv2/lv4.
        # Bản cũ dùng `sector` cho cấp 3, nên chỉ coi nó là cấp 2 khi có icb_code_lv2.
        icb_lv2_layout = 'icb_code_lv2' in row and 'icb_name2' not in row
        return {
            'ticker': ticker,
            'industry': (row.get('icb_name2') or row.get('industry') or row.get('industry_en')
                         or (row.get('sector') if icb_lv2_layout else None)),
            'sector': row.get('icb_name3') or (None if icb_lv2_layout else row.get('sector')),
            'subsector': row.get('icb_name4') or row.get('subsector'),
            'icb_code_lv2': row.get('icb_code_lv2'),
            'icb_code_lv4': row.get('icb_code_lv4'),
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
        Each DataFrame is long-format as returned by vnstock 4.x: rows = line
        items (item, item_en, item_id), one column per period, latest first.
        Values in VND. See statement_to_records() / ratio_to_records().
    """
    setup_api_key()
    try:
        from vnstock.api.financial import Finance
    except ImportError as e:
        log.error(f"vnstock Finance import failed: {e}")
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
            'balance_sheet': list of per-period dicts keyed by item_id,
                             latest first, in tỷ đồng,
            'income': same,
            'cash_flow': same,
            'ratio': per-period dicts (unscaled); [] if stale,
        }
    """
    cache_path = _cache_path(ticker, period)

    if use_cache and _is_cache_fresh(cache_path, cache_ttl_days):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('schema') == CACHE_SCHEMA:
                log.debug(f"  {ticker} fundamentals from cache")
                # Always re-fetch current price (cheap, changes daily)
                price = fetch_current_price(ticker)
                if price:
                    data['current_price'] = price
                return data
            log.debug(f"  {ticker} cache schema {data.get('schema')} != {CACHE_SCHEMA}, refetching")
        except Exception as e:
            log.warning(f"  {ticker} cache read failed: {e}")

    overview = fetch_company_overview(ticker)
    statements = fetch_financial_statements(ticker, period=period)
    price = fetch_current_price(ticker)

    if not statements:
        log.warning(f"  {ticker}: no financial statements available")
        return None

    result = {
        'schema': CACHE_SCHEMA,
        'ticker': ticker,
        'fetched_at': datetime.now().isoformat(),
        'vnstock_version': vnstock_version(),
        'period': period,
        'current_price': price,
        'overview': overview or {},
    }

    # Bảng dạng dài (dòng = khoản mục, cột = kỳ) → list record theo kỳ
    for key in ('balance_sheet', 'income', 'cash_flow'):
        result[key] = statement_to_records(statements.get(key))
    latest_year = None
    for key in ('income', 'balance_sheet'):
        if result[key]:
            latest_year = _period_sort_key(result[key][0]['period'])[0]
            break
    result['ratio'] = ratio_to_records(statements.get('ratio'), latest_year)

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
