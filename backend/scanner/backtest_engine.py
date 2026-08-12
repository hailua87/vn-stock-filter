"""
BACKTEST ENGINE — bản viết lại cho đúng thực tế giao dịch Việt Nam
================================================================================
Bản cũ (scanner/backtest.py) tự đánh lừa theo 5 cách:

  1. `ret = (max_close / entry - 1)` — đó là Maximum Favorable Excursion, tức
     lợi nhuận nếu bán ĐÚNG ĐỈNH trong 5 phiên. Không ai làm được.
  2. Không có T+2: ở VN mua phiên T thì sớm nhất T+2 mới bán được. Đo "chạm
     mục tiêu trong 5 phiên" mà bỏ qua ràng buộc này là thổi phồng hit rate.
  3. Không phí: ~0,2-0,3% khứ hồi + thuế bán 0,1%.
  4. Không benchmark: hit rate 62% vô nghĩa nếu 58% mã bất kỳ cũng tăng 5%
     trong cùng giai đoạn. Phải so với base rate và với VN-Index.
  5. Hiệu năng: `for date: for ticker: evaluate(toàn bộ lịch sử)` = 125.000 lần
     tính lại chỉ báo cho 250 phiên × 500 mã ⇒ hàng giờ, nên chưa từng chạy nổi.

Bản này:
  - Tính chỉ báo MỘT LẦN cho cả chuỗi, lấy tín hiệu theo mask (nhanh hơn ~100×)
  - Mô phỏng lệnh thật: vào lệnh giá MỞ CỬA phiên T+1 (không phải giá đóng cửa
    phiên có tín hiệu — đó là look-ahead), nắm giữ tối thiểu T+2, thoát theo
    stop/target/hết hạn
  - Trừ phí và thuế
  - Báo cáo ALPHA so với VN-Index cùng kỳ nắm giữ, và base rate của toàn universe
  - Tính information coefficient của TỪNG tiêu chí để hiệu chỉnh trọng số
    (thay cho việc đặt tay tất cả = 1)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .indicators import atr, rsi, obv, bollinger_width, obv_normalized_change
from .criteria import DEFAULT_CONFIG, DEFAULT_CRITERIA_WEIGHTS

log = logging.getLogger(__name__)


# Chi phí giao dịch thực tế tại VN (2026)
FEE_BUY_PCT = 0.0015          # phí mua ~0,15%
FEE_SELL_PCT = 0.0015         # phí bán ~0,15%
TAX_SELL_PCT = 0.001          # thuế TNCN chuyển nhượng 0,1%
ROUND_TRIP_COST = FEE_BUY_PCT + FEE_SELL_PCT + TAX_SELL_PCT   # ~0,4%

# T+2: mua phiên T, chứng khoán về tài khoản T+2 → sớm nhất T+2 mới bán được.
SETTLEMENT_DAYS = 2


@dataclass
class Trade:
    ticker: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str          # target | stop | timeout
    holding_days: int
    gross_return_pct: float
    net_return_pct: float     # đã trừ phí + thuế
    benchmark_return_pct: float
    alpha_pct: float
    score: float
    rating: str
    scores: dict = field(default_factory=dict)


@dataclass
class BacktestReport:
    trades: pd.DataFrame
    n_trades: int
    win_rate_pct: float
    mean_net_return_pct: float
    median_net_return_pct: float
    mean_alpha_pct: float
    alpha_win_rate_pct: float          # % lệnh thắng benchmark
    base_rate_pct: float               # % mã bất kỳ đạt cùng ngưỡng lợi nhuận
    edge_vs_base_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    by_rating: dict
    criteria_ic: dict                  # information coefficient từng tiêu chí
    suggested_weights: dict
    config: dict

    def summary_lines(self) -> List[str]:
        return [
            f"Số lệnh                : {self.n_trades}",
            f"Tỷ lệ thắng            : {self.win_rate_pct:.1f}%",
            f"Base rate (mã bất kỳ)  : {self.base_rate_pct:.1f}%",
            f"EDGE so với base rate  : {self.edge_vs_base_rate_pct:+.1f} điểm %",
            f"Lợi nhuận TB (net)     : {self.mean_net_return_pct:+.2f}%",
            f"Lợi nhuận trung vị     : {self.median_net_return_pct:+.2f}%",
            f"ALPHA TB vs VN-Index   : {self.mean_alpha_pct:+.2f}%",
            f"% lệnh thắng benchmark : {self.alpha_win_rate_pct:.1f}%",
            f"Profit factor          : {self.profit_factor:.2f}",
            f"Max drawdown           : {self.max_drawdown_pct:.1f}%",
        ]


# ────────────────────────────────────────────────────────────────────────
# Vector hoá: tính toàn bộ tiêu chí cho MỌI phiên trong một lần
# ────────────────────────────────────────────────────────────────────────

def compute_criteria_matrix(df: pd.DataFrame, config: Optional[dict] = None) -> pd.DataFrame:
    """
    Trả về DataFrame cùng độ dài `df`, mỗi cột là một tiêu chí (0/1) tại phiên đó.

    Đây là điểm khác biệt cốt lõi so với bản cũ: chỉ báo được tính một lần trên
    toàn chuỗi thay vì gọi lại `evaluate()` cho từng phiên với toàn bộ lịch sử.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    d = df.sort_values('Date').reset_index(drop=True).copy()

    close, high, low, vol = d['Close'], d['High'], d['Low'], d['Volume']

    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    vol_ma20 = vol.rolling(20).mean()
    atr14 = atr(d, 14)
    atr_pct = atr14 / close * 100
    rsi14 = rsi(close, 14)
    bbw = bollinger_width(close, 20)
    high20 = high.rolling(20).max()
    obv_series = obv(close, vol)

    out = pd.DataFrame(index=d.index)

    # C1 — nén biến động theo ATR
    atr_avg20 = atr_pct.rolling(20).mean().shift(1)
    out['atr_squeeze'] = (atr_pct < atr_avg20 * cfg['atr_squeeze_ratio']).astype(int)

    # C2 — Bollinger width ở nhóm thấp nhất 60 phiên
    bbw_q = bbw.rolling(60).quantile(cfg['bbw_squeeze_quantile'])
    out['bb_squeeze'] = (bbw <= bbw_q).astype(int)

    # C3 — sát đỉnh 20 phiên nhưng chưa vượt
    dist_high = (high20 - close) / high20 * 100
    out['near_high20'] = ((dist_high > 0) & (dist_high <= cfg['near_high_pct'])).astype(int)

    # C4 — tích luỹ âm thầm: OBV ròng >= N phiên khối lượng, giá chưa chạy
    obv_days = (obv_series - obv_series.shift(10)) / vol_ma20.replace(0, np.nan)
    price_chg_10 = close.pct_change(10)
    out['stealth_accum'] = ((obv_days >= cfg['stealth_obv_days_min'])
                            & (price_chg_10 < cfg['stealth_price_chg_max'])).astype(int)

    # C5 — khối lượng tăng
    vol5 = vol.rolling(5).mean()
    out['vol_surge'] = (vol5 > vol_ma20 * cfg['vol_surge_ratio']).astype(int)

    # C6 — đóng cửa nửa trên biên độ >= 3/5 phiên
    rng = (high - low).replace(0, np.nan)
    upper = ((close - low) / rng >= cfg['upper_close_threshold']).astype(int)
    out['upper_close'] = (upper.rolling(5).sum() >= cfg['upper_close_min_days']).astype(int)

    # C7 — MA10 > MA20 và MA20 hướng lên
    out['ma_align'] = ((ma10 > ma20) & (ma20 >= ma20.shift(5))).astype(int)

    # C8 — RSI vùng lành mạnh
    out['rsi_zone'] = ((rsi14 >= cfg['rsi_lower']) & (rsi14 <= cfg['rsi_upper'])).astype(int)

    # C9 — pocket pivot: khối lượng hôm nay > khối lượng lớn nhất của các phiên giảm
    #
    # min_periods=1 là BẮT BUỘC: `down_vol` là NaN ở mọi phiên tăng, nên cửa sổ
    # 10 phiên hiếm khi có đủ 10 giá trị không-NaN. Với min_periods mặc định
    # (= window), kết quả gần như luôn NaN ⇒ tiêu chí không bao giờ bật.
    is_down = (close < close.shift(1))
    down_vol = vol.where(is_down)
    max_down_vol_10 = down_vol.rolling(10, min_periods=1).max().shift(1)
    out['pocket_pivot'] = ((close > close.shift(1))
                           & (vol > max_down_vol_10)).astype(int)

    # C10 — không gap down mạnh trong 5 phiên
    gap_down = (d['Open'] < close.shift(1) * (1 - cfg['gap_down_threshold']))
    recent_gap = gap_down.rolling(5, min_periods=1).max().fillna(0).astype(bool)
    out['no_gap_down'] = (~recent_gap).astype(int)

    out = out.fillna(0).astype(int)

    # Điều kiện lọc cơ bản (thanh khoản + đủ lịch sử)
    liquid = vol.rolling(20).mean() >= cfg['min_avg_volume']
    warmup = pd.Series(np.arange(len(d)) >= cfg['min_history_days'], index=d.index)
    out['_eligible'] = (liquid & warmup).fillna(False).astype(int)
    out['Date'] = d['Date']
    return out


