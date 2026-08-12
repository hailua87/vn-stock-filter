"""
HIỆU CHỈNH TRỌNG SỐ TIÊU CHÍ — khung nghiên cứu factor
================================================================================
Trả lời câu hỏi: trọng số nào cho 10 tiêu chí Pre-Breakout là TỐI ƯU?

Nguyên tắc thiết kế (vì sao làm thế này chứ không phải "chạy optimizer"):

1. NHÃN LÀ RANK CHÉO, KHÔNG PHẢI LỢI NHUẬN TUYỆT ĐỐI
   Với mỗi phiên, xếp hạng phần trăm lợi nhuận vượt VN-Index trong H phiên tới
   của toàn universe. Việc này tự động khử beta thị trường và khử biến động
   thay đổi theo thời gian. Nếu tối ưu trên lợi nhuận tuyệt đối, mọi tiêu chí
   đều "đúng" trong bull market.

2. CHÂN TRỜI H QUYẾT ĐỊNH KẾT QUẢ NHIỀU HƠN TRỌNG SỐ
   H = 1-5 phiên là vùng ĐẢO CHIỀU ngắn hạn (TTCK VN do cá nhân chi phối nên
   hiệu ứng này rất mạnh); H = 20-60 phiên là vùng MOMENTUM. Cùng một bộ tiêu
   chí có thể có IC trái dấu ở hai khung. Luôn quét nhiều H trước khi chốt.

3. NGƯỠNG Ý NGHĨA PHẢI TÍNH ĐA KIỂM ĐỊNH
   10 tiêu chí × 4 chân trời = 40 phép thử. Bonferroni cho α = 5% ⇒ t ≈ 3,2.
   Dùng ngưỡng t > 2 như thông thường là tự lừa mình.

4. SAI SỐ CHUẨN PHẢI HIỆU CHỈNH CHỒNG LẤN
   Nhãn H phiên khiến IC của các phiên liền kề tự tương quan mạnh. Dùng sai số
   chuẩn Newey-West với lag = H, nếu không t-stat bị thổi phồng ~√H lần.

5. GOM CỤM TRƯỚC KHI PHÂN BỔ
   atr_squeeze và bb_squeeze đo cùng một hiện tượng (ρ ~ 0,6-0,75). Phân bổ
   trọng số ở cấp CỤM rồi mới chia trong cụm — nếu không, một thông tin được
   tính hai lần.

6. SHRINKAGE NẶNG
   Cỡ mẫu thực tế rất nhỏ: với H = 20 phiên, một năm chỉ có ~12 kỳ độc lập.
   Trọng số cuối = 50% từ dữ liệu + 50% từ prior "đều nhau".

Không dùng ML (gradient boosting...) một cách có chủ ý: cỡ mẫu không cho phép,
và tính giải thích được của điểm số là một TÍNH NĂNG SẢN PHẨM, không phải phụ.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .backtest_engine import compute_criteria_matrix
from .criteria import DEFAULT_CRITERIA_WEIGHTS
from .price_units import VND_PER_QUOTE_UNIT

log = logging.getLogger(__name__)


# Chân trời cần quét. 5 và 10 nằm vùng đảo chiều, 20 và 40 nằm vùng momentum.
DEFAULT_HORIZONS = (5, 10, 20, 40)

# Ngưỡng chấp nhận một tiêu chí (xem nguyên tắc 3)
T_STAT_THRESHOLD = 3.0
MIN_IC_MEAN = 0.02
MIN_ICIR = 0.25

# Ngưỡng gom cụm: hai tiêu chí tương quan trên mức này coi như cùng một thông tin
CLUSTER_CORR_THRESHOLD = 0.60

# Tỷ lệ pha trộn giữa trọng số từ dữ liệu và prior đều nhau
DEFAULT_SHRINKAGE = 0.50

# Giả định thanh khoản: chỉ mua được tối đa ngần này khối lượng một phiên.
# Rất nhiều "alpha" trong backtest VN biến mất khi áp ràng buộc này.
MAX_PARTICIPATION_RATE = 0.02


# ════════════════════════════════════════════════════════════════════════
# THỐNG KÊ NỀN (tự cài để không phụ thuộc scipy)
# ════════════════════════════════════════════════════════════════════════

def norm_cdf(x: float) -> float:
    """Hàm phân phối tích luỹ chuẩn."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """
    Nghịch đảo CDF chuẩn — thuật toán hữu tỉ của Acklam, sai số < 1.15e-9.
    Cần cho công thức Deflated Sharpe Ratio.
    """
    if not 0.0 < p < 1.0:
        return float('-inf') if p <= 0 else float('inf')

    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]

    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / \
           (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)


def newey_west_tstat(series: pd.Series, lag: int) -> float:
    """
    t-stat của trung bình chuỗi, hiệu chỉnh tự tương quan kiểu Newey-West.

    Vì sao bắt buộc: IC tính trên nhãn H phiên thì IC của phiên t và t+1 dùng
    chung H-1 phiên dữ liệu tương lai ⇒ tự tương quan cực mạnh. Dùng sai số
    chuẩn thường sẽ thổi phồng t-stat khoảng √H lần — với H = 20 là 4,5 lần,
    đủ để biến nhiễu thành "phát hiện có ý nghĩa thống kê".
    """
    x = pd.Series(series).dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 10:
        return float('nan')

    mean = x.mean()
    dev = x - mean
    gamma0 = float(dev @ dev) / n

    lag = max(0, min(int(lag), n - 1))
    var_nw = gamma0
    for l in range(1, lag + 1):
        gamma_l = float(dev[l:] @ dev[:-l]) / n
        weight = 1.0 - l / (lag + 1.0)          # kernel Bartlett
        var_nw += 2.0 * weight * gamma_l

    if var_nw <= 0:
        return float('nan')
    return mean / math.sqrt(var_nw / n)


def deflated_sharpe_ratio(sharpe: float, n_trials: int, n_obs: int,
                          skew: float = 0.0, kurtosis: float = 3.0) -> float:
    """
    Deflated Sharpe Ratio (Bailey & López de Prado 2014).

    Vì sao cần: nếu bạn thử K cấu hình tham số, Sharpe cao nhất trong K cấu hình
    ĐƯỢC KỲ VỌNG là dương ngay cả khi dữ liệu hoàn toàn ngẫu nhiên. DSR khấu trừ
    đúng phần "may mắn do thử nhiều lần".

    Trả về xác suất Sharpe thật > 0. DSR < 0,95 ⇒ chưa đủ bằng chứng.
    """
    if n_obs < 10 or n_trials < 1:
        return float('nan')

    # Sharpe kỳ vọng cao nhất trong n_trials phép thử độc lập, khi Sharpe thật = 0
    euler = 0.5772156649015329
    if n_trials == 1:
        sr0 = 0.0
    else:
        sr0 = (
            (1 - euler) * norm_ppf(1 - 1.0 / n_trials)
            + euler * norm_ppf(1 - 1.0 / (n_trials * math.e))
        )
        # chuẩn hoá theo độ phân tán của ước lượng Sharpe
        sr0 *= 1.0 / math.sqrt(n_obs)

    denom = 1 - skew * sharpe + (kurtosis - 1) / 4.0 * sharpe ** 2
    if denom <= 0:
        return float('nan')
    z = (sharpe - sr0) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return norm_cdf(z)


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Tương quan hạng Spearman (pandas rank + Pearson, không cần scipy)."""
    df = pd.DataFrame({'a': a, 'b': b}).dropna()
    if len(df) < 5 or df['a'].nunique() < 2 or df['b'].nunique() < 2:
        return float('nan')
    return float(df['a'].rank().corr(df['b'].rank()))


