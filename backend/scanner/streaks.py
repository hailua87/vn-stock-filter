"""
Nhật ký tín hiệu: mã vào danh sách từ phiên nào, giữ được bao lâu, đã mất chưa.

Vì sao cần: mỗi lượt quét sinh ra một danh sách MỚI và không nhớ gì về phiên
trước. Nên người đọc không phân biệt được hai thứ rất khác nhau:

    mã vừa xuất hiện hôm nay          — tín hiệu mới, chưa kiểm chứng
    mã giữ tín hiệu tám phiên liền    — nền đã kéo dài, khác hẳn về ý nghĩa

Bảng tín hiệu hiện tại hiển thị cả hai y như nhau.

Dữ liệu lấy từ chính các bản lưu phiên đã xuất bản (`archive/`), không tính
lại gì: bản lưu là thứ đã công bố, nên nhật ký luôn khớp với cái người đọc
từng nhìn thấy. Dựng lại từ đầu bất cứ lúc nào cũng ra cùng kết quả.

MỘT ĐIỀU PHẢI HIỂU ĐÚNG khi đọc file này: "vắng mặt" ở một phiên nghĩa là mã
KHÔNG đạt tín hiệu phiên đó — nhưng chỉ đúng với những phiên CÓ trong bản lưu.
Phiên mà lượt quét hỏng hẳn thì không có bản lưu, và nó đơn giản không nằm
trong dòng thời gian; chuỗi phiên liền kề được tính trên các phiên đã lưu, chứ
không phải trên lịch giao dịch. Cổng độ phủ (MIN_COVERAGE_FOR_ARCHIVE) đảm bảo
bản lưu nào tồn tại thì đại diện được cho cả phiên.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

SCHEMA = 1

# Số phiên nhìn lại. 20 phiên ~ một tháng giao dịch: đủ dài để thấy nền kéo
# dài, đủ ngắn để tệp không phình và để "chuỗi" còn có nghĩa với người đọc.
WINDOW = 20

# Bốn chiến lược và nơi cất bản lưu của chúng. Pre-Breakout nằm thẳng trong
# web/data/archive (lý do lịch sử), ba cái còn lại có thư mục riêng.
STRATEGY_DIRS = {
    'pre_breakout': 'archive',
    'golden_cross_long': 'golden_cross_long/archive',
    'golden_cross_short': 'golden_cross_short/archive',
    'ichimoku': 'ichimoku/archive',
}


def _sessions_from(archive_dir: Path, window: int) -> List[tuple]:
    """[(ngày, {mã}), ...] cũ → mới, chỉ lấy `window` phiên gần nhất."""
    if not archive_dir.is_dir():
        return []
    files = sorted(p for p in archive_dir.glob('*.json') if p.stem != 'index')
    out = []
    for p in files[-window:]:
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            # Bản lưu hỏng thì BỎ QUA phiên đó thay vì coi là "không mã nào
            # có tín hiệu" — cái sau sẽ cắt nhầm mọi chuỗi đang chạy.
            continue
        tickers = {s.get('ticker') for s in (d.get('signals') or []) if s.get('ticker')}
        out.append((p.stem, tickers))
    return out


def _streak_of(ticker: str, sessions: List[tuple]) -> dict:
    """Chuỗi hiện tại và lịch sử của một mã trong dòng thời gian đã cho."""
    present = [day for day, tks in sessions if ticker in tks]
    if not present:
        return {}

    # Chuỗi liền kề tính NGƯỢC từ phiên mới nhất: đứt một phiên là dừng.
    streak = 0
    for _, tks in reversed(sessions):
        if ticker not in tks:
            break
        streak += 1

    return {
        'streak': streak,                 # 0 nghĩa là phiên mới nhất không có
        'appearances': len(present),      # tổng số phiên có mặt trong cửa sổ
        'first': present[0],
        'last': present[-1],
        'active': streak > 0,
    }


def build(web_dir: Path, window: int = WINDOW,
          now: Optional[datetime] = None,
          strategies: Optional[Dict[str, str]] = None) -> dict:
    """Nhật ký cho cả bốn chiến lược, đọc từ bản lưu đã xuất bản."""
    web_dir = Path(web_dir)
    now = now or datetime.now()
    dirs = strategies if strategies is not None else STRATEGY_DIRS

    out: Dict[str, dict] = {}
    timeline: Dict[str, list] = {}
    for name, rel in dirs.items():
        sessions = _sessions_from(web_dir / rel, window)
        timeline[name] = [day for day, _ in sessions]
        everyone = sorted({t for _, tks in sessions for t in tks})
        rows = {t: s for t in everyone if (s := _streak_of(t, sessions))}
        # Sắp theo chuỗi dài nhất rồi tới số lần xuất hiện: thứ tự này là thứ
        # giao diện muốn hiển thị, đừng bắt nó sắp lại.
        out[name] = dict(sorted(rows.items(),
                                key=lambda kv: (-kv[1]['streak'],
                                                -kv[1]['appearances'], kv[0])))
    return {
        'schema': SCHEMA,
        'generated_at': now.isoformat(timespec='seconds'),
        'window': window,
        'sessions': timeline,
        'note': ('Chuỗi phiên đếm trên các phiên CÓ bản lưu, không phải trên '
                 'lịch giao dịch. Phiên mà lượt quét hỏng không nằm trong đây.'),
        'strategies': out,
    }


def write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    return path


def summary(payload: dict) -> Iterable[str]:
    """Vài dòng cho log, để người xem log biết nó đã dựng được gì."""
    for name, rows in payload['strategies'].items():
        active = sum(1 for r in rows.values() if r['active'])
        longest = max((r['streak'] for r in rows.values()), default=0)
        yield (f"  {name:<20} {len(rows):>3} mã trong {payload['window']} phiên | "
               f"{active} đang có tín hiệu | chuỗi dài nhất {longest} phiên")
