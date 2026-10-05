"""
Chien luoc MA7 x MA25 — 5 tin hieu mua/ban cho co phieu Viet Nam.

Gap = (MA7 - MA25) / ATR14. Chia cho ATR de mot nguong dung chung duoc cho ma
it bien dong (VNM) lan ma bien dong manh (SSI): cung 2.000d chenh lech MA la
"rat cang" voi ma ATR 500d nhung "binh thuong" voi ma ATR 2.000d.

Tin hieu (uu tien tu tren xuong — moi ma chi mang MOT tin hieu):

  THOAT     MA7 cat xuong MA25 trong <= 3 phien (tinh ca hom nay) va van nam
            duoi. Voi ma dang giu: them cat lo cung -7% tu gia mua, va MA7 nam
            duoi MA25 bat ke cat tu bao gio.
  GIAM      MA7 van tren MA25 nhung gia dong cua duoi MA25 kem KL >= 1,3 x TB20.
  CHOT_LOI  Gap vua tao dinh (1-3 phien truoc) o muc >= phan vi 90 cua chinh ma
            do trong 250 phien, va da thu hep lien tuc tu dinh.
  MUA_1     MA7 cat len MA25 1-3 phien truoc, gia dong cua tren MA25 moi phien
            tu luc cat, MA25 khong doc xuong, KL phien cat >= 1,3 x TB20.
  MUA_2     MA7 tren MA25 suot 5 phien, Gap thu hep ve <= 0,5, MA7 vua quay len
            2 phien lien tiep, khong phien nao dong cua duoi MA25, KL nhip chinh
            thap hon KL truoc nhip.

Vi sao khong dung "Gap lon nhat / nho nhat": cuc tri chi biet duoc SAU khi no
qua — khong chay duoc theo thoi gian thuc. Thay bang nguong (phan vi 90, 0,5
ATR) cong dieu kien "da bat dau dao chieu".

Vi sao tin hieu song 1-3 phien: lich chay hang ngay co the hong mot ca; tin
hieu chi song dung mot phien thi mat han. 3 phien cung khop voi T+2 — qua do
la gia da di qua xa diem vao.

Dieu kien loc (chi chan tin hieu MUA, khong chan tin hieu ban — mot ma dang
giu van phai bao duoc khi can thoat du thanh khoan da can):
  - VN-Index dong cua tren MA50 (truyen vao qua `market_ok`)
  - GTGD TB20 >= 10 ty (dung chung base_conditions)
  - Gia tren MA99
  - Khong co su kien quyen trong 5 phien gan nhat (neu caller truyen events)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .indicators_ext import ma
from ..indicators import atr as atr_series, rsi_last
from .. import base_conditions as BC

log = logging.getLogger(__name__)

SIGNALS = ('THOAT', 'GIAM', 'CHOT_LOI', 'MUA_1', 'MUA_2')
BUY_SIGNALS = ('MUA_1', 'MUA_2')

# Sai so cho phep khi so Gap (don vi ATR) — xem CHOT_LOI
EPS = 1e-6

SIGNAL_LABELS = {
    'THOAT': 'Thoat het',
    'GIAM': 'Giam ty trong',
    'CHOT_LOI': 'Chot loi 30-50%',
    'MUA_1': 'Mua - giao cat',
    'MUA_2': 'Mua - nhip chinh',
    'GIU': 'Dang giu - chua co tin hieu',
}

DEFAULT_CONFIG = {
    'fast': 7,
    'slow': 25,
    'trend_ma': 99,
    'atr_period': 14,
    # MA99 can 99 phien; them 31 phien de MUA_2 nhin duoc 5 phien + 20 phien
    # KL nen truoc nhip chinh ma van con MA99 hop le.
    'min_history': 130,
    # Lich su Gap de tinh phan vi. run_daily lay 400 ngay lich ~ 270 phien,
    # tru 25 phien warmup cua MA25 con ~245 diem Gap — nen tran 250, san 120.
    # Duoi 120 diem thi phan vi 90 qua nhieu nhieu, khong ban CHOT_LOI.
    'gap_hist_window': 250,
    'gap_hist_min': 120,
    'gap_pctl': 0.90,
    'signal_max_age': 3,          # tin hieu song toi da 3 phien
    'slow_slope_lookback': 5,     # MA25 "khong doc xuong" so voi 5 phien truoc
    'vol_ma': 20,
    'vol_surge': 1.3,
    'pullback_gap_max': 0.5,
    'pullback_window': 5,
    'turn_up_bars': 2,
    'stop_loss_pct': 0.07,
    'min_avg_value': BC.MIN_AVG_VALUE_20D,
    'corporate_action_lookback_days': 5,
}


@dataclass
class MA725Result:
    ticker: str
    exchange: str
    date: pd.Timestamp
    close: float
    volume: int
    signal: Optional[str]           # mot trong SIGNALS, 'GIU', hoac None
    signal_age: Optional[int]       # so phien tu luc tin hieu hinh thanh
    blocked_by: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    position: Optional[dict] = None  # chi co khi ma nam trong danh muc dang giu

    @property
    def actionable(self) -> bool:
        """Tin hieu ban luon hanh dong duoc; tin hieu mua phai qua het bo loc."""
        if self.signal is None or self.signal == 'GIU':
            return False
        if self.signal in BUY_SIGNALS:
            return not self.blocked_by
        return True

    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'exchange': self.exchange,
            'date': self.date.isoformat() if hasattr(self.date, 'isoformat') else str(self.date),
            'close': self.close,
            'volume': self.volume,
            'signal': self.signal,
            'signal_label': SIGNAL_LABELS.get(self.signal, ''),
            'signal_age': self.signal_age,
            'actionable': self.actionable,
            'blocked_by': ','.join(self.blocked_by),
            **{f'c_{k}': v for k, v in self.checks.items()},
            **{f'm_{k}': v for k, v in self.metrics.items()},
            **{f'p_{k}': v for k, v in (self.position or {}).items()},
        }


# ---------------------------------------------------------------- helpers

def _cross_age(above: pd.Series, direction: str, max_age: int) -> Optional[int]:
    """
    So phien tu lan cat gan nhat (0 = cat hom nay), chi xet `max_age` phien.

    "Cat len" tai bar i: above[i] True va above[i-1] False. Bar co NaN (MA chua
    du du lieu) khong tinh la cat — tranh ban tin hieu gia o doan warmup.
    """
    vals = above.tolist()
    n = len(vals)
    for k in range(0, min(max_age, n - 1)):
        i = n - 1 - k
        cur, prev = vals[i], vals[i - 1]
        if cur is None or prev is None or pd.isna(cur) or pd.isna(prev):
            continue
        if direction == 'up' and cur and not prev:
            return k
        if direction == 'down' and (not cur) and prev:
            return k
    return None


def _avg_volume_before(vol: pd.Series, idx: int, n: int) -> Optional[float]:
    """KL trung binh n phien TRUOC bar idx (khong tinh chinh bar do)."""
    if idx - n < 0:
        return None
    v = float(vol.iloc[idx - n:idx].mean())
    return v if v > 0 else None


def _r(x, nd=2):
    return None if x is None or pd.isna(x) else round(float(x), nd)


# ---------------------------------------------------------------- evaluate

def evaluate(df: pd.DataFrame, ticker: str,
             config: Optional[dict] = None,
             market_ok: Optional[bool] = None,
             events: Optional[list] = None,
             entry_price: Optional[float] = None) -> Optional[MA725Result]:
    """
    Danh gia mot ma tai phien cuoi cua df.

    Args:
        df: OHLCV da dieu chinh (Date, Open, High, Low, Close, Volume[, Exchange,
            StaleCache]), gia theo NGHIN dong nhu bang dien.
        market_ok: True/False = VN-Index tren/duoi MA50; None = khong biet.
            None CHAN tin hieu mua — khong biet thi khong mua.
        events: su kien quyen (corporate_actions) neu caller co.
        entry_price: gia mua (nghin dong) neu ma dang nam trong danh muc.

    Tra None khi khong du du lieu hoac du lieu stale. Tra ket qua voi
    signal=None khi khong co tin hieu (va khong giu ma) — caller tu loc.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    if df is None or len(df) < cfg['min_history']:
        return None
    # Cung luat voi golden_cross/ichimoku: nen cuoi stale la nen cua phien
    # cu mang ngay moi — moi tin hieu tinh tren no deu sai ngay.
    if 'StaleCache' in df.columns and bool(df['StaleCache'].iloc[-1]):
        return None

    df = df.reset_index(drop=True)
    close = df['Close'].astype(float)
    vol = df['Volume'].astype(float)

    ma_f = ma(close, cfg['fast'])
    ma_s = ma(close, cfg['slow'])
    ma_t = ma(close, cfg['trend_ma'])
    atr_v = atr_series(df, cfg['atr_period'])
    # ATR = 0 (ma dung gia nhieu phien) -> Gap vo nghia, de NaN thay vi inf
    gap = (ma_f - ma_s) / atr_v.where(atr_v > 0)

    t = len(df) - 1
    if any(pd.isna(s.iloc[t]) for s in (ma_f, ma_s, ma_t, gap)):
        return None

    # above giu NaN o doan warmup de _cross_age bo qua
    above = (ma_f > ma_s).astype(object).where(ma_f.notna() & ma_s.notna())
    max_age = cfg['signal_max_age']
    vol_n = cfg['vol_ma']
    surge = cfg['vol_surge']

    last_close = float(close.iloc[t])
    is_above = bool(ma_f.iloc[t] > ma_s.iloc[t])
    checks: dict = {}

    # ---------- THOAT: cat xuong
    down_age = _cross_age(above, 'down', max_age)
    exit_cross = down_age is not None and not is_above
    checks['cat_xuong'] = exit_cross

    # ---------- GIAM: dong cua duoi MA25 kem KL lon, MA7 van tren
    # Tim bar gan nhat (trong max_age phien) thoa dieu kien, va moi phien tu do
    # toi nay deu van duoi MA25 — gia da hoi len tren MA25 thi canh bao het han.
    giam_age = None
    if is_above:
        for k in range(0, max_age):
            i = t - k
            avg_v = _avg_volume_before(vol, i, vol_n)
            if (close.iloc[i] < ma_s.iloc[i] and avg_v
                    and vol.iloc[i] >= surge * avg_v):
                if all(close.iloc[j] < ma_s.iloc[j] for j in range(i, t + 1)):
                    giam_age = k
                break
    checks['giam_ty_trong'] = giam_age is not None

    # ---------- CHOT_LOI: Gap vua tao dinh o vung phan vi 90
    hist = gap.iloc[max(0, t - cfg['gap_hist_window']):t].dropna()
    gap_p = float(hist.quantile(cfg['gap_pctl'])) if len(hist) >= cfg['gap_hist_min'] else None
    chot_age = None
    if gap_p is not None and is_above and gap_p > 0:
        # Dinh = Gap lon nhat trong (max_age + 1) phien gan nhat, phai nam truoc
        # hom nay, va Gap giam lien tuc tu dinh toi hom nay.
        window = gap.iloc[t - max_age:t + 1]
        # Lay phien CUOI cung dat max: Gap di ngang 2 phien o dinh roi moi giam
        # thi dinh la phien sau, khong phai phien dau (phien dau -> phien sau
        # khong "giam", luat giam lien tuc tu dinh se loai oan).
        peak_i = int(window[window >= window.max() - EPS].index[-1])
        k = t - peak_i
        # Dinh phai la dinh THAT: phien truoc dinh khong cao hon. Thieu dieu kien
        # nay thi mot nhip Gap giam keo dai se luon co "dinh" o mep cua so (t-3)
        # va ban CHOT_LOI moi ngay suot ca nhip giam.
        # `>` chu khong `>=` P90: chuoi Gap gan nhu hang so (xu huong tang deu)
        # co P90 bang chinh no — bang nhau khong phai la "cang bat thuong".
        # So sanh kem EPS: rolling mean de lai sai so dau phay dong ~1e-14, du
        # de mot chuoi Gap phang tao "dinh" gia (do duoc tren duong tang deu).
        if (1 <= k <= max_age and gap.iloc[peak_i] > gap_p + EPS
                and gap.iloc[peak_i] >= gap.iloc[peak_i - 1] - EPS):
            if all(gap.iloc[j] < gap.iloc[j - 1] - EPS for j in range(peak_i + 1, t + 1)):
                chot_age = k
    checks['chot_loi'] = chot_age is not None

    # ---------- MUA_1: giao cat da xac nhan
    up_age = _cross_age(above, 'up', max_age + 1)
    mua1_age = None
    mua1_detail = {}
    if up_age is not None and 1 <= up_age <= max_age and is_above:
        ci = t - up_age
        still_above = all(bool(ma_f.iloc[j] > ma_s.iloc[j]) for j in range(ci, t + 1))
        closes_ok = all(close.iloc[j] > ma_s.iloc[j] for j in range(ci + 1, t + 1))
        lb = cfg['slow_slope_lookback']
        slope_ok = t - lb >= 0 and ma_s.iloc[t] >= ma_s.iloc[t - lb]
        avg_v = _avg_volume_before(vol, ci, vol_n)
        vol_ok = bool(avg_v) and vol.iloc[ci] >= surge * avg_v
        mua1_detail = {'giu_tren_ma25': closes_ok, 'ma25_khong_giam': bool(slope_ok),
                       'kl_phien_cat': bool(vol_ok)}
        if still_above and closes_ok and slope_ok and vol_ok:
            mua1_age = up_age
    checks['mua_1'] = mua1_age is not None

    # ---------- MUA_2: nhip chinh trong xu huong tang
    w = cfg['pullback_window']
    tu = cfg['turn_up_bars']
    mua2 = False
    if is_above and t - w - vol_n >= 0:
        win = range(t - w + 1, t + 1)
        stay_above = all(bool(ma_f.iloc[j] > ma_s.iloc[j]) for j in win)
        gap_low = float(gap.iloc[t - w + 1:t + 1].min()) <= cfg['pullback_gap_max']
        # "Quay len": tang dung `tu` phien lien tiep, phien truoc do khong tang.
        # Dieu kien sau bien no thanh SU KIEN, khong phai trang thai — tranh
        # bao mua moi ngay trong mot xu huong tang deu.
        rises = all(ma_f.iloc[t - i] > ma_f.iloc[t - i - 1] for i in range(tu))
        was_falling = ma_f.iloc[t - tu] <= ma_f.iloc[t - tu - 1]
        no_close_below = all(close.iloc[j] >= ma_s.iloc[j] for j in win)
        # KL nhip chinh = cac phien trong cua so truoc 2 phien quay len;
        # KL nen = TB20 phien ngay truoc cua so.
        pb_vol = float(vol.iloc[t - w + 1:t - tu + 1].mean())
        base_vol = _avg_volume_before(vol, t - w + 1, vol_n)
        vol_dry = bool(base_vol) and pb_vol < base_vol
        checks.update({'m2_tren_ma25_5p': stay_above, 'm2_gap_thap': gap_low,
                       'm2_ma7_quay_len': rises and was_falling,
                       'm2_khong_dong_duoi_ma25': no_close_below,
                       'm2_kl_can': vol_dry})
        mua2 = stay_above and gap_low and rises and was_falling and no_close_below and vol_dry
    checks['mua_2'] = mua2
    checks.update({f'm1_{k}': v for k, v in mua1_detail.items()})

    # ---------- Danh muc dang giu
    position = None
    stop_hit = False
    if entry_price:
        stop = entry_price * (1 - cfg['stop_loss_pct'])
        stop_hit = last_close <= stop
        position = {'gia_mua': round(float(entry_price), 2),
                    'lai_lo_pct': round((last_close / entry_price - 1) * 100, 2),
                    'gia_cat_lo': round(stop, 2),
                    'cham_cat_lo': stop_hit}

    # ---------- Chon mot tin hieu theo thu tu uu tien
    signal, age = None, None
    if exit_cross:
        signal, age = 'THOAT', down_age
    elif position and (stop_hit or not is_above):
        # Dang giu ma MA7 duoi MA25 (cat tu lau, qua cua so 3 phien) hoac cham
        # cat lo: van phai bao thoat — khong de lot vi tin hieu "het han".
        signal, age = 'THOAT', None
    elif giam_age is not None:
        signal, age = 'GIAM', giam_age
    elif chot_age is not None:
        signal, age = 'CHOT_LOI', chot_age
    elif mua1_age is not None:
        signal, age = 'MUA_1', mua1_age
    elif mua2:
        signal, age = 'MUA_2', 0
    elif position:
        signal = 'GIU'

    # ---------- Bo loc (chi y nghia voi tin hieu mua, nhung luon tinh de hien)
    ctx = BC.context_metrics(df)
    blocked = []
    if market_ok is not True:
        blocked.append('vnindex_duoi_ma50' if market_ok is False else 'khong_ro_vnindex')
    if not BC.passes_liquidity(ctx, cfg['min_avg_value']):
        blocked.append('thanh_khoan_thap')
    if last_close <= float(ma_t.iloc[t]):
        blocked.append('duoi_ma99')
    if events:
        from ..corporate_actions import has_recent_event
        if has_recent_event(events, days=cfg['corporate_action_lookback_days']):
            blocked.append('su_kien_quyen')
    if signal not in BUY_SIGNALS:
        blocked_out = []
    else:
        blocked_out = blocked

    # ---------- Metrics
    from ..price_limits import classify_price_limit, band_for
    exch = str(df['Exchange'].iloc[-1]) if 'Exchange' in df.columns else ''
    limit_info = classify_price_limit(df, exch or None)
    # Giam qua bien do san trong 30 phien = gia chua dieu chinh su kien quyen
    # (bien do HOSE 7% thi gia that khong the giam 10% mot phien).
    band = band_for(exch or None)
    suspicious = bool((close.tail(30).pct_change() < -(band + 0.005)).any())
    vol_avg20 = _avg_volume_before(vol, t, vol_n)

    metrics = {
        'ma7': _r(ma_f.iloc[t]),
        'ma25': _r(ma_s.iloc[t]),
        'ma99': _r(ma_t.iloc[t]),
        'atr14': _r(atr_v.iloc[t], 3),
        'gap': _r(gap.iloc[t]),
        'gap_p90': _r(gap_p),
        'gap_pct': _r((ma_f.iloc[t] / ma_s.iloc[t] - 1) * 100),
        'vol_ratio': _r(vol.iloc[t] / vol_avg20) if vol_avg20 else None,
        'avg_value20_ty': _r(ctx['avg_value20'] / 1e9, 1) if ctx.get('avg_value20') else None,
        'rsi14': _r(rsi_last(close, 14), 1),
        'change_1d_pct': limit_info['change_1d_pct'],
        'limit_status': limit_info['limit_status'],
        'tradable_warning': limit_info['tradable_warning'],
        'suspicious_data': suspicious,
        'cat_lo_goi_y': _r(last_close * (1 - cfg['stop_loss_pct'])) if signal in BUY_SIGNALS else None,
        'filters_failed': ','.join(blocked),
    }

    return MA725Result(
        ticker=ticker,
        exchange=exch,
        date=df['Date'].iloc[-1],
        close=round(last_close, 2),
        volume=int(vol.iloc[t]),
        signal=signal,
        signal_age=age,
        blocked_by=blocked_out,
        checks={k: bool(v) for k, v in checks.items()},
        metrics=metrics,
        position=position,
    )