# ════════════════════════════════════════════════════════════════════════
# XÂY PANEL DỮ LIỆU
# ════════════════════════════════════════════════════════════════════════

@dataclass
class PanelSpec:
    horizons: Sequence[int] = DEFAULT_HORIZONS
    min_turnover_vnd: float = 1_000_000_000     # 1 tỷ/phiên — dưới mức này không giao dịch được
    max_participation: float = MAX_PARTICIPATION_RATE
    exclude_limit_moves: bool = True


def build_panel(by_ticker: Dict[str, pd.DataFrame],
                index_df: Optional[pd.DataFrame] = None,
                spec: Optional[PanelSpec] = None,
                config: Optional[dict] = None) -> pd.DataFrame:
    """
    Dựng panel dài: mỗi dòng = (phiên, mã) kèm giá trị 10 tiêu chí và nhãn tương lai.

    Cột nhãn cho mỗi chân trời H:
        fwd_ret_H      : lợi nhuận thực tế (vào giá mở cửa T+1, thoát đóng cửa T+1+H)
        fwd_excess_H   : trừ lợi nhuận VN-Index cùng kỳ
        fwd_rank_H     : phân vị chéo của fwd_excess_H trong cùng phiên (0-1)

    Cột `tradable`: lệnh có khớp được trên thực tế không (thanh khoản + biên độ).
    """
    spec = spec or PanelSpec()
    criteria = list(DEFAULT_CRITERIA_WEIGHTS)

    index_ret = None
    if index_df is not None and not index_df.empty:
        idx = index_df.sort_values('Date').reset_index(drop=True)
        index_ret = idx.set_index('Date')['Close'].astype(float)

    frames = []
    for ticker, raw in by_ticker.items():
        if raw is None or len(raw) < 120:
            continue
        d = raw.sort_values('Date').reset_index(drop=True)
        try:
            matrix = compute_criteria_matrix(d, config)
        except Exception as e:
            log.debug(f"  {ticker}: bỏ qua ({e})")
            continue

        rows = matrix[criteria + ['_eligible']].copy()
        rows['Date'] = d['Date'].to_numpy()
        rows['ticker'] = ticker

        entry = d['Open'].shift(-1)              # vào lệnh giá mở cửa phiên kế tiếp
        rows['entry_price'] = entry.to_numpy()

        # ── Tính khả thi lệnh ──────────────────────────────────────────
        # ĐƠN VỊ: cache OHLCV lưu giá theo đơn vị quote của vnstock (nghìn VND).
        # Phải quy đổi sang VND trước khi so với ngưỡng GTGD, nếu không mọi mã
        # đều bị coi là kém thanh khoản và panel rỗng.
        turnover20 = (d['Close'] * VND_PER_QUOTE_UNIT * d['Volume']).rolling(20).mean()
        tradable = turnover20 >= spec.min_turnover_vnd

        if spec.exclude_limit_moves:
            # Phiên vào lệnh mà giá mở = cao = thấp (trần/sàn cứng, không khớp
            # được khối lượng đáng kể) thì lệnh giả định là không thực hiện được.
            nxt_open = d['Open'].shift(-1)
            nxt_high = d['High'].shift(-1)
            nxt_low = d['Low'].shift(-1)
            locked = (nxt_high - nxt_low).abs() < 1e-9
            tradable = tradable & ~locked.fillna(True)

        rows['tradable'] = tradable.fillna(False).to_numpy()
        rows['turnover20'] = turnover20.to_numpy()

        # ── Nhãn tương lai ─────────────────────────────────────────────
        for h in spec.horizons:
            exit_price = d['Close'].shift(-(1 + h))
            fwd = (exit_price / entry - 1) * 100
            rows[f'fwd_ret_{h}'] = fwd.to_numpy()

        frames.append(rows)

    if not frames:
        return pd.DataFrame()

    panel = pd.concat(frames, ignore_index=True)
    panel = panel[panel['_eligible'] == 1].drop(columns=['_eligible'])
    panel = panel[panel['tradable']].copy()

    # ── Trừ lợi nhuận chỉ số cùng kỳ, rồi xếp hạng chéo theo phiên ──────
    for h in spec.horizons:
        col = f'fwd_ret_{h}'
        if index_ret is not None:
            idx_fwd = (index_ret.shift(-(1 + h)) / index_ret.shift(-1) - 1) * 100
            panel[f'fwd_excess_{h}'] = panel[col] - panel['Date'].map(idx_fwd)
        else:
            # Không có chỉ số: dùng trung vị chéo làm proxy cho lợi nhuận thị trường
            med = panel.groupby('Date')[col].transform('median')
            panel[f'fwd_excess_{h}'] = panel[col] - med

        panel[f'fwd_rank_{h}'] = (
            panel.groupby('Date')[f'fwd_excess_{h}']
            .rank(pct=True)
        )

    return panel.dropna(subset=[f'fwd_excess_{h}' for h in spec.horizons], how='all')


