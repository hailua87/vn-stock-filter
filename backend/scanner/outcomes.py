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


def _measure(pairs: List[tuple], price_of: Callable[[str], Optional[pd.DataFrame]],
             index_s: Optional[pd.Series], horizons=HORIZONS) -> dict:
    """
    Đo một tập (mã, ngày vào) cho trước. Tín hiệu thật và giả dược đều đi qua
    ĐÚNG hàm này — nếu hai bên dùng code khác nhau thì chênh lệch có thể đến từ
    code chứ không từ dữ liệu, và cả phép thử mất nghĩa.
    """
    rows, skip = [], {'no_price': 0, 'no_entry_bar': 0}
    for ticker, day in pairs:
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


def build_strategy(sessions: List[tuple], price_of: Callable[[str], Optional[pd.DataFrame]],
                   index_s: Optional[pd.Series], horizons=HORIZONS) -> dict:
    """Sổ cho MỘT chiến lược. Không đọc file, không gọi mạng."""
    return _measure(entries_from(sessions), price_of, index_s, horizons)


# ─── Phép thử giả dược ──────────────────────────────────────────────────────
#
# Vì sao bắt buộc phải có: lượt 29/09 cho cả bốn chiến lược đều ÂM so với
# VN-Index ở mọi chân trời (pre_breakout −2,65% sau 20 phiên, thắng 34%). Nhìn
# thì như chiến lược không hiệu quả. Nhưng có một cách giải thích khác:
#
#     VN-Index là chỉ số bình quân gia quyền theo VỐN HOÁ. Nếu nhóm vốn hoá
#     lớn dẫn dắt thị trường, thì MÃ TRUNG VỊ BẤT KỲ cũng thua chỉ số — không
#     cần chiến lược nào sai. Rổ sau khi lọc GTGD vẫn chủ yếu là mã vừa và nhỏ.
#
# Nếu đúng vậy thì −2,65% không phải điểm trừ của pre_breakout; nó là điểm trừ
# của việc không mua VIC, VCB, FPT.
#
# Giả dược phân xử: cùng NGÀY, cùng RỔ, nhưng mã chọn NGẪU NHIÊN.
#   giả dược ≈ −2,6%  ->  chiến lược TRUNG TÍNH, và cái cần sửa là mốc so sánh
#   giả dược ≈  0%    ->  chiến lược thật sự âm
#
# Khớp NGÀY là điểm mấu chốt: lấy ngày ngẫu nhiên nữa thì pha thị trường trở
# thành biến thứ hai và phép thử mất nghĩa.
MIN_AVG_VALUE_20D = 10_000_000_000.0     # khớp base_conditions.MIN_AVG_VALUE_20D
PLACEBO_PER_ENTRY = 3                    # ba đối chứng mỗi lần vào, cho biên hẹp hơn


def _eligible(price_of, universe, day: str, min_value: float,
              cache: dict) -> List[str]:
    """
    Mã ĐỦ ĐIỀU KIỆN VÀO RỔ tại `day`: có giá phiên đó và GTGD TB20 >= ngưỡng.

    Phải lọc thanh khoản, không lấy bừa cả 500 mã: tín hiệu chỉ phát ra từ rổ
    sau điều kiện nền (500 -> ~113 mã), nên đối chứng lấy từ cả 500 sẽ gồm mã
    kém thanh khoản — vốn có hành vi giá khác hẳn — và phép thử lại lệch.
    """
    if day in cache:
        return cache[day]
    out = []
    for t in universe:
        df = price_of(t)
        if df is None or getattr(df, 'empty', True):
            continue
        if 'Close' not in df or 'Volume' not in df:
            continue
        d = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        pos = d.searchsorted(day)
        if pos >= len(d) or d.iloc[pos] != day or pos < 19:
            continue
        w = df.iloc[pos - 19:pos + 1]
        # quote_to_vnd: giá nguồn theo NGHÌN đồng (xem scanner/price_units.py)
        val = float((w['Close'] * 1000.0 * w['Volume']).mean())
        if val >= min_value:
            out.append(t)
    cache[day] = out
    return out


