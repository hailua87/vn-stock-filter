"""
Chuỗi nến + MA cho màn Chi tiết mã (blueprint v4 §11.1).

Điểm dễ sai nhất: cắt 60 phiên TRƯỚC rồi mới tính MA50 — khi đó 49 phiên đầu
trong khung nhìn rỗng dù dữ liệu để tính chúng vẫn còn nguyên trong lịch sử.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from scanner import ohlc_export as OE


def frame(n, start=10.0, step=1.0):
    idx = pd.date_range('2026-01-01', periods=n, freq='D')
    close = [start + step * i for i in range(n)]
    return pd.DataFrame({
        'Date': idx,
        'Open': [c - 0.5 for c in close],
        'High': [c + 1.0 for c in close],
        'Low': [c - 1.0 for c in close],
        'Close': close,
        'Volume': [1_000_000] * n,
    })


def test_ma_uses_history_before_the_window_not_just_the_window():
    """200 phiên lịch sử, nhìn 60 phiên cuối: MA50 phải đầy đủ 60 giá trị."""
    s = OE.series_for(frame(200))
    assert len(s['c']) == 60
    assert len(s['ma50']) == 60
    assert all(v is not None for v in s['ma50'])
    # MA50 tại phiên cuối = trung bình 50 giá đóng cửa cuối
    closes = frame(200)['Close'].tolist()
    assert s['ma50'][-1] == pytest.approx(sum(closes[-50:]) / 50, abs=0.01)


def test_missing_ma_is_none_not_zero():
    """Lịch sử ngắn hơn cửa sổ MA: ô thiếu phải là None. Vẽ 0 sẽ kéo đường
    MA sụp xuống đáy biểu đồ, trông như giá sập."""
    s = OE.series_for(frame(30))
    assert s['ma50'] == [None] * 30
    assert s['ma20'][:19] == [None] * 19 and s['ma20'][19] is not None


def test_series_carries_full_ohlc_and_dates():
    s = OE.series_for(frame(5), sessions=5)
    assert s['dates'][0] == '2026-01-01' and s['dates'][-1] == '2026-01-05'
    assert s['o'][0] == 9.5 and s['h'][0] == 11.0 and s['l'][0] == 9.0 and s['c'][0] == 10.0


def test_short_history_returns_what_it_has():
    s = OE.series_for(frame(3))
    assert len(s['c']) == 3


def test_empty_or_partial_frame_gives_none():
    assert OE.series_for(None) is None
    assert OE.series_for(pd.DataFrame()) is None
    assert OE.series_for(pd.DataFrame({'Close': [1.0]})) is None   # thiếu O/H/L


def test_build_only_exports_requested_tickers():
    by_ticker = {'FPT': frame(80), 'VNM': frame(80), 'HPG': frame(80)}
    out = OE.build(by_ticker, ['FPT', 'HPG', 'KHONGCO'])
    assert sorted(out) == ['FPT', 'HPG']


def test_tickers_from_mixes_dataframe_and_objects():
    df = pd.DataFrame({'ticker': ['FPT', 'VNM']})
    objs = [SimpleNamespace(ticker='HPG'), SimpleNamespace(ticker='FPT')]
    assert OE.tickers_from(df, objs, None, pd.DataFrame()) == {'FPT', 'VNM', 'HPG'}


def test_write_keeps_price_unit_and_is_readable(tmp_path):
    p = OE.write(tmp_path / 'ohlc' / 'latest.json',
                 OE.build({'FPT': frame(80)}, ['FPT']), '2026-09-22')
    d = json.loads(p.read_text(encoding='utf-8'))
    assert d['price_unit'] == 'nghin_dong'      # cùng đơn vị với `close` trong tín hiệu
    assert d['session_date'] == '2026-09-22'
    assert d['ma_windows'] == [7, 20, 25, 50]   # MA7/MA25 cho cap giao cat, MA20/MA50 giu cho man cu
    assert len(d['series']['FPT']['c']) == 60


# ─── universe watchlist: nến cũng phải có cho mã không có tín hiệu ──────────

def test_quality_universe_reads_published_file(tmp_path):
    p = tmp_path / 'quality' / 'latest.json'
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'items': [{'ticker': 'VHM'}, {'ticker': 'NVL'}, {}]}),
                 encoding='utf-8')
    assert OE.quality_universe(p) == {'VHM', 'NVL'}


@pytest.mark.parametrize('content', ['', '{ hong', '{"items": null}', '{}'])
def test_quality_universe_never_raises(tmp_path, content):
    """Thiếu hoặc hỏng tệp thì trả rỗng, không làm đổ cả lượt quét: nến chỉ là
    phần phụ của màn Chi tiết mã."""
    p = tmp_path / 'q.json'
    p.write_text(content, encoding='utf-8')
    assert OE.quality_universe(p) == set()
    assert OE.quality_universe(tmp_path / 'khong-co.json') == set()


def test_build_covers_watchlist_ticker_without_signal():
    """
    VHM có đủ điểm 4 chiều nhưng không khớp chiến lược nào. Trước 23/09/2026
    nó không có nến, và màn Chi tiết mã mở ra thấy "Chưa có dữ liệu nến" —
    đúng nhóm người ta theo dõi dài hạn nhất.
    """
    by_ticker = {'FPT': frame(80), 'VHM': frame(80)}
    published = {'FPT'}
    watchlist = {'VHM'}
    out = OE.build(by_ticker, published | watchlist)
    assert sorted(out) == ['FPT', 'VHM']


# ── Schema 2: khoi luong, MA7/MA25, MACD ────────────────────────────────────

def _ema(xs, span):
    """EMA de quy viet tay (seed = gia tri dau) — doc lap voi pandas.ewm."""
    a = 2 / (span + 1)
    out, prev = [], None
    for x in xs:
        prev = x if prev is None else a * x + (1 - a) * prev
        out.append(prev)
    return out


def wavy(n):
    import math
    df = frame(n)
    df['Close'] = [20 + 3 * math.sin(i / 6) + 0.02 * i for i in range(n)]
    df['Volume'] = [1_000_000 + 37_000 * (i % 9) for i in range(n)]
    return df


def test_macd_matches_hand_rolled_ema_and_uses_full_history():
    df = wavy(200)
    s = OE.series_for(df)
    c = df['Close'].tolist()
    dif = [f - sl for f, sl in zip(_ema(c, 12), _ema(c, 26))]
    dea = _ema(dif[25:], 9)                       # DEA bat dau tu khi DIF co nghia
    assert s['dif'][-1] == pytest.approx(dif[-1], abs=1e-4)
    assert s['dea'][-1] == pytest.approx(dea[-1], abs=1e-4)
    assert s['macd'][-1] == pytest.approx(dif[-1] - dea[-1], abs=2e-4)
    # Tinh tren 60 phien cat san se ra so khac: chung minh dang dung lich su
    s60 = OE.series_for(df.tail(60))
    assert abs(s60['dea'][-1] - s['dea'][-1]) > 1e-3


def test_macd_warmup_is_none():
    s = OE.series_for(wavy(40), sessions=40)
    assert s['dif'][:25] == [None] * 25 and s['dif'][25] is not None
    assert s['dea'][:33] == [None] * 33 and s['dea'][33] is not None
    assert s['macd'][32] is None and s['macd'][33] is not None


def test_ma7_ma25_volume_and_vol_ma20():
    df = wavy(120)
    s = OE.series_for(df)
    c, v = df['Close'].tolist(), df['Volume'].tolist()
    assert s['ma7'][-1] == pytest.approx(sum(c[-7:]) / 7, abs=0.01)
    assert s['ma25'][-1] == pytest.approx(sum(c[-25:]) / 25, abs=0.01)
    assert s['v'] == v[-60:]
    # MA20 khoi luong TINH CA phien hien tai, nhu bang dien
    assert s['vma20'][-1] == round(sum(v[-20:]) / 20)
    assert all(len(s[k]) == 60 for k in ('v', 'vma20', 'ma7', 'ma25', 'dif', 'dea', 'macd'))


def test_no_volume_column_still_exports_price():
    df = wavy(80).drop(columns='Volume')
    s = OE.series_for(df)
    assert 'v' not in s and 'vma20' not in s and len(s['c']) == 60


def test_write_declares_schema_2(tmp_path):
    p = OE.write(tmp_path / 'o.json', {'X': OE.series_for(wavy(80))}, '2026-10-09')
    d = json.loads(p.read_text(encoding='utf-8'))
    assert d['schema'] == 2 and d['vol_ma'] == 20 and d['macd'] == [12, 26, 9]
    assert {'v', 'vma20', 'ma7', 'ma25', 'dif', 'dea', 'macd'} <= set(d['series']['X'])


def test_crosses_use_unrounded_ma_and_match_strategy_definition():
    """Hai MA sat nhau toi muc lam tron 2 chu so bang nhau: diem cat phai
    theo so that, khong theo so da lam tron."""
    import numpy as np
    # Gia phang 10,00 roi nhich 0,02 o phien cuoi: MA7 = 10,0029, MA25 = 10,0008
    # — ca hai lam tron ve 10,00, nhung MA7 da nam tren MA25.
    df = frame(80)
    df['Close'] = [10.0] * 80
    df.loc[79, 'Close'] = 10.02
    s = OE.series_for(df)
    assert s['ma7'][-1] == s['ma25'][-1]          # lam tron thi BANG nhau
    assert s['x7_25'] == [[59, 1]]                 # nhung so that la da cat len


def test_crosses_positions_and_directions_on_wave():
    df = wavy(200)
    s = OE.series_for(df)
    c = df['Close']
    a, b = c.rolling(7).mean(), c.rolling(25).mean()
    want = []
    for i in range(140, 200):
        if (a.iloc[i] > b.iloc[i]) != (a.iloc[i - 1] > b.iloc[i - 1]):
            want.append([i - 140, 1 if a.iloc[i] > b.iloc[i] else -1])
    assert want, 'duong song phai co giao cat — test se xanh ma khong kiem gi'
    assert s['x7_25'] == want
    assert all(d in (1, -1) for _, d in s['x20_50'])


def test_crosses_ignore_warmup():
    s = OE.series_for(wavy(30), sessions=30)
    assert all(i >= 25 for i, _ in s['x7_25'])
    assert s['x20_50'] == []


def test_macd_seed_matches_board_convention_early_in_series():
    """Sau 200 phien moi cach seed EMA deu hoi tu, nen phep so o cuoi chuoi
    khong phan biet duoc adjust=True/False. So o DAU chuoi, noi chung con khac:
    bang dien (TradingView/Binance) dung EMA de quy, seed = gia dau."""
    df = wavy(40)
    s = OE.series_for(df, sessions=40)
    c = df['Close'].tolist()
    dif = [f - sl for f, sl in zip(_ema(c, 12), _ema(c, 26))]
    for i in (25, 30, 39):
        assert s['dif'][i] == pytest.approx(dif[i], abs=1e-4)
