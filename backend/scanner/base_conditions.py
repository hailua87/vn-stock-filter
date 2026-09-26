"""
Điều kiện nền và dữ liệu bối cảnh cho màn Scan (blueprint v4 §7.2, §7.3).

Áp TRƯỚC chiến lược, dùng chung cho cả 4:

    GTGD trung bình 20 phiên ≥ 10 tỷ đồng   (tín hiệu trên mã thanh khoản thấp
                                             không dùng được)

Kèm dữ liệu cho cột sparkline: 20 giá đóng cửa gần nhất.

Đơn vị: vnstock trả giá theo NGHÌN đồng (bảng điện), khối lượng theo cổ phiếu.
GTGD quy về ĐỒNG qua price_units.quote_to_vnd — cùng một chỗ đổi đơn vị với
phần định giá, để không có hai quy ước song song.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from .price_units import quote_to_vnd

MIN_AVG_VALUE_20D = 10_000_000_000.0   # 10 tỷ đồng (§7.2, mặc định cấu hình)
SPARK_SESSIONS = 20


def context_metrics(df: pd.DataFrame, sessions: int = SPARK_SESSIONS) -> dict:
    """{'avg_value20': đồng|None, 'spark20': [giá đóng cửa cũ→mới]} từ OHLCV một mã."""
    if df is None or df.empty or 'Close' not in df or 'Volume' not in df:
        return {'avg_value20': None, 'spark20': []}
    tail = df.tail(sessions)
    closes = [round(float(c), 2) for c in tail['Close'] if pd.notna(c)]
    values = [quote_to_vnd(float(c)) * float(v)
              for c, v in zip(tail['Close'], tail['Volume'])
              if pd.notna(c) and pd.notna(v)]
    return {
        'avg_value20': round(sum(values) / len(values), 0) if values else None,
        'spark20': closes,
    }


def passes_liquidity(ctx: dict, min_avg_value: float = MIN_AVG_VALUE_20D) -> bool:
    """Thiếu số liệu thì KHÔNG loại: để chiến lược chạy, cột GTGD sẽ hiện '—'."""
    v = (ctx or {}).get('avg_value20')
    return True if v is None else v >= min_avg_value


def build_context(by_ticker: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
    return {t: context_metrics(df) for t, df in (by_ticker or {}).items()}


def filter_universe(by_ticker: Dict[str, pd.DataFrame], context: Dict[str, dict],
                    min_avg_value: float = MIN_AVG_VALUE_20D) -> tuple:
    """Trả (by_ticker đã lọc, danh sách mã bị loại). Ngưỡng <= 0 là tắt điều kiện."""
    if min_avg_value is None or min_avg_value <= 0:
        return by_ticker, []
    kept, dropped = {}, []
    for t, df in (by_ticker or {}).items():
        (kept.__setitem__(t, df) if passes_liquidity(context.get(t), min_avg_value)
         else dropped.append(t))
    return kept, dropped


def attach(results, context: Dict[str, dict]) -> list:
    """Gắn avg_value20 + spark20 vào `metrics` (thành cột m_* khi xuất JSON)."""
    for r in results or []:
        m = getattr(r, 'metrics', None)
        if isinstance(m, dict):
            m.update(context.get(getattr(r, 'ticker', None)) or
                     {'avg_value20': None, 'spark20': []})
    return results