def placebo_strategy(sessions: List[tuple], price_of, universe: List[str],
                     index_s, horizons=HORIZONS, per_entry=PLACEBO_PER_ENTRY,
                     min_value=MIN_AVG_VALUE_20D, seed=20260929) -> dict:
    """
    Cùng thước đo, nhưng mã chọn NGẪU NHIÊN trong rổ đủ điều kiện của CHÍNH
    ngày đó, và LOẠI những mã có tín hiệu phiên đó — để đối chứng là "mã không
    có tín hiệu", đúng thứ cần so.
    """
    import random

    by_day = {day: tks for day, tks in sessions}
    picks, cache = [], {}
    for ticker, day in entries_from(sessions):
        pool = [t for t in _eligible(price_of, universe, day, min_value, cache)
                if t not in by_day.get(day, set())]
        if not pool:
            continue
        # Hạt giống suy từ (ngày, mã) nên kết quả KHÔNG đổi theo thứ tự vòng lặp
        # — dựng lại lúc nào cũng ra cùng con số.
        rnd = random.Random(f'{seed}:{day}:{ticker}')
        k = min(per_entry, len(pool))
        for t in rnd.sample(pool, k):
            picks.append((t, day))

    out = _measure(picks, price_of, index_s, horizons)
    out['draws_per_entry'] = per_entry
    out['seed'] = seed
    return out


MIN_CHO_CI = 30          # duoi muc nay thi bootstrap cung khong cuu duoc
CI_LO, CI_HI = 2.5, 97.5  # khoang 95%, khong phai 90%


