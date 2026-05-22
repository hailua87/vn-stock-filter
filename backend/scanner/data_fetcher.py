"""
Data fetcher for Vietnam stock market.

Primary source: vnstock (https://github.com/thinh-vu/vnstock)
  └─ Underneath it wraps VCI / TCBS / SSI / MSN public APIs.
Fallback: TCBS direct REST.

Cache: parquet files per ticker in `backend/data/cache/`.
Daily increment: only fetch missing dates.
"""
from __future__ import annotations
import os
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
# Universe — list of tickers on each exchange
# ─────────────────────────────────────────────────────────────────────────
def get_ticker_universe(exchanges: tuple = ('HOSE', 'HNX', 'UPCOM')) -> pd.DataFrame:
    """
    Return a DataFrame with columns: ticker, exchange, sector (optional).
    Uses vnstock.listing to pull the live universe.
    """
    try:
        from vnstock import Listing
        listing = Listing()
        df = listing.all_symbols()  # ticker, organ_name, ...
        # vnstock returns 'exchange' or we can use specific endpoints:
        out = []
        for ex in exchanges:
            sub = listing.symbols_by_exchange(ex.lower())
            sub['exchange'] = ex
            out.append(sub[['symbol', 'exchange']].rename(columns={'symbol': 'ticker'}))
        result = pd.concat(out, ignore_index=True).drop_duplicates('ticker')
        return result
    except Exception as e:
        log.warning(f"vnstock listing failed ({e}), falling back to cached universe")
        return _load_fallback_universe(exchanges)


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
# Historical OHLCV fetcher
# ─────────────────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker: str, start: str, end: str,
                source: str = 'VCI', retries: int = 2,
                adjusted: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV for a single ticker.

    Args:
        adjusted: if True, prices are back-adjusted for splits/stock dividends.
            vnstock's VCI source returns adjusted prices by default.
            TCBS has a separate `adjusted=True` flag.
            We always request adjusted to keep technical indicators consistent
            across corporate actions.

    Returns DataFrame: Date, Open, High, Low, Close, Volume
    """
    try:
        from vnstock import Vnstock
    except ImportError:
        log.error("vnstock not installed. Run: pip install vnstock")
        return None

    for attempt in range(retries + 1):
        try:
            stock = Vnstock().stock(symbol=ticker, source=source)
            # vnstock v3+: history() accepts `interval` and returns adjusted
            # prices by default for VCI. For TCBS we may need to pass adjusted.
            try:
                df = stock.quote.history(start=start, end=end, interval='1D',
                                         adjusted=adjusted)
            except TypeError:
                # Older vnstock version — no adjusted kwarg
                df = stock.quote.history(start=start, end=end, interval='1D')

            if df is None or df.empty:
                return None
            df = df.rename(columns={
                'time': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })
            df['Date'] = pd.to_datetime(df['Date'])
            df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].sort_values('Date')
            return df.reset_index(drop=True)
        except Exception as e:
            log.warning(f"  {ticker} attempt {attempt+1}: {e}")
            time.sleep(1 + attempt)
    return None


def fetch_with_cache(ticker: str, exchange: str, lookback_days: int = 180,
                     force_refresh: bool = False, adjusted: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV using local parquet cache. Only pulls incremental data
    since last cached date.

    Note: cache key includes adjusted flag — switching from raw → adjusted
    will trigger a full refresh (otherwise old unadjusted prices would mix
    with new adjusted ones).
    """
    suffix = '_adj' if adjusted else '_raw'
    cache_file = CACHE_DIR / f'{ticker}{suffix}.parquet'
    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)

    if cache_file.exists() and not force_refresh:
        cached = pd.read_parquet(cache_file)
        cached['Date'] = pd.to_datetime(cached['Date'])
        last_date = cached['Date'].max().date()
        if last_date >= end - timedelta(days=1):
            df = cached[cached['Date'] >= pd.Timestamp(start)]
        else:
            # Incremental fetch. For adjusted prices we need to be careful:
            # if a corporate action occurred between last_date and today,
            # historical prices may have been re-adjusted by the data source.
            # → refresh last 30 days to catch any retroactive adjustments.
            refetch_start = (last_date - timedelta(days=30))
            new = fetch_ohlcv(ticker, str(refetch_start), str(end), adjusted=adjusted)
            if new is not None and not new.empty:
                # Overwrite overlap range with fresh data
                cached_old = cached[cached['Date'] < pd.Timestamp(refetch_start)]
                df = pd.concat([cached_old, new]).drop_duplicates('Date').sort_values('Date')
                df.to_parquet(cache_file, index=False)
            else:
                df = cached
        df['Exchange'] = exchange
        df['Ticker'] = ticker
        return df.reset_index(drop=True)
    else:
        df = fetch_ohlcv(ticker, str(start), str(end), adjusted=adjusted)
        if df is None or df.empty:
            return None
        df.to_parquet(cache_file, index=False)
        df['Exchange'] = exchange
        df['Ticker'] = ticker
        return df


def fetch_universe(tickers_df: pd.DataFrame, lookback_days: int = 180,
                   max_workers: int = 4, delay: float = 0.2) -> pd.DataFrame:
    """
    Fetch OHLCV for entire universe. Uses threading + delay to respect
    VCI/TCBS rate limits (typically 5-10 req/sec).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_frames = []

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
            except Exception as e:
                log.warning(f"  {tk}: {e}")
            if done % 50 == 0:
                log.info(f"  Fetched {done}/{len(futures)} tickers")

    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


def fetch_vnindex(lookback_days: int = 180) -> Optional[pd.DataFrame]:
    """VN-Index for relative strength calculation."""
    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)
    try:
        from vnstock import Vnstock
        idx = Vnstock().stock(symbol='VNINDEX', source='VCI').quote.history(
            start=str(start), end=str(end), interval='1D')
        idx = idx.rename(columns={'time': 'Date', 'close': 'Close'})
        idx['Date'] = pd.to_datetime(idx['Date'])
        return idx[['Date', 'Close']]
    except Exception as e:
        log.error(f"VN-Index fetch failed: {e}")
        return None