# ════════════════════════════════════════════════════════════════════════
# IC ĐƠN BIẾN
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ICResult:
    criterion: str
    horizon: int
    ic_mean: float
    ic_std: float
    icir: float
    t_stat: float
    hit_rate_pct: float     # % phiên có IC > 0
    n_periods: int
    passes: bool
    reason: str = ''

    def as_dict(self) -> dict:
        return {
            'criterion': self.criterion, 'horizon': self.horizon,
            'ic_mean': round(self.ic_mean, 4), 'ic_std': round(self.ic_std, 4),
            'icir': round(self.icir, 3), 't_stat': round(self.t_stat, 2),
            'hit_rate_pct': round(self.hit_rate_pct, 1),
            'n_periods': self.n_periods, 'passes': self.passes,
            'reason': self.reason,
        }


def cross_sectional_ic(panel: pd.DataFrame, criterion: str, horizon: int,
                       min_names_per_date: int = 20) -> pd.Series:
    """
    Chuỗi IC theo phiên: tương quan hạng giữa tiêu chí và rank lợi nhuận vượt trội.

    Cài đặt vector hoá (không lặp Python qua từng phiên): trên dữ liệu thật
    (~400 mã × 5 năm × 10 tiêu chí × 4 chân trời) bản lặp mất hàng chục phút.
    Spearman = Pearson trên hạng, và Pearson theo nhóm tính được bằng các tổng
    luỹ tích nên gom hết vào groupby-sum.
    """
    label = f'fwd_rank_{horizon}'
    if criterion not in panel.columns or label not in panel.columns:
        return pd.Series(dtype=float)

    df = panel[['Date', criterion, label]].dropna()
    if df.empty:
        return pd.Series(dtype=float)

    # Loại các phiên có quá ít mã — tương quan chéo trên 5 mã là vô nghĩa
    sizes = df.groupby('Date')[criterion].transform('size')
    df = df[sizes >= min_names_per_date]
    if df.empty:
        return pd.Series(dtype=float)

    # Hạng trong từng phiên (ties → hạng trung bình, đúng định nghĩa Spearman)
    x = df.groupby('Date')[criterion].rank()
    y = df.groupby('Date')[label].rank()
    tmp = pd.DataFrame({'Date': df['Date'].to_numpy(),
                        'x': x.to_numpy(), 'y': y.to_numpy()})
    tmp['xy'] = tmp['x'] * tmp['y']
    tmp['xx'] = tmp['x'] ** 2
    tmp['yy'] = tmp['y'] ** 2

    g = tmp.groupby('Date')
    n = g.size()
    sx, sy = g['x'].sum(), g['y'].sum()
    sxy, sxx, syy = g['xy'].sum(), g['xx'].sum(), g['yy'].sum()

    num = n * sxy - sx * sy
    den = np.sqrt((n * sxx - sx ** 2) * (n * syy - sy ** 2))
    ic = (num / den).replace([np.inf, -np.inf], np.nan).dropna()
    return ic.sort_index()