def _weighted_score(matrix: pd.DataFrame, weights: dict) -> pd.Series:
    cols = [c for c in matrix.columns if c in weights]
    return sum(matrix[c] * weights[c] for c in cols)


# ────────────────────────────────────────────────────────────────────────
# Mô phỏng lệnh
# ────────────────────────────────────────────────────────────────────────

def _simulate_trade(d: pd.DataFrame, signal_idx: int,
                    target_pct: float, stop_pct: float,
                    max_holding_days: int) -> Optional[dict]:
    """
    Mô phỏng một lệnh từ tín hiệu tại `signal_idx`.

    Quy tắc bám thực tế:
      - Vào lệnh ở giá MỞ CỬA phiên kế tiếp. Dùng giá đóng cửa của chính phiên
        có tín hiệu là look-ahead: lúc biết tín hiệu thì phiên đã đóng rồi.
      - Không được bán trước T+2 (SETTLEMENT_DAYS) kể cả khi chạm target/stop.
      - Trong phiên, ưu tiên kiểm tra STOP trước TARGET (giả định bảo thủ: nếu
        cả hai cùng bị chạm trong một phiên thì coi như thua).
    """
    entry_idx = signal_idx + 1
    if entry_idx >= len(d):
        return None

    entry_price = float(d['Open'].iloc[entry_idx])
    if entry_price <= 0:
        return None

    target_price = entry_price * (1 + target_pct)
    stop_price = entry_price * (1 - stop_pct)

    last_idx = min(entry_idx + max_holding_days, len(d) - 1)
    for i in range(entry_idx, last_idx + 1):
        held = i - entry_idx
        can_sell = held >= SETTLEMENT_DAYS       # ràng buộc T+2

        if can_sell:
            if float(d['Low'].iloc[i]) <= stop_price:
                return {'exit_idx': i, 'exit_price': stop_price, 'reason': 'stop'}
            if float(d['High'].iloc[i]) >= target_price:
                return {'exit_idx': i, 'exit_price': target_price, 'reason': 'target'}

    return {'exit_idx': last_idx,
            'exit_price': float(d['Close'].iloc[last_idx]),
            'reason': 'timeout'}


