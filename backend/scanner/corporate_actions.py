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


def fetch_events(ticker: str, lookback_days: int = 365,
                 lookahead_days: int = 30) -> list[CorporateAction]:
    """
    Fetch corporate actions for a ticker.
    Returns events in [today - lookback_days, today + lookahead_days].
    Uses vnstock company.events().
    """
    cache_file = EVENTS_CACHE / f'{ticker}.json'
    today = date.today()

    # Use cache if < 24h old
    if cache_file.exists():
        age = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age < 24:
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                return [CorporateAction(**e) for e in cached]
            except Exception:
                pass

    events = []
    try:
        from vnstock import Vnstock
        company = Vnstock().stock(symbol=ticker, source='TCBS').company
        # TCBS has the most complete events API for Vietnamese stocks
        df = company.events()
        if df is None or df.empty:
            _save_cache(cache_file, [])
            return []

        # Normalise columns — vnstock columns may vary by version
        col_map = {}
        for c in df.columns:
            c_lower = c.lower()
            if 'date' in c_lower and 'rights' in c_lower or c_lower == 'rightsexdate' or c_lower == 'ex_date':
                col_map[c] = 'ex_date'
            elif 'type' in c_lower or 'event' in c_lower:
                col_map[c] = 'event_type'
            elif 'ratio' in c_lower or 'value' in c_lower:
                col_map[c] = 'value'
            elif 'description' in c_lower or 'note' in c_lower:
                col_map[c] = 'description'
        df = df.rename(columns=col_map)

        for _, row in df.iterrows():
            ex_date_raw = row.get('ex_date')
            if pd.isna(ex_date_raw):
                continue
            try:
                ex_date = pd.to_datetime(ex_date_raw).date()
            except Exception:
                continue

            if ex_date < today - timedelta(days=lookback_days):
                continue
            if ex_date > today + timedelta(days=lookahead_days):
                continue

            event_type, ratio = _classify(
                str(row.get('event_type', '')),
                row.get('value', 0),
                str(row.get('description', '')),
            )
            events.append(CorporateAction(
                ticker=ticker,
                ex_date=str(ex_date),
                event_type=event_type,
                ratio=float(ratio) if ratio else 0.0,
                description=str(row.get('description', ''))[:200],
            ))
    except Exception as e:
        log.warning(f"  events {ticker}: {e}")

    _save_cache(cache_file, events)
    return events


def _classify(event_str: str, value, description: str) -> tuple[str, float]:
    """Heuristic classification of event text → (type, ratio)."""
    text = (event_str + ' ' + description).lower()
    try:
        v = float(value) if value not in (None, '') else 0.0
    except (ValueError, TypeError):
        v = 0.0

    if 'split' in text or 'tách' in text or 'chia tách' in text:
        return 'split', v if v > 1 else 2.0
    if 'thưởng' in text or 'stock dividend' in text or 'stock div' in text or 'bằng cổ phiếu' in text or 'cổ phiếu' in text and 'cổ tức' in text:
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