def evaluate_criterion(panel: pd.DataFrame, criterion: str, horizon: int) -> ICResult:
    ic = cross_sectional_ic(panel, criterion, horizon)

    if len(ic) < 30:
        # Phân biệt hai nguyên nhân rất khác nhau — nếu không, báo cáo chỉ hiện
        # "—" và người đọc không biết là thiếu dữ liệu hay tiêu chí hỏng.
        if criterion in panel.columns:
            fire_rate = float(panel[criterion].mean())
            if fire_rate <= 0.001:
                reason = 'tiêu chí KHÔNG BAO GIỜ bật — kiểm tra lại định nghĩa'
            elif fire_rate >= 0.999:
                reason = 'tiêu chí LUÔN bật — không có sức phân biệt, nên chuyển thành veto'
            else:
                reason = f'không đủ số phiên có biến thiên chéo ({len(ic)}<30)'
        else:
            reason = 'không có trong panel'
        return ICResult(criterion, horizon, float('nan'), float('nan'), float('nan'),
                        float('nan'), float('nan'), len(ic), False, reason)

    ic_mean = float(ic.mean())
    ic_std = float(ic.std(ddof=1))
    icir = ic_mean / ic_std if ic_std > 0 else float('nan')
    t_stat = newey_west_tstat(ic, lag=horizon)
    hit_rate = float((ic > 0).mean() * 100)

    reasons = []
    if abs(ic_mean) < MIN_IC_MEAN:
        reasons.append(f'|IC| < {MIN_IC_MEAN}')
    if not math.isnan(icir) and abs(icir) < MIN_ICIR:
        reasons.append(f'|ICIR| < {MIN_ICIR}')
    if math.isnan(t_stat) or abs(t_stat) < T_STAT_THRESHOLD:
        reasons.append(f'|t| < {T_STAT_THRESHOLD} (đã tính đa kiểm định)')

    return ICResult(criterion, horizon, ic_mean, ic_std, icir, t_stat, hit_rate,
                    len(ic), not reasons, '; '.join(reasons))


