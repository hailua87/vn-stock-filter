"""
Fibonacci Retracement levels for Vietnamese stocks.

Methodology:
  1. Find swing high and swing low in the lookback window (default 60 days).
  2. Determine swing direction:
       - If low occurs BEFORE high → uptrend swing (Fibo measures pullback from high)
       - If high occurs BEFORE low → downtrend swing (Fibo measures bounce from low)
  3. Compute Fibonacci retracement levels (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%).
  4. Classify levels relative to current price:
       - Levels below current price → SUPPORTS
       - Levels above current price → RESISTANCES
  5. Return nearest 3 supports + nearest 3 resistances.

Fibonacci levels and their meaning:
  - 23.6%: minor pullback, weakest level
  - 38.2%: common pullback in strong trend
  - 50%: psychological midpoint (not a true Fib but widely watched)
  - 61.8%: "golden ratio", strongest retracement level
  - 78.6%: deep pullback, still considered within trend
"""
from __future__ import annotations
from typing import List, Dict
import pandas as pd


# Standard Fibonacci retracement ratios
FIBO_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIBO_LABELS = {
    0.0: '0%',
    0.236: '23.6%',
    0.382: '38.2%',
    0.5: '50%',
    0.618: '61.8%',  # golden ratio — most important
    0.786: '78.6%',
    1.0: '100%',
}


def find_swing_extremes(df: pd.DataFrame, lookback: int = 60) -> Dict:
    """
    Find the highest high and lowest low in the lookback window.

    Returns:
        {
            'high': float,           # max high price
            'high_date': str,        # date of max high
            'high_idx': int,         # position in df (relative to lookback slice)
            'low': float,
            'low_date': str,
            'low_idx': int,
            'direction': str,        # 'up' if low before high, else 'down'
            'range': float,          # high - low
        }
    """
    window = df.tail(lookback).reset_index(drop=True)
    if len(window) < 10:
        return None

    high_idx = int(window['High'].idxmax())
    low_idx = int(window['Low'].idxmin())
    high = float(window['High'].iloc[high_idx])
    low = float(window['Low'].iloc[low_idx])

    high_date = window['Date'].iloc[high_idx]
    low_date = window['Date'].iloc[low_idx]

    direction = 'up' if low_idx < high_idx else 'down'

    return {
        'high': round(high, 2),
        'high_date': str(high_date.date()) if hasattr(high_date, 'date') else str(high_date),
        'high_idx': high_idx,
        'low': round(low, 2),
        'low_date': str(low_date.date()) if hasattr(low_date, 'date') else str(low_date),
        'low_idx': low_idx,
        'direction': direction,
        'range': round(high - low, 2),
    }


def compute_fibo_levels(swing: Dict) -> List[Dict]:
    """
    Compute all 7 Fibonacci retracement levels from a swing.

    For uptrend swing (low → high): levels are measured DOWN from high.
        - 0% = high
        - 100% = low
        - 61.8% = high - (range × 0.618)

    For downtrend swing (high → low): levels are measured UP from low.
        - 0% = low
        - 100% = high
        - 61.8% = low + (range × 0.618)

    Returns list of level dicts ordered by price ascending.
    """
    if not swing:
        return []

    high = swing['high']
    low = swing['low']
    rng = swing['range']
    direction = swing['direction']

    levels = []
    for ratio in FIBO_RATIOS:
        if direction == 'up':
            # Fibo retracement: measure from high downward
            price = high - rng * ratio
        else:
            # Downtrend: measure from low upward
            price = low + rng * ratio

        levels.append({
            'ratio': ratio,
            'label': FIBO_LABELS[ratio],
            'price': round(price, 2),
            'is_golden': ratio == 0.618,
        })

    # Sort by price ascending
    levels.sort(key=lambda x: x['price'])
    return levels


def get_fibo_support_resistance(df: pd.DataFrame, current_price: float = None,
                                 lookback: int = 60,
                                 n_levels: int = 3) -> Dict:
    """
    Get Fibonacci-based support and resistance for a stock.

    Args:
        df: OHLC dataframe with Date, High, Low, Close columns
        current_price: defaults to last Close if not provided
        lookback: number of bars to look back for swing detection
        n_levels: number of nearest levels above/below to return

    Returns:
        {
            'current': float,
            'swing': {high, low, direction, range, ...},
            'supports': [
                {'price': 45.2, 'label': '61.8%', 'ratio': 0.618,
                 'distance_pct': 2.3, 'is_golden': True, 'type': 'fibo'},
                ...
            ],
            'resistances': [...],
            'all_levels': [...],   # all 7 Fibo levels for visualization
        }
    """
    if current_price is None:
        current_price = float(df['Close'].iloc[-1])

    swing = find_swing_extremes(df, lookback=lookback)
    if not swing:
        return {
            'current': round(current_price, 2),
            'swing': None,
            'supports': [],
            'resistances': [],
            'all_levels': [],
        }

    levels = compute_fibo_levels(swing)

    # Classify each level
    supports = []
    resistances = []
    for lv in levels:
        # Build enriched level dict
        enriched = {
            'price': lv['price'],
            'label': lv['label'],
            'ratio': lv['ratio'],
            'is_golden': lv['is_golden'],
            'type': 'fibo',
        }

        if lv['price'] < current_price:
            enriched['distance_pct'] = round(
                (current_price - lv['price']) / current_price * 100, 2)
            supports.append(enriched)
        elif lv['price'] > current_price:
            enriched['distance_pct'] = round(
                (lv['price'] - current_price) / current_price * 100, 2)
            resistances.append(enriched)
        # If exactly equal, skip (very rare)

    # Sort: supports descending (nearest first), resistances ascending
    supports.sort(key=lambda x: -x['price'])
    resistances.sort(key=lambda x: x['price'])

    return {
        'current': round(current_price, 2),
        'swing': swing,
        'supports': supports[:n_levels],
        'resistances': resistances[:n_levels],
        'all_levels': levels,
    }
