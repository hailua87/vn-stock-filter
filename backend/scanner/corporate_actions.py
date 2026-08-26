"""
Corporate actions handler — splits, cash dividends, stock dividends, rights issues.

Why this matters:
  When a stock pays a 10% stock dividend on day T, raw close goes from 100 to ~90.91.
  Without adjustment, the scanner sees a "9% drop" and flags it as bearish.
  Every indicator (ATR, BB, MA, OBV) gets polluted around the ex-date.

Strategy:
  1. Fetch adjusted prices from vnstock (preferred — they handle it correctly).
  2. Also fetch the corporate actions calendar so we can:
     - Warn users about upcoming ex-rights dates
     - Skip signals on/near ex-rights dates (volatility unrelated to TA)
     - Flag stocks with recent events in the UI

Data sources:
  - vnstock: stock.events() returns dividend/split history
  - TCBS: REST endpoint for upcoming ex-rights calendar
  - Fallback: scrape vietstock.vn or cafef.vn if API fails

Schema for events:
  {
    'ticker': str,
    'ex_date': date,          # ngày giao dịch không hưởng quyền
    'record_date': date,       # ngày chốt danh sách
    'event_type': str,         # 'cash_dividend', 'stock_dividend', 'split', 'rights_issue'
    'ratio': float,            # e.g. 0.10 = 10% stock dividend, or 1000 VND cash
    'description': str,
  }
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import pandas as pd

log = logging.getLogger(__name__)

EVENTS_CACHE = Path(__file__).resolve().parent.parent / 'data' / 'cache' / 'events'
EVENTS_CACHE.mkdir(parents=True, exist_ok=True)


@dataclass
class CorporateAction:
    ticker: str
    ex_date: str            # YYYY-MM-DD
    event_type: str         # cash_dividend | stock_dividend | split | rights_issue | unknown
    ratio: float            # 0.10 for 10% stock div, or VND for cash
    description: str = ''

    def to_dict(self):
        return asdict(self)

    @property
    def is_dilutive(self) -> bool:
        """Events that change share count → affect price mechanically."""
        return self.event_type in ('stock_dividend', 'split', 'rights_issue')

    @property
    def price_impact_pct(self) -> float:
        """Approximate % drop in price on ex-date due to this event."""
        if self.event_type == 'stock_dividend':
            # 10% stock dividend → price drops by ratio/(1+ratio)
            return -self.ratio / (1 + self.ratio) * 100
        if self.event_type == 'split':
            # 1:N split → price drops to 1/N
            return -(1 - 1/self.ratio) * 100 if self.ratio > 0 else 0
        if self.event_type == 'rights_issue':
            # Approximation: depends on offer price; treat conservatively
            return -self.ratio / (1 + self.ratio) * 50
        # Cash dividend: price drops by div amount, but as % depends on price.
        # We compute this at the call site where we know the price.
        return 0


# Tên cột có thể gặp ở các source/phiên bản vnstock khác nhau.
_EX_DATE_KEYS = ('ex_date', 'exdate', 'exrightdate', 'rightsexdate', 'exercise_date',
                 'ngay_gdkhq', 'date', 'public_date', 'issue_date')
_TYPE_KEYS = ('event_type', 'eventtype', 'event_name', 'event_title', 'type',
              'dividend_type', 'issue_method', 'title')
_VALUE_KEYS = ('ratio', 'value', 'exercise_ratio', 'cash_dividend_percentage',
               'issue_ratio', 'cash_year', 'price')
_DESC_KEYS = ('description', 'event_desc', 'note', 'event_list_name', 'title')


def _pick(row: dict, keys: tuple, default=None):
    """Lấy giá trị đầu tiên khớp một trong `keys` (không phân biệt hoa thường)."""
    lower = {str(k).lower().replace(' ', '_'): v for k, v in row.items()}
    for k in keys:
        if k in lower:
            v = lower[k]
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
    return default


def _read_cache(cache_file: Path, max_age_hours: float = 24) -> Optional[list]:
    if not cache_file.exists():
        return None
    age = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
    if age >= max_age_hours:
        return None
    try:
        with open(cache_file, encoding='utf-8') as f:
            return [CorporateAction(**e) for e in json.load(f)]
    except Exception:
        return None


def fetch_events(ticker: str, lookback_days: int = 365,
                 lookahead_days: int = 30) -> list[CorporateAction]:
    """
    Lấy sự kiện quyền của một mã, trong [today - lookback, today + lookahead].

    FIX (vnstock 4.x): bản cũ gọi `Vnstock().stock(source='TCBS').company` —
    class `Vnstock` đã deprecated 31/08/2025 và source TCBS bị GỠ khỏi vnstock
    4.x. Mọi lần gọi đều ném exception, bị `except` nuốt và trả về [] rồi cache
    lại danh sách rỗng 24h ⇒ toàn bộ bộ lọc sự kiện quyền chưa từng chạy.

    Nay dùng `vnstock.api.company.Company(source='vci')`, thử `events()` trước
    rồi `dividends()` (một số mã chỉ có bảng cổ tức).
    """
    cache_file = EVENTS_CACHE / f'{ticker}.json'
    today = date.today()

    cached = _read_cache(cache_file)
    if cached is not None:
        return cached

    events: list[CorporateAction] = []
    try:
        from vnstock.api.company import Company
        company = Company(symbol=ticker, source='vci')

        frames = []
        for method in ('events', 'dividends'):
            fn = getattr(company, method, None)
            if fn is None:
                continue
            try:
                df = fn()
                if df is not None and not df.empty:
                    frames.append(df)
            except Exception as e:
                log.debug(f"  {ticker}.{method}(): {type(e).__name__}: {str(e)[:100]}")

        for df in frames:
            for row in df.to_dict(orient='records'):
                ex_date_raw = _pick(row, _EX_DATE_KEYS)
                if ex_date_raw is None:
                    continue
                try:
                    ex_date = pd.to_datetime(ex_date_raw).date()
                except Exception:
                    continue

                if not (today - timedelta(days=lookback_days)
                        <= ex_date
                        <= today + timedelta(days=lookahead_days)):
                    continue

                description = str(_pick(row, _DESC_KEYS, '') or '')
                event_type, ratio = _classify(
                    str(_pick(row, _TYPE_KEYS, '') or ''),
                    _pick(row, _VALUE_KEYS, 0),
                    description,
                )
                events.append(CorporateAction(
                    ticker=ticker,
                    ex_date=str(ex_date),
                    event_type=event_type,
                    ratio=float(ratio) if ratio else 0.0,
                    description=description[:200],
                ))

        # Khử trùng lặp khi events() và dividends() cùng trả một sự kiện
        seen = set()
        deduped = []
        for e in events:
            key = (e.ex_date, e.event_type, round(e.ratio, 4))
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        events = deduped

    except ImportError:
        log.warning("  vnstock chưa cài hoặc quá cũ — bỏ qua corporate actions")
        return []
    except Exception as e:
        log.warning(f"  events {ticker}: {type(e).__name__}: {str(e)[:120]}")
        # KHÔNG cache khi lỗi: cache rỗng 24h sẽ che mất sự kiện thật.
        return []

    _save_cache(cache_file, events)
    return events


def fetch_events_batch(tickers, delay: float = 1.0,
                       lookback_days: int = 365,
                       lookahead_days: int = 30) -> dict:
    """
    Lấy sự kiện cho nhiều mã, tôn trọng rate limit của vnstock.

    Chỉ nên gọi cho danh sách mã ĐÃ có tín hiệu (vài chục mã) chứ không phải cả
    universe 500 mã — sự kiện quyền chỉ dùng để loại/ghi chú kết quả cuối.
    """
    import time
    out = {}
    for i, tk in enumerate(tickers, 1):
        cached = _read_cache(EVENTS_CACHE / f'{tk}.json')
        if cached is not None:
            out[tk] = cached
            continue
        if i > 1:
            time.sleep(delay)
        out[tk] = fetch_events(tk, lookback_days, lookahead_days)
    return out


def _classify(event_str: str, value, description: str) -> tuple[str, float]:
    """Heuristic classification of event text → (type, ratio)."""
    text = (event_str + ' ' + description).lower()
    try:
        v = float(value) if value not in (None, '') else 0.0
    except (ValueError, TypeError):
        v = 0.0

    # Thứ tự kiểm tra quan trọng: "cổ tức bằng cổ phiếu" phải rơi vào
    # stock_dividend chứ không phải cash_dividend.
    # Dấu ngoặc ở nhánh stock_dividend là bắt buộc — bản cũ viết
    # `... or 'cổ phiếu' in text and 'cổ tức' in text` dựa vào độ ưu tiên
    # `and` > `or`, đúng về kết quả nhưng cực dễ hỏng khi sửa.
    if 'split' in text or 'tách' in text or 'chia tách' in text:
        return 'split', v if v > 1 else 2.0
    if ('thưởng' in text or 'stock dividend' in text or 'stock div' in text
            or 'bằng cổ phiếu' in text
            or ('cổ phiếu' in text and 'cổ tức' in text)):
        # ratio in % form usually (e.g. 10 means 10%)
        return 'stock_dividend', v / 100 if v > 1 else v
    if 'phát hành' in text or 'rights' in text or 'chào bán' in text:
        return 'rights_issue', v / 100 if v > 1 else v
    if 'cổ tức' in text or 'dividend' in text or 'tiền' in text:
        return 'cash_dividend', v  # VND per share
    return 'unknown', v


def _save_cache(path: Path, events: list[CorporateAction]):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump([e.to_dict() for e in events], f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────
# Integration helpers — used by scanner
# ─────────────────────────────────────────────────────────────────

def has_recent_event(events: list[CorporateAction], days: int = 5) -> Optional[CorporateAction]:
    """Returns the most recent dilutive event within `days`, if any."""
    today = date.today()
    cutoff = today - timedelta(days=days)
    for e in events:
        try:
            ex = date.fromisoformat(e.ex_date)
        except Exception:
            continue
        if cutoff <= ex <= today and e.is_dilutive:
            return e
    return None


def has_upcoming_event(events: list[CorporateAction], days: int = 5) -> Optional[CorporateAction]:
    """Returns upcoming ex-rights within `days` (warning for users)."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    upcoming = []
    for e in events:
        try:
            ex = date.fromisoformat(e.ex_date)
        except Exception:
            continue
        if today < ex <= cutoff:
            upcoming.append(e)
    upcoming.sort(key=lambda x: x.ex_date)
    return upcoming[0] if upcoming else None