def _benchmark_return(index_close: Optional[pd.Series],
                      index_dates: Optional[pd.Series],
                      start_date, end_date) -> float:
    """Lợi nhuận VN-Index trong đúng khoảng nắm giữ của lệnh."""
    if index_close is None or index_dates is None:
        return 0.0
    mask_start = index_dates >= start_date
    mask_end = index_dates <= end_date
    if not mask_start.any() or not mask_end.any():
        return 0.0
    try:
        p0 = float(index_close[mask_start].iloc[0])
        p1 = float(index_close[mask_end].iloc[-1])
    except (IndexError, ValueError):
        return 0.0
    if p0 <= 0:
        return 0.0
    return (p1 / p0 - 1) * 100


def run_backtest(by_ticker: Dict[str, pd.DataFrame],
                 index_df: Optional[pd.DataFrame] = None,
                 min_score: float = 6.0,
                 target_pct: float = 0.08,
                 stop_pct: float = 0.05,
                 max_holding_days: int = 20,
                 weights: Optional[dict] = None,
                 config: Optional[dict] = None,
                 min_gap_days: int = 10) -> BacktestReport:
    """
    Chạy backtest trên toàn universe.

    Args:
        by_ticker: {ticker: DataFrame OHLCV} — đã sort theo Date
        index_df: VN-Index để tính alpha
        min_score: ngưỡng điểm để mở lệnh
        target_pct / stop_pct: mục tiêu và cắt lỗ (tính từ giá vào lệnh)
        max_holding_days: tối đa số phiên nắm giữ
        min_gap_days: khoảng cách tối thiểu giữa 2 lệnh cùng mã, tránh đếm
                      trùng một sóng thành nhiều lệnh
    """
    weights = weights or DEFAULT_CRITERIA_WEIGHTS
    max_score = sum(weights.values())

    index_close = index_dates = None
    if index_df is not None and not index_df.empty:
        idx = index_df.sort_values('Date').reset_index(drop=True)
        index_close, index_dates = idx['Close'], idx['Date']

    trades: List[Trade] = []
    base_rate_hits = 0
    base_rate_total = 0

    for ticker, raw in by_ticker.items():
        if raw is None or len(raw) < 80:
            continue
        d = raw.sort_values('Date').reset_index(drop=True)

        try:
            matrix = compute_criteria_matrix(d, config)
        except Exception as e:
            log.debug(f"  {ticker}: bỏ qua ({e})")
            continue

        score = _weighted_score(matrix, weights)
        eligible = matrix['_eligible'].astype(bool)
        signal_mask = eligible & (score >= min_score)

        last_entry_idx = -10_000
        for signal_idx in np.flatnonzero(signal_mask.to_numpy()):
            signal_idx = int(signal_idx)
            if signal_idx - last_entry_idx < min_gap_days:
                continue        # cùng một sóng, không mở lệnh chồng
            if signal_idx + 1 + SETTLEMENT_DAYS >= len(d):
                continue        # không đủ phiên để mô phỏng cho hết

            sim = _simulate_trade(d, signal_idx, target_pct, stop_pct, max_holding_days)
            if sim is None:
                continue
            last_entry_idx = signal_idx

            entry_idx = signal_idx + 1
            entry_price = float(d['Open'].iloc[entry_idx])
            exit_price = sim['exit_price']
            gross = (exit_price / entry_price - 1) * 100
            net = gross - ROUND_TRIP_COST * 100

            entry_date = d['Date'].iloc[entry_idx]
            exit_date = d['Date'].iloc[sim['exit_idx']]
            bench = _benchmark_return(index_close, index_dates, entry_date, exit_date)

            row_scores = {c: int(matrix[c].iloc[signal_idx])
                          for c in weights if c in matrix.columns}
            total = float(score.iloc[signal_idx])
            pct = total / max_score if max_score else 0
            rating = 'A+' if pct >= 0.8 else 'A' if pct >= 0.6 else 'B' if pct >= 0.4 else 'C'

            trades.append(Trade(
                ticker=ticker,
                signal_date=d['Date'].iloc[signal_idx],
                entry_date=entry_date,
                entry_price=round(entry_price, 2),
                exit_date=exit_date,
                exit_price=round(exit_price, 2),
                exit_reason=sim['reason'],
                holding_days=sim['exit_idx'] - entry_idx,
                gross_return_pct=round(gross, 2),
                net_return_pct=round(net, 2),
                benchmark_return_pct=round(bench, 2),
                alpha_pct=round(net - bench, 2),
                score=round(total, 2),
                rating=rating,
                scores=row_scores,
            ))

        # BASE RATE: với MỌI phiên hợp lệ (không cần tín hiệu), tỷ lệ đạt target
        # trong cùng khung thời gian là bao nhiêu? Không có con số này thì
        # "win rate 62%" hoàn toàn vô nghĩa.
        eligible_idx = np.flatnonzero(eligible.to_numpy())
        for i in eligible_idx[::max_holding_days] if len(eligible_idx) else []:
            i = int(i)
            if i + 1 + SETTLEMENT_DAYS >= len(d):
                continue
            sim = _simulate_trade(d, i, target_pct, stop_pct, max_holding_days)
            if sim is None:
                continue
            base_rate_total += 1
            if sim['reason'] == 'target':
                base_rate_hits += 1

    return _build_report(trades, weights, base_rate_hits, base_rate_total, {
        'min_score': min_score,
        'max_score': max_score,
        'target_pct': target_pct,
        'stop_pct': stop_pct,
        'max_holding_days': max_holding_days,
        'settlement_days': SETTLEMENT_DAYS,
        'round_trip_cost_pct': ROUND_TRIP_COST * 100,
        'min_gap_days': min_gap_days,
    })


