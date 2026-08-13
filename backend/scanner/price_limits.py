"""
BIÊN ĐỘ DAO ĐỘNG & TRẠNG THÁI TRẦN/SÀN
================================================================================
Vì sao cần:

  Dashboard trước đây không hề phân biệt mã đang ở giá trần hay giá sàn — trong
  khi đây là thông tin giao dịch quan trọng bậc nhất ở TTCK Việt Nam:

    - Mã dư mua trần: bạn KHÔNG MUA ĐƯỢC. Một "tín hiệu breakout" trên mã đang
      trần cứng là tín hiệu không thực hiện được, và nếu backtest coi như mua
      được thì kết quả là ảo.
    - Mã dư bán sàn: không thoát được hàng, rủi ro thực tế lớn hơn nhiều so với
      những gì stop-loss trên giấy thể hiện.

  Nhà đầu tư VN đọc bảng điện theo quy ước màu: TÍM = trần, XANH LAM = sàn,
  VÀNG = tham chiếu. Không hiển thị quy ước này là bỏ mất một tầng thông tin
  mà mọi người dùng bản địa đều mong đợi.

BIÊN ĐỘ THEO SÀN (giao dịch bình thường):
    HOSE  ±7%     HNX  ±10%     UPCoM  ±15%

Lưu ý: cổ phiếu mới niêm yết phiên đầu và cổ phiếu sau thời gian dài bị đình
chỉ có biên độ rộng hơn; module này không xử lý các ngoại lệ đó nên chỉ dùng
kết quả như tín hiệu cảnh báo, không phải chân lý tuyệt đối.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

# Biên độ dao động theo sàn (tỷ lệ, không phải %)
EXCHANGE_BANDS = {
    'HOSE': 0.07,
    'HNX': 0.10,
    'UPCOM': 0.15,
    'UPCOM-VN': 0.15,
}
DEFAULT_BAND = 0.07

# Dung sai khi so với biên độ: giá khớp phải làm tròn theo bước giá nên
# thay đổi thực tế hiếm khi đúng bằng 7,00%.
BAND_TOLERANCE = 0.003          # 0,3 điểm phần trăm


def band_for(exchange: Optional[str]) -> float:
    """Biên độ dao động của sàn. Không rõ sàn → dùng mức chặt nhất (HOSE)."""
    if not exchange:
        return DEFAULT_BAND
    return EXCHANGE_BANDS.get(str(exchange).strip().upper(), DEFAULT_BAND)


def classify_price_limit(df: pd.DataFrame, exchange: Optional[str] = None) -> dict:
    """
    Phân loại trạng thái giá của phiên gần nhất.

    Returns:
        {
          'change_1d_pct': float|None,  # % thay đổi so với phiên trước
          'limit_status': str,          # ceiling | floor | near_ceiling |
                                        # near_floor | reference | normal
          'limit_locked': bool,         # trần/sàn CỨNG (High == Low == Close)
          'band_pct': float,            # biên độ của sàn, tính bằng %
          'tradable_warning': str|None, # cảnh báo về khả năng khớp lệnh
        }
    """
    empty = {'change_1d_pct': None, 'limit_status': 'unknown', 'limit_locked': False,
             'band_pct': band_for(exchange) * 100, 'tradable_warning': None}

    if df is None or len(df) < 2:
        return empty

    try:
        close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2])
        high = float(df['High'].iloc[-1])
        low = float(df['Low'].iloc[-1])
    except (KeyError, IndexError, TypeError, ValueError):
        return empty

    if prev_close <= 0:
        return empty

    band = band_for(exchange)
    change = close / prev_close - 1

    # Trần/sàn CỨNG: cả phiên chỉ khớp ở đúng một mức giá.
    locked = abs(high - low) < 1e-9

    if change >= band - BAND_TOLERANCE:
        status = 'ceiling'
    elif change <= -(band - BAND_TOLERANCE):
        status = 'floor'
    elif change >= band * 0.7:
        status = 'near_ceiling'
    elif change <= -band * 0.7:
        status = 'near_floor'
    elif abs(change) < 1e-9:
        status = 'reference'
    else:
        status = 'normal'

    warning = None
    if status == 'ceiling':
        warning = ('Đang ở giá TRẦN' + (' và khoá cứng cả phiên' if locked else '') +
                   ' — nhiều khả năng không mua được ở mức giá này')
    elif status == 'floor':
        warning = ('Đang ở giá SÀN' + (' và khoá cứng cả phiên' if locked else '') +
                   ' — nhiều khả năng không thoát được hàng')
    elif status == 'near_ceiling':
        warning = 'Sát giá trần — thanh khoản bên bán mỏng, khó khớp đủ khối lượng'

    return {
        'change_1d_pct': round(change * 100, 2),
        'limit_status': status,
        'limit_locked': bool(locked),
        'band_pct': round(band * 100, 1),
        'tradable_warning': warning,
    }