def apply_event_filter(results: list, lookback_days: int = 5,
                       lookahead_days: int = 5, delay: float = 1.0) -> list:
    """
    Áp bộ lọc sự kiện quyền lên KẾT QUẢ đã chấm điểm của bất kỳ strategy nào.

    Vì sao lọc ở bước sau thay vì trong `evaluate()`:
      - Sự kiện quyền chỉ có 2 tác dụng: (a) loại mã vừa có sự kiện pha loãng,
        (b) gắn cảnh báo sự kiện sắp tới. Cả hai đều không đổi điểm số.
      - Gọi API cho toàn universe 500 mã tốn ~17 phút và gần như toàn bộ là
        lãng phí; sau khi lọc chỉ còn vài chục mã có tín hiệu.
      - Quan trọng hơn: trước đây chỉ Pre-Breakout truyền `events`, còn
        Golden Cross và Ichimoku gọi `evaluate()` KHÔNG có events ⇒ 3 strategy
        hành xử khác nhau. Nay dùng chung một đường.

    Trả về danh sách kết quả đã lọc, có ghi `metrics['upcoming_event']`.
    """
    if not results:
        return results

    tickers = sorted({r.ticker for r in results})
    events_map = fetch_events_batch(tickers, delay=delay,
                                    lookahead_days=max(lookahead_days, 30))

    kept = []
    dropped = 0
    for r in results:
        events = events_map.get(r.ticker) or []
        if events and has_recent_event(events, days=lookback_days):
            dropped += 1
            continue
        upcoming = has_upcoming_event(events, days=lookahead_days) if events else None
        if upcoming is not None and isinstance(getattr(r, 'metrics', None), dict):
            r.metrics['upcoming_event'] = {
                'type': upcoming.event_type,
                'ex_date': upcoming.ex_date,
                'ratio': upcoming.ratio,
            }
        kept.append(r)

    if dropped:
        log.info(f"  Corporate actions: loại {dropped} mã có sự kiện pha loãng "
                 f"trong {lookback_days} phiên gần nhất")
    return kept


def event_summary(events: list[CorporateAction]) -> dict:
    """Compact summary for UI display."""
    if not events:
        return {'count': 0, 'latest': None, 'upcoming': None}
    recent = has_recent_event(events, days=10)
    upcoming = has_upcoming_event(events, days=30)
    return {
        'count': len(events),
        'latest': recent.to_dict() if recent else None,
        'upcoming': upcoming.to_dict() if upcoming else None,
    }
