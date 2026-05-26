"""
BACKTEST FRAMEWORK FOR VALUATION ENGINE
================================================================================
Mục đích: Đo lường accuracy của fair value đã tính trong quá khứ so với giá
thực tế N tháng sau, để:
  1. Validate logic engine có hoạt động đúng không
  2. Calibrate INDUSTRY_METHOD_WEIGHTS bằng data thực
  3. Detect ngành nào model định giá kém để cải thiện

LOGIC:
  Với mỗi snapshot t (lưu trong web/data/valuation/archive/<date>.json),
  so sánh giá thực tế tại t+horizon:
    - Hit rate: % verdict đúng (STRONG BUY → giá tăng ≥ X%)
    - Mean Absolute Error: |fair_value - actual_price_t+h| / fair_value
    - Direction accuracy: % upside đúng dấu

  Output bảng theo industry × verdict + scatter plot fair vs actual.

USAGE:
    cd backend
    python backtest.py --horizon 90 --min-snapshots 5

NOTE: Cần có ít nhất 2 snapshots cách nhau >= horizon ngày trong archive/
để chạy backtest. Lần đầu deploy → chờ 3 tháng accumulating data.
"""
from __future__ import annotations
import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('backtest')


# ============================================================================
# DATA LOADING
# ============================================================================

def load_snapshots(archive_dir: Path) -> List[Dict[str, Any]]:
    """Load all snapshots từ archive directory, sorted by date asc."""
    snapshots = []
    for f in sorted(archive_dir.glob('*.json')):
        if f.stem == 'index':
            continue
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            data['_snapshot_date'] = f.stem
            snapshots.append(data)
        except Exception as e:
            log.warning(f"  Skip {f.name}: {e}")
    return snapshots


def fetch_actual_price(ticker: str, target_date: str,
                       ohlcv_cache_dir: Path) -> Optional[float]:
    """
    Lấy giá thực tế tại target_date (hoặc ngày giao dịch gần nhất sau đó)
    từ OHLCV parquet cache.

    Args:
        ticker: Stock code
        target_date: 'YYYY-MM-DD'
        ohlcv_cache_dir: Path tới backend/data/cache/
    """
    import pandas as pd
    target = pd.Timestamp(target_date)

    for suffix in ('_adj', '_raw'):
        cache_file = ohlcv_cache_dir / f'{ticker}{suffix}.parquet'
        if not cache_file.exists():
            continue
        try:
            df = pd.read_parquet(cache_file)
            df['Date'] = pd.to_datetime(df['Date'])
            # Lấy giá ngày target hoặc 1-5 ngày sau (tránh weekend/holiday)
            window = df[(df['Date'] >= target) & (df['Date'] <= target + timedelta(days=7))]
            if not window.empty:
                return float(window.iloc[0]['Close'])
        except Exception as e:
            log.debug(f"  {ticker} cache read failed: {e}")
    return None


# ============================================================================
# METRICS
# ============================================================================

def evaluate_verdict_hit(verdict: str, return_pct: float,
                         thresholds: Dict[str, float] = None) -> bool:
    """
    Xác định verdict tại snapshot t có "đúng" sau N ngày không.

    Mặc định thresholds:
      - STRONG BUY: actual return ≥ +15% → HIT
      - BUY        : actual return ≥ +5%
      - HOLD       : -10% < return < +10%
      - SELL       : return ≤ -5%
      - STRONG SELL: return ≤ -15%
    """
    th = thresholds or {
        'STRONG BUY': 15.0,
        'BUY': 5.0,
        'HOLD_LOWER': -10.0, 'HOLD_UPPER': 10.0,
        'SELL': -5.0,
        'STRONG SELL': -15.0,
    }

    if verdict == 'STRONG BUY':
        return return_pct >= th['STRONG BUY']
    if verdict == 'BUY':
        return return_pct >= th['BUY']
    if verdict == 'HOLD':
        return th['HOLD_LOWER'] < return_pct < th['HOLD_UPPER']
    if verdict == 'SELL':
        return return_pct <= th['SELL']
    if verdict == 'STRONG SELL':
        return return_pct <= th['STRONG SELL']
    return False


