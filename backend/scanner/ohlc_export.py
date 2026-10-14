"""
Chuỗi nến + MA cho màn Chi tiết mã (blueprint v4 §11.1).

Ghi một tệp DÙNG CHUNG `web/data/ohlc/latest.json` thay vì nhét nến vào từng
`latest.json` của 4 chiến lược: cùng một mã hay xuất hiện ở nhiều chiến lược,
nhét vào từng tệp là chép lại 4 lần dữ liệu y hệt. Giao diện chỉ nạp tệp này
khi người đọc mở một mã, nên bảng scan không nặng thêm.

Chỉ xuất những mã CÓ tín hiệu ở ít nhất một chiến lược — toàn bộ universe thì
tệp phình lên vô ích vì màn chi tiết chỉ mở được từ bảng tín hiệu.

Đơn vị: giữ nguyên NGHÌN đồng như `close` trong tín hiệu, để giao diện không
phải đổi đơn vị giữa bảng và biểu đồ.

Schema 2 (10/2026) thêm khối lượng, MA7/MA25, MA20 của khối lượng và MACD
(12, 26, 9) cho ba tầng biểu đồ giá / khối lượng / MACD. Mọi chỉ báo tính trên
TOÀN BỘ lịch sử rồi mới cắt — với MACD điều này còn quan trọng hơn MA: EMA26
khởi động từ 60 phiên sẽ lệch hẳn so với bảng điện.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

SESSIONS = 60
SCHEMA = 2
MA_WINDOWS = (7, 20, 25, 50)
VOL_MA = 20
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
# Cap MA ma man Chi tiet danh dau diem giao cat.
CROSS_PAIRS = ((7, 25), (20, 50))
_OHLC = ('Open', 'High', 'Low', 'Close')


def crosses(fast: pd.Series, slow: pd.Series, sessions: int) -> list:
    """
    Diem giao cat trong `sessions` phien cuoi: [[vi tri trong khung, +1|-1]].

    Tinh tren MA CHUA LAM TRON. Giao dien tu do tren mang da lam tron 2 chu
    so (10 dong) se truot diem cat mot phien moi khi hai duong sat nhau — do
    tren 31 ma ngay 05/10/2026: lech o 6 ma.

    Cung dinh nghia voi strategies/ma7_25.py: "tren" la fast > slow (bang nhau
    tinh la duoi), giao cat la luc trang thai do doi. Phien truoc khi ca hai MA
    co so thi khong tinh.
    """
    valid = fast.notna() & slow.notna()
    above = fast > slow
    flip = valid & valid.shift(1, fill_value=False) & (above != above.shift(1))
    n = len(fast)
    start = max(0, n - sessions)
    return [[i - start, 1 if bool(above.iloc[i]) else -1]
            for i in range(start, n) if bool(flip.iloc[i])]


def macd(close: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW,
         signal: int = MACD_SIGNAL) -> tuple:
    """
    (DIF, DEA, MACD) theo quy uoc bang dien/Binance: DIF = EMA12 - EMA26,
    DEA = EMA9 cua DIF, MACD = DIF - DEA (KHONG nhan 2 nhu mot so app Trung
    Quoc). EMA kieu `adjust=False` (de quy), giong TradingView.

    Chua du `slow` phien thi DIF chua co nghia -> None; DEA can them `signal`
    phien nua.
    """
    c = close.astype(float)
    dif = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    dif = dif.where(pd.Series(range(len(c)), index=c.index) >= slow - 1)
    dea = dif.ewm(span=signal, adjust=False).mean()
    dea = dea.where(pd.Series(range(len(c)), index=c.index) >= slow + signal - 2)
    return dif, dea, dif - dea


def series_for(df: pd.DataFrame, sessions: int = SESSIONS,
               ma_windows: Iterable[int] = MA_WINDOWS) -> Optional[dict]:
    """
    Nến và MA của một mã, cũ → mới.

    MA tính trên TOÀN BỘ lịch sử rồi mới cắt đuôi. Cắt trước rồi mới tính thì
    MA50 của 49 phiên đầu trong khung nhìn sẽ rỗng, dù dữ liệu để tính chúng
    vẫn nằm ngay đó.
    """
    if df is None or df.empty or not all(c in df for c in _OHLC):
        return None
    ma = {f'ma{w}': df['Close'].rolling(w).mean() for w in ma_windows}
    has_vol = 'Volume' in df
    if has_vol:
        vol = df['Volume'].astype(float)
        vma = vol.rolling(VOL_MA).mean()
    dif, dea, hist = macd(df['Close'])
    xs = {f'x{a}_{b}': crosses(df['Close'].rolling(a).mean(), df['Close'].rolling(b).mean(), sessions)
          for a, b in CROSS_PAIRS}

    tail = df.tail(sessions)
    if tail.empty:
        return None
    out = {'dates': [_as_date(d) for d in tail['Date']] if 'Date' in tail else []}
    for col in _OHLC:
        out[col[0].lower()] = _nums(tail[col])   # Open→o, High→h, Low→l, Close→c
    for name, s in ma.items():
        out[name] = _nums(s.tail(sessions))
    if has_vol:
        out['v'] = [None if pd.isna(x) else int(x) for x in vol.tail(sessions)]
        out[f'vma{VOL_MA}'] = [None if pd.isna(x) else int(round(x)) for x in vma.tail(sessions)]
    # 4 chu so: MACD cua ma gia 7 nghin dong chi co bien do ~0,05 — lam tron 2
    # chu so nhu gia se xoa sach histogram.
    out['dif'] = _nums(dif.tail(sessions), 4)
    out['dea'] = _nums(dea.tail(sessions), 4)
    out['macd'] = _nums(hist.tail(sessions), 4)
    out.update(xs)
    return out


def _as_date(v) -> Optional[str]:
    if pd.isna(v):
        return None
    return str(pd.Timestamp(v).date())


def _nums(s: pd.Series, nd: int = 2) -> list:
    """None chứ không phải 0 cho ô thiếu: MA chưa đủ cửa sổ là KHÔNG CÓ số,
    vẽ thành 0 sẽ kéo đường MA sụp xuống đáy biểu đồ."""
    return [None if pd.isna(v) else round(float(v), nd) for v in s]


def build(by_ticker: Dict[str, pd.DataFrame], tickers: Iterable[str],
          sessions: int = SESSIONS) -> Dict[str, dict]:
    want = sorted({t for t in tickers if t})
    out = {}
    for t in want:
        s = series_for(by_ticker.get(t), sessions)
        if s:
            out[t] = s
    return out


def tickers_from(*result_sets) -> set:
    """Gom mã từ hỗn hợp DataFrame kết quả và danh sách object có `.ticker`."""
    found = set()
    for rs in result_sets:
        if rs is None:
            continue
        if isinstance(rs, pd.DataFrame):
            if not rs.empty and 'ticker' in rs:
                found.update(rs['ticker'].tolist())
        else:
            found.update(getattr(r, 'ticker', None) for r in rs)
    found.discard(None)
    return found


def quality_universe(path: Path) -> set:
    """
    Mã trong `web/data/quality/latest.json`.

    Màn Chi tiết mã mở được cho cả mã KHÔNG có tín hiệu kỹ thuật (góc dài hạn
    không phụ thuộc tín hiệu), nên nến cũng phải có cho chúng. Trước đây chỉ
    xuất mã đã công bố tín hiệu, và hậu quả là 34/36 mã bất động sản mở ra thấy
    "Chưa có dữ liệu nến" — đúng nhóm người ta theo dõi dài hạn nhất.

    Đọc tệp đã xuất bản chứ không tự tính lại universe: `run_daily` không biết
    quy tắc chọn rổ của Module B, và hai nơi tự tính sẽ lệch nhau.
    """
    try:
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        return {i['ticker'] for i in (d.get('items') or []) if i.get('ticker')}
    except Exception:
        return set()


def write(path: Path, series: Dict[str, dict], session_date: Optional[str],
          sessions: int = SESSIONS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema': SCHEMA,
        'session_date': session_date,
        'sessions': sessions,
        'price_unit': 'nghin_dong',
        'ma_windows': list(MA_WINDOWS),
        'vol_ma': VOL_MA,
        'macd': [MACD_FAST, MACD_SLOW, MACD_SIGNAL],
        'note': 'MA tính trên toàn bộ lịch sử rồi mới cắt về khung nhìn.',
        'series': series,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    return path
