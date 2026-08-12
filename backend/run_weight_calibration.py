#!/usr/bin/env python3
"""
Hiệu chỉnh trọng số tiêu chí Pre-Breakout từ dữ liệu lịch sử.

QUY TRÌNH (đọc kỹ trước khi tin kết quả):
  1. Dựng panel (phiên × mã) với nhãn = rank chéo lợi nhuận vượt VN-Index
  2. Bảng IC cho mọi tiêu chí × chân trời, t-stat hiệu chỉnh Newey-West
  3. Ma trận tương quan + gom cụm chống đếm trùng
  4. Trọng số: ICIR cấp cụm, shrink 50% về prior đều nhau
  5. Walk-forward có purging/embargo → IC NGOÀI MẪU + độ ổn định trọng số

CẢNH BÁO VỀ CỠ MẪU:
  Với H = 20 phiên, một năm chỉ cho ~12 kỳ độc lập. Cần 5-7 năm dữ liệu mới
  kết luận được. Nếu cache chỉ có ~400 phiên, hãy chạy backfill_history.py
  trước — kết quả trên 1,6 năm dữ liệu KHÔNG đủ để đổi trọng số production.

Usage:
    python backend/run_weight_calibration.py
    python backend/run_weight_calibration.py --horizon 20 --apply
    python backend/run_weight_calibration.py --horizons 5,10,20,40 --json-out out.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.weight_calibration import (
    PanelSpec, build_panel, evaluate_all, correlation_matrix, cluster_criteria,
    calibrate_weights, walk_forward, DEFAULT_HORIZONS, T_STAT_THRESHOLD,
)
from scanner.criteria import DEFAULT_CRITERIA_WEIGHTS
from run_backtest import load_universe_from_cache, VNINDEX_CACHE, CACHE_DIR

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('calibration')


def print_ic_table(ic_df: pd.DataFrame, horizons):
    print("\n" + "=" * 92)
    print("  BẢNG INFORMATION COEFFICIENT (IC chéo theo phiên, t-stat Newey-West)")
    print("=" * 92)
    print(f"  Ngưỡng đạt: |IC| > 0,02  và  |ICIR| > 0,25  và  |t| > {T_STAT_THRESHOLD}")
    print(f"  (t > {T_STAT_THRESHOLD} chứ không phải 2,0 vì đang kiểm định "
          f"{len(DEFAULT_CRITERIA_WEIGHTS)} tiêu chí × {len(horizons)} chân trời)")

    for h in horizons:
        sub = ic_df[ic_df['horizon'] == h].sort_values('ic_mean', ascending=False)
        print(f"\n  ── Chân trời H = {h} phiên " + "─" * 55)
        print(f"     {'Tiêu chí':<18} {'IC':>8} {'ICIR':>7} {'t-stat':>8} "
              f"{'%IC>0':>7} {'N':>6}  {'Đạt':>5}")
        print(f"     {'-'*18} {'-'*8} {'-'*7} {'-'*8} {'-'*7} {'-'*6}  {'-'*5}")
        for _, r in sub.iterrows():
            mark = '  ✓' if r['passes'] else '  ·'
            ic = f"{r['ic_mean']:+.4f}" if pd.notna(r['ic_mean']) else '—'
            icir = f"{r['icir']:+.2f}" if pd.notna(r['icir']) else '—'
            t = f"{r['t_stat']:+.2f}" if pd.notna(r['t_stat']) else '—'
            hit = f"{r['hit_rate_pct']:.0f}%" if pd.notna(r['hit_rate_pct']) else '—'
            print(f"     {r['criterion']:<18} {ic:>8} {icir:>7} {t:>8} "
                  f"{hit:>7} {r['n_periods']:>6}  {mark:>5}")


def print_clusters(corr: pd.DataFrame, clusters: dict):
    print("\n" + "=" * 92)
    print("  GOM CỤM TIÊU CHÍ (chống đếm trùng một thông tin)")
    print("=" * 92)
    for name, members in clusters.items():
        if len(members) > 1:
            pairs = []
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    if a in corr.columns and b in corr.columns:
                        pairs.append(f"{a}~{b}={corr.loc[a, b]:+.2f}")
            print(f"     ● {', '.join(members)}")
            if pairs:
                print(f"       tương quan: {'  '.join(pairs)}")
        else:
            print(f"     ○ {members[0]} (độc lập)")


def print_weights(wr, current: dict):
    print("\n" + "=" * 92)
    print(f"  TRỌNG SỐ ĐỀ XUẤT (H = {wr.horizon} phiên)")
    print("=" * 92)
    print(f"     {'Tiêu chí':<18} {'Hiện tại':>10} {'Đề xuất':>10} {'Thay đổi':>12}")
    print(f"     {'-'*18} {'-'*10} {'-'*10} {'-'*12}")
    for crit in sorted(wr.weights, key=lambda k: -wr.weights[k]):
        old = current.get(crit, 0.0)
        new = wr.weights[crit]
        delta = new - old
        note = '  ← loại bỏ' if new == 0 else ''
        print(f"     {crit:<18} {old:>10.2f} {new:>10.2f} {delta:>+11.2f}{note}")
    print(f"     {'-'*18} {'-'*10} {'-'*10}")
    print(f"     {'TỔNG':<18} {sum(current.values()):>10.2f} "
          f"{sum(wr.weights.values()):>10.2f}   (giữ nguyên thang điểm)")

    if wr.notes:
        print("\n     Ghi chú:")
        for n in wr.notes:
            print(f"       • {n}")


def print_walk_forward(folds, summary):
    print("\n" + "=" * 92)
    print("  KIỂM ĐỊNH NGOÀI MẪU — walk-forward có purging & embargo")
    print("=" * 92)
    if 'error' in summary:
        print(f"     ⚠️  {summary['error']}")
        return

    print(f"     {'Fold':<6} {'Test từ':<12} {'đến':<12} {'N test':>8} "
          f"{'IC OOS':>9} {'t-stat':>8}")
    print(f"     {'-'*6} {'-'*12} {'-'*12} {'-'*8} {'-'*9} {'-'*8}")
    for f in folds:
        print(f"     {f.fold:<6} {str(f.test_start.date()):<12} "
              f"{str(f.test_end.date()):<12} {f.n_test:>8} "
              f"{f.oos_ic_mean:>+9.4f} {f.oos_ic_t:>+8.2f}")

    print(f"\n     IC ngoài mẫu trung bình : {summary['oos_ic_mean']:+.4f}")
    print(f"     Số fold IC dương        : {summary['oos_ic_positive_folds']}")
    print(f"     Deflated Sharpe (xác suất): {summary['deflated_sharpe_prob']}")

    print(f"\n     ĐỘ ỔN ĐỊNH TRỌNG SỐ (CV cao = nhiễu, không đáng tin)")
    print(f"     {'Tiêu chí':<18} {'TB':>8} {'Độ lệch':>9} {'CV':>7}")
    print(f"     {'-'*18} {'-'*8} {'-'*9} {'-'*7}")
    for crit, s in sorted(summary['weight_stability'].items(),
                          key=lambda kv: -kv[1]['mean']):
        if s['always_zero']:
            continue
        cv = f"{s['cv']:.2f}" if s['cv'] is not None else '—'
        flag = '  ⚠ không ổn định' if s['cv'] and s['cv'] > 0.5 else ''
        print(f"     {crit:<18} {s['mean']:>8.2f} {s['std']:>9.2f} {cv:>7}{flag}")

    print(f"\n     ➤ KẾT LUẬN: {summary['verdict']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cache-dir', type=str, default=str(CACHE_DIR))
    p.add_argument('--limit', type=int, default=None)
    p.add_argument('--horizons', type=str,
                   default=','.join(map(str, DEFAULT_HORIZONS)))
    p.add_argument('--horizon', type=int, default=20,
                   help='Chân trời dùng để chốt trọng số')
    p.add_argument('--shrinkage', type=float, default=0.5)
    p.add_argument('--folds', type=int, default=5)
    p.add_argument('--min-turnover', type=float, default=1e9,
                   help='GTGD trung bình 20 phiên tối thiểu (VND)')
    p.add_argument('--json-out', type=str, default=None)
    p.add_argument('--apply', action='store_true',
                   help='Ghi trọng số vào backend/data/criteria_weights.json')
    args = p.parse_args()

    horizons = [int(h) for h in args.horizons.split(',')]

    log.info("Đọc OHLCV cache...")
    by_ticker = load_universe_from_cache(Path(args.cache_dir), args.limit)
    if not by_ticker:
        log.error("Cache rỗng — chạy run_daily.py hoặc backfill_history.py trước")
        sys.exit(1)

    index_df = None
    if VNINDEX_CACHE.exists():
        index_df = pd.read_parquet(VNINDEX_CACHE)
        index_df['Date'] = pd.to_datetime(index_df['Date'])

    n_sessions = max(len(d) for d in by_ticker.values())
    log.info(f"  {len(by_ticker)} mã, tối đa {n_sessions} phiên")
    if n_sessions < 750:
        log.warning(
            f"⚠️  Chỉ có ~{n_sessions/250:.1f} năm dữ liệu. Với H=20 phiên, một năm "
            f"chỉ cho ~12 kỳ độc lập → KHÔNG đủ để đổi trọng số production. "
            f"Hãy chạy backfill_history.py (khuyến nghị 5-7 năm)."
        )

    log.info("Dựng panel + tính nhãn tương lai...")
    spec = PanelSpec(horizons=horizons, min_turnover_vnd=args.min_turnover)
    panel = build_panel(by_ticker, index_df, spec)
    if panel.empty:
        log.error("Panel rỗng — kiểm tra ngưỡng thanh khoản hoặc độ dài lịch sử")
        sys.exit(1)
    log.info(f"  Panel: {len(panel):,} quan sát, {panel['Date'].nunique()} phiên, "
             f"{panel['ticker'].nunique()} mã")

    ic_df = evaluate_all(panel, horizons)
    print_ic_table(ic_df, horizons)

    corr = correlation_matrix(panel)
    clusters = cluster_criteria(corr)
    print_clusters(corr, clusters)

    wr = calibrate_weights(panel, horizon=args.horizon, shrinkage=args.shrinkage)
    print_weights(wr, DEFAULT_CRITERIA_WEIGHTS)

    log.info("Chạy walk-forward (purging + embargo)...")
    folds, summary = walk_forward(panel, horizon=args.horizon,
                                  n_folds=args.folds, shrinkage=args.shrinkage)
    print_walk_forward(folds, summary)

    payload = {
        'horizon_chosen': args.horizon,
        'horizons_scanned': horizons,
        'shrinkage': args.shrinkage,
        'n_observations': len(panel),
        'n_sessions': int(panel['Date'].nunique()),
        'n_tickers': int(panel['ticker'].nunique()),
        'ic_table': ic_df.to_dict('records'),
        'clusters': clusters,
        'current_weights': DEFAULT_CRITERIA_WEIGHTS,
        'suggested_weights': wr.weights,
        'dropped': wr.dropped,
        'walk_forward': summary,
        'notes': wr.notes,
    }

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                       encoding='utf-8')
        log.info(f"  Báo cáo → {out}")

    if args.apply:
        # Chốt chặn: không cho phép áp trọng số khi kiểm định ngoài mẫu không đạt.
        oos_ok = (summary.get('oos_ic_mean', 0) or 0) > 0.02
        if not oos_ok:
            log.error(
                "❌ TỪ CHỐI áp trọng số: IC ngoài mẫu không đạt ngưỡng 0,02. "
                "Áp trọng số fit trong mẫu mà không có xác nhận ngoài mẫu chính là "
                "định nghĩa của overfitting."
            )
            sys.exit(2)

        target = Path(__file__).resolve().parent / 'data' / 'criteria_weights.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            'version': pd.Timestamp.now().strftime('%Y%m%d'),
            'horizon': args.horizon,
            'weights': wr.weights,
            'oos_ic_mean': summary.get('oos_ic_mean'),
            'calibrated_on': {'n_obs': len(panel),
                              'n_sessions': int(panel['Date'].nunique())},
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        log.info(f"✓ Đã ghi trọng số → {target}")
        log.info("  Nhớ chạy shadow 3 tháng (champion/challenger) trước khi thay chính thức.")


if __name__ == '__main__':
    main()
