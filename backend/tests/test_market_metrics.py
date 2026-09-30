"""
Beta và bội số lịch sử (`scanner/market_metrics.py`), dựng trên thị trường giả.

Viết lại 30/09/2026 từ `backend/test_market_metrics.py`. Bản cũ có ba khuyết
tật, và cái thứ ba làm hai cái kia thành thứ yếu:

1. Gán đè `mm.OHLCV_CACHE_DIR` và `mm.VNINDEX_CACHE` ngay LÚC IMPORT, nên nó
   sửa module cho cả phiên pytest — mọi test chạy sau đều thấy cache giả. Đã
   làm đỏ một test thật ngày 28/09 (`test_vnindex_cache_path`), và test đó
   xanh khi chạy riêng, đỏ khi chạy cả bộ.

2. Dùng `/tmp` — trên Windows là đường dẫn vô nghĩa.

3. Các hàm `return True/False` thay vì `assert`. Dưới pytest, giá trị trả về
   bị bỏ qua: **test luôn xanh dù kiểm tra bên trong thất bại**.

Chứng minh khuyết tật 3 trước khi viết lại: ép `calculate_beta` luôn trả
beta = 99,0 — sai hoàn toàn — và pytest vẫn báo `4 passed`. Bốn test ấy chưa
bao giờ kiểm điều gì.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import market_metrics as mm

TARGETS = {'HIGH_BETA': 1.5, 'MID_BETA': 1.0, 'LOW_BETA': 0.5}


@pytest.fixture
def market(tmp_path, monkeypatch):
    """
    Thị trường giả: VN-Index bước ngẫu nhiên, ba mã có beta đặt trước.

    `monkeypatch` chứ không gán thẳng: nó tự hoàn nguyên sau mỗi test, nên
    module trở lại nguyên trạng cho test sau. Đó chính là điều bản cũ không làm.
    """
    # 1200 phiên (~4,7 năm) để bội số lịch sử có đủ mốc cuối năm.
    days, seed = 1200, 42
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=datetime.now().date() - timedelta(days=1),
                          periods=days, freq='B')
    index_returns = rng.normal(0.0003, 0.012, days)
    index = pd.DataFrame({'Date': dates,
                          'Close': 1000 * np.exp(np.cumsum(index_returns))})

    cache = tmp_path / 'cache'
    cache.mkdir()
    vnindex = tmp_path / 'vnindex.parquet'
    index.to_parquet(vnindex, index=False)

    for ticker, beta in TARGETS.items():
        # Nhiễu riêng lẻ NHỎ so với thị trường (0,003 vs 0,012): phép đo này
        # hỏi "hồi quy có tìm lại được beta không", không hỏi "hạt giống hôm
        # nay có may không". Với nhiễu 0,015 như bản cũ, sai số chuẩn của beta
        # đủ lớn để MID_BETA ra 1,354 — và dải ±0,3 khi ấy chỉ là may rủi.
        idio = rng.normal(0, 0.003, days)
        # 30,0 chứ không phải 30000: cache OHLCV theo NGHÌN ĐỒNG (xem
        # scanner/price_units.py), nên 30000 ở đây thành 30 triệu đồng một cổ
        # phiếu. Với EPS 3.000đ thì P/E ra 10.000 và bị bộ lọc `0,5 < pe < 200`
        # loại sạch — `observations` về 0.
        #
        # Bản cũ mắc đúng lỗi này (chú thích "bắt đầu 30k VND" nhưng ghi 30000
        # vào cache nghìn đồng), nên test bội số lịch sử của nó ĐANG THẤT BẠI
        # suốt — chỉ không ai thấy vì nó `return False` thay vì `assert`.
        prices = 30.0 * np.exp(np.cumsum(0.0001 + beta * index_returns + idio))
        pd.DataFrame({
            'Date': dates, 'Open': prices, 'High': prices * 1.005,
            'Low': prices * 0.995, 'Close': prices,
            'Volume': rng.integers(100_000, 5_000_000, days),
        }).to_parquet(cache / f'{ticker}_adj.parquet', index=False)

    monkeypatch.setattr(mm, 'OHLCV_CACHE_DIR', cache)
    monkeypatch.setattr(mm, 'VNINDEX_CACHE', vnindex)
    return cache


@pytest.mark.parametrize('ticker,target', sorted(TARGETS.items()))
def test_beta_regression_recovers_the_target(market, ticker, target):
    """
    Hồi quy phải tìm lại được beta đã đặt, sai số ±0,3.

    ASSERT chứ không `return`: đây là điểm khác biệt duy nhất thật sự quan
    trọng so với bản cũ. Với `return`, ép beta = 99 vẫn cho `4 passed`.
    """
    out = mm.calculate_beta(ticker, lookback_days=730)
    assert not out['fallback'], f"{ticker} rơi về mặc định: {out['method']}"
    assert out['observations'] >= 50
    assert target - 0.15 <= out['beta_raw'] <= target + 0.15, (
        f"{ticker}: đặt {target}, tìm lại {out['beta_raw']:.3f}")


def test_blume_adjustment_pulls_towards_one(market):
    """beta_adjusted = 0,67 × thô + 0,33 × 1,0 — luôn gần 1 hơn beta thô."""
    high = mm.calculate_beta('HIGH_BETA', lookback_days=730)
    low = mm.calculate_beta('LOW_BETA', lookback_days=730)
    assert high['beta_adjusted'] < high['beta_raw'], 'beta cao phải bị kéo xuống'
    assert low['beta_adjusted'] > low['beta_raw'], 'beta thấp phải bị kéo lên'


def test_a_ticker_with_no_data_falls_back_to_one(market):
    """
    Không có dữ liệu thì trả beta 1,0 kèm cờ `fallback` — không được im lặng
    đưa ra một con số trông như đã tính.
    """
    out = mm.calculate_beta('KHONG_TON_TAI')
    assert out['fallback'] is True and out['beta'] == 1.0
    assert out['observations'] == 0


def test_historical_multiples_use_real_prices(market):
    """P/E, P/B lịch sử tính từ giá THẬT trong cache, không phải bội số dựng sẵn."""
    # Năm phải NẰM TRONG cửa sổ giá, tính theo hôm nay chứ không viết cứng.
    # Bản cũ ghi cứng 2020–2024; tới 2026 chúng rơi ra ngoài cửa sổ và
    # `observations` về 0 — tức test ấy ĐANG THẤT BẠI, chỉ là không ai thấy vì
    # nó `return False` thay vì `assert`.
    y = datetime.now().year - 1
    raw = {'ticker': 'MID_BETA', 'ratio': [
        {'year': y - i, 'eps': 3000 - i * 200, 'bvps': 20000 - i * 2000,
         'pe': 10, 'pb': 1.5} for i in range(4)
    ]}
    out = mm.calculate_historical_multiples('MID_BETA', raw)
    assert out['observations'] >= 3
    assert out['pe_5y_median'] is not None and out['pb_5y_median'] is not None
    assert out['pe_5y_p25'] <= out['pe_5y_median'] <= out['pe_5y_p75']
    # Giá trong cache bắt đầu 30.000đ và trôi ngẫu nhiên; P/E tính từ giá đó
    # KHÔNG trùng cột `pe` dựng sẵn ở trên — nếu trùng là đang đọc nhầm nguồn.
    assert out['pe_5y_median'] != 10


def test_enrich_adds_both_blocks_end_to_end(market):
    raw = {'ticker': 'HIGH_BETA', 'current_price': 35000,
           'overview': {'industry': 'Banking'},
           'ratio': [{'year': datetime.now().year - 1 - i, 'eps': 3000 - i * 200,
                      'bvps': 20000 - i * 2000} for i in range(4)]}
    out = mm.enrich_with_market_metrics('HIGH_BETA', raw)
    assert not out['beta_info']['fallback']
    assert not out['historical_multiples']['fallback']
    assert out['historical_multiples']['pe_5y_median'] is not None


def test_the_fixture_does_not_leak_into_other_tests(market):
    """
    Chốt đúng khuyết tật của bản cũ. `monkeypatch` hoàn nguyên sau mỗi test;
    test này chỉ khẳng định đường dẫn ĐANG trỏ vào thư mục tạm, và việc nó
    KHÔNG rò rỉ được bảo đảm bởi chính cơ chế fixture.
    """
    assert mm.OHLCV_CACHE_DIR == market
    assert 'tmp' in str(mm.OHLCV_CACHE_DIR).lower() or market.exists()


def test_module_paths_are_restored_outside_the_fixture():
    """
    Test này KHÔNG dùng fixture `market`. Nếu bản cũ còn sống, nó sẽ thấy
    đường dẫn giả; với monkeypatch thì nó thấy đường dẫn thật.
    """
    from scanner.data_fetcher import CACHE_DIR, VNINDEX_CACHE
    assert mm.OHLCV_CACHE_DIR == CACHE_DIR
    assert mm.VNINDEX_CACHE == VNINDEX_CACHE