def direction_correct(upside_pct: float, actual_return_pct: float,
                      neutral_band: float = 5.0) -> Optional[bool]:
    """
    Verdict direction đúng nếu:
      - upside > +neutral_band và actual > 0
      - upside < -neutral_band và actual < 0
    Returns None nếu upside hoặc actual nằm trong neutral band (không đánh giá).
    """
    if abs(upside_pct) < neutral_band:
        return None
    if abs(actual_return_pct) < 1.0:  # quá flat, không đánh giá
        return None
    return (upside_pct > 0) == (actual_return_pct > 0)


# ============================================================================
# BACKTEST CORE
# ============================================================================

def backtest_snapshot(snapshot: Dict[str, Any], horizon_days: int,
                      ohlcv_cache_dir: Path) -> List[Dict[str, Any]]:
    """
    Backtest một snapshot tại date t: với mỗi ticker, lấy giá tại t+horizon
    và so sánh với prediction.
    """
    snapshot_date = snapshot['_snapshot_date']
    target_date = (datetime.fromisoformat(snapshot_date)
                   + timedelta(days=horizon_days)).strftime('%Y-%m-%d')

    # Skip nếu target_date còn ở tương lai
    if target_date > datetime.now().strftime('%Y-%m-%d'):
        log.debug(f"  Skip {snapshot_date} → {target_date} (future)")
        return []

    results = []
    for signal in snapshot.get('signals', []):
        ticker = signal['ticker']
        predicted_price = signal['fair_value']
        snapshot_price = signal['current_price']
        verdict = signal['verdict']
        upside_pct = signal['upside_pct']
        industry = signal['industry']
        confidence = signal['confidence']

        actual_price = fetch_actual_price(ticker, target_date, ohlcv_cache_dir)
        if actual_price is None:
            continue

        actual_return_pct = (actual_price - snapshot_price) / snapshot_price * 100
        prediction_error_pct = abs(predicted_price - actual_price) / predicted_price * 100

        results.append({
            'ticker': ticker,
            'industry': industry,
            'snapshot_date': snapshot_date,
            'target_date': target_date,
            'snapshot_price': snapshot_price,
            'predicted_fair_value': predicted_price,
            'actual_price': actual_price,
            'predicted_upside_pct': upside_pct,
            'actual_return_pct': actual_return_pct,
            'prediction_error_pct': prediction_error_pct,
            'verdict': verdict,
            'confidence': confidence,
            'verdict_hit': evaluate_verdict_hit(verdict, actual_return_pct),
            'direction_correct': direction_correct(upside_pct, actual_return_pct),
        })

    return results


def run_backtest(archive_dir: Path, ohlcv_cache_dir: Path,
                 horizon_days: int = 90,
                 min_confidence: float = 50) -> Dict[str, Any]:
    """
    Main entry: chạy backtest qua tất cả snapshots, return aggregated metrics.
    """
    log.info(f"Loading snapshots from {archive_dir}")
    snapshots = load_snapshots(archive_dir)
    log.info(f"  Loaded {len(snapshots)} snapshots")

    if len(snapshots) == 0:
        return {
            'error': 'no_snapshots',
            'message': 'Chưa có archived snapshots nào trong archive/. Chạy run_valuation.py vài lần đã.',
        }

    all_results = []
    for snap in snapshots:
        results = backtest_snapshot(snap, horizon_days, ohlcv_cache_dir)
        # Filter low-confidence
        results = [r for r in results if r['confidence'] >= min_confidence]
        all_results.extend(results)
        log.info(f"  Snapshot {snap['_snapshot_date']}: {len(results)} comparisons")

    if len(all_results) == 0:
        return {
            'error': 'insufficient_data',
            'message': (f'Không có snapshot nào đủ tuổi (>={horizon_days} ngày) '
                        f'để so sánh với giá hiện tại. Đợi thêm hoặc giảm --horizon.'),
            'snapshots_loaded': len(snapshots),
        }

    return aggregate_results(all_results, horizon_days, min_confidence)


