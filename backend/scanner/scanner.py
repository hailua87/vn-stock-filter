"""
Main scanner engine. Orchestrates: fetch → evaluate → rank → export.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
import pandas as pd

from .criteria import evaluate, CriteriaResult, DEFAULT_CONFIG
from .data_fetcher import get_ticker_universe, fetch_universe, fetch_vnindex
from .corporate_actions import apply_event_filter

log = logging.getLogger(__name__)


class BreakoutScanner:
    def __init__(self, config: Optional[dict] = None,
                 exchanges: tuple = ('HOSE', 'HNX', 'UPCOM'),
                 fetch_corporate_actions: bool = True):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.exchanges = exchanges
        self.results: list[CriteriaResult] = []
        self.fetch_corporate_actions = fetch_corporate_actions

    def scan_from_dataframe(self, df_all: pd.DataFrame) -> pd.DataFrame:
        """
        Scan a pre-loaded DataFrame with columns:
        Ticker, Exchange, Date, Open, High, Low, Close, Volume

        Bộ lọc sự kiện quyền chạy SAU khi chấm điểm, chỉ trên các mã có tín hiệu
        — xem corporate_actions.apply_event_filter (trước đây gọi API cho từng
        mã trong vòng lặp: 500 request mỗi lần chạy, và tất cả đều fail).
        """
        self.results = []
        # groupby thay cho boolean-mask trong vòng lặp: tránh quét lại toàn bộ
        # DataFrame N lần (O(N²) trên universe 500 mã × 400 phiên).
        groups = dict(tuple(df_all.groupby('Ticker', sort=False)))
        log.info(f"Scanning {len(groups)} tickers...")

        for i, (tk, df_tk) in enumerate(groups.items(), 1):
            df_tk = df_tk.sort_values('Date').reset_index(drop=True)
            try:
                res = evaluate(df_tk, tk, self.config)
                if res is not None:
                    self.results.append(res)
            except Exception as e:
                log.warning(f"  {tk}: {e}")
            if i % 100 == 0:
                log.info(f"  Processed {i}/{len(groups)}")

        if self.fetch_corporate_actions:
            self.results = apply_event_filter(
                self.results,
                lookback_days=self.config['corporate_action_lookback_days'],
                lookahead_days=self.config['corporate_action_lookahead_days'],
            )

        return self.to_dataframe()

    def scan_live(self, lookback_days: int = 180) -> pd.DataFrame:
        """Full pipeline: fetch universe → scan."""
        log.info("Loading ticker universe...")
        universe = get_ticker_universe(self.exchanges)
        log.info(f"  Total tickers: {len(universe)}")

        log.info("Fetching OHLCV data...")
        df_all = fetch_universe(universe, lookback_days=lookback_days)
        if df_all.empty:
            log.error("No data fetched")
            return pd.DataFrame()

        return self.scan_from_dataframe(df_all)

    def to_dataframe(self, min_score: int = 0) -> pd.DataFrame:
        """Convert results to a sortable DataFrame."""
        if not self.results:
            return pd.DataFrame()
        rows = [r.to_dict() for r in self.results if r.total_score >= min_score]
        df = pd.DataFrame(rows)
        if 'total_score' in df.columns:
            df = df.sort_values('total_score', ascending=False).reset_index(drop=True)
        return df

    def top_signals(self, n: int = 30, min_rating: str = 'B') -> pd.DataFrame:
        """Return top N signals filtered by rating."""
        rating_order = {'A+': 4, 'A': 3, 'B': 2, 'C': 1}
        min_lvl = rating_order.get(min_rating, 2)
        df = self.to_dataframe()
        if df.empty:
            return df
        df = df[df['rating'].map(rating_order) >= min_lvl]
        return df.head(n)
