"""
Phễu ngưỡng: vì sao có (hoặc không có) mã nào đạt chuẩn.

Câu hỏi ban đầu là "backtest ngưỡng đi". Backtest KHÔNG LÀM ĐƯỢC — xem
`docs/threshold-backtest.md`: mới có 4 bản lưu chấm chất lượng trong 8 ngày,
chân trời quan sát ~6 phiên, trong khi một chỉ tiêu dài hạn cần 60–250 phiên.

Nhưng có một câu hỏi về ngưỡng trả lời được NGAY, không cần nhìn về tương lai:
ngưỡng có ĐẠT TỚI ĐƯỢC không, và nếu không thì nút thắt nằm ở đâu?

Đo trên rổ 200 mã ngày 27/09/2026:

    200 mã → 184 chấm đủ 4 chiều → 3 vượt cả 4 ngưỡng → 0 đạt chuẩn

Ba mã vượt hết là CTR, HDB, FPT. Cả ba rớt ở BƯỚC CUỐI — `classify` còn đòi
định giá Hấp dẫn hoặc Hợp lý, mà 182/200 mã không có định giá.

Kết luận: ngưỡng KHÔNG sai. Tỷ lệ 3/184 ≈ 1,6% đúng như phép nhân percentile
gợi ý (top 25% × 30% × 30% × 35% ≈ 0,8% nếu độc lập; cao hơn chút vì các chiều
tương quan dương, đúng như mong đợi ở doanh nghiệp tốt). Nút thắt là ĐỘ PHỦ
ĐỊNH GIÁ.

Đóng gói thành phễu tự tính mỗi lượt chạy chứ không phải một phép đo rời: con
số rời sẽ cũ đi mà không ai biết, còn phễu thì luôn nói về rổ hiện tại.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import config as C
from .status import DIMS

# Định giá phải thuộc nhóm này thì `classify` mới cho ĐẠT CHUẨN (xem status.py).
QUALIFYING_BANDS = ('ATTRACTIVE', 'FAIR')


def _scores(item: dict) -> Dict[str, Optional[float]]:
    return {d: (item.get('dims', {}).get(d) or {}).get('score') for d in DIMS}


def funnel(items: List[dict], qualify: Optional[dict] = None) -> dict:
    """
    Phễu từ cả rổ xuống số mã đạt chuẩn, kèm chỗ rơi rụng ở từng bước.

    `near_miss` là phần đáng đọc nhất: những mã vượt HẾT ngưỡng bốn chiều mà
    vẫn không đạt chuẩn, cùng lý do. Nếu danh sách này dài mà số đạt chuẩn vẫn
    bằng 0 thì vấn đề không nằm ở ngưỡng.
    """
    q = qualify or C.QUALIFY
    total = len(items)
    scored, passed_all, qual = [], [], []
    fail_by_dim = {d: 0 for d in q}
    near_miss = []

    for it in items:
        s = _scores(it)
        if any(v is None for v in s.values()):
            continue
        scored.append(it)
        short = [d for d, lim in q.items() if s[d] < lim]
        for d in short:
            fail_by_dim[d] += 1
        if short:
            continue
        passed_all.append(it)
        if it.get('status') == 'QUAL':
            qual.append(it)
        else:
            band = (it.get('valuation') or {}).get('band') or 'NOT_AVAILABLE'
            near_miss.append({
                'ticker': it.get('ticker'), 'model': it.get('model'),
                'band': band, 'status': it.get('status'),
                'scores': {d: round(v, 1) for d, v in s.items()},
            })

    # Nút thắt = chiều làm rớt nhiều mã nhất trong số ĐÃ CHẤM ĐỦ. Chỉ có nghĩa
    # khi còn mã để rớt; rổ rỗng thì nói không biết.
    binding = max(fail_by_dim, key=fail_by_dim.get) if scored else None

    return {
        'universe': total,
        'scored_all_dims': len(scored),
        'passed_all_thresholds': len(passed_all),
        'qualified': len(qual),
        'fail_by_dim': fail_by_dim,
        'binding_dim': binding,
        # Rớt ở BƯỚC CUỐI: vượt hết ngưỡng nhưng định giá không đủ tin cậy.
        # Đây là chỗ phân biệt "ngưỡng quá chặt" với "thiếu định giá".
        'blocked_by_valuation': len(near_miss),
        'near_miss': near_miss,
        'qualifying_bands': list(QUALIFYING_BANDS),
    }


def summary(f: dict):
    yield (f"  Phễu ngưỡng: {f['universe']} mã → {f['scored_all_dims']} chấm đủ "
           f"→ {f['passed_all_thresholds']} vượt cả 4 ngưỡng → {f['qualified']} đạt chuẩn")
    if f['scored_all_dims']:
        n = f['scored_all_dims']
        parts = ', '.join(f"{d} {c}/{n}" for d, c in
                          sorted(f['fail_by_dim'].items(), key=lambda kv: -kv[1]))
        yield f"    rớt theo chiều: {parts} | nút thắt: {f['binding_dim']}"
    if f['blocked_by_valuation']:
        who = ', '.join(f"{m['ticker']}({m['band']})" for m in f['near_miss'][:6])
        yield (f"    {f['blocked_by_valuation']} mã vượt hết ngưỡng nhưng KHÔNG đạt "
               f"chuẩn vì định giá: {who}")
