#!/usr/bin/env python3
"""
SINH LẠI DỮ LIỆU DASHBOARD TỪ CACHE — hoàn toàn OFFLINE
================================================================================
Khác `run_daily.py` ở chỗ KHÔNG gọi API vnstock: đọc thẳng parquet cache đã có.

Dùng khi:
  - Vừa sửa logic backend và muốn thấy kết quả trên giao diện ngay, mà không
    phải chờ tới lần scan theo lịch (file JSON cũ thiếu các trường mới nên UI
    hiển thị "—").
  - Đang chạy backfill và không muốn tranh quota 60 req/phút.
  - Không có mạng.

GIỚI HẠN PHẢI BIẾT:
  - Universe chỉ gồm những mã ĐÃ có trong cache, không phải toàn thị trường.
  - Ngày dữ liệu là phiên cuối trong cache, không phải hôm nay.
  - Không có bộ lọc sự kiện quyền (cần mạng).
  ⇒ Output được đánh dấu `metadata.offline_rebuild = true` để giao diện và
    người đọc biết đây không phải bản scan chính thức.

Usage:
    python backend/rebuild_web_data.py
    python backend/rebuild_web_data.py --min-score 4
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import BreakoutScanner
from scanner.exporter import to_json, write_json
from scanner.market_regime import (
    compute_regime, compute_breadth, compute_relative_strength, annotate_results,
)
from scanner.strategies import golden_cross, ichimoku
from scanner.top_liquid import get_top_liquid_tickers

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('rebuild')

CACHE_DIR = Path(__file__).resolve().parent / 'data' / 'cache'
VNINDEX_CACHE = Path(__file__).resolve().parent / 'data' / 'vnindex_cache.parquet'


def load_from_cache(lookback: int = 400) -> dict:
    """
    Đọc OHLCV từ parquet cache và bổ sung các cột mà strategy cần.

    Cache do backfill_history ghi chỉ có OHLCV thuần (Date/Open/High/Low/Close/
    Volume) — thiếu Exchange. Sàn ảnh hưởng trực tiếp tới biên độ trần/sàn nên
    phải suy từ danh sách curated; không rõ thì mặc định HOSE (biên chặt nhất,
    tức thận trọng nhất).
    """
    exchange_map = dict(get_top_liquid_tickers())

    by_ticker = {}
    for f in sorted(CACHE_DIR.glob('*_adj.parquet')):
        ticker = f.stem.replace('_adj', '')
        try:
            df = pd.read_parquet(f)
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date').tail(lookback).reset_index(drop=True)
            if len(df) < 80:
                continue
            df['Ticker'] = ticker
            df['Exchange'] = exchange_map.get(ticker, 'HOSE')
            df['StaleCache'] = False      # dữ liệu lịch sử, không phải cache hỏng
            by_ticker[ticker] = df
        except Exception as e:
            log.debug(f"  {ticker}: {e}")
    return by_ticker


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min-score', type=float, default=5)
    p.add_argument('--min-score-goldencross', type=float, default=2)
    p.add_argument('--min-score-ichimoku', type=float, default=3)
    p.add_argument('--web-data-dir', type=str, default='web/data')
    p.add_argument('--lookback', type=int, default=400)
    args = p.parse_args()

    web_dir = Path(args.web_data_dir)
    if not web_dir.exists():
        log.error(f"Không thấy {web_dir} — chạy lệnh này từ thư mục gốc của repo")
        sys.exit(1)

    log.info("Đọc OHLCV từ cache (không gọi mạng)...")
    by_ticker = load_from_cache(args.lookback)
    if not by_ticker:
        log.error("Cache rỗng — chạy backfill_history.py hoặc run_daily.py trước")
        sys.exit(1)

    last_session = max(df['Date'].max() for df in by_ticker.values())
    log.info(f"  {len(by_ticker)} mã | phiên cuối trong cache: {last_session.date()}")

    index_df = None
    if VNINDEX_CACHE.exists():
        index_df = pd.read_parquet(VNINDEX_CACHE)
        index_df['Date'] = pd.to_datetime(index_df['Date'])

    regime = compute_regime(index_df)
    breadth = compute_breadth(by_ticker)
    rs_map = compute_relative_strength(by_ticker, index_df)
    log.info(f"  Regime: {regime.get('regime')} | breadth "
             f"{breadth.get('pct_above_ma50')}% | RS cho {len(rs_map)} mã")

    market_context = {**regime, 'breadth': breadth}
    today = last_session.strftime('%Y-%m-%d')
    df_all = pd.concat(by_ticker.values(), ignore_index=True)

    base_meta = {
        'exchanges': ['CACHE'],
        'total_scanned': len(by_ticker),
        'market_context': market_context,
        'offline_rebuild': True,       # giao diện/người đọc biết đây không phải scan chính thức
        'cache_last_session': today,
    }

    # ── Pre-Breakout ──────────────────────────────────────────────────────
    scanner = BreakoutScanner(fetch_corporate_actions=False)
    df_pb = scanner.scan_from_dataframe(df_all)
    n_pb = 0
    if not df_pb.empty:
        if rs_map:
            df_pb['m_rs_score'] = df_pb['ticker'].map(lambda t: (rs_map.get(t) or {}).get('rs_score'))
            df_pb['m_rs_rank'] = df_pb['ticker'].map(lambda t: (rs_map.get(t) or {}).get('rs_rank'))
        sig = df_pb[df_pb['total_score'] >= args.min_score].copy()
        n_pb = len(sig)
        to_json(sig, web_dir / 'latest.json',
                metadata={**base_meta, 'min_score': args.min_score})
    log.info(f"  Pre-Breakout: {n_pb} tín hiệu")

    # ── 3 strategy còn lại ────────────────────────────────────────────────
    def run(label, fn, subdir, min_score):
        results = []
        for ticker, df_t in by_ticker.items():
            try:
                r = fn(df_t, ticker)
                if r:
                    results.append(r)
            except Exception as e:
                log.debug(f"  {label} {ticker}: {e}")
        annotate_results(results, rs_map)

        signals = sorted((r.to_dict() for r in results if r.total_score >= min_score),
                         key=lambda s: -s['total_score'])
        out = web_dir / subdir
        out.mkdir(parents=True, exist_ok=True)
        write_json({
            'generated_at': datetime.now().isoformat(),
            'strategy': subdir,
            'total': len(signals),
            'metadata': {**base_meta, 'min_score': min_score},
            'signals': signals,
        }, out / 'latest.json')
        log.info(f"  {label}: {len(signals)} tín hiệu")

    run('GC dài hạn', lambda d, t: golden_cross.evaluate(d, t, preset='long'),
        'golden_cross_long', args.min_score_goldencross)
    run('GC ngắn hạn', lambda d, t: golden_cross.evaluate(d, t, preset='short'),
        'golden_cross_short', args.min_score_goldencross)
    run('Ichimoku', lambda d, t: ichimoku.evaluate(d, t),
        'ichimoku', args.min_score_ichimoku)

    log.info("")
    log.info(f"Xong. Mở lại dashboard để xem (dữ liệu phiên {today}).")
    log.info("LƯU Ý: đây là bản dựng offline từ cache, KHÔNG phải scan chính thức.")


if __name__ == '__main__':
    main()
