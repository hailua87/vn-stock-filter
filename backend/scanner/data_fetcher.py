"""
Data fetcher for Vietnam stock market — gọi thẳng API Vietcap (VCI) / KBS.

Nguồn (từ 26/09/2026): `scanner/sources/` thay vnstock. PyPI cách ly
vnstock + vnai từ 24–25/09/2026 nên không cài được nữa; lý do và bảng việc
tương ứng nằm ở docstring `scanner/sources/__init__.py`. Đầu ra giữ đúng
hình dạng vnstock 4.0.7 trả về nên phần phía sau không đổi.

Giá: VCI trả giá đã điều chỉnh cổ tức/chia tách (backward-adjusted), theo
NGHÌN đồng. Giá sẽ khác cafef/app môi giới ở mã vừa chia cổ tức tiền; đó là
chủ ý, cho phân tích kỹ thuật không có gap giả.

Giới hạn tần suất: `sources.http` giữ khoảng cách tối thiểu giữa hai lượt gọi
(mặc định 1 s, env SOURCE_MIN_INTERVAL) — đúng mức 60 lượt/phút vnstock từng
áp. Nguồn trả HTTP 429 thì ném RateLimitError; vòng thử lại ở đây chờ 65 s.

Cache: parquet files per ticker in `backend/data/cache/` with suffix
'_adj.parquet' (adjusted prices). Daily increment: only fetch missing dates.
"""
from __future__ import annotations
import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
import logging

import pandas as pd

from .trading_calendar import last_expected_session, now_ict

from .price_units import quote_to_vnd
from .sources import vci as _vci
from .sources.http import RateLimitError  # financial_fetcher import lại từ đây

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Nơi fetch_universe ghi tiến độ khi vòng lặp dừng sớm. Nằm trong CACHE_DIR để đi
# cùng cache OHLCV mà workflow đã save/restore sẵn.
CHECKPOINT_PATH = CACHE_DIR / 'fetch_checkpoint.json'


class _Skipped:
    """Mã chưa được thử vì van đã đóng — khác hẳn mã đã thử và hỏng."""
    __slots__ = ()

    def __repr__(self):
        return '<skipped>'


_SKIPPED = _Skipped()


# ─────────────────────────────────────────────────────────────────────────
# Tương thích ngược với thời vnstock
# ─────────────────────────────────────────────────────────────────────────
# RateLimitError nay đến từ sources.http (HTTP 429). Thời vnstock, nó được sinh
# ra bằng cách vá sys.exit vì vnai gọi sys.exit() khi quá hạn mức — bản vá đó
# đã bỏ cùng vnstock.


def setup_api_key(api_key: Optional[str] = None) -> bool:
    """Không còn tác dụng: API Vietcap/KBS không cần khóa. Giữ để code gọi cũ
    (run_valuation, run_quality, backfill_history) không phải đổi."""
    return False


# ─────────────────────────────────────────────────────────────────────────
# Universe — list of tickers on each exchange
# ─────────────────────────────────────────────────────────────────────────
def get_ticker_universe(exchanges: tuple = ('HOSE', 'HNX', 'UPCOM'),
                        limit: Optional[int] = None,
                        use_liquidity_sort: bool = True) -> pd.DataFrame:
    """
    Return a DataFrame with columns: ticker, exchange.
    Danh sách lấy từ KBS (xem _fetch_full_universe).

    Args:
        exchanges: which exchanges to include
        limit: max tickers to return (for free-tier rate limit). If None, all.
        use_liquidity_sort: if True and limit is set, sort by liquidity (cached
            average turnover) before applying limit. Falls back to curated
            top-liquid list if no cache exists.
    """
    # Always load full universe first
    full_universe = _fetch_full_universe(exchanges)

    if limit is None or not use_liquidity_sort:
        if limit:
            return full_universe.head(limit).reset_index(drop=True)
        return full_universe

    # Sort by cached liquidity score (highest first)
    return _sort_by_liquidity(full_universe, limit)


