"""
Data fetcher for Vietnam stock market — vnstock 4.x compatible.

Migration notes (vnstock 4.x):
  Old API: Vnstock().stock(symbol='ACB').quote.history(...)
  New API: from vnstock.api.quote import Quote
           Quote(symbol='ACB', source='vci').history(...)

  The old `Vnstock` class was deprecated on 31/08/2025.
  See: https://vnstocks.com/vnstock-migration

  Valid sources (lowercase): vci, kbs, msn, dnse, binance, fmp, fmarket.
  TCBS was REMOVED in vnstock 4.x — using it raises ValueError.

API Key (vnstock 4.x):
  Anonymous users have STRICT rate limits (few req/min). Register a free
  API key at https://vnstocks.com/login to get 60 req/min (Community).
  Set the env variable VNSTOCK_API_KEY before fetching.

Rate limit handling:
  vnstock calls sys.exit() when rate limit hit — we MONKEY-PATCH sys.exit
  to raise RateLimitError instead, so we can catch and retry.

Primary source: 'vci' (returns backward-adjusted prices — dividends already
subtracted from historical bars). Prices will differ from cafef/broker apps
for tickers with recent cash dividends; that's expected and correct for
technical analysis (no fake gaps).

Cache: parquet files per ticker in `backend/data/cache/` with suffix
'_adj.parquet' (adjusted prices). Daily increment: only fetch missing dates.
"""
from __future__ import annotations
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
import logging

import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────
# Monkey-patch sys.exit so vnstock's rate-limit doesn't kill the process
# ─────────────────────────────────────────────────────────────────────────
class RateLimitError(Exception):
    """Raised when vnstock tries to sys.exit() due to rate limit."""
    pass


_original_sys_exit = sys.exit
_patched = False


def _patched_sys_exit(code=0):
    """Override sys.exit — convert to RateLimitError if called from vnstock."""
    # Check if call came from vnstock/vnai code
    import traceback
    stack = traceback.extract_stack()
    in_vnstock = any('vnstock' in (frame.filename or '') or 'vnai' in (frame.filename or '')
                     for frame in stack)
    if in_vnstock:
        raise RateLimitError(f"vnstock rate-limit triggered sys.exit({code})")
    # Otherwise behave normally
    _original_sys_exit(code)


def patch_sys_exit():
    """Apply the monkey patch. Idempotent."""
    global _patched
    if not _patched:
        sys.exit = _patched_sys_exit
        _patched = True


# ─────────────────────────────────────────────────────────────────────────
# API Key setup — call this ONCE at startup
# ─────────────────────────────────────────────────────────────────────────
_api_key_initialized = False

def setup_api_key(api_key: Optional[str] = None) -> bool:
    """
    Configure vnstock API key. Reads from VNSTOCK_API_KEY env var if not given.
    Returns True if a key was configured, False otherwise.
    Must be called before any fetch_* function.
    """
    global _api_key_initialized
    if _api_key_initialized:
        return True

    # Patch sys.exit BEFORE any vnstock import/call
    patch_sys_exit()

    if api_key is None:
        api_key = os.environ.get('VNSTOCK_API_KEY')

    if not api_key:
        log.warning("No VNSTOCK_API_KEY set — using anonymous mode (strict rate limit)")
        _api_key_initialized = True
        return False

    try:
        import vnai
        vnai.setup_api_key(api_key)
        log.info("✓ vnstock API key configured")
        _api_key_initialized = True
        return True
    except Exception as e:
        log.error(f"Failed to setup API key: {e}")
        _api_key_initialized = True
        return False


# ─────────────────────────────────────────────────────────────────────────
# Universe — list of tickers on each exchange
# ─────────────────────────────────────────────────────────────────────────
def get_ticker_universe(exchanges: tuple = ('HOSE', 'HNX', 'UPCOM'),
                        limit: Optional[int] = None,
                        use_liquidity_sort: bool = True) -> pd.DataFrame:
    """
    Return a DataFrame with columns: ticker, exchange.
    Uses vnstock 4.x Listing API.

    Args:
        exchanges: which exchanges to include
        limit: max tickers to return (for free-tier rate limit). If None, all.
        use_liquidity_sort: if True and limit is set, sort by liquidity (cached
            average turnover) before applying limit. Falls back to curated
            top-liquid list if no cache exists.
    """
    setup_api_key()

    # Always load full universe from vnstock first
    full_universe = _fetch_full_universe(exchanges)

    if limit is None or not use_liquidity_sort:
        if limit:
            return full_universe.head(limit).reset_index(drop=True)
        return full_universe

    # Sort by cached liquidity score (highest first)
    return _sort_by_liquidity(full_universe, limit)


