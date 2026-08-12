"""
MARKET REGIME & RELATIVE STRENGTH
================================================================================
Hai thứ quyết định alpha nhưng trước đây hoàn toàn vắng mặt trong scanner:

1. MARKET REGIME (bối cảnh thị trường)
   Phần lớn tín hiệu breakout thất bại khi VN-Index nằm dưới MA50/MA200. Trước
   fix, hệ thống bắn tín hiệu "MUA MẠNH 8-12% NAV" giống hệt nhau trong uptrend
   lẫn downtrend. `fetch_vnindex` được import trong scanner.py nhưng KHÔNG hề
   được dùng ở đâu.

2. RELATIVE STRENGTH (sức mạnh tương đối vs VN-Index)
   Yếu tố dự báo mạnh nhất trong mọi nghiên cứu momentum (O'Neil/CANSLIM dùng
   RS Rating làm điều kiện tiên quyết). Hàm `indicators.relative_strength()` đã
   tồn tại sẵn nhưng cũng là dead code.

Module này KHÔNG tự quyết định loại mã nào — nó cung cấp bối cảnh để:
  - Dashboard hiển thị cảnh báo khi thị trường risk-off
  - Xếp hạng ưu tiên các mã khoẻ hơn thị trường
  - Backtest sau này đo được alpha thay vì beta thuần
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# Các khung thời gian tính RS, kèm trọng số (giống tinh thần RS Rating của
# IBD: ưu tiên hiệu suất gần đây nhưng vẫn tính cả xu hướng dài hơn).
RS_LOOKBACKS = {21: 0.40, 63: 0.35, 126: 0.25}   # ~1 tháng / 3 tháng / 6 tháng


def compute_regime(index_df: Optional[pd.DataFrame]) -> Dict:
    """
    Đánh giá trạng thái thị trường từ chuỗi VN-Index.

    Returns:
        {
          'available': bool,
          'close': float, 'ma50': float, 'ma200': float,
          'above_ma50': bool, 'above_ma200': bool, 'ma50_rising': bool,
          'change_20d_pct': float, 'drawdown_from_high_pct': float,
          'regime': 'risk_on' | 'neutral' | 'risk_off',
          'label': mô tả tiếng Việt,
          'position_size_multiplier': float,   # gợi ý co tỷ trọng khi risk-off
        }
    """
    unavailable = {
        'available': False,
        'regime': 'unknown',
        'label': 'Không lấy được VN-Index — không đánh giá được bối cảnh thị trường',
        'position_size_multiplier': 1.0,
    }
    if index_df is None or len(index_df) < 60:
        return unavailable

    df = index_df.sort_values('Date').reset_index(drop=True)
    close = df['Close'].astype(float)

    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean() if len(close) >= 200 else None

    last = float(close.iloc[-1])
    ma50_last = float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else None
    ma200_last = (float(ma200.iloc[-1])
                  if ma200 is not None and pd.notna(ma200.iloc[-1]) else None)

    above_ma50 = ma50_last is not None and last > ma50_last
    above_ma200 = ma200_last is not None and last > ma200_last
    ma50_rising = (ma50_last is not None and len(ma50) > 10
                   and pd.notna(ma50.iloc[-11]) and ma50_last > float(ma50.iloc[-11]))

    change_20d = ((last / float(close.iloc[-21]) - 1) * 100) if len(close) > 21 else 0.0
    high_252 = float(close.tail(252).max())
    drawdown = (last / high_252 - 1) * 100 if high_252 else 0.0

    # Phân loại: cần cả vị trí so với MA và độ dốc MA50.
    score = sum([above_ma50, above_ma200, ma50_rising])
    if score >= 3:
        regime, label = 'risk_on', 'Thị trường thuận lợi — VN-Index trên MA50 & MA200, MA50 hướng lên'
        multiplier = 1.0
    elif score == 2:
        regime, label = 'neutral', 'Thị trường trung tính — tín hiệu mua nên vào với tỷ trọng nhỏ hơn'
        multiplier = 0.6
    else:
        regime, label = 'risk_off', 'Thị trường bất lợi — phần lớn tín hiệu breakout thất bại trong giai đoạn này'
        multiplier = 0.3

    return {
        'available': True,
        'close': round(last, 2),
        'ma50': round(ma50_last, 2) if ma50_last else None,
        'ma200': round(ma200_last, 2) if ma200_last else None,
        'above_ma50': bool(above_ma50),
        'above_ma200': bool(above_ma200),
        'ma50_rising': bool(ma50_rising),
        'change_20d_pct': round(change_20d, 2),
        'drawdown_from_high_pct': round(drawdown, 2),
        'regime': regime,
        'label': label,
        'position_size_multiplier': multiplier,
    }


def compute_breadth(by_ticker: Dict[str, pd.DataFrame], ma_period: int = 50) -> Dict:
    """
    Độ rộng thị trường = % số mã đang nằm trên MA(ma_period).

    Chỉ báo này bổ sung cho regime: chỉ số có thể được kéo bởi vài mã vốn hoá
    lớn trong khi phần lớn cổ phiếu đã giảm.
    """
    above = 0
    total = 0
    for df in by_ticker.values():
        if df is None or len(df) < ma_period:
            continue
        close = df['Close'].astype(float)
        ma = close.rolling(ma_period).mean().iloc[-1]
        if pd.isna(ma):
            continue
        total += 1
        if float(close.iloc[-1]) > float(ma):
            above += 1

    pct = round(above / total * 100, 1) if total else None
    return {
        f'pct_above_ma{ma_period}': pct,
        'sample_size': total,
    }


def _pct_change(series: pd.Series, periods: int) -> Optional[float]:
    if len(series) <= periods:
        return None
    past = float(series.iloc[-(periods + 1)])
    if past <= 0:
        return None
    return (float(series.iloc[-1]) / past - 1) * 100


def compute_relative_strength(by_ticker: Dict[str, pd.DataFrame],
                              index_df: Optional[pd.DataFrame]) -> Dict[str, Dict]:
    """
    Tính sức mạnh tương đối của từng mã so với VN-Index.

    rs_score = Σ trọng số × (hiệu suất mã - hiệu suất index) ở mỗi khung.
    rs_rank  = phân vị 1-99 trong universe được quét (giống RS Rating của IBD).

    Returns: {ticker: {'rs_score': float, 'rs_21d': ..., 'rs_63d': ...,
                       'rs_126d': ..., 'rs_rank': int}}
    """
    if index_df is None or len(index_df) < 30:
        log.warning("  RS: không có VN-Index → bỏ qua relative strength")
        return {}

    idx = index_df.sort_values('Date').reset_index(drop=True)['Close'].astype(float)
    index_returns = {p: _pct_change(idx, p) for p in RS_LOOKBACKS}

    raw: Dict[str, Dict] = {}
    for ticker, df in by_ticker.items():
        if df is None or len(df) < 30:
            continue
        close = df.sort_values('Date')['Close'].astype(float)

        score = 0.0
        weight_used = 0.0
        detail = {}
        for period, weight in RS_LOOKBACKS.items():
            stock_ret = _pct_change(close, period)
            index_ret = index_returns.get(period)
            if stock_ret is None or index_ret is None:
                continue
            excess = stock_ret - index_ret
            detail[f'rs_{period}d'] = round(excess, 2)
            score += weight * excess
            weight_used += weight

        if weight_used == 0:
            continue
        detail['rs_score'] = round(score / weight_used, 2)
        raw[ticker] = detail

    # Xếp hạng phân vị 1-99
    if raw:
        scores = np.array([v['rs_score'] for v in raw.values()])
        for ticker, v in raw.items():
            pct = float((scores < v['rs_score']).mean() * 100)
            v['rs_rank'] = int(max(1, min(99, round(pct))))

    return raw


def annotate_results(results: list, rs_map: Dict[str, Dict]) -> list:
    """Gắn RS vào `metrics` của từng kết quả strategy (dùng chung cho cả 4)."""
    if not rs_map:
        return results
    for r in results:
        metrics = getattr(r, 'metrics', None)
        if not isinstance(metrics, dict):
            continue
        rs = rs_map.get(r.ticker)
        if rs:
            metrics['rs_score'] = rs.get('rs_score')
            metrics['rs_rank'] = rs.get('rs_rank')
            metrics['rs_63d'] = rs.get('rs_63d')
    return results
