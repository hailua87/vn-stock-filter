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
    assert d['ma_windows'] == [20, 50]
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