def _fetch_full_universe(exchanges: tuple) -> pd.DataFrame:
    """Fetch full ticker list from vnstock API."""
    try:
        from vnstock.api.listing import Listing
        listing = Listing()
        all_df = listing.all_symbols()
        cols = {c.lower(): c for c in all_df.columns}
        ticker_col = cols.get('symbol') or cols.get('ticker') or all_df.columns[0]
        all_df = all_df.rename(columns={ticker_col: 'ticker'})

        if 'exchange' in cols:
            ex_col = cols['exchange']
            all_df = all_df.rename(columns={ex_col: 'exchange'})
            result = all_df[all_df['exchange'].isin(exchanges)][['ticker', 'exchange']]
        else:
            out = []
            for ex in exchanges:
                try:
                    sub = listing.symbols_by_exchange(ex.lower())
                    sub_cols = {c.lower(): c for c in sub.columns}
                    tk_col = sub_cols.get('symbol') or sub_cols.get('ticker') or sub.columns[0]
                    sub = sub.rename(columns={tk_col: 'ticker'})
                    sub['exchange'] = ex
                    out.append(sub[['ticker', 'exchange']])
                except Exception as e:
                    log.warning(f"  symbols_by_exchange({ex}) failed: {e}")
            if out:
                result = pd.concat(out, ignore_index=True)
            else:
                return _load_fallback_universe(exchanges)

        # Override exchange using top_liquid.py (source of truth for curated list).
        # vnstock listing sometimes returns duplicate ticker rows with different
        # exchanges (e.g. DVN appears on both HOSE and UPCOM historical records).
        # Our curated top_liquid lists reflect the CURRENT trading venue.
        try:
            from .top_liquid import get_top_liquid_tickers
            override_map = dict(get_top_liquid_tickers())  # {ticker: exchange}
            corrections = 0
            for idx, row in result.iterrows():
                tk = row['ticker']
                if tk in override_map and row['exchange'] != override_map[tk]:
                    log.info(f"  Exchange override: {tk} {row['exchange']} → {override_map[tk]}")
                    result.at[idx, 'exchange'] = override_map[tk]
                    corrections += 1
            if corrections:
                log.info(f"  Applied {corrections} exchange corrections from top_liquid")
        except Exception as e:
            log.warning(f"  Exchange override skipped: {e}")

        # Drop duplicates AFTER override (keeps the corrected row)
        result = result.drop_duplicates('ticker').reset_index(drop=True)
        result = result[result['ticker'].str.len().between(3, 5)]
        log.info(f"  Full universe: {len(result)} tickers from {exchanges}")
        return result.reset_index(drop=True)
    except Exception as e:
        log.warning(f"vnstock listing failed ({e}), falling back to curated list")
        return _load_fallback_universe(exchanges)


def _sort_by_liquidity(universe: pd.DataFrame, limit: int) -> pd.DataFrame:
    """
    Sort universe by liquidity (avg turnover) and return top N.

    Strategy:
      1. Read existing parquet cache files — each contains historical OHLCV.
         Compute avg(Close * Volume) over last 20 days = avg turnover (VND).
      2. For tickers without cache, use the curated TOP_LIQUID list as proxy
         (these are known liquid stocks).
      3. Combine: cached liquidity scores + curated list = ranked universe.
    """
    from .top_liquid import get_top_liquid_tickers

    # Step 1: compute liquidity from cache
    # FIX: glob cả *_adj.parquet (default mới) và *_raw.parquet (legacy fallback).
    # Trước đó chỉ glob *_adj.parquet với suffix='_raw' khiến luôn miss.
    liquidity = {}  # ticker → avg turnover
    seen = set()
    for pattern, strip in (('*_adj.parquet', '_adj'), ('*_raw.parquet', '_raw')):
        for cache_file in CACHE_DIR.glob(pattern):
            ticker = cache_file.stem.replace(strip, '')
            if ticker in seen:
                continue
            seen.add(ticker)
            try:
                df = pd.read_parquet(cache_file)
                if len(df) < 5:
                    continue
                recent = df.tail(20)
                avg_turnover = (recent['Close'] * recent['Volume']).mean()
                if pd.notna(avg_turnover) and avg_turnover > 0:
                    liquidity[ticker] = avg_turnover
            except Exception:
                continue

    log.info(f"  Liquidity cache: {len(liquidity)} tickers with historical data")

    # Step 2: rank universe
    # Tickers with cache: use actual liquidity
    # Tickers without cache: use position in TOP_LIQUID curated list (higher = better)
    curated = get_top_liquid_tickers()
    curated_score = {tk: (len(curated) - i) * 1e9
                     for i, (tk, _) in enumerate(curated)}
    # Note: curated_score is in same units as liquidity (VND) so they're comparable.
    # 1e9 multiplier ensures even unknown stocks are ranked sensibly.

    def score(row):
        if row['ticker'] in liquidity:
            return liquidity[row['ticker']]
        return curated_score.get(row['ticker'], 0)

    universe = universe.copy()
    universe['liquidity'] = universe.apply(score, axis=1)
    universe = universe.sort_values('liquidity', ascending=False)
    top_n = universe.head(limit)[['ticker', 'exchange']].reset_index(drop=True)

    log.info(f"  Selected top {len(top_n)} by liquidity (limit={limit})")
    return top_n