def aggregate_results(results: List[Dict], horizon_days: int,
                      min_confidence: float) -> Dict[str, Any]:
    """Tổng hợp metrics theo: overall, by_verdict, by_industry."""
    n = len(results)

    # Overall
    direction_results = [r['direction_correct'] for r in results
                         if r['direction_correct'] is not None]
    direction_hit_rate = (sum(direction_results) / len(direction_results) * 100
                          if direction_results else 0)

    verdict_hit_rate = sum(1 for r in results if r['verdict_hit']) / n * 100
    mae_pct = float(np.mean([r['prediction_error_pct'] for r in results]))
    median_error_pct = float(np.median([r['prediction_error_pct'] for r in results]))

    # By verdict
    by_verdict = defaultdict(list)
    for r in results:
        by_verdict[r['verdict']].append(r)

    verdict_stats = {}
    for v, items in by_verdict.items():
        actual_returns = [it['actual_return_pct'] for it in items]
        hits = sum(1 for it in items if it['verdict_hit'])
        verdict_stats[v] = {
            'count': len(items),
            'hit_rate_pct': round(hits / len(items) * 100, 1),
            'mean_actual_return_pct': round(float(np.mean(actual_returns)), 2),
            'median_actual_return_pct': round(float(np.median(actual_returns)), 2),
            'mean_predicted_upside_pct': round(float(np.mean([it['predicted_upside_pct'] for it in items])), 2),
        }

    # By industry
    by_industry = defaultdict(list)
    for r in results:
        by_industry[r['industry']].append(r)

    industry_stats = {}
    for ind, items in by_industry.items():
        if len(items) < 3:
            continue  # cần ít nhất 3 mã để stats có ý nghĩa
        dir_results = [it['direction_correct'] for it in items
                       if it['direction_correct'] is not None]
        dir_acc = sum(dir_results) / len(dir_results) * 100 if dir_results else 0
        errors = [it['prediction_error_pct'] for it in items]
        industry_stats[ind] = {
            'count': len(items),
            'direction_accuracy_pct': round(dir_acc, 1),
            'mean_error_pct': round(float(np.mean(errors)), 1),
            'median_error_pct': round(float(np.median(errors)), 1),
            'verdict_hit_rate_pct': round(
                sum(1 for it in items if it['verdict_hit']) / len(items) * 100, 1
            ),
        }

    # Top wins and losses
    sorted_by_error = sorted(results, key=lambda r: r['prediction_error_pct'])
    top_accurate = sorted_by_error[:5]
    top_inaccurate = sorted_by_error[-5:]

    return {
        'config': {
            'horizon_days': horizon_days,
            'min_confidence': min_confidence,
            'total_comparisons': n,
        },
        'overall': {
            'direction_accuracy_pct': round(direction_hit_rate, 1),
            'verdict_hit_rate_pct': round(verdict_hit_rate, 1),
            'mean_absolute_error_pct': round(mae_pct, 1),
            'median_error_pct': round(median_error_pct, 1),
        },
        'by_verdict': verdict_stats,
        'by_industry': industry_stats,
        'top_accurate': [
            {k: v for k, v in r.items() if k != 'verdict_hit' and k != 'direction_correct'}
            for r in top_accurate
        ],
        'top_inaccurate': [
            {k: v for k, v in r.items() if k != 'verdict_hit' and k != 'direction_correct'}
            for r in top_inaccurate
        ],
    }


# ============================================================================
# PRESENTATION
# ============================================================================

