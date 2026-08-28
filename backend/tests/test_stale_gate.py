"""
Cổng chặn "gần như cả rổ bị đóng dấu stale".

Ghim sự cố 28/08/2026. Tick intraday tới muộn 19h45, chạy lúc 08:17 ICT — trước
giờ ATO. `last_trading_session` khai phiên T là phiên gần nhất, nhưng trước 09:15
thì phiên T chưa có cây nến nào, nên cả 500/500 mã bị `StaleCache = True` (404
trong số đó có dữ liệu hoàn toàn tươi cho phiên đã chốt). Mọi strategy reject
sạch, và ba file `latest.json` bị ghi đè bằng kết quả rỗng.

Hai lớp phòng thủ, test ở đây giữ cả hai:
  - `last_expected_session` xét GIỜ, nên mã không bị đóng dấu oan nữa
  - cổng `check_stale_universe` chặn hẳn nếu chuyện đó vẫn xảy ra vì lý do khác
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging

import pandas as pd
import pytest

from scanner import data_fetcher
from scanner.data_fetcher import fetch_universe
import run_daily
from run_daily import MAX_STALE_RATIO, check_stale_universe, stale_ratio


def _frame(ticker: str, stale: bool) -> pd.DataFrame:
    return pd.DataFrame({
        'Date': pd.date_range('2026-06-01', periods=70, freq='D'),
        'Close': range(70),
        'Volume': range(70),
        'Ticker': ticker,
        'Exchange': 'HOSE',
        'StaleCache': stale,
    })


def _by_ticker(n_stale: int, n_fresh: int) -> dict:
    d = {f'S{i:03d}': _frame(f'S{i:03d}', True) for i in range(n_stale)}
    d.update({f'F{i:03d}': _frame(f'F{i:03d}', False) for i in range(n_fresh)})
    return d


# ── Tỷ lệ ────────────────────────────────────────────────────────────────
def test_muc_nen_thuc_te_khong_bi_chan():
    """96/500 mã stale — con số THẬT của ngày 28/08, phải đi lọt."""
    ratio, n_stale, n_total, _ = stale_ratio(_by_ticker(96, 404))
    assert (ratio, n_stale, n_total) == (0.192, 96, 500)
    assert ratio < MAX_STALE_RATIO


def test_ca_hong_28_08_bi_chan():
    ratio, n_stale, n_total, _ = stale_ratio(_by_ticker(500, 0))
    assert (ratio, n_stale, n_total) == (1.0, 500, 500)
    assert ratio >= MAX_STALE_RATIO


def test_cong_cho_qua_va_tra_ty_le(caplog):
    with caplog.at_level(logging.INFO, logger='daily'):
        assert check_stale_universe(_by_ticker(96, 404), {}) == 0.192


def test_cong_thoat_han_khong_ghi_gi(caplog):
    with caplog.at_level(logging.ERROR, logger='daily'):
        with pytest.raises(SystemExit) as exc:
            check_stale_universe(_by_ticker(500, 0), {})
    assert exc.value.code == 1


def test_thieu_dau_thi_noi_khong_ro_chu_khong_doan(caplog):
    """fetch_summary rỗng → thông báo không được bịa ra một ngày nào đó."""
    with caplog.at_level(logging.ERROR, logger='daily'):
        with pytest.raises(SystemExit):
            check_stale_universe(_by_ticker(500, 0), {})
    assert 'không rõ' in caplog.text


# ── 4e: expected trong thông báo lỗi == last_session vòng fetch THỰC SỰ dùng ──
def test_expected_khop_last_session_ma_data_fetcher_da_dung(monkeypatch, caplog):
    """
    Đây là chỗ bản vá trước còn hở: cổng TỰ TÍNH lại mốc, nên sửa data_fetcher
    mà quên cổng thì thông báo lỗi báo một con số, còn thứ gây STALE là con số
    khác. Nay chỉ còn một nguồn: vòng fetch đóng dấu, cổng đọc.
    """
    seen = []

    def fake_fetch(ticker, exchange, lookback_days, last_session=None):
        seen.append(last_session)
        return _frame(ticker, False)

    monkeypatch.setattr(data_fetcher, 'fetch_with_cache', fake_fetch)

    tickers = pd.DataFrame({'ticker': [f'T{i:03d}' for i in range(5)],
                            'exchange': ['HOSE'] * 5})
    out = fetch_universe(tickers, delay=0)
    summary = out.attrs['fetch_summary']

    # Cả rổ dùng CHUNG một mốc — không mã nào tự tính riêng.
    assert len(set(seen)) == 1 and seen[0] is not None
    assert summary['last_session'] == seen[0].isoformat()

    with caplog.at_level(logging.ERROR, logger='daily'):
        with pytest.raises(SystemExit):
            check_stale_universe(_by_ticker(500, 0), summary)

    # Con số trong thông báo lỗi CHÍNH LÀ con số đã gây ra STALE.
    assert f"last_session kỳ vọng: {seen[0].isoformat()}" in caplog.text