def _load_fallback_universe(exchanges: tuple) -> pd.DataFrame:
    """Static fallback list of liquid tickers if API is down."""
    fallback = {
        'HOSE': ['VCB','VIC','VHM','VRE','HPG','FPT','MWG','MBB','TCB','VPB',
                 'STB','GAS','MSN','PNJ','DGC','SSI','VND','HCM','VCI','BID',
                 'CTG','SHB','EIB','ACB','POW','REE','GVR','GMD','VNM','SAB',
                 'PLX','BCM','BVH','PHR','DPM','DCM','PVD','HSG','NKG','HDB'],
        'HNX':  ['SHS','CEO','IDC','PVS','MBS','TNG','NTP','PVI','HUT','BVS',
                 'VCS','LAS','TVC','VC3','TIG'],
        'UPCOM':['ACV','BSR','VEA','VGI','OIL','QNS','VTP','MCH','MSR','SIP',
                 'VGT','LTG','FOX','MFS','BVB'],
    }
    rows = []
    for ex in exchanges:
        for tk in fallback.get(ex, []):
            rows.append({'ticker': tk, 'exchange': ex})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────
# Historical OHLCV fetcher — vnstock 4.x API
# ─────────────────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker: str, start: str, end: str,
                source: str = 'vci', retries: int = 2,
                adjusted: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV for a single ticker using vnstock 4.x.

    FIX (2026-05-26): chuyển source mặc định từ 'TCBS' → 'VCI'. Lý do:
    vnstock 4.x đã BỎ source 'TCBS' — chỉ chấp nhận: kbs, vci, msn, dnse,
    binance, fmp, fmarket. PUSH_GUIDE.md trước đó set source='TCBS' khiến
    MỌI fetch fail với ValueError → fallback xuống cache cũ → giá sai phiên.

    VCI trả về backward-adjusted prices (đã trừ cổ tức/cổ phiếu thưởng quá
    khứ). Giá hiển thị sẽ KHÁC cafef cho mã có cổ tức gần đây — ví dụ VND
    có cổ tức 500đ chia 15/07/2025 nên giá VCI sẽ thấp hơn cafef ~0.5.
    Đây là TRADE-OFF có chủ ý: adjusted price cho phân tích kỹ thuật chính
    xác hơn (RSI/Ichimoku/Fibonacci không bị gap giả), tuy giá tuyệt đối
    khác broker app. UI nên có note "✓ Giá điều chỉnh" để user hiểu.

    `adjusted` parameter chỉ ảnh hưởng suffix cache file (_adj vs _raw),
    không ảnh hưởng VCI vì VCI luôn trả adjusted.

    Returns DataFrame: Date, Open, High, Low, Close, Volume
    """
    setup_api_key()
    try:
        from vnstock.api.quote import Quote
    except ImportError:
        log.error("vnstock not installed or version too old. Run: pip install -U vnstock")
        return None

    for attempt in range(retries + 1):
        try:
            q = Quote(symbol=ticker, source=source)
            df = q.history(start=start, end=end, interval='1D')

            if df is None or df.empty:
                return None

            df = df.rename(columns={
                'time': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })

            required = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            missing = [c for c in required if c not in df.columns]
            if missing:
                log.warning(f"  {ticker}: missing columns {missing}, got {list(df.columns)}")
                return None

            df['Date'] = pd.to_datetime(df['Date'])
            df = df[required].sort_values('Date')
            return df.reset_index(drop=True)
        except RateLimitError as e:
            # vnstock called sys.exit() due to rate limit; wait full 60s
            log.warning(f"  {ticker} rate-limit hit, waiting 65s for reset...")
            time.sleep(65)
        except SystemExit as e:
            # Backup: if monkey-patch didn't catch it
            log.warning(f"  {ticker} SystemExit raised, waiting 65s...")
            time.sleep(65)
        except ValueError as e:
            # FIX: invalid source / invalid ticker là lỗi config, không phải transient.
            # Trước đây retry 3 lần x 500 mã x 2-4s → tốn ~1h CI vô ích trước khi fail.
            # Nay: phát hiện và RAISE để fail-fast — pipeline sẽ stop ngay.
            err_str = str(e)
            if 'source' in err_str.lower() or 'Lớp Quote' in err_str:
                log.error(f"FATAL CONFIG ERROR: {err_str}")
                raise RuntimeError(
                    f"vnstock source='{source}' không hợp lệ. Sửa data_fetcher.py "
                    f"đặt source thành một trong: kbs, vci, msn, dnse, fmp, fmarket. "
                    f"Original error: {err_str}"
                ) from e
            # ValueError khác (parse, range...) thì retry như cũ
            log.warning(f"  {ticker} attempt {attempt+1}: ValueError: {str(e)[:150]}")
            time.sleep(2 + attempt * 2)
        except BaseException as e:
            err_str = str(e).lower()
            if 'rate' in err_str or 'limit' in err_str or '429' in err_str:
                wait = 60
                log.warning(f"  {ticker} rate-limited (msg), waiting {wait}s...")
                time.sleep(wait)
            else:
                log.warning(f"  {ticker} attempt {attempt+1}: {type(e).__name__}: {str(e)[:150]}")
                time.sleep(2 + attempt * 2)
    return None


def _last_trading_session(today: 'date') -> 'date':
    """
    Phiên giao dịch gần nhất tính đến `today` (chưa tính giờ trong ngày).
    HOSE/HNX/UPCOM nghỉ thứ Bảy và Chủ Nhật (không xét nghỉ lễ — đơn giản hoá).
    - Nếu today là Thứ Hai → phiên gần nhất = Thứ Sáu tuần trước.
    - Nếu today là Thứ Bảy/Chủ Nhật → phiên gần nhất = Thứ Sáu cùng tuần.
    - Còn lại: chính `today`.
    Caller có trách nhiệm hiểu phiên T có thể CHƯA close (intraday).
    """
    d = today
    # weekday(): Mon=0..Sun=6
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d = d - timedelta(days=1)
    return d


def fetch_with_cache(ticker: str, exchange: str, lookback_days: int = 180,
                     force_refresh: bool = False, adjusted: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV using local parquet cache. Only pulls incremental data
    since last cached date.

    FIX (2026-05-26): adjusted=True mặc định (đi đôi với source='vci' trong
    fetch_ohlcv). Cache file dùng suffix '_adj.parquet'. Cache cũ '_raw.parquet'
    (do TCBS-fail-fallback ghi) là dữ liệu rác — workflow cần purge trước
    lần chạy đầu sau fix (đã bump cache key v1 → v2 trong daily-scan.yml).

    FIX: kiểm tra cache có chứa đúng phiên giao dịch gần nhất theo lịch không.
    Trước đây: last_date >= end - 1 day (sai trên thứ Hai + sau nghỉ lễ).
    Bây giờ: last_date >= _last_trading_session(end).

    FIX (2026-05-26 evening): STRICT SESSION VALIDATION ở cuối function.
    Triệu chứng: ACB hiển thị giá 24.30 / KL 22M trong khi SSI báo 24.80 / 58.82M
    cùng phiên 26/05/2026. KL chênh 62% → vnstock VCI trả data PARTIAL (có data
    nhưng thiếu phiên 26/05). Code cũ ghi vào cache và return bình thường, không
    flag StaleCache → strategy không reject → output sai data dưới ngày đúng.

    Fix: bất kể đường nào dẫn đến df (cache fresh / refetch / fresh fetch), CUỐI
    function check `df['Date'].max().date() >= last_session`. Nếu KHÔNG → đánh dấu
    StaleCache=True → strategy evaluate() reject mã đó.
    """
    suffix = '_adj' if adjusted else '_raw'
    cache_file = CACHE_DIR / f'{ticker}{suffix}.parquet'
    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)
    last_session = _last_trading_session(end)

    df: Optional[pd.DataFrame] = None
    refetch_explicit_failed = False  # True nếu refetch trả None/empty

    if cache_file.exists() and not force_refresh:
        try:
            cached = pd.read_parquet(cache_file)
            cached['Date'] = pd.to_datetime(cached['Date'])
            last_date = cached['Date'].max().date()
            if last_date >= last_session:
                # Cache đã chứa phiên gần nhất — dùng luôn
                df = cached[cached['Date'] >= pd.Timestamp(start)].copy()
            else:
                # Cache cũ — refetch incremental (refresh 30 ngày cuối phòng late corp actions)
                refetch_start = (last_date - timedelta(days=30))
                new = fetch_ohlcv(ticker, str(refetch_start), str(end), adjusted=adjusted)
                if new is not None and not new.empty:
                    cached_old = cached[cached['Date'] < pd.Timestamp(refetch_start)]
                    df = pd.concat([cached_old, new]).drop_duplicates('Date').sort_values('Date')
                    # Chỉ ghi cache nếu refetch trả về data tới phiên gần nhất.
                    # Tránh trường hợp partial data (có data nhưng thiếu last_session)
                    # ghi đè cache cũ với cùng vấn đề. Việc check StaleCache ở dưới
                    # sẽ flag df, không cần stop early.
                    new_last_date = pd.to_datetime(new['Date']).max().date()
                    if new_last_date >= last_session:
                        df.to_parquet(cache_file, index=False)
                else:
                    # Refetch fail rõ ràng → dùng cache cũ, sẽ flag StaleCache ở cuối
                    df = cached.copy()
                    refetch_explicit_failed = True
                    log.warning(
                        f"  {ticker}: refetch FAILED (empty), using stale cache "
                        f"(last={last_date}, expected={last_session})"
                    )
        except Exception as e:
            log.warning(f"  cache read failed for {ticker}: {e}, refetching from scratch")
            df = None

    if df is None:
        # Không có cache hoặc cache read fail → fetch from scratch
        df = fetch_ohlcv(ticker, str(start), str(end), adjusted=adjusted)
        if df is None or df.empty:
            return None
        try:
            df.to_parquet(cache_file, index=False)
        except Exception as e:
            log.warning(f"  cache write failed for {ticker}: {e}")

    # ──────────── STRICT SESSION VALIDATION ────────────
    # Bất kể df đến từ đâu (cache fresh / merged / fresh fetch), check phiên cuối.
    # Nếu thiếu phiên gần nhất → flag StaleCache để strategy reject.
    df['Date'] = pd.to_datetime(df['Date'])
    df_last_date = df['Date'].max().date()
    is_stale = (df_last_date < last_session) or refetch_explicit_failed

    if is_stale:
        log.warning(
            f"  {ticker}: STALE — df.last={df_last_date}, expected={last_session} "
            f"({'refetch failed' if refetch_explicit_failed else 'vnstock chưa cập nhật'})"
        )

    df = df.copy()
    df['Exchange'] = exchange
    df['Ticker'] = ticker
    df['StaleCache'] = is_stale
    return df.reset_index(drop=True)


