"""
Chuỗi nến + MA cho màn Chi tiết mã (blueprint v3 §11.1).

Ghi một tệp DÙNG CHUNG `web/data/ohlc/latest.json` thay vì nhét nến vào từng
`latest.json` của 4 chiến lược: cùng một mã hay xuất hiện ở nhiều chiến lược,
nhét vào từng tệp là chép lại 4 lần dữ liệu y hệt. Giao diện chỉ nạp tệp này
khi người đọc mở một mã, nên bảng scan không nặng thêm.

Chỉ xuất những mã CÓ tín hiệu ở ít nhất một chiến lược — toàn bộ universe thì
tệp phình lên vô ích vì màn chi tiết chỉ mở được từ bảng tín hiệu.

Đơn vị: giữ nguyên NGHÌN đồng như `close` trong tín hiệu, để giao diện không
phải đổi đơn vị giữa bảng và biểu đồ.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

SESSIONS = 60
MA_WINDOWS = (20, 50)
_OHLC = ('Open', 'High', 'Low', 'Close')


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

    tail = df.tail(sessions)
    if tail.empty:
        return None
    out = {'dates': [_as_date(d) for d in tail['Date']] if 'Date' in tail else []}
    for col in _OHLC:
        out[col[0].lower()] = _nums(tail[col])   # Open→o, High→h, Low→l, Close→c
    for name, s in ma.items():
        out[name] = _nums(s.tail(sessions))
    return out


def _as_date(v) -> Optional[str]:
    if pd.isna(v):
        return None
    return str(pd.Timestamp(v).date())


def _nums(s: pd.Series) -> list:
    """None chứ không phải 0 cho ô thiếu: MA chưa đủ cửa sổ là KHÔNG CÓ số,
    vẽ thành 0 sẽ kéo đường MA sụp xuống đáy biểu đồ."""
    return [None if pd.isna(v) else round(float(v), 2) for v in s]


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


def write(path: Path, series: Dict[str, dict], session_date: Optional[str],
          sessions: int = SESSIONS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema': 1,
        'session_date': session_date,
        'sessions': sessions,
        'price_unit': 'nghin_dong',
        'ma_windows': list(MA_WINDOWS),
        'note': 'MA tính trên toàn bộ lịch sử rồi mới cắt về khung nhìn.',
        'series': series,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    return path