def _fetch_full_universe(exchanges: tuple) -> pd.DataFrame:
    """Danh sách cổ phiếu theo sàn từ KBS; lỗi thì về danh sách curated.

    Khác thời vnstock (26/09/2026). Theo mã nguồn vnstock (chưa đo trên log):
    `Listing().all_symbols()` nguồn KBS không có cột sàn, nên code cũ rơi
    vào nhánh `symbols_by_exchange(ex)` — hàm này không nhận tham số sàn (ex
    rơi vào `get_all`) và trả TOÀN BỘ mã. Hệ quả: mọi mã bị gắn sàn của vòng
    lặp đầu tiên (HOSE), chỉ mã có trong top_liquid được sửa lại sàn, và
    chứng chỉ quỹ 3–5 ký tự cũng lọt vào. Nay đọc sàn và loại chứng khoán
    thẳng từ KBS, chỉ giữ `type == 'stock'`.
    """
    try:
        from .sources import kbs
        from .sources.http import with_retry
        all_df = with_retry(kbs.listing)
        if all_df.empty:
            raise ValueError('KBS listing rỗng')
        all_df = all_df[all_df['type'] == 'stock'].rename(columns={'symbol': 'ticker'})
        result = all_df[all_df['exchange'].isin(exchanges)][['ticker', 'exchange']].copy()
        if result.empty:
            # Nguồn đổi mã sàn/loại (vd. 'HSX', 'STOCK_CP') thì lọc ra rỗng mà
            # không có lỗi nào — phải rơi về danh sách curated, không chạy 0 mã.
            raise ValueError(f"KBS listing không còn cổ phiếu nào ở {exchanges} sau khi lọc "
                             f"(loại: {sorted(set(all_df['type']))[:5]})")

        # Override exchange using top_liquid.py (source of truth for curated list).
        # Nguồn danh sách đôi khi có mã trùng với sàn khác nhau (vd. DVN có cả
        # bản ghi HOSE và UPCOM lịch sử).
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
        log.warning(f"KBS listing failed ({e}), falling back to curated list")
        return _load_fallback_universe(exchanges)


# Cửa sổ đo thanh khoán và hạn dùng của số đo.
#
# Vì sao cần hạn dùng: tệp cache của một mã ĐÃ NGỪNG GIAO DỊCH vẫn còn nguyên
# các phiên cũ. `tail(20)` không hỏi 20 dòng đó từ bao giờ, nên ART/TTB/SJF —
# phiên cuối 2024-07-25, cũ 14 tháng — vẫn được coi là có số đo. Quá hạn thì
# coi như KHÔNG CÓ số đo, chứ không phải có số đo bằng 0.
LIQUIDITY_WINDOW = 20
LIQUIDITY_MAX_AGE_DAYS = 30


def measure_liquidity(df: pd.DataFrame, today: Optional[date] = None,
                      window: int = LIQUIDITY_WINDOW,
                      max_age_days: int = LIQUIDITY_MAX_AGE_DAYS) -> Optional[float]:
    """
    GTGD trung bình `window` phiên gần nhất, tính bằng ĐỒNG. None nếu số liệu
    quá cũ hoặc không đủ để nói gì.

    Đổi đơn vị qua `price_units.quote_to_vnd`: vnstock báo giá theo NGHÌN đồng.
    Bản cũ nhân thẳng Close × Volume rồi gọi kết quả là "VND" — sai 1000 lần, và
    chính chỗ đó làm hỏng xếp hạng (xem `_sort_by_liquidity`).
    """
    if df is None or df.empty or 'Close' not in df or 'Volume' not in df:
        return None
    today = today or date.today()
    if 'Date' in df:
        cutoff = pd.Timestamp(today) - pd.Timedelta(days=max_age_days)
        df = df[pd.to_datetime(df['Date'], errors='coerce') >= cutoff]
    if df.empty:
        return None
    recent = df.tail(window)
    vals = [quote_to_vnd(float(c)) * float(v)
            for c, v in zip(recent['Close'], recent['Volume'])
            if pd.notna(c) and pd.notna(v)]
    if not vals:
        return None
    avg = sum(vals) / len(vals)
    return avg if avg > 0 else None