def evaluate_all(panel: pd.DataFrame,
                 horizons: Sequence[int] = DEFAULT_HORIZONS,
                 criteria: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """Bảng IC cho mọi (tiêu chí × chân trời)."""
    criteria = list(criteria or DEFAULT_CRITERIA_WEIGHTS)
    rows = [evaluate_criterion(panel, c, h).as_dict()
            for h in horizons for c in criteria]
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════════════
# GOM CỤM CHỐNG ĐẾM TRÙNG
# ════════════════════════════════════════════════════════════════════════

def correlation_matrix(panel: pd.DataFrame,
                       criteria: Optional[Sequence[str]] = None) -> pd.DataFrame:
    criteria = [c for c in (criteria or DEFAULT_CRITERIA_WEIGHTS) if c in panel.columns]
    return panel[criteria].corr()


def cluster_criteria(corr: pd.DataFrame,
                     threshold: float = CLUSTER_CORR_THRESHOLD) -> Dict[str, List[str]]:
    """
    Gom cụm phân cấp đơn giản (single linkage trên |ρ|).

    Với ≤ 15 tiêu chí, không cần scipy: union-find trên các cặp vượt ngưỡng là đủ
    và cho kết quả giống single-linkage cắt ở `threshold`.
    """
    names = list(corr.columns)
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            rho = corr.loc[a, b]
            if pd.notna(rho) and abs(rho) >= threshold:
                union(a, b)

    clusters: Dict[str, List[str]] = {}
    for n in names:
        clusters.setdefault(find(n), []).append(n)
    # Đặt tên cụm theo thành viên đầu tiên cho dễ đọc
    return {f'cluster_{i+1}:{members[0]}': sorted(members)
            for i, members in enumerate(clusters.values())}


# ════════════════════════════════════════════════════════════════════════
# TÍNH TRỌNG SỐ
# ════════════════════════════════════════════════════════════════════════

@dataclass
class WeightResult:
    horizon: int
    weights: Dict[str, float]
    clusters: Dict[str, List[str]]
    ic_table: pd.DataFrame
    dropped: List[str]
    shrinkage: float
    total_weight: float
    notes: List[str] = field(default_factory=list)


def calibrate_weights(panel: pd.DataFrame,
                      horizon: int = 20,
                      shrinkage: float = DEFAULT_SHRINKAGE,
                      total_weight: Optional[float] = None,
                      criteria: Optional[Sequence[str]] = None) -> WeightResult:
    """
    Tính trọng số theo quy trình: IC đơn biến → loại tiêu chí yếu → gom cụm →
    phân bổ theo ICIR ở cấp cụm → shrink về prior đều nhau → chuẩn hoá thang điểm.

    `total_weight` mặc định giữ nguyên tổng của DEFAULT_CRITERIA_WEIGHTS (= 10)
    để ngưỡng `--min-score` và toàn bộ dữ liệu archive cũ không đổi ý nghĩa.
    """
    criteria = list(criteria or DEFAULT_CRITERIA_WEIGHTS)
    total_weight = total_weight or sum(DEFAULT_CRITERIA_WEIGHTS.values())
    notes: List[str] = []

    ic_rows = [evaluate_criterion(panel, c, horizon) for c in criteria]
    ic_table = pd.DataFrame([r.as_dict() for r in ic_rows])

    survivors = [r for r in ic_rows if r.passes and r.ic_mean > 0]
    dropped = [r.criterion for r in ic_rows if r not in survivors]

    if not survivors:
        notes.append(
            "KHÔNG tiêu chí nào vượt ngưỡng ý nghĩa. Đây là kết quả HỢP LỆ và "
            "cần được tôn trọng: giữ trọng số đều, coi hệ thống là bộ tạo "
            "watchlist chứ không phải tín hiệu giao dịch."
        )
        return WeightResult(horizon, dict(DEFAULT_CRITERIA_WEIGHTS), {}, ic_table,
                            dropped, shrinkage, total_weight, notes)

    corr = correlation_matrix(panel, [r.criterion for r in survivors])
    clusters = cluster_criteria(corr)
    notes.append(f"{len(survivors)} tiêu chí vượt ngưỡng, gom thành {len(clusters)} cụm")

    # ICIR đại diện cho cụm = trung bình ICIR các thành viên
    icir_by_crit = {r.criterion: abs(r.icir) for r in survivors
                    if not math.isnan(r.icir)}
    cluster_icir = {}
    for cname, members in clusters.items():
        vals = [icir_by_crit.get(m, 0.0) for m in members]
        cluster_icir[cname] = float(np.mean(vals)) if vals else 0.0

    total_icir = sum(cluster_icir.values())
    n_clusters = len(clusters)

    weights = {c: 0.0 for c in criteria}
    for cname, members in clusters.items():
        # Pha trộn: phần từ dữ liệu (ICIR) và phần từ prior đều nhau
        w_data = (cluster_icir[cname] / total_icir) if total_icir > 0 else 1 / n_clusters
        w_prior = 1.0 / n_clusters
        w_cluster = shrinkage * w_data + (1 - shrinkage) * w_prior
        # Chia đều trong cụm — các thành viên đo cùng một thông tin
        for m in members:
            weights[m] = w_cluster / len(members)

    # Chuẩn hoá về đúng thang điểm cũ
    s = sum(weights.values())
    if s > 0:
        weights = {k: round(v / s * total_weight, 3) for k, v in weights.items()}

    notes.append(f"Shrinkage λ = {shrinkage} (50% dữ liệu / 50% prior đều nhau)")
    if dropped:
        notes.append("Bị loại (trọng số 0): " + ', '.join(dropped))

    return WeightResult(horizon, weights, clusters, ic_table, dropped,
                        shrinkage, total_weight, notes)


# ════════════════════════════════════════════════════════════════════════
# WALK-FORWARD CÓ PURGING & EMBARGO
# ════════════════════════════════════════════════════════════════════════

@dataclass
class FoldResult:
    fold: int
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train: int
    n_test: int
    weights: Dict[str, float]
    oos_ic_mean: float
    oos_ic_t: float


def walk_forward(panel: pd.DataFrame,
                 horizon: int = 20,
                 n_folds: int = 5,
                 embargo_days: int = 5,
                 shrinkage: float = DEFAULT_SHRINKAGE) -> Tuple[List[FoldResult], dict]:
    """
    Kiểm định ngoài mẫu bằng cửa sổ mở rộng, có purging và embargo.

    PURGING: loại khỏi tập train mọi quan sát có cửa sổ nhãn (H phiên) chồng lấn
    tập test. Không làm điều này thì mô hình "nhìn thấy" tương lai của tập test
    thông qua nhãn chồng lấn — đây là dạng rò rỉ tinh vi nhất và phổ biến nhất
    trong backtest tài chính.

    EMBARGO: bỏ thêm `embargo_days` phiên ngay sau mốc chia, phòng tự tương quan
    còn sót của chính chuỗi giá.
    """
    dates = np.array(sorted(panel['Date'].unique()))
    if len(dates) < (n_folds + 1) * (horizon + embargo_days) * 2:
        log.warning("Không đủ lịch sử cho walk-forward — kết quả chỉ mang tính tham khảo")

    fold_size = len(dates) // (n_folds + 1)
    if fold_size < 5:
        return [], {'error': 'không đủ dữ liệu'}

    results: List[FoldResult] = []
    for k in range(1, n_folds + 1):
        test_start_i = fold_size * k
        test_end_i = min(fold_size * (k + 1), len(dates) - 1)
        if test_end_i <= test_start_i:
            break

        test_start, test_end = dates[test_start_i], dates[test_end_i]
        # Purge: nhãn của quan sát train phải kết thúc TRƯỚC khi test bắt đầu
        purge_i = max(0, test_start_i - horizon - embargo_days)
        train_end = dates[purge_i]

        train = panel[panel['Date'] <= train_end]
        test = panel[(panel['Date'] >= test_start) & (panel['Date'] <= test_end)]
        if len(train) < 500 or len(test) < 100:
            continue

        wr = calibrate_weights(train, horizon=horizon, shrinkage=shrinkage)

        # Chấm điểm tập test bằng trọng số học từ tập train
        test = test.copy()
        cols = [c for c in wr.weights if c in test.columns]
        test['_score'] = sum(test[c] * wr.weights[c] for c in cols)
        oos_ic = cross_sectional_ic(test, '_score', horizon)

        results.append(FoldResult(
            fold=k, train_end=pd.Timestamp(train_end),
            test_start=pd.Timestamp(test_start), test_end=pd.Timestamp(test_end),
            n_train=len(train), n_test=len(test),
            weights=wr.weights,
            oos_ic_mean=float(oos_ic.mean()) if len(oos_ic) else float('nan'),
            oos_ic_t=newey_west_tstat(oos_ic, horizon) if len(oos_ic) else float('nan'),
        ))

    summary = _summarize_folds(results, horizon)
    return results, summary


def _summarize_folds(folds: List[FoldResult], horizon: int) -> dict:
    if not folds:
        return {'error': 'không có fold hợp lệ'}

    ics = [f.oos_ic_mean for f in folds if not math.isnan(f.oos_ic_mean)]
    if not ics:
        return {'error': 'không tính được IC ngoài mẫu'}

    # Ổn định trọng số: tiêu chí nào đổi dấu/biến động mạnh giữa các fold là nhiễu
    all_crit = sorted({c for f in folds for c in f.weights})
    stability = {}
    for c in all_crit:
        vals = [f.weights.get(c, 0.0) for f in folds]
        mean_w = float(np.mean(vals))
        std_w = float(np.std(vals))
        stability[c] = {
            'mean': round(mean_w, 3),
            'std': round(std_w, 3),
            'cv': round(std_w / mean_w, 2) if mean_w > 0 else None,
            'always_zero': all(v == 0 for v in vals),
        }

    # Sharpe hoá IC ngoài mẫu để tính DSR
    ic_mean = float(np.mean(ics))
    ic_std = float(np.std(ics, ddof=1)) if len(ics) > 1 else 0.0
    sharpe_like = ic_mean / ic_std if ic_std > 0 else 0.0

    return {
        'n_folds': len(folds),
        'oos_ic_mean': round(ic_mean, 4),
        'oos_ic_std': round(ic_std, 4),
        'oos_ic_positive_folds': f"{sum(1 for v in ics if v > 0)}/{len(ics)}",
        'weight_stability': stability,
        'deflated_sharpe_prob': round(
            deflated_sharpe_ratio(sharpe_like, n_trials=len(all_crit) * 4,
                                  n_obs=len(ics)), 3),
        'verdict': _verdict(ic_mean, ics),
    }


def _verdict(ic_mean: float, ics: List[float]) -> str:
    positive_ratio = sum(1 for v in ics if v > 0) / len(ics)
    if ic_mean > 0.02 and positive_ratio >= 0.6:
        return "CÓ tín hiệu ngoài mẫu — đủ cơ sở để triển khai trọng số mới"
    if ic_mean > 0:
        return ("Tín hiệu YẾU và không nhất quán — giữ trọng số đều, "
                "cần thêm dữ liệu hoặc thêm yếu tố mới (RS ngành, khối ngoại)")
    return ("KHÔNG có tín hiệu ngoài mẫu — bộ tiêu chí hiện tại không có edge. "
            "Không nên dùng làm tín hiệu giao dịch.")