def _build_report(trades: List[Trade], weights: dict,
                  base_hits: int, base_total: int, config: dict) -> BacktestReport:
    if not trades:
        return BacktestReport(
            trades=pd.DataFrame(), n_trades=0, win_rate_pct=0, mean_net_return_pct=0,
            median_net_return_pct=0, mean_alpha_pct=0, alpha_win_rate_pct=0,
            base_rate_pct=0, edge_vs_base_rate_pct=0, profit_factor=0,
            max_drawdown_pct=0, by_rating={}, criteria_ic={},
            suggested_weights=dict(weights), config=config,
        )

    df = pd.DataFrame([{
        'ticker': t.ticker, 'signal_date': t.signal_date, 'entry_date': t.entry_date,
        'entry': t.entry_price, 'exit_date': t.exit_date, 'exit': t.exit_price,
        'reason': t.exit_reason, 'holding_days': t.holding_days,
        'gross_pct': t.gross_return_pct, 'net_pct': t.net_return_pct,
        'bench_pct': t.benchmark_return_pct, 'alpha_pct': t.alpha_pct,
        'score': t.score, 'rating': t.rating, **t.scores,
    } for t in trades]).sort_values('entry_date').reset_index(drop=True)

    wins = df[df['net_pct'] > 0]['net_pct']
    losses = df[df['net_pct'] <= 0]['net_pct']
    profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float('inf')

    # Đường vốn giả định: mỗi lệnh cùng tỷ trọng, tuần tự theo thời gian
    equity = (1 + df['net_pct'] / 100).cumprod()
    drawdown = (equity / equity.cummax() - 1) * 100

    base_rate = (base_hits / base_total * 100) if base_total else 0.0
    target_hit_rate = (df['reason'] == 'target').mean() * 100

    by_rating = {}
    for rating, grp in df.groupby('rating'):
        by_rating[rating] = {
            'n': len(grp),
            'win_rate_pct': round((grp['net_pct'] > 0).mean() * 100, 1),
            'mean_net_pct': round(grp['net_pct'].mean(), 2),
            'mean_alpha_pct': round(grp['alpha_pct'].mean(), 2),
        }

    criteria_ic = _criteria_information_coefficient(df, weights)
    suggested = _suggest_weights(criteria_ic, weights)

    return BacktestReport(
        trades=df,
        n_trades=len(df),
        win_rate_pct=round((df['net_pct'] > 0).mean() * 100, 1),
        mean_net_return_pct=round(df['net_pct'].mean(), 2),
        median_net_return_pct=round(df['net_pct'].median(), 2),
        mean_alpha_pct=round(df['alpha_pct'].mean(), 2),
        alpha_win_rate_pct=round((df['alpha_pct'] > 0).mean() * 100, 1),
        base_rate_pct=round(base_rate, 1),
        edge_vs_base_rate_pct=round(target_hit_rate - base_rate, 1),
        profit_factor=round(profit_factor, 2) if profit_factor != float('inf') else float('inf'),
        max_drawdown_pct=round(drawdown.min(), 1) if len(drawdown) else 0.0,
        by_rating=by_rating,
        criteria_ic=criteria_ic,
        suggested_weights=suggested,
        config=config,
    )


