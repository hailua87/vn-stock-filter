"""
Backtest framework — BẢN CŨ, giữ lại cho tương thích ngược.

⚠️  KHÔNG DÙNG ĐỂ RA QUYẾT ĐỊNH. Hãy dùng `scanner/backtest_engine.py`
    (CLI: `python backend/run_backtest.py`).

Module này đo `max_close` trong N phiên — tức Maximum Favorable Excursion, lợi
nhuận nếu bán ĐÚNG ĐỈNH. Nó còn bỏ qua T+2, bỏ phí/thuế, không so với
benchmark hay base rate, và gọi lại `evaluate()` cho từng phiên nên chậm tới
mức không chạy nổi trên universe thật. Con số nó đưa ra luôn đẹp hơn thực tế.

`backtest_engine` khắc phục toàn bộ những điểm trên và còn tính information
coefficient của từng tiêu chí để hiệu chỉnh trọng số.
"""
from __future__ import annotations

import warnings as _warnings
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np
import logging

from .criteria import evaluate, DEFAULT_CONFIG

log = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    total_signals: int
    successful: int
    failed: int
    hit_rate: float
    avg_return_pct: float
    avg_days_to_break: float
    by_rating: dict
    trades: pd.DataFrame


def backtest(df_all: pd.DataFrame,
             lookahead_days: int = 5,
             breakout_threshold: float = 0.05,
             min_score: int = 6,
             config: Optional[dict] = None,
             warmup_days: int = 60) -> BacktestResult:
    """
    Walk forward through history. At each date t (t > warmup_days),
    evaluate every ticker using only data [:t], record signals,
    then check whether price broke out within next `lookahead_days`.

    Args:
        df_all: DataFrame with Ticker, Exchange, Date, OHLCV
        lookahead_days: how many days forward to measure success
        breakout_threshold: % gain required to count as successful break
        min_score: signal threshold
        warmup_days: history needed before generating first signal
    """
    _warnings.warn(
        "scanner.backtest.backtest() đo Maximum Favorable Excursion, bỏ qua T+2 "
        "và phí giao dịch nên cho kết quả lạc quan giả tạo. "
        "Dùng scanner.backtest_engine.run_backtest() thay thế.",
        DeprecationWarning, stacklevel=2,
    )
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    df_all = df_all.copy()
    df_all['Date'] = pd.to_datetime(df_all['Date'])
    df_all = df_all.sort_values(['Ticker', 'Date'])

    all_dates = sorted(df_all['Date'].unique())
    if len(all_dates) < warmup_days + lookahead_days + 1:
        raise ValueError("Not enough history for backtest")

    trades = []
    test_dates = all_dates[warmup_days:-lookahead_days]
    log.info(f"Backtesting across {len(test_dates)} dates...")

    for i, t in enumerate(test_dates):
        df_t = df_all[df_all['Date'] <= t]
        for tk, grp in df_t.groupby('Ticker'):
            if len(grp) < warmup_days:
                continue
            try:
                res = evaluate(grp, tk, cfg)
            except Exception:
                continue
            if res is None or res.total_score < min_score:
                continue

            # Look ahead — get next lookahead_days prices for this ticker
            future = df_all[(df_all['Ticker'] == tk) & (df_all['Date'] > t)].head(lookahead_days)
            if len(future) == 0:
                continue
            entry = res.close
            target = entry * (1 + breakout_threshold)
            success = (future['Close'] >= target).any()
            days_to_break = None
            if success:
                days_to_break = int((future['Close'] >= target).idxmax() - future.index[0]) + 1
            max_close = future['Close'].max()
            ret = (max_close / entry - 1) * 100

            trades.append({
                'date': t, 'ticker': tk, 'score': res.total_score, 'rating': res.rating,
                'entry': entry, 'max_close': round(max_close, 2),
                'return_pct': round(ret, 2),
                'success': bool(success),
                'days_to_break': days_to_break,
            })
        if (i + 1) % 20 == 0:
            log.info(f"  {i+1}/{len(test_dates)} dates processed, {len(trades)} signals so far")

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        return BacktestResult(0, 0, 0, 0.0, 0.0, 0.0, {}, df_trades)

    hit_rate = df_trades['success'].mean() * 100
    by_rating = df_trades.groupby('rating').agg(
        n=('success', 'size'),
        hit_rate=('success', lambda x: round(x.mean() * 100, 1)),
        avg_ret=('return_pct', lambda x: round(x.mean(), 2)),
    ).to_dict('index')

    return BacktestResult(
        total_signals=len(df_trades),
        successful=int(df_trades['success'].sum()),
        failed=int((~df_trades['success']).sum()),
        hit_rate=round(hit_rate, 2),
        avg_return_pct=round(df_trades['return_pct'].mean(), 2),
        avg_days_to_break=round(df_trades.loc[df_trades['success'], 'days_to_break'].mean(), 2)
                          if df_trades['success'].any() else 0,
        by_rating=by_rating,
        trades=df_trades,
    )


def print_report(r: BacktestResult):
    print("=" * 60)
    print("BACKTEST REPORT")
    print("=" * 60)
    print(f"Total signals:       {r.total_signals}")
    print(f"Successful:          {r.successful}")
    print(f"Failed:              {r.failed}")
    print(f"Hit rate:            {r.hit_rate}%")
    print(f"Avg return:          {r.avg_return_pct}%")
    print(f"Avg days to break:   {r.avg_days_to_break}")
    print("\nBy rating:")
    for rating, stats in sorted(r.by_rating.items(), reverse=True):
        print(f"  {rating}: n={stats['n']}, hit={stats['hit_rate']}%, avg_ret={stats['avg_ret']}%")
    print("=" * 60)
