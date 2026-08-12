#!/usr/bin/env python3
"""
Chạy backtest chiến lược kỹ thuật trên OHLCV cache đã có.

Khác `backend/backtest.py` (đo độ chính xác của ĐỊNH GIÁ), file này đo hiệu quả
của TÍN HIỆU KỸ THUẬT — và là nguồn duy nhất để hiệu chỉnh trọng số tiêu chí
trong `scanner/criteria.DEFAULT_CRITERIA_WEIGHTS`.

Usage:
    # Dùng toàn bộ cache hiện có
    python backend/run_backtest.py

    # Quét nhạy theo ngưỡng điểm
    python backend/run_backtest.py --min-score 5 --target 8 --stop 5 --hold 20

    # Xuất chi tiết từng lệnh
    python backend/run_backtest.py --export backend/data/results/trades.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.backtest_engine import run_backtest, print_report

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('backtest')

CACHE_DIR = Path(__file__).resolve().parent / 'data' / 'cache'
VNINDEX_CACHE = Path(__file__).resolve().parent / 'data' / 'vnindex_cache.parquet'


def load_universe_from_cache(cache_dir: Path, limit: int | None = None) -> dict:
    """Đọc toàn bộ parquet cache thành {ticker: DataFrame}."""
    by_ticker = {}
    seen = set()
    for pattern, strip in (('*_adj.parquet', '_adj'), ('*_raw.parquet', '_raw')):
        for f in sorted(cache_dir.glob(pattern)):
            ticker = f.stem.replace(strip, '')
            if ticker in seen:
                continue
            try:
                df = pd.read_parquet(f)
                df['Date'] = pd.to_datetime(df['Date'])
                if len(df) >= 80:
                    by_ticker[ticker] = df.sort_values('Date').reset_index(drop=True)
                    seen.add(ticker)
            except Exception as e:
                log.debug(f"  {ticker}: {e}")
            if limit and len(by_ticker) >= limit:
                return by_ticker
    return by_ticker


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cache-dir', type=str, default=str(CACHE_DIR))
    p.add_argument('--limit', type=int, default=None, help='Số mã tối đa')
    p.add_argument('--min-score', type=float, default=6.0)
    p.add_argument('--target', type=float, default=8.0, help='Mục tiêu chốt lời (%%)')
    p.add_argument('--stop', type=float, default=5.0, help='Cắt lỗ (%%)')
    p.add_argument('--hold', type=int, default=20, help='Số phiên nắm giữ tối đa')
    p.add_argument('--export', type=str, default=None, help='Xuất CSV chi tiết lệnh')
    p.add_argument('--json-out', type=str, default=None, help='Xuất tóm tắt JSON')
    args = p.parse_args()

    cache_dir = Path(args.cache_dir)
    if not cache_dir.exists():
        log.error(f"Không tìm thấy cache: {cache_dir}. Chạy run_daily.py trước.")
        sys.exit(1)

    log.info(f"Đọc OHLCV cache từ {cache_dir}...")
    by_ticker = load_universe_from_cache(cache_dir, args.limit)
    log.info(f"  {len(by_ticker)} mã có đủ lịch sử")
    if not by_ticker:
        log.error("Cache rỗng — chưa có dữ liệu để backtest")
        sys.exit(1)

    index_df = None
    if VNINDEX_CACHE.exists():
        index_df = pd.read_parquet(VNINDEX_CACHE)
        index_df['Date'] = pd.to_datetime(index_df['Date'])
        log.info(f"  VN-Index: {len(index_df)} phiên (dùng để tính alpha)")
    else:
        log.warning("  Không có cache VN-Index → alpha sẽ bằng lợi nhuận tuyệt đối")

    report = run_backtest(
        by_ticker,
        index_df=index_df,
        min_score=args.min_score,
        target_pct=args.target / 100,
        stop_pct=args.stop / 100,
        max_holding_days=args.hold,
    )
    print_report(report)

    if args.export and report.n_trades:
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        report.trades.to_csv(out, index=False, encoding='utf-8-sig')
        log.info(f"  Chi tiết lệnh → {out}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            'config': report.config,
            'n_trades': report.n_trades,
            'win_rate_pct': report.win_rate_pct,
            'base_rate_pct': report.base_rate_pct,
            'edge_vs_base_rate_pct': report.edge_vs_base_rate_pct,
            'mean_net_return_pct': report.mean_net_return_pct,
            'mean_alpha_pct': report.mean_alpha_pct,
            'alpha_win_rate_pct': report.alpha_win_rate_pct,
            'profit_factor': (report.profit_factor
                              if report.profit_factor != float('inf') else None),
            'max_drawdown_pct': report.max_drawdown_pct,
            'by_rating': report.by_rating,
            'criteria_ic': report.criteria_ic,
            'suggested_weights': report.suggested_weights,
        }
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                       encoding='utf-8')
        log.info(f"  Tóm tắt → {out}")

    # Cảnh báo quan trọng: tín hiệu không đánh bại base rate thì không có edge.
    if report.n_trades and report.edge_vs_base_rate_pct <= 0:
        log.warning("⚠️  Tín hiệu KHÔNG vượt base rate — bộ tiêu chí hiện tại chưa có edge")


if __name__ == '__main__':
    main()