def _cached_liquidity(today: Optional[date] = None) -> dict:
    """{ticker: GTGD trung bình, ĐỒNG} từ các tệp parquet đã cache."""
    out, seen = {}, set()
    # Glob cả *_adj.parquet (mặc định mới) và *_raw.parquet (fallback cũ).
    for pattern, strip in (('*_adj.parquet', '_adj'), ('*_raw.parquet', '_raw')):
        for cache_file in CACHE_DIR.glob(pattern):
            ticker = cache_file.stem.replace(strip, '')
            if ticker in seen:
                continue
            seen.add(ticker)
            try:
                v = measure_liquidity(pd.read_parquet(cache_file), today)
            except Exception:
                continue
            if v is not None:
                out[ticker] = v
    return out


def _sort_by_liquidity(universe: pd.DataFrame, limit: int,
                       today: Optional[date] = None) -> pd.DataFrame:
    """
    Xếp universe theo thanh khoản và lấy top N.

    HAI BẬC, không trộn vào một thang điểm:

      bậc 1 — mã CÓ số đo thật trong 30 ngày qua, xếp theo GTGD giảm dần;
      bậc 2 — mã không có số đo, xếp theo thứ tự danh sách curated.

    Vì sao tách bậc: bản cũ cho mã curated điểm `(623 − hạng) × 1e9`, tức từ
    1 tỷ tới 623 tỷ, rồi so thẳng với thanh khoản đo được — mà thanh khoản đo
    được cao nhất (FPT) chỉ là 4,3e8 vì quên đổi nghìn đồng sang đồng. Kết quả
    là MỌI mã curated đều đứng trên MỌI mã đo được, và số đo thật chưa bao giờ
    thực sự được dùng. Đó là lý do ART (ngừng giao dịch từ 07/2024) vẫn lọt vào
    rổ 200 mã của Module B.

    Hai đại lượng này không cùng đơn vị và không bao giờ so sánh được với nhau;
    ép chung một thang là cách tự lừa mình. Danh sách curated chỉ còn đúng vai
    trò của nó: đoán tạm khi CHƯA có số đo.
    """
    from .top_liquid import get_top_liquid_tickers

    liquidity = _cached_liquidity(today)
    curated_rank = {tk: i for i, (tk, _) in enumerate(get_top_liquid_tickers())}
    log.info(f"  Thanh khoản đo được (≤{LIQUIDITY_MAX_AGE_DAYS} ngày): "
             f"{len(liquidity)} mã")

    universe = universe.copy()
    universe['_measured'] = universe['ticker'].isin(liquidity)
    universe['_liq'] = universe['ticker'].map(liquidity).fillna(0.0)
    # Chưa có số đo: xếp theo thứ tự curated; ngoài danh sách thì xuống cuối.
    universe['_curated'] = universe['ticker'].map(curated_rank).fillna(10 ** 9)
    universe = universe.sort_values(
        ['_measured', '_liq', '_curated'], ascending=[False, False, True])

    top_n = universe.head(limit)[['ticker', 'exchange']].reset_index(drop=True)
    n_measured = int(universe.head(limit)['_measured'].sum())
    log.info(f"  Chọn {len(top_n)} mã (limit={limit}): {n_measured} theo số đo thật, "
             f"{len(top_n) - n_measured} theo danh sách curated")
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
# Historical OHLCV fetcher — Vietcap (VCI)
# ─────────────────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker: str, start: str, end: str,
                source: str = 'vci', retries: int = 2,
                adjusted: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV for a single ticker from Vietcap (VCI).

    VCI trả về backward-adjusted prices (đã trừ cổ tức/cổ phiếu thưởng quá
    khứ). Giá hiển thị sẽ KHÁC cafef cho mã có cổ tức gần đây — ví dụ VND
    có cổ tức 500đ chia 15/07/2025 nên giá VCI sẽ thấp hơn cafef ~0.5.
    Đây là TRADE-OFF có chủ ý: adjusted price cho phân tích kỹ thuật chính
    xác hơn (RSI/Ichimoku/Fibonacci không bị gap giả), tuy giá tuyệt đối
    khác broker app. UI nên có note "✓ Giá điều chỉnh" để user hiểu.

    `source` chỉ nhận 'vci' (giữ tham số cho code gọi cũ). `adjusted` chỉ
    ảnh hưởng suffix cache file (_adj vs _raw), không ảnh hưởng VCI vì VCI
    luôn trả adjusted.

    Returns DataFrame: Date, Open, High, Low, Close, Volume — hoặc None nếu
    nguồn không có dữ liệu hay vẫn hỏng sau `retries` lần thử lại.
    """
    if str(source).lower() != 'vci':
        # Lỗi cấu hình, không phải lỗi tạm thời: dừng ngay thay vì thử lại
        # 500 mã × 3 lần (bài học 26/05/2026 với source='TCBS').
        raise RuntimeError(f"fetch_ohlcv chỉ hỗ trợ source='vci', nhận '{source}'")

    for attempt in range(retries + 1):
        try:
            df = _vci.ohlcv(ticker, start, end)
            if df is None or df.empty:
                return None

            df = df.rename(columns={
                'time': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })
            required = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            df['Date'] = pd.to_datetime(df['Date'])
            df = df[required].sort_values('Date')
            return df.reset_index(drop=True)
        except RateLimitError:
            log.warning(f"  {ticker} rate-limited (HTTP 429), waiting 65s...")
            time.sleep(65)
        except ValueError as e:
            # Ngày/tham số sai là lỗi của code gọi — thử lại cũng vậy.
            log.error(f"  {ticker}: {e}")
            return None
        except Exception as e:
            log.warning(f"  {ticker} attempt {attempt+1}: {type(e).__name__}: {str(e)[:150]}")
            time.sleep(2 + attempt * 2)
    return None


def _last_trading_session(today: 'date') -> 'date':
    """
    Phiên giao dịch gần nhất tính đến `today` (chưa tính giờ trong ngày).

    FIX: bản cũ chỉ trừ T7/CN. Trong kỳ nghỉ Tết (5-7 phiên), 30/4 hay 2/9,
    "phiên gần nhất" rơi vào ngày thường không có giao dịch → mọi mã bị gắn
    StaleCache → Golden Cross và Ichimoku trả 0 tín hiệu suốt kỳ nghỉ, còn
    workflow vẫn commit file rỗng đè lên dữ liệu tốt.

    Nay dùng bảng nghỉ lễ HOSE (scanner/trading_calendar.py). Caller vẫn có
    trách nhiệm hiểu phiên T có thể CHƯA đóng cửa (intraday).
    """
    from .trading_calendar import last_trading_session
    return last_trading_session(today)


# ── Điều tiết lượt gọi mạng ────────────────────────────────────────────────
# Trước 2026-09-23, fetch_universe NGỦ `delay` giây trước MỌI mã, kể cả mã lấy
# thẳng từ cache không gọi mạng: 500 mã × 2 s ≈ 16,7 phút của ngân sách 45 phút
# chỉ để ngủ. Ngày nguồn chậm (mỗi lần gọi ~3 s) thì mỗi mã tốn 2 + 3 = 5 s.
# Nay `delay` là KHOẢNG CÁCH TỐI THIỂU giữa hai lần gọi mạng thật: vẫn giữ trần
# rate limit, nhưng mã từ cache tốn ~0 s và mã chậm tốn max(delay, thời gian gọi).
_net_lock = threading.Lock()
_net_last_call = 0.0
_net_min_interval = 0.0


def _net_throttle() -> None:
    """Chờ tới khi cách lần gọi mạng trước ít nhất `_net_min_interval` giây."""
    global _net_last_call
    with _net_lock:
        wait = _net_last_call + _net_min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _net_last_call = time.monotonic()


def fetch_with_cache(ticker: str, exchange: str, lookback_days: int = 180,
                     force_refresh: bool = False, adjusted: bool = True,
                     last_session: Optional['date'] = None) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV using local parquet cache. Only pulls incremental data
    since last cached date.

    FIX (2026-05-26): adjusted=True mặc định (đi đôi với source='vci' trong
    fetch_ohlcv). Cache file dùng suffix '_adj.parquet'. Cache cũ '_raw.parquet'
    (do TCBS-fail-fallback ghi) là dữ liệu rác — workflow cần purge trước
    lần chạy đầu sau fix (đã bump cache key v1 → v2 trong daily-scan.yml).

    FIX: kiểm tra cache có chứa đúng phiên giao dịch gần nhất theo lịch không.
    Trước đây: last_date >= end - 1 day (sai trên thứ Hai + sau nghỉ lễ).
    Bây giờ: last_date >= last_expected_session(now_ict()) — xét cả giờ.

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
    # Đồng hồ ICT, không phải đồng hồ runner. `datetime.now()` trần ở đây chạy
    # giờ UTC trên GitHub Actions: ca EOD 23:05 ICT là 16:05 UTC, quét quá 8
    # tiếng thì `end` lùi mất một ngày so với ngày phiên thật.
    now = now_ict()
    end = now.date()
    start = end - timedelta(days=lookback_days)
    # `last_expected_session` chứ không phải `last_trading_session`: mốc so phải
    # xét GIỜ. Trước 09:15 thì phiên T chưa có nến nào, khai nó ra là đóng dấu
    # STALE oan cho cả rổ — đúng chuyện đã xảy ra lúc 08:17 ICT ngày 28/08/2026.
    #
    # Caller truyền `last_session` vào để CẢ RỔ dùng chung một mốc: vòng fetch
    # 500 mã chạy ~26 phút, tự tính trong từng mã thì rổ nào vắt qua 09:15 sẽ có
    # mã so với phiên hôm qua, mã so với phiên hôm nay. `fetch_universe` chốt
    # một lần rồi đóng dấu vào fetch_summary để cổng stale báo đúng con số đã
    # dùng. Gọi lẻ (không qua fetch_universe) thì vẫn tự tính như cũ.
    if last_session is None:
        last_session = last_expected_session(now)

    df: Optional[pd.DataFrame] = None
    refetch_explicit_failed = False  # True nếu refetch trả None/empty

    if cache_file.exists() and not force_refresh:
        try:
            cached = pd.read_parquet(cache_file)
            cached['Date'] = pd.to_datetime(cached['Date'])
            last_date = cached['Date'].max().date()
            today = end  # alias để code rõ ràng hơn

            # FIX (2026-05-27): Force refresh nếu last_date == today.
            #
            # Lý do: vnstock VCI có data freshness lag ~6-8h sau giờ đóng cửa HOSE.
            # Trong khoảng 14:45-22:00 ICT, vnstock trả giá tạm (matched price giữa
            # phiên), không phải giá ATC chính thức. Nếu workflow chạy trong khoảng
            # này → cache ghi giá tạm → lần sau dùng cache (vì last_date >= last_session
            # vẫn pass) → data sai vĩnh viễn cho phiên đó.
            #
            # Fix: chỉ dùng cache nếu last_date là PHIÊN ĐÃ QUA HẲN (không phải hôm
            # nay). Nếu last_date == today → luôn refetch để pickup data mới nếu
            # vnstock vừa update.
            #
            # Hệ quả: mỗi run workflow sẽ refetch phiên hôm nay (chậm thêm ~2-3 phút
            # cho 500 mã). Đổi lại data luôn fresh nhất có thể.
            #
            # ĐO LẠI (2026-09-22): nhận định "giá tạm tới 22:00" ở trên KHÔNG còn
            # đúng với giá đóng cửa. So archive ghi lúc ~17:00 ICT với dữ liệu
            # vnstock lấy lại sau khi phiên đã chốt lâu:
            #   16/09 (ghi 17:16): Close trùng 41/45 mã, Volume thiếu ở 9/45 mã
            #                      (trung vị 0,12%, tối đa 2,08%)
            #   18/09 (ghi 16:59): Close trùng 57/60 mã, Volume thiếu ở 7/60 mã
            #                      (trung vị 0,08%, tối đa 0,36%)
            # Các mã còn lại lệch Close theo một TỶ LỆ CỐ ĐỊNH qua mọi phiên (FPT
            # đúng 1,1000 = cổ tức cổ phiếu 10%): đó là vnstock điều chỉnh hồi tố
            # chuỗi giá adjusted sau sự kiện quyền, không phải giá tạm.
            # Tức là sau ~17:00 ICT giá đã chốt; chỉ Volume còn có thể nhích nhẹ
            # (thỏa thuận cộng muộn). Quy tắc refetch-khi-last_date==today vẫn giữ
            # vì rẻ và còn bắt được phần Volume đó, và run chạy sau nửa đêm (dùng
            # cache của run ~17:00) vì vậy KHÔNG mang giá sai. Mới đo 2 phiên —
            # đo thêm trước khi dựa vào kết luận này để đổi giờ chạy.
            cache_fresh = (last_date >= last_session) and (last_date < today)

            if cache_fresh:
                # Cache chứa phiên ĐÃ QUA HẲN — dùng luôn, không refetch
                df = cached[cached['Date'] >= pd.Timestamp(start)].copy()
            else:
                # 2 trường hợp:
                #   a) last_date < last_session → cache cũ thực sự
                #   b) last_date == today → có thể vnstock đã update, refetch để chắc
                # Refetch incremental (refresh 30 ngày cuối phòng late corp actions)
                refetch_start = (last_date - timedelta(days=30))
                _net_throttle()
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
        _net_throttle()
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
            f"({'refetch failed' if refetch_explicit_failed else 'nguồn chưa cập nhật'})"
        )

    df = df.copy()
    df['Exchange'] = exchange
    df['Ticker'] = ticker
    df['StaleCache'] = is_stale
    return df.reset_index(drop=True)


def fetch_universe(tickers_df: pd.DataFrame, lookback_days: int = 180,
                   max_workers: int = 1, delay: float = 2.0,
                   time_budget_s: Optional[float] = None,
                   max_consecutive_failures: int = 20,
                   checkpoint_path: Optional[Path] = None,
                   checkpoint_every: int = 25,
                   clock=None) -> pd.DataFrame:
    """
    Fetch OHLCV for entire universe. Single-threaded with delay
    to respect the source rate limit (~60 req/min).
    Each ticker fetch may use 2 internal API calls (metadata + history),
    so we use 2.0s delay = 30 req/min = 60 internal calls/min, safe under 60/min.

    FIX (2026-08-27): NGÂN SÁCH THỜI GIAN + CẦU DAO.

    Triệu chứng: 17-20/08/2026 cả 8 ca daily-scan đều chết vì
    `##[error]The action 'Run daily scan' has timed out after 60 minutes.`
    Không có traceback — nó không crash, nó HẾT GIỜ.

    Cơ chế: vnstock VCI trả lỗi lai rai (`RetryError[<Future ... raised
    UnboundLocalError>]`, hoặc read-timeout 30s tới trading.vietcap.com.vn).
    `fetch_ohlcv` thử lại 3 lần cho mọi lỗi không phải rate-limit, ngủ 2/4/6s
    giữa các lần. Đo trên log thật: ~26s mỗi mã khi upstream hỏng kiểu này, có
    lúc 90s+. Với 500 mã, 60 phút chỉ đủ tới mã thứ ~140 rồi runner giết cả job
    — và vì bị giết TRƯỚC bước ghi file, 140 mã đã lấy về cũng mất trắng.

    Nghịch lý cần chặn: upstream hỏng NHẸ thì tốn giờ nhất. Hỏng dứt khoát
    (ValueError sai source) đã có đường fail-fast từ trước; hỏng lai rai thì
    không, nên nó cứ bò cho tới lúc bị giết.

    Hai cái van, và chúng chặn hai thứ khác nhau:

      time_budget_s  — trần cứng cho TOÀN BỘ vòng lặp. Đặt dưới
                       `timeout-minutes` của workflow (45 < 60) để mình tự dừng
                       trong tay mình, còn kịp trả dữ liệu và ghi checkpoint.
                       Chặn cả trường hợp upstream chỉ chậm chứ không lỗi.
      max_consecutive_failures — cầu dao. Khi upstream sập hẳn thì mã nào cũng
                       hỏng; ngồi đợi hết 45 phút để xác nhận điều đã rõ sau 20
                       mã là phí. Đếm LIÊN TIẾP chứ không đếm tổng: một rổ 500 mã
                       luôn có sẵn dăm mã chết (huỷ niêm yết, mã mới), đếm tổng
                       sẽ nhả cầu dao oan.

    Dừng vì bất kỳ van nào cũng KHÔNG phải lỗi: hàm trả về phần đã lấy được và
    ghi lý do vào `df.attrs['fetch_summary']`. Caller quyết định phần dữ liệu đó
    có đủ dùng không — xem run_daily.

    Args:
        max_workers: 1 = sequential (safer for rate limit)
        delay: seconds between requests
        time_budget_s: trần thời gian, giây. None = không giới hạn (hành vi cũ).
        max_consecutive_failures: số mã hỏng liên tiếp thì nhả cầu dao.
                                  <= 0 để tắt cầu dao.
        checkpoint_path: file JSON ghi tiến độ. None = không ghi.
        checkpoint_every: ghi checkpoint sau mỗi ngần này mã.
        clock: hàm trả về giây đơn điệu tăng — chỉ để test tiêm đồng hồ giả.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    now = clock or time.monotonic
    started_at = now()
    # Mốc phiên được chốt MỘT lần cho cả vòng, KHÔNG tính lại theo từng mã.
    #
    # Vòng fetch 500 mã kéo ~26 phút. Tính lẻ trong mỗi mã thì một vòng vắt qua
    # 09:15 sẽ có mã đầu rổ so với phiên T-1 và mã cuối rổ so với phiên T —
    # `StaleCache` mang hai nghĩa khác nhau trong cùng một frame, và không còn
    # một con số nào để đóng dấu vào fetch_summary cho cổng stale đọc.
    session_expected = last_expected_session(now_ict())
    started_wall = datetime.now().isoformat(timespec='seconds')
    deadline = (started_at + time_budget_s) if time_budget_s else None

    total = len(tickers_df)
    all_frames = []
    ok_tickers: list[str] = []
    failed_tickers: list[str] = []
    skipped_tickers: list[str] = []
    consecutive_failures = 0
    stop_reason: Optional[str] = None
    stop_event = threading.Event()

    def _summary(done: int) -> dict:
        return {
            'started_at': started_wall,
            'elapsed_s': round(now() - started_at, 1),
            'total': total,
            'done': done,
            'ok': len(ok_tickers),
            'failed': len(failed_tickers),
            'skipped': len(skipped_tickers),
            'coverage': round(len(ok_tickers) / total, 4) if total else 0.0,
            # Mốc StaleCache mà vòng fetch này THỰC SỰ đã dùng. Cổng stale trong
            # run_daily đọc từ đây thay vì tự tính lại — hai phép tính rời nhau
            # thì sửa một chỗ quên chỗ kia, thông báo lỗi sẽ báo sai mốc.
            'last_session': session_expected.isoformat(),
            'stop_reason': stop_reason,
            'truncated': stop_reason is not None,
            'time_budget_s': time_budget_s,
            'max_consecutive_failures': max_consecutive_failures,
            'ok_tickers': list(ok_tickers),
            'failed_tickers': list(failed_tickers),
            'skipped_tickers': list(skipped_tickers),
        }

    def _write_checkpoint(done: int) -> None:
        """
        Ghi tiến độ ra đĩa. Đây là phần "thay vì mất trắng": dữ liệu OHLCV thật
        đã nằm trong parquet cache theo từng mã, còn file này ghi lại mã nào đã
        xong để lần chạy sau — và người đọc log — biết vòng lặp dừng ở đâu và
        vì sao.

        Nuốt mọi lỗi ghi: checkpoint hỏng không được phép giết một vòng fetch
        đang chạy tốt.
        """
        if checkpoint_path is None:
            return
        try:
            p = Path(checkpoint_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(_summary(done), f, ensure_ascii=False, indent=2)
        except Exception as e:                       # noqa: BLE001
            log.warning(f"  checkpoint write failed: {e}")

    def _worker(row):
        # Kiểm ngay tại cửa: mọi future đã được submit từ đầu, nên khi van đã
        # đóng thì phần còn lại phải trả về tức thì thay vì nối thêm một lượt
        # fetch 26-90 giây nữa.
        if stop_event.is_set():
            return _SKIPPED
        if deadline is not None and now() >= deadline:
            return _SKIPPED
        # `delay` không còn ngủ ở đây — xem _net_throttle
        return fetch_with_cache(row['ticker'], row['exchange'], lookback_days,
                                last_session=session_expected)

    # `delay` giờ là khoảng cách tối thiểu giữa hai lượt gọi mạng thật (xem
    # _net_throttle), đặt cho suốt vòng này rồi trả lại giá trị cũ ở cuối hàm.
    global _net_min_interval
    prev_interval, _net_min_interval = _net_min_interval, (delay or 0.0)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_worker, r): r['ticker']
                   for _, r in tickers_df.iterrows()}
        done = 0
        for fut in as_completed(futures):
            tk = futures[fut]
            done += 1
            try:
                df = fut.result()
                if df is _SKIPPED:
                    skipped_tickers.append(tk)
                    continue
                if df is not None and len(df) > 60:
                    all_frames.append(df)
                    ok_tickers.append(tk)
                    consecutive_failures = 0
                else:
                    failed_tickers.append(tk)
                    consecutive_failures += 1
            except Exception as e:
                failed_tickers.append(tk)
                consecutive_failures += 1
                log.warning(f"  {tk}: {e}")

            if stop_reason is None:
                # Cầu dao trước: khi upstream sập hẳn, nhả sớm còn giữ được thời
                # gian cho các bước sau của workflow.
                if (max_consecutive_failures > 0
                        and consecutive_failures >= max_consecutive_failures):
                    stop_reason = 'circuit_breaker'
                    stop_event.set()
                    log.error(
                        f"  CẦU DAO: {consecutive_failures} mã hỏng liên tiếp "
                        f"(ngưỡng {max_consecutive_failures}) — dừng ở {done}/{total}. "
                        f"Upstream hỏng, không phải mã lẻ."
                    )
                elif deadline is not None and now() >= deadline:
                    stop_reason = 'time_budget'
                    stop_event.set()
                    log.error(
                        f"  HẾT NGÂN SÁCH: {round(now() - started_at)}s "
                        f"(trần {time_budget_s}s) — dừng ở {done}/{total}, "
                        f"giữ lại {len(ok_tickers)} mã đã lấy xong."
                    )
                if stop_reason is not None:
                    _write_checkpoint(done)

            if done % checkpoint_every == 0:
                log.info(f"  Fetched {done}/{total} tickers "
                         f"(ok={len(ok_tickers)}, fail={len(failed_tickers)})")
                _write_checkpoint(done)

    summary = _summary(done)
    _write_checkpoint(done)

    log.info(f"  Total: {summary['ok']} succeeded, {summary['failed']} failed, "
             f"{summary['skipped']} skipped in {summary['elapsed_s']}s")
    if stop_reason:
        log.error(f"  VÒNG FETCH DỪNG SỚM ({stop_reason}) — "
                  f"độ phủ {summary['coverage']:.1%} ({summary['ok']}/{total}).")

    if not all_frames:
        out = pd.DataFrame()
    else:
        out = pd.concat(all_frames, ignore_index=True)
    # attrs sống sót qua concat khi gán sau; caller đọc để biết có bị cắt không.
    out.attrs['fetch_summary'] = summary
    _net_min_interval = prev_interval
    return out


def fetch_vnindex(lookback_days: int = 180) -> Optional[pd.DataFrame]:
    """VN-Index for relative strength calculation."""
    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)
    try:
        from .sources.http import with_retry
        idx = with_retry(_vci.ohlcv, 'VNINDEX', str(start), str(end))
        if idx.empty:
            log.error("VN-Index fetch failed: nguồn trả rỗng")
            return None
        idx = idx.rename(columns={'time': 'Date', 'close': 'Close'})
        idx['Date'] = pd.to_datetime(idx['Date'])
        return idx[['Date', 'Close']]
    except Exception as e:
        log.error(f"VN-Index fetch failed: {e}")
        return None