def _criteria_information_coefficient(df: pd.DataFrame, weights: dict) -> dict:
    """
    Information coefficient của từng tiêu chí = chênh lệch alpha trung bình giữa
    nhóm có tiêu chí (=1) và nhóm không có (=0).

    Đây chính là dữ liệu cần để hiệu chỉnh DEFAULT_CRITERIA_WEIGHTS thay vì đặt
    tay tất cả = 1. Tiêu chí có IC âm là đang LÀM HẠI kết quả.
    """
    ic = {}
    for crit in weights:
        if crit not in df.columns:
            continue
        on = df[df[crit] == 1]['alpha_pct']
        off = df[df[crit] == 0]['alpha_pct']
        if len(on) < 10 or len(off) < 10:
            ic[crit] = {'ic': None, 'n_on': len(on), 'n_off': len(off),
                        'note': 'không đủ mẫu'}
            continue
        ic[crit] = {
            'ic': round(float(on.mean() - off.mean()), 2),
            'n_on': len(on),
            'n_off': len(off),
            'alpha_on': round(float(on.mean()), 2),
            'alpha_off': round(float(off.mean()), 2),
        }
    return ic


def _suggest_weights(criteria_ic: dict, current: dict) -> dict:
    """
    Gợi ý trọng số tỷ lệ thuận với IC dương, chuẩn hoá để tổng bằng tổng cũ
    (giữ nguyên thang điểm, không phá vỡ ngưỡng min_score và dữ liệu archive).

    Tiêu chí IC <= 0 nhận trọng số 0 kèm khuyến nghị xem xét loại bỏ.
    """
    positives = {k: v['ic'] for k, v in criteria_ic.items()
                 if v.get('ic') is not None and v['ic'] > 0}
    if not positives:
        return dict(current)

    total_ic = sum(positives.values())
    total_weight = sum(current.values())
    suggested = {k: 0.0 for k in current}
    for k, ic_val in positives.items():
        suggested[k] = round(ic_val / total_ic * total_weight, 2)
    return suggested