def fetch_universe(tickers_df: pd.DataFrame, lookback_days: int = 180,
                   max_workers: int = 1, delay: float = 2.0) -> pd.DataFrame:
    """
    Fetch OHLCV for entire universe. Single-threaded with delay
    to respect vnstock 4.x free-tier rate limit (60 req/min Community).
    Each ticker fetch may use 2 internal API calls (metadata + history),
    so we use 2.0s delay = 30 req/min = 60 internal calls/min, safe under 60/min.

    Args:
        max_workers: 1 = sequential (safer for rate limit)
        delay: seconds between requests
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_frames = []
    success = 0
    fail = 0

    def _worker(row):
        time.sleep(delay)
        return fetch_with_cache(row['ticker'], row['exchange'], lookback_days)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_worker, r): r['ticker']
                   for _, r in tickers_df.iterrows()}
        done = 0
        for fut in as_completed(futures):
            tk = futures[fut]
            done += 1
            try:
                df = fut.result()
                if df is not None and len(df) > 60:
                    all_frames.append(df)
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
                log.warning(f"  {tk}: {e}")
            if done % 25 == 0:
                log.info(f"  Fetched {done}/{len(futures)} tickers (ok={success}, fail={fail})")

    log.info(f"  Total: {success} succeeded, {fail} failed")
    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


def fetch_vnindex(lookback_days: int = 180) -> Optional[pd.DataFrame]:
    """VN-Index for relative strength calculation."""
    setup_api_key()
    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)
    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol='VNINDEX', source='vci')
        idx = q.history(start=str(start), end=str(end), interval='1D')
        idx = idx.rename(columns={'time': 'Date', 'close': 'Close'})
        idx['Date'] = pd.to_datetime(idx['Date'])
        return idx[['Date', 'Close']]
    except Exception as e:
        log.error(f"VN-Index fetch failed: {e}")
        return None