def median_gap_ci(a, b, rounds=2000, seed=20260929, lo=CI_LO, hi=CI_HI,
                  block=None):
    """
    Khoảng tin cậy 95% cho CHÊNH LỆCH trung vị giữa tín hiệu và giả dược,
    bằng BOOTSTRAP KHỐI theo ngày.

    `a`, `b`: list các cặp (ngày_vào, giá_trị). Giá trị phải là `excess` —
    cùng đại lượng với con số được báo cáo.

    Vì sao bắt buộc có khoảng: chênh lệch đo được chỉ cỡ phần mười phần trăm.
    Báo một con số như thế trần trụi là mời người đọc hiểu nó thành kết luận,
    trong khi với độ phân tán của lợi suất cổ phiếu nó có thể không khác 0.

    ──────────────────────────────────────────────────────────────────────
    VÌ SAO KHỐI, KHÔNG PHẢI LẤY MẪU TỪNG DÒNG

    Bản trước lấy mẫu từng lần vào một cách độc lập. Các lần vào ở đây KHÔNG
    độc lập, theo hai trục:

      · THỜI GIAN — hai lần vào cách nhau 3 phiên thì cửa sổ 20 phiên của
        chúng dùng chung 17 ngày giá. Chúng gần như cùng một quan sát.
      · CẮT NGANG — mọi lần vào trong CÙNG một phiên cùng chịu một cú chuyển
        động của thị trường. Trừ chỉ số đã bớt phần lớn, nhưng phần dư theo
        ngày vẫn còn.

    Lấy mẫu từng dòng coi 1816 lần vào là 1816 quan sát độc lập, trong khi số
    quan sát thực tế nhỏ hơn nhiều. Hệ quả: khoảng tin cậy HẸP GIẢ, và một
    chênh lệch không có thật trông như "khác 0".

    Cách chữa: lấy mẫu theo KHỐI NGÀY LIÊN TIẾP, độ dài khối = kỳ quan sát.
    Trong một khối, mọi quan hệ phụ thuộc được giữ nguyên; giữa hai khối cách
    xa nhau thì cửa sổ không còn chồng lấn.

    LẤY MẪU CẶP: cùng một bộ khối ngày dùng cho CẢ tín hiệu lẫn giả dược.
    Hai bên vốn đo trên cùng những phiên đó, nên bắt cặp giữ đúng cấu trúc và
    loại phần chuyển động chung của thị trường khỏi chênh lệch.
    """
    import random
    if len(a) < MIN_CHO_CI or len(b) < MIN_CHO_CI:
        return None

    nhom_a, nhom_b = {}, {}
    for ngay, v in a:
        nhom_a.setdefault(ngay, []).append(v)
    for ngay, v in b:
        nhom_b.setdefault(ngay, []).append(v)
    ngay_sx = sorted(set(nhom_a) | set(nhom_b))
    D = len(ngay_sx)

    L = max(1, int(block or 1))
    # Can it nhat HAI khoi, neu khong thi moi lan lay mau deu ra gan nhu cung
    # mot tap va khoang tin cay hep gia — dung loai sai dang di chua.
    if D < 2 * L:
        return {'gap_lo': None, 'gap_hi': None, 'rounds': 0, 'includes_zero': None,
                'block': L, 'n_dates': D, 'level': hi - lo,
                'ly_do': f'chi co {D} ngay vao, can >= {2 * L} de chia khoi {L} phien'}

    rnd = random.Random(seed)
    so_khoi = -(-D // L)                    # tran chia
    dau_toi_da = D - L
    gaps = []
    for _ in range(rounds):
        ngay_lay = []
        for _ in range(so_khoi):
            d0 = rnd.randint(0, dau_toi_da)
            ngay_lay.extend(ngay_sx[d0:d0 + L])
        ra = [v for ng in ngay_lay for v in nhom_a.get(ng, ())]
        rb = [v for ng in ngay_lay for v in nhom_b.get(ng, ())]
        if not ra or not rb:
            continue
        gaps.append(median(ra) - median(rb))
    if len(gaps) < rounds // 2:
        return None
    gaps.sort()

    def q(pct):
        return gaps[min(len(gaps) - 1, int(len(gaps) * pct / 100))]

    g_lo, g_hi = q(lo), q(hi)
    return {'gap_lo': round(g_lo, 4), 'gap_hi': round(g_hi, 4),
            'rounds': len(gaps), 'includes_zero': g_lo <= 0 <= g_hi,
            'block': L, 'n_dates': D, 'level': hi - lo}


def build(web_dir: Path, price_of: Callable[[str], Optional[pd.DataFrame]],
          index_df: Optional[pd.DataFrame] = None,
          horizons=HORIZONS, now: Optional[datetime] = None,
          strategies: Optional[Dict[str, str]] = None,
          universe: Optional[List[str]] = None) -> dict:
    """
    `universe` bật phép thử giả dược. Không truyền thì bỏ qua — nhưng khi đó
    mọi con số `median_excess` đều KHÔNG PHÂN XỬ ĐƯỢC giữa "chiến lược kém" và
    "mã trung vị thua chỉ số vốn hoá". Xem chú thích ở MIN_AVG_VALUE_20D.
    """
    web_dir = Path(web_dir)
    index_s = _close_series(index_df)
    dirs = strategies if strategies is not None else STRATEGY_DIRS
    out = {}
    for name, rel in dirs.items():
        sessions = sessions_from(web_dir / rel)
        row = build_strategy(sessions, price_of, index_s, horizons)
        if universe:
            row['placebo'] = placebo_strategy(sessions, price_of, universe,
                                              index_s, horizons)
            # Khoảng tin cậy đặt NGAY CẠNH cặp số, không để người đọc tự đoán
            # xem chênh lệch 0,3% có nghĩa gì.
            row['gap_ci'] = {}
            for n in horizons:
                k = str(n)
                # EXCESS, khong phai `ret`. Ban truoc lay `ret` trong khi con so
                # dat canh khoang la `median_excess` — khoang mo ta mot dai luong
                # KHAC voi dai luong no di kem.
                def _cap(rows):
                    return [(r['date'], r['exits'][k]['excess']) for r in rows
                            if k in r['exits'] and r['exits'][k].get('excess') is not None]
                row['gap_ci'][k] = median_gap_ci(_cap(row['rows']),
                                                 _cap(row['placebo']['rows']),
                                                 block=n)
        out[name] = row
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


def _pct(v):
    return '—' if v is None else f'{v:+.2%}'


def summary(payload: dict):
    """
    In KÈM giả dược, không bao giờ in riêng con số chiến lược.

    Một dòng chỉ ghi "−2,65%" sẽ bị đọc thành "chiến lược lỗ", trong khi nó có
    thể chỉ là "mã trung vị thua chỉ số vốn hoá". Hai con số cạnh nhau thì
    người đọc thấy ngay điều cần thấy: CHÊNH LỆCH giữa chúng.
    """
    last = str(payload['horizons'][-1])
    for name, s in payload['strategies'].items():
        h = s['by_horizon'].get(last, {})
        p = (s.get('placebo') or {}).get('by_horizon', {}).get(last, {})
        edge = (None if h.get('median_excess') is None or p.get('median_excess') is None
                else h['median_excess'] - p['median_excess'])
        ci = (s.get('gap_ci') or {}).get(last)
        verdict = ('—' if not ci else
                   f"chưa đủ ngày ({ci.get('ly_do')})" if ci.get('includes_zero') is None else
                   f"KHÔNG khác 0 ({_pct(ci['gap_lo'])}..{_pct(ci['gap_hi'])}, "
                   f"{ci.get('level', 95):.0f}%)" if ci['includes_zero'] else
                   f"khác 0 ({_pct(ci['gap_lo'])}..{_pct(ci['gap_hi'])}, "
                   f"{ci.get('level', 95):.0f}%)")
        yield (f"  {name:<20} {s['entries']:>4} lần vào | {last} phiên: "
               f"n={h.get('n', 0):>4} vượt chỉ số {_pct(h.get('median_excess'))} "
               f"| giả dược {_pct(p.get('median_excess'))} (n={p.get('n', 0)}) "
               f"| CHÊNH {_pct(edge)} → {verdict}")