def print_report(metrics: Dict[str, Any]) -> None:
    """In báo cáo backtest ra console với format đẹp."""
    if 'error' in metrics:
        print(f"\n❌ {metrics['message']}\n")
        return

    cfg = metrics['config']
    overall = metrics['overall']

    print("\n" + "=" * 78)
    print(f"  BACKTEST REPORT — Horizon {cfg['horizon_days']} ngày")
    print("=" * 78)
    print(f"  Total comparisons      : {cfg['total_comparisons']}")
    print(f"  Min confidence filter  : {cfg['min_confidence']}%")

    print(f"\n  📊 OVERALL METRICS")
    print(f"     Direction accuracy  : {overall['direction_accuracy_pct']}% "
          f"(verdict đúng hướng)")
    print(f"     Verdict hit rate    : {overall['verdict_hit_rate_pct']}% "
          f"(đúng dải target)")
    print(f"     Mean abs error      : {overall['mean_absolute_error_pct']}% "
          f"(|fair - actual| / fair)")
    print(f"     Median error        : {overall['median_error_pct']}%")

    print(f"\n  🎯 BY VERDICT")
    print(f"     {'Verdict':<13} {'Count':>6} {'Hit Rate':>10} {'Actual Ret':>12} {'Predicted':>12}")
    print(f"     {'-'*13} {'-'*6} {'-'*10} {'-'*12} {'-'*12}")
    order = ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL']
    for v in order:
        if v in metrics['by_verdict']:
            s = metrics['by_verdict'][v]
            print(f"     {v:<13} {s['count']:>6} "
                  f"{s['hit_rate_pct']:>9.1f}% "
                  f"{s['mean_actual_return_pct']:>+11.1f}% "
                  f"{s['mean_predicted_upside_pct']:>+11.1f}%")

    if metrics['by_industry']:
        print(f"\n  🏭 BY INDUSTRY (n ≥ 3)")
        print(f"     {'Industry':<28} {'N':>4} {'Direction':>10} {'Med Error':>10} {'Hit Rate':>10}")
        print(f"     {'-'*28} {'-'*4} {'-'*10} {'-'*10} {'-'*10}")
        sorted_inds = sorted(metrics['by_industry'].items(),
                             key=lambda x: -x[1]['direction_accuracy_pct'])
        for ind, s in sorted_inds:
            print(f"     {ind:<28} {s['count']:>4} "
                  f"{s['direction_accuracy_pct']:>9.1f}% "
                  f"{s['median_error_pct']:>9.1f}% "
                  f"{s['verdict_hit_rate_pct']:>9.1f}%")

    print(f"\n  ✓ TOP 5 MOST ACCURATE")
    for r in metrics['top_accurate']:
        print(f"     {r['ticker']:<5} {r['snapshot_date']} → {r['target_date']}: "
              f"predicted={r['predicted_fair_value']:,.0f}, actual={r['actual_price']:,.0f}, "
              f"error={r['prediction_error_pct']:.1f}%")

    print(f"\n  ✗ TOP 5 LEAST ACCURATE")
    for r in metrics['top_inaccurate']:
        print(f"     {r['ticker']:<5} {r['snapshot_date']} → {r['target_date']}: "
              f"predicted={r['predicted_fair_value']:,.0f}, actual={r['actual_price']:,.0f}, "
              f"error={r['prediction_error_pct']:.1f}%")

    print("\n" + "=" * 78 + "\n")


def save_report(metrics: Dict, output_path: Path) -> None:
    """Save backtest report to JSON for dashboard consumption."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  Backtest report saved: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive-dir', type=str,
                        default='web/data/valuation/archive',
                        help='Thư mục chứa snapshot JSON')
    parser.add_argument('--ohlcv-cache', type=str,
                        default='backend/data/cache',
                        help='Thư mục OHLCV parquet cache')
    parser.add_argument('--horizon', type=int, default=90,
                        help='Số ngày sau snapshot để so sánh giá (default: 90)')
    parser.add_argument('--min-confidence', type=float, default=50,
                        help='Filter signals có confidence >= X (default: 50)')
    parser.add_argument('--output', type=str,
                        default='web/data/valuation/backtest_report.json',
                        help='Output path cho JSON report')
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    ohlcv_cache = Path(args.ohlcv_cache)

    if not archive_dir.exists():
        log.error(f"Archive dir không tồn tại: {archive_dir}")
        return

    metrics = run_backtest(archive_dir, ohlcv_cache,
                          horizon_days=args.horizon,
                          min_confidence=args.min_confidence)

    print_report(metrics)

    output_path = Path(args.output)
    save_report(metrics, output_path)


if __name__ == '__main__':
    main()
