"""
`web/data/health.json` — tình trạng dữ liệu cho khối "Tình trạng dữ liệu" của
màn Hôm nay (blueprint v4 §11.2, §13).

Một người ghi duy nhất: `run_daily`. Trạng thái của hai nguồn chạy hằng tuần
(định giá, chất lượng) được ĐỌC từ chính tệp chúng đã xuất bản, chứ không phải
do chúng tự khai vào đây. Hai người ghi chung một tệp thì lần ghi sau xóa mất
phần của lần ghi trước — mà hai workflow này chạy trên hai lịch khác nhau.

Tệp trước đó được đọc lại trước khi ghi đè, vì một kiểm tra của §13 cần nó:
"số mã trong danh sách giảm > 5% so với lần trước". Không giữ lại con số cũ thì
không có gì để so.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

SCHEMA = 1

# Tỷ lệ mã stale đủ để nói ra, thấp hơn nhiều so với cổng chặn cứng 0,95 ở
# run_daily: cổng kia để không ghi đè dữ liệu tốt bằng rác, ngưỡng này chỉ để
# người đọc biết phiên hôm nay có bao nhiêu mã chưa kịp cập nhật.
STALE_NOTICE = 0.20
# §13: rổ co lại quá mức này so với lần chạy trước là dấu hiệu nguồn hỏng.
UNIVERSE_DROP = 0.05
# Hai nguồn hằng tuần quá số ngày này mà chưa chạy lại thì coi là cũ.
WEEKLY_MAX_AGE_DAYS = 10


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _age_days(stamp: Optional[str], now: datetime) -> Optional[int]:
    """Số ngày từ `stamp` (ISO hoặc YYYY-MM-DD) tới `now`. Không đọc được → None."""
    if not stamp:
        return None
    try:
        s = str(stamp).replace('Z', '+00:00')
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = datetime.strptime(str(stamp)[:10], '%Y-%m-%d')
        except ValueError:
            return None
    if d.tzinfo is not None:
        d = d.replace(tzinfo=None)
    return max(0, (now - d).days)


def _weekly_source(path: Path, now: datetime, label: str) -> dict:
    """Trạng thái một nguồn hằng tuần, đọc từ tệp nó đã xuất bản."""
    d = _read_json(path)
    if d is None:
        return {'label': label, 'available': False, 'reason': 'chưa có tệp'}
    generated = d.get('generated_at')
    # Tep dinh gia khong co `as_of` lan `metadata.session_date`; truoc day o nay
    # hien '—' trong khi tep hoan toan biet no duoc sinh ngay nao.
    as_of = (d.get('as_of') or (d.get('metadata') or {}).get('session_date')
             or (generated[:10] if isinstance(generated, str) else None))
    n = len(d.get('items') or d.get('signals') or [])
    return {
        'label': label,
        'available': True,
        'as_of': as_of,
        'generated_at': generated,
        'age_days': _age_days(generated or as_of, now),
        'count': n,
    }


def build(*, session_date, run_meta: dict, fetch_summary: dict, completeness,
          decision: dict, stale_ratio: Optional[float], universe: int,
          base_conditions: dict, web_dir: Path, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    previous = _read_json(Path(web_dir) / 'health.json') or {}

    daily = {
        'label': 'Scan hằng ngày',
        'session_date': session_date,
        'run_type': run_meta.get('run_type'),
        'run_date_ict': run_meta.get('run_date_ict'),
        'run_time_ict': run_meta.get('run_time_ict'),
        'universe': universe,
        'universe_after_base': base_conditions.get('universe_after'),
        'dropped_low_liquidity': base_conditions.get('dropped_low_liquidity'),
        'fetch': {
            'coverage': fetch_summary.get('coverage'),
            # Khoa la 'ok', khong phai 'succeeded' — xem data_fetcher._summary.
            'succeeded': fetch_summary.get('ok'),
            'skipped': fetch_summary.get('skipped'),
            'failed': fetch_summary.get('failed'),
            'stop_reason': fetch_summary.get('stop_reason'),
        },
        'stale_ratio': stale_ratio,
        'session_completeness': completeness,
        'archive_written': bool(decision.get('write')),
        'archive_reason': decision.get('reason'),
    }
    sources = {
        'daily_scan': daily,
        'valuation': _weekly_source(Path(web_dir) / 'valuation' / 'latest.json', now, 'Định giá'),
        'quality': _weekly_source(Path(web_dir) / 'quality' / 'latest.json', now, 'Chất lượng'),
    }

    return {
        'schema': SCHEMA,
        'generated_at': now.isoformat(timespec='seconds'),
        'sources': sources,
        'issues': _issues(daily, sources, previous, now),
    }


def _issues(daily: dict, sources: dict, previous: dict, now: datetime) -> list:
    out = []

    def add(code, severity, message):
        out.append({'code': code, 'severity': severity, 'message': message})

    f = daily['fetch']
    if f.get('stop_reason'):
        add('fetch_stopped', 'warn',
            f"Vòng lấy dữ liệu dừng sớm ({f['stop_reason']}) — "
            f"độ phủ {f.get('coverage')}. Rổ quét nhỏ hơn bình thường.")
    if f.get('failed'):
        add('fetch_failed', 'warn',
            f"{f['failed']} mã không lấy được dữ liệu, đã bỏ qua trong phiên này.")

    sr = daily.get('stale_ratio')
    if sr is not None and sr >= STALE_NOTICE:
        add('stale_high', 'warn',
            f"{sr:.0%} số mã có dữ liệu chưa cập nhật tới phiên mới nhất "
            f"(nguồn chậm). Tín hiệu của những mã đó tính trên giá cũ.")

    if not daily['archive_written']:
        # Ca intraday KHÔNG ghi archive theo đúng thiết kế — nói là "lỗi" thì sai,
        # nhưng vẫn phải nói ra, vì nó giải thích vì sao hôm nay chưa có bản lưu.
        add('archive_skipped', 'info',
            f"Chưa ghi bản lưu phiên: {daily.get('archive_reason') or 'không rõ lý do'}.")

    # §13: rổ co lại so với lần chạy trước
    prev_n = ((previous.get('sources') or {}).get('daily_scan') or {}).get('universe')
    now_n = daily.get('universe')
    if isinstance(prev_n, int) and isinstance(now_n, int) and prev_n > 0:
        drop = (prev_n - now_n) / prev_n
        if drop > UNIVERSE_DROP:
            add('universe_shrank', 'error',
                f"Danh sách mã giảm {drop:.0%} so với lần chạy trước "
                f"({prev_n} → {now_n}). Nguồn danh sách có thể đang lỗi.")

    for key in ('valuation', 'quality'):
        s = sources[key]
        if not s.get('available'):
            add(f'{key}_missing', 'warn', f"{s['label']}: chưa có dữ liệu.")
            continue
        age = s.get('age_days')
        if age is not None and age > WEEKLY_MAX_AGE_DAYS:
            add(f'{key}_stale', 'warn',
                f"{s['label']}: chạy lần cuối cách đây {age} ngày "
                f"(lịch là hằng tuần).")

    return out


def refresh_weekly(path: Path, web_dir: Path, now: Optional[datetime] = None) -> Optional[dict]:
    """
    Cập nhật LẠI phần của hai nguồn hằng tuần trong `health.json`, giữ nguyên
    phần `daily_scan`.

    Vì sao cần: `run_daily` là người ghi tệp này, nhưng nó chạy theo lịch khác
    `weekly-valuation`. Lượt chấm chất lượng 23/09 chạy lúc 22:35, sau lượt quét
    20:46 — nên tới sáng hôm sau màn Hôm nay vẫn báo "Chất lượng 2026-09-22"
    trong khi dữ liệu thật đã là 23-09. Nói sai trong cả một cửa sổ nhiều giờ.

    Không dựng lại cả tệp: `run_quality` KHÔNG biết gì về lượt quét (độ phủ
    fetch, tỷ lệ stale, cổng archive). Dựng lại sẽ xoá mất những số đó. Ở đây
    chỉ thay hai khoá nó thật sự sở hữu, rồi tính lại danh sách vấn đề.

    Trả về payload mới, hoặc None nếu chưa có tệp — khi đó không tạo mới, vì
    một `health.json` thiếu hẳn phần `daily_scan` còn khó đọc hơn là không có.
    """
    now = now or datetime.now()
    path, web_dir = Path(path), Path(web_dir)
    payload = _read_json(path)
    if not payload or not (payload.get('sources') or {}).get('daily_scan'):
        return None

    sources = payload['sources']
    sources['valuation'] = _weekly_source(web_dir / 'valuation' / 'latest.json', now, 'Định giá')
    sources['quality'] = _weekly_source(web_dir / 'quality' / 'latest.json', now, 'Chất lượng')
    payload['generated_at'] = now.isoformat(timespec='seconds')
    payload['weekly_refreshed_at'] = payload['generated_at']
    # `previous` rỗng: kiểm tra "rổ co lại" là việc của lượt quét, không phải
    # của lượt chấm chất lượng. Tính lại ở đây sẽ so tệp với chính nó.
    payload['issues'] = _issues(sources['daily_scan'], sources, {}, now)
    write(path, payload)
    return payload


def write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