def print_report(report: BacktestReport) -> None:
    print("\n" + "=" * 78)
    print("  BACKTEST REPORT — mô phỏng có T+2, phí và benchmark")
    print("=" * 78)

    cfg = report.config
    print(f"  Ngưỡng điểm      : {cfg['min_score']}/{cfg['max_score']}")
    print(f"  Mục tiêu / cắt lỗ: +{cfg['target_pct']*100:.0f}% / -{cfg['stop_pct']*100:.0f}%")
    print(f"  Nắm giữ tối đa   : {cfg['max_holding_days']} phiên (T+{cfg['settlement_days']} mới bán được)")
    print(f"  Chi phí khứ hồi  : {cfg['round_trip_cost_pct']:.2f}%")

    if report.n_trades == 0:
        print("\n  ⚠️  Không có lệnh nào — hạ min_score hoặc kiểm tra dữ liệu đầu vào\n")
        return

    print(f"\n  📊 KẾT QUẢ")
    for line in report.summary_lines():
        print(f"     {line}")

    print(f"\n  🎯 THEO XẾP HẠNG")
    print(f"     {'Rating':<8} {'N':>5} {'Win rate':>10} {'Net TB':>10} {'Alpha TB':>10}")
    print(f"     {'-'*8} {'-'*5} {'-'*10} {'-'*10} {'-'*10}")
    for rating in ['A+', 'A', 'B', 'C']:
        s = report.by_rating.get(rating)
        if s:
            print(f"     {rating:<8} {s['n']:>5} {s['win_rate_pct']:>9.1f}% "
                  f"{s['mean_net_pct']:>+9.2f}% {s['mean_alpha_pct']:>+9.2f}%")

    print(f"\n  🔬 INFORMATION COEFFICIENT TỪNG TIÊU CHÍ")
    print(f"     (chênh lệch alpha giữa nhóm CÓ và KHÔNG có tiêu chí)")
    print(f"     {'Tiêu chí':<18} {'IC':>8} {'n(1)':>7} {'n(0)':>7}")
    print(f"     {'-'*18} {'-'*8} {'-'*7} {'-'*7}")
    ranked = sorted(report.criteria_ic.items(),
                    key=lambda kv: (kv[1].get('ic') is None, -(kv[1].get('ic') or 0)))
    for crit, s in ranked:
        ic_str = f"{s['ic']:+.2f}" if s.get('ic') is not None else '—'
        print(f"     {crit:<18} {ic_str:>8} {s.get('n_on', 0):>7} {s.get('n_off', 0):>7}")

    print(f"\n  ⚖️  TRỌNG SỐ GỢI Ý (thay cho việc đặt tay tất cả = 1)")
    for crit, w in sorted(report.suggested_weights.items(), key=lambda kv: -kv[1]):
        flag = '  ← cân nhắc loại bỏ' if w == 0 else ''
        print(f"     {crit:<18} {w:>5.2f}{flag}")

    print("\n" + "=" * 78 + "\n")
