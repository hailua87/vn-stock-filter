"""
Cắt lỗ / mục tiêu / R:R cho kết quả scan (blueprint v4 §7.3, §14.4 — audit F5).

Quy tắc đã chốt (22/09/2026), dùng đúng dữ liệu đã có, không thêm giả định:

    cắt lỗ  = hỗ trợ gần nhất DƯỚI giá đóng cửa   (m_supports)
    mục tiêu = kháng cự gần nhất TRÊN giá đóng cửa (m_resistances)
    R:R     = (mục tiêu − giá) / (giá − cắt lỗ)

Không có "vùng vào": giá đóng cửa là mốc. Thiếu một trong hai mức thì KHÔNG
hiển thị R:R (không thay bằng số mặc định) và `levels_note` nói rõ thiếu gì.

Ràng buộc thị trường VN (§7.4):
  - Kịch trần: không đề xuất mức nào (mua ở trần không khả thi).
  - Kịch sàn: gắn cờ để giao diện KHÔNG hiển thị tín hiệu.

Các mức là GỢI Ý THEO CHIẾN LƯỢC, không phải lệnh — giao diện phải ghi câu đó.
"""
from __future__ import annotations

from typing import Optional, Sequence

CEILING_NOTE = 'Kịch trần — không đề xuất mức vào'
FLOOR_NOTE = 'Kịch sàn — không hiển thị tín hiệu'


def _nearest(levels: Optional[Sequence[dict]], close: float, below: bool) -> Optional[float]:
    """Mức gần giá nhất, dưới (below=True) hoặc trên giá. None nếu không có."""
    best = None
    for lv in levels or []:
        p = lv.get('price') if isinstance(lv, dict) else lv
        if p is None:
            continue
        p = float(p)
        if below and p < close or (not below and p > close):
            if best is None or abs(close - p) < abs(close - best):
                best = p
    return best


def levels_for(close: Optional[float], supports, resistances,
               limit_status: Optional[str] = None) -> dict:
    """Trả {'stop', 'target', 'rr', 'levels_note', 'suppress_signal'}."""
    out = {'stop': None, 'target': None, 'rr': None,
           'levels_note': None, 'suppress_signal': False}
    if limit_status == 'floor':
        return {**out, 'levels_note': FLOOR_NOTE, 'suppress_signal': True}
    if limit_status == 'ceiling':
        return {**out, 'levels_note': CEILING_NOTE}
    if close is None or close <= 0:
        return {**out, 'levels_note': 'Thiếu giá đóng cửa'}

    stop = _nearest(supports, close, below=True)
    target = _nearest(resistances, close, below=False)
    out['stop'], out['target'] = stop, target

    missing = []
    if stop is None:
        missing.append('hỗ trợ dưới giá')
    if target is None:
        missing.append('kháng cự trên giá')
    if missing:
        out['levels_note'] = 'Thiếu ' + ' và '.join(missing)
        return out

    risk = close - stop
    out['rr'] = round((target - close) / risk, 2) if risk > 0 else None
    return out


def attach(results) -> list:
    """Gắn stop/target/rr vào `metrics` của mọi kết quả strategy (dùng chung cho cả 4)."""
    for r in results or []:
        m = getattr(r, 'metrics', None)
        if not isinstance(m, dict):
            continue
        m.update(levels_for(getattr(r, 'close', None), m.get('supports'),
                            m.get('resistances'), m.get('limit_status')))
    return results
