"""
Quy doi dinh gia (blueprint 9) va phan loai trang thai watchlist (blueprint 10).

Nhan hien thi (co dau) nam o day vi di thang len UI. Ma trang thai (QUAL, MON,
...) la khoa on dinh cho JSON va archive; doi nhan khong duoc doi ma.
"""
from __future__ import annotations

from typing import Optional

from . import config as C

VALUATION_LABEL = {
    'ATTRACTIVE': 'Hấp dẫn',
    'FAIR': 'Hợp lý',
    'EXPENSIVE': 'Đắt',
    'NOT_AVAILABLE': 'Chưa có',
}
STATUS_LABEL = {
    'QUAL': 'Đủ chuẩn',
    'MON': 'Theo dõi',
    'REV': 'Cần xem lại',
    'RES': 'Thiếu dữ liệu',
    'EXC': 'Loại',
}
DIM_LABEL = {
    'quality': 'Chất lượng',
    'growth': 'Tăng trưởng',
    'governance': 'Quản trị',
    'resilience': 'Chống chịu',
}
DIMS = ('quality', 'growth', 'governance', 'resilience')


def _primary_method(signal: dict) -> Optional[str]:
    details = signal.get('method_details') or []
    if not details:
        return None
    return max(details, key=lambda m: m.get('weight') or 0).get('method')


def valuation_band(signal: Optional[dict]) -> dict:
    """signal: 1 phan tu cua web/data/valuation/latest.json['signals']."""
    empty = {'band': 'NOT_AVAILABLE', 'label': VALUATION_LABEL['NOT_AVAILABLE'],
             'upside_pct': None, 'confidence': None, 'method': None, 'reason': 'Chưa định giá'}
    if not signal:
        return empty

    upside, conf = signal.get('upside_pct'), signal.get('confidence')
    method = _primary_method(signal)
    out = {**empty, 'upside_pct': upside, 'confidence': conf, 'method': method}
    if upside is None or conf is None:
        return {**out, 'reason': 'Engine không trả upside hoặc độ tin cậy'}

    # Engine da tu ha verdict ve HOLD khi cac phuong phap mau thuan. Voi muc dinh
    # gia thi mau thuan nghia la fair value khong dung duoc -> Chua co, khong phai Hop ly.
    if signal.get('methods_conflict'):
        return {**out, 'reason': 'Các phương pháp định giá mâu thuẫn'}

    # Engine da ha verdict ve HOLD vi chua du can cu (nhom tai chinh chua co
    # NPL/CAR, hoac chi 1 phuong phap) -> muc dinh gia cung la Chua co. Thieu
    # buoc nay thi ngan hang van hien "Hap dan" (TPB, MSB 21/09).
    if signal.get('guard_reason'):
        return {**out, 'reason': signal['guard_reason']}

    eff_conf = conf
    if method in C.SIMPLIFIED_METHODS:
        eff_conf = min(conf, C.VALUATION_MIN_CONFIDENCE - 1)
    if eff_conf < C.VALUATION_MIN_CONFIDENCE:
        why = (f'Phương pháp chính {method} còn giản lược' if method in C.SIMPLIFIED_METHODS
               else f'Độ tin cậy {conf:.0f}% dưới {C.VALUATION_MIN_CONFIDENCE:.0f}%')
        return {**out, 'reason': why}

    if upside >= C.VALUATION_ATTRACTIVE_UPSIDE:
        band = 'ATTRACTIVE'
    elif upside < C.VALUATION_EXPENSIVE_UPSIDE:
        band = 'EXPENSIVE'
    else:
        band = 'FAIR'
    return {**out, 'band': band, 'label': VALUATION_LABEL[band], 'reason': None}


def _fmt(v: float) -> str:
    return f'{v:.0f}'


def classify(dims: dict, valuation: dict, veto_reason: Optional[str] = None,
             model_active: bool = True) -> dict:
    """
    dims = {'quality': float|None, 'growth': ..., 'governance': ..., 'resilience': ...}
    Thu tu danh gia co y nghia: veto truoc, thieu du lieu truoc nguong. Dao thu tu
    thi mot ma thieu Quan tri co the roi vao "Can xem lai" voi ly do sai.
    """
    if veto_reason:
        return {'status': 'EXC', 'label': STATUS_LABEL['EXC'], 'reason': f'Veto: {veto_reason}'}

    if not model_active:
        return {'status': 'RES', 'label': STATUS_LABEL['RES'],
                'reason': 'Mô hình ngành chưa kích hoạt'}

    missing = [d for d in DIMS if dims.get(d) is None]
    if missing:
        names = ', '.join(DIM_LABEL[d] for d in missing)
        return {'status': 'RES', 'label': STATUS_LABEL['RES'],
                'reason': f'Thiếu hoặc độ phủ dưới {C.COVERAGE_MIN:.0%}: {names}'}

    weak = [f'{DIM_LABEL[d]} {_fmt(dims[d])} dưới {lim}'
            for d, lim in C.REVIEW_BELOW.items() if dims[d] < lim]
    if weak:
        return {'status': 'REV', 'label': STATUS_LABEL['REV'], 'reason': ', '.join(weak)}

    short = [f'{DIM_LABEL[d]} {_fmt(dims[d])} dưới {lim}'
             for d, lim in C.QUALIFY.items() if dims[d] < lim]
    if not short:
        band = valuation.get('band', 'NOT_AVAILABLE')
        if band in ('ATTRACTIVE', 'FAIR'):
            return {'status': 'QUAL', 'label': STATUS_LABEL['QUAL'],
                    'reason': 'Đạt cả 4 ngưỡng, định giá ' + VALUATION_LABEL[band]}
        why = 'định giá Đắt' if band == 'EXPENSIVE' else 'chưa có định giá đủ tin cậy'
        return {'status': 'MON', 'label': STATUS_LABEL['MON'],
                'reason': f'Đạt 4 ngưỡng nhưng {why}'}

    return {'status': 'MON', 'label': STATUS_LABEL['MON'], 'reason': ', '.join(short)}


def sharp_drops(current: dict, previous: Optional[dict]) -> list:
    """Chieu giam >= SHARP_DROP_POINTS so voi lan cham truoc. Chi hien thi, khong doi trang thai."""
    if not previous:
        return []
    out = []
    for d in DIMS:
        a, b = previous.get(d), current.get(d)
        if a is not None and b is not None and a - b >= C.SHARP_DROP_POINTS:
            out.append(d)
    return out


def model_for(industry: Optional[str]) -> Optional[str]:
    if industry is None:
        return None
    if industry in C.INDUSTRY_TO_MODEL:
        return C.INDUSTRY_TO_MODEL[industry]
    return C.DEFAULT_MODEL
