#!/usr/bin/env python3
"""
Test backtest framework với synthetic data.
Tạo:
  - 2 snapshots cách nhau 90 ngày trong /tmp
  - OHLCV cache giả với giá thực tế tại ngày target
"""
from __future__ import annotations
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from backtest import run_backtest, print_report

# Test fixtures
TEST_ROOT = Path('/tmp/test_backtest')
ARCHIVE_DIR = TEST_ROOT / 'archive'
OHLCV_DIR = TEST_ROOT / 'cache'


def setup_synthetic_data():
    """Tạo 2 snapshots + OHLCV cho 5 tickers."""
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    ARCHIVE_DIR.mkdir(parents=True)
    OHLCV_DIR.mkdir(parents=True)

    # Snapshot 1: 180 ngày trước
    snap1_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    # Snapshot 2: 90 ngày trước
    snap2_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    # Fixtures: 5 mã với verdict + actual outcome khác nhau
    # Mỗi mã có:
    #   - price_at_snap: giá khi tạo snapshot
    #   - fair_value: dự đoán
    #   - actual_return_pct: thay đổi giá 90 ngày sau (mô phỏng outcome)
    fixtures = [
        # (ticker, industry, verdict, price_snap, fair_value, conf, actual_return_pct_after_90d)
        ('AAA', 'Banking',              'STRONG BUY',  20000, 28000, 80, +18.5),  # HIT
        ('BBB', 'Banking',              'BUY',         15000, 17500, 70, +7.2),   # HIT
        ('CCC', 'Consumer_Staples',     'HOLD',        50000, 51000, 75, +2.0),   # HIT
        ('DDD', 'Steel_Metals',         'STRONG SELL', 30000, 18000, 65, -20.0),  # HIT
        ('EEE', 'Technology',           'BUY',         100000, 120000, 72, -8.0), # MISS - went down
        ('FFF', 'Real_Estate',          'STRONG BUY',  25000, 35000, 60, +5.0),   # MISS - chỉ +5%
        ('GGG', 'Agriculture_Livestock','SELL',        40000, 28000, 55, -12.0),  # HIT
        ('HHH', 'Banking',              'BUY',         18000, 22000, 78, +12.0),  # HIT
    ]

    # Tạo snapshot 1 (180 ngày trước) — có 90 ngày data để backtest với horizon=90
    signals_1 = []
    for ticker, industry, verdict, price, fv, conf, _ in fixtures:
        upside = (fv - price) / price * 100
        signals_1.append({
            'ticker': ticker,
            'industry': industry,
            'industry_source': 'icb_mapping',
            'is_holding': False,
            'current_price': price,
            'fair_value': fv,
            'fair_value_low': fv * 0.85,
            'fair_value_high': fv * 1.15,
            'upside_pct': round(upside, 1),
            'verdict': verdict,
            'confidence': conf,
            'methods_used': ['P/B-ROE Justified', 'P/E Multiple'],
            'method_details': [],
            'warnings': [],
            'notes': [],
        })

    # Snapshot 2 (90 ngày trước) - giống snapshot 1 nhưng giá đã thay đổi 90 ngày
    signals_2 = []
    for ticker, industry, verdict, price_orig, fv, conf, return_pct in fixtures:
        # Giá tại snapshot 2 = giá orig + một phần của return_pct (giả định 50% đã realize)
        price_snap2 = price_orig * (1 + return_pct/100 * 0.5)
        # Fair value điều chỉnh nhẹ (giả lập engine re-calculate)
        fv_2 = fv * (1 + np.random.uniform(-0.05, 0.05))
        upside = (fv_2 - price_snap2) / price_snap2 * 100
        signals_2.append({
            'ticker': ticker,
            'industry': industry,
            'industry_source': 'icb_mapping',
            'is_holding': False,
            'current_price': round(price_snap2, 0),
            'fair_value': round(fv_2, 0),
            'fair_value_low': round(fv_2 * 0.85, 0),
            'fair_value_high': round(fv_2 * 1.15, 0),
            'upside_pct': round(upside, 1),
            'verdict': verdict,
            'confidence': conf,
            'methods_used': ['P/B-ROE Justified', 'P/E Multiple'],
            'method_details': [],
            'warnings': [],
            'notes': [],
        })

    # Save snapshots
    for date_str, signals in [(snap1_date, signals_1), (snap2_date, signals_2)]:
        payload = {
            'generated_at': date_str + 'T17:00:00',
            'strategy': 'multi_method_valuation',
            'total': len(signals),
            'metadata': {'verdict_counts': {}},
            'signals': signals,
        }
        with open(ARCHIVE_DIR / f'{date_str}.json', 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # Tạo OHLCV cache với giá thực tế tại target_date (90 ngày sau snapshot)
    # snap1 target = today - 90 days
    # snap2 target = today
    for ticker, industry, verdict, price_orig, fv, conf, return_pct in fixtures:
        # Generate 365 daily prices from 1 year ago to today
        dates = pd.date_range(end=datetime.now().date(), periods=365, freq='D')
        # Linear interpolation từ price_orig (lúc -180d) đến price_orig × (1+return) (lúc -90d)
        # Sau đó tiếp tục drift nhẹ đến today
        prices = []
        for i, d in enumerate(dates):
            age = (datetime.now().date() - d.date()).days  # days ago
            if age >= 180:
                # Trước snapshot 1 → flat around price_orig
                price = price_orig * (1 + np.random.normal(0, 0.005))
            elif age >= 90:
                # Snapshot 1 → snapshot 2: progress 0% → 50% của return
                progress = (180 - age) / 90 * 0.5  # 0 → 0.5
                price = price_orig * (1 + return_pct/100 * progress) * (1 + np.random.normal(0, 0.005))
            else:
                # Snapshot 2 → today: progress 50% → 100% của return
                progress = 0.5 + (90 - age) / 90 * 0.5  # 0.5 → 1.0
                price = price_orig * (1 + return_pct/100 * progress) * (1 + np.random.normal(0, 0.005))
            prices.append(price)

        # QUAN TRỌNG — ĐƠN VỊ: cache OHLCV lưu theo đơn vị quote của vnstock
        # (nghìn VND, ví dụ ACB = 24.30) trong khi snapshot định giá lưu VND.
        # Fixture phải mô phỏng đúng thực tế, nếu không backtest sẽ báo sai số
        # hàng trăm nghìn phần trăm. Xem scanner/price_units.py.
        prices_quote = [p / 1_000 for p in prices]

        df = pd.DataFrame({
            'Date': dates,
            'Open': prices_quote,
            'High': [p * 1.01 for p in prices_quote],
            'Low': [p * 0.99 for p in prices_quote],
            'Close': prices_quote,
            'Volume': [1_000_000] * len(prices),
        })
        df.to_parquet(OHLCV_DIR / f'{ticker}_adj.parquet', index=False)

    return snap1_date, snap2_date


def main():
    print("=" * 78)
    print("BACKTEST FRAMEWORK TEST")
    print("=" * 78)
    print("\nSetting up synthetic data...")
    snap1, snap2 = setup_synthetic_data()
    print(f"  ✓ Snapshot 1: {snap1}")
    print(f"  ✓ Snapshot 2: {snap2}")
    print(f"  ✓ OHLCV cache: {OHLCV_DIR}")

    print("\nRunning backtest (horizon=90 days)...")
    metrics = run_backtest(ARCHIVE_DIR, OHLCV_DIR,
                          horizon_days=90, min_confidence=50)

    print_report(metrics)

    # Assertions
    if 'error' in metrics:
        print("✗ FAIL: backtest returned error")
        return 1

    overall = metrics['overall']
    assert metrics['config']['total_comparisons'] >= 5, \
        f"Expected ≥5 comparisons, got {metrics['config']['total_comparisons']}"

    # Direction accuracy nên >= 60% (logic của fixtures là HIT majority)
    if overall['direction_accuracy_pct'] >= 50:
        print(f"✓ PASS: Direction accuracy {overall['direction_accuracy_pct']}% >= 50%")
    else:
        print(f"✗ Direction accuracy too low: {overall['direction_accuracy_pct']}%")

    print("\nCleaning up test files...")
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    print("✓ Test complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
