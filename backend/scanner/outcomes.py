"""
Sổ theo dõi kết quả: tín hiệu sau N phiên lãi hay lỗ so với thị trường.

Hợp đồng dữ liệu đầy đủ ở `docs/outcomes-contract.md` — chốt TRƯỚC khi viết file
này. Bốn quyết định quan trọng nhất, nhắc lại vì chúng quyết định con số có
nghĩa hay không:

1. Một dòng = (chiến lược, mã, phiên VÀO), và phiên vào là phiên ĐẦU TIÊN của
   một chuỗi liên tiếp. MCH có tín hiệu 20 phiên liền; đếm mỗi phiên là một lần
   vào thì một mã chiếm 20 quan sát gần như trùng nhau và lấn át thống kê.

2. Giá vào và giá ra lấy từ CÙNG một chuỗi đã điều chỉnh. Trường `close` trong
   bản lưu là giá tại thời điểm đó, chưa điều chỉnh cho sự kiện quyền xảy ra
   sau — trộn hai gốc sẽ biến một lần chia cổ tức thành khoản lỗ.

3. Luôn kèm `excess` so với VN-Index. "Sau 20 phiên +3%" vô nghĩa nếu thị
   trường cùng kỳ +5%.

4. Thiếu dữ liệu thì LOẠI và đếm riêng, không thay bằng 0.

Đây KHÔNG phải backtest: không mô phỏng lệnh, không phí, không trượt giá.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Callable, Dict, List, Optional

import pandas as pd

SCHEMA = 1
HORIZONS = (5, 10, 20)

# Cùng danh sách với streaks.py — bản lưu nằm ở đâu.
STRATEGY_DIRS = {
    'pre_breakout': 'archive',
    'golden_cross_long': 'golden_cross_long/archive',
    'golden_cross_short': 'golden_cross_short/archive',
    'ichimoku': 'ichimoku/archive',
}


def sessions_from(archive_dir: Path) -> List[tuple]:
    """[(ngày, {mã}), ...] cũ → mới. Bản lưu hỏng thì BỎ QUA phiên đó."""
    if not Path(archive_dir).is_dir():
        return []
    out = []
    for p in sorted(x for x in Path(archive_dir).glob('*.json') if x.stem != 'index'):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((p.stem, {s.get('ticker') for s in (d.get('signals') or [])
                             if s.get('ticker')}))
    return out


def entries_from(sessions: List[tuple]) -> List[tuple]:
    """
    [(mã, phiên vào), ...] — CHỈ phiên đầu của mỗi chuỗi liên tiếp.

    Mã ra rồi vào lại tính là hai lần vào: đó là hai lần tín hiệu thật sự phát
    ra. Nhưng 20 phiên liền nhau chỉ là MỘT lần vào.
    """
    out, prev = [], set()
    for day, tks in sessions:
        for t in sorted(tks - prev):
            out.append((t, day))
        prev = tks
    return out


def _close_series(df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    """Chuỗi Close theo ngày (chuỗi ký tự), đã sắp xếp. None nếu không dùng được."""
    if df is None or getattr(df, 'empty', True):
        return None
    if 'Date' not in df or 'Close' not in df:
        return None
    s = df[['Date', 'Close']].copy()
    s['Date'] = pd.to_datetime(s['Date']).dt.strftime('%Y-%m-%d')
    s = s.drop_duplicates('Date').sort_values('Date').set_index('Date')['Close']
    return s if len(s) else None


def _forward(series: pd.Series, day: str, n: int):
    """
    (giá tại `day`, giá sau `n` PHIÊN của chính chuỗi này, ngày ra).

    Trả (None, None, None) khi không có `day`, hoặc chưa đủ n phiên phía sau.
    """
    idx = series.index
    pos = idx.get_indexer([day])[0] if day in idx else -1
    if pos < 0:
        return None, None, None
    if pos + n >= len(idx):
        return float(series.iloc[pos]), None, None
    return float(series.iloc[pos]), float(series.iloc[pos + n]), idx[pos + n]


def _index_return(index_s: Optional[pd.Series], d0: str, d1: str) -> Optional[float]:
    """
    Lợi suất VN-Index giữa HAI NGÀY LỊCH của mã, không phải theo số phiên của
    index — hai bên có thể lệch phiên.

    Ngày không có trong chuỗi index thì lấy phiên gần nhất TRƯỚC đó; không có
    phiên nào trước đó thì trả None chứ không đoán.
    """
    if index_s is None or not d0 or not d1:
        return None
    def at(d):
        prior = index_s.index[index_s.index <= d]
        return float(index_s.loc[prior[-1]]) if len(prior) else None
    a, b = at(d0), at(d1)
    if a is None or b is None or a == 0:
        return None
    return (b - a) / a


def build_strategy(sessions: List[tuple], price_of: Callable[[str], Optional[pd.DataFrame]],
                   index_s: Optional[pd.Series],
                   horizons=HORIZONS) -> dict:
    """Sổ cho MỘT chiến lược. Không đọc file, không gọi mạng."""
    rows, skip = [], {'no_price': 0, 'no_entry_bar': 0}
    for ticker, day in entries_from(sessions):
        s = _close_series(price_of(ticker))
        if s is None:
            skip['no_price'] += 1
            continue
        entry = None
        exits = {}
        for n in horizons:
            e0, e1, d1 = _forward(s, day, n)
            if e0 is None:
                break
            entry = e0
            if e1 is None or e0 == 0:
                continue          # chưa đủ n phiên — để trống, KHÔNG thay bằng 0
            ret = (e1 - e0) / e0
            idx_ret = _index_return(index_s, day, d1)
            exits[str(n)] = {'ret': round(ret, 4),
                             'excess': None if idx_ret is None else round(ret - idx_ret, 4)}
        if entry is None:
            skip['no_entry_bar'] += 1
            continue
        rows.append({'ticker': ticker, 'date': day, 'entry': round(entry, 2),
                     'exits': exits})

    by_h = {}
    for n in horizons:
        k = str(n)
        rets = [r['exits'][k]['ret'] for r in rows if k in r['exits']]
        exc = [r['exits'][k]['excess'] for r in rows
               if k in r['exits'] and r['exits'][k]['excess'] is not None]
        by_h[k] = {
            'n': len(rets),
            'incomplete': len(rows) - len(rets),
            # Trung vị chứ không phải trung bình: một mã tăng 300% kéo trung
            # bình lên và làm cả chiến lược trông tốt.
            'median_ret': round(median(rets), 4) if rets else None,
            'median_excess': round(median(exc), 4) if exc else None,
            'hit_rate': round(sum(1 for x in exc if x > 0) / len(exc), 3) if exc else None,
            'n_excess': len(exc),
        }
    return {'entries': len(rows), 'skipped': skip, 'by_horizon': by_h, 'rows': rows}


def build(web_dir: Path, price_of: Callable[[str], Optional[pd.DataFrame]],
          index_df: Optional[pd.DataFrame] = None,
          horizons=HORIZONS, now: Optional[datetime] = None,
          strategies: Optional[Dict[str, str]] = None) -> dict:
    web_dir = Path(web_dir)
    index_s = _close_series(index_df)
    dirs = strategies if strategies is not None else STRATEGY_DIRS
    out = {}
    for name, rel in dirs.items():
        out[name] = build_strategy(sessions_from(web_dir / rel), price_of,
                                   index_s, horizons)
    return {
        'schema': SCHEMA,
        'generated_at': (now or datetime.now()).isoformat(timespec='seconds'),
        'horizons': list(horizons),
        'benchmark': 'VNINDEX' if index_s is not None else None,
        'note': ('Một dòng = một LẦN VÀO (phiên đầu của chuỗi liên tiếp), không '
                 'phải mỗi phiên có tín hiệu. `excess` là phần hơn/kém VN-Index '
                 'cùng khoảng ngày. KHÔNG phải backtest: không phí, không trượt '
                 'giá, không mô phỏng lệnh. Xem docs/outcomes-contract.md.'),
        'strategies': out,
    }


def write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    return path


def summary(payload: dict):
    for name, s in payload['strategies'].items():
        h = s['by_horizon'].get(str(payload['horizons'][-1]), {})
        me = h.get('median_excess')
        hr = h.get('hit_rate')
        yield (f"  {name:<20} {s['entries']:>4} lần vào | "
               f"{payload['horizons'][-1]} phiên: n={h.get('n', 0):>4} "
               f"trung vị vượt chỉ số {'—' if me is None else f'{me:+.2%}'} "
               f"| thắng {'—' if hr is None else f'{hr:.0%}'}")
