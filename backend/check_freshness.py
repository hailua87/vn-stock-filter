#!/usr/bin/env python3
"""
CANH GAC DO TUOI DU LIEU - chay DOC LAP voi daily-scan.
================================================================================
Vì sao tồn tại file này:

Ngày 17-20/08/2026, `daily-scan` fail cả 8 ca liên tiếp: mỗi run chạy hết 60
phút rồi bị `timeout-minutes` giết. Vì nó chết TRƯỚC bước ghi file, `latest.json`
vẫn giữ nguyên nội dung phiên 14/08 — hợp lệ về cú pháp, đọc được, không mang cờ
lỗi nào. Dashboard hiển thị bình thường suốt 5 phiên bằng dữ liệu cũ, và không ai
biết cho đến khi ngồi soi `gh run list` bằng tay.

Đó là lỗi VẮNG MẶT, không phải lỗi phát ra tiếng. Không một bước nào bên trong
`daily-scan` bắt được nó, vì `daily-scan` chính là thứ đã chết.

Nguyên tắc thiết kế — file này KHÔNG được phụ thuộc vào bất cứ thứ gì đã hỏng:

  - KHÔNG `needs:` hay `workflow_run:` trên daily-scan. Nếu daily-scan không bao
    giờ khởi động (như ca EOD 26/08 bị GitHub bỏ hẳn tick cron), một trigger phụ
    thuộc cũng sẽ không bao giờ chạy — im lặng nhân đôi.
  - KHÔNG gọi mạng, KHÔNG đụng vnstock, KHÔNG dùng cache OHLCV. Chỉ đọc file JSON
    đã commit trong repo. vnstock sập thì cái chuông vẫn phải kêu được.
  - KHÔNG tin đồng hồ của bên ghi dữ liệu. Mốc so sánh là lịch giao dịch
    (`scanner/trading_calendar.py`), không phải `generated_at` trong file — một
    file dữ liệu cũ vẫn có thể mang `generated_at` mới nếu có ai chạy tay.

Cách đo: so `metadata.session_date` với phiên ĐÁNG LẼ đã phải có, đếm bằng ĐƠN VỊ
PHIÊN. Đo bằng ngày lịch thì sáng Thứ Hai nào cũng kêu oan (dữ liệu Thứ Sáu trễ 3
ngày lịch nhưng 0 phiên), và ngược lại im thin thít suốt kỳ nghỉ Tết.

Mã thoát:
    0 — dữ liệu tươi trong ngưỡng cho phép
    2 — LỆCH: cần báo động
    1 — script tự nó hỏng (tham số sai...); workflow cũng phải coi là báo động
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _load_trading_calendar():
    """
    Nạp `scanner/trading_calendar.py` THẲNG TỪ FILE, không qua câu lệnh
    `from scanner.trading_calendar import ...`.

    Vì sao phải vòng vèo: `import scanner.trading_calendar` chạy
    `scanner/__init__.py` trước, mà file đó `from .scanner import BreakoutScanner`
    → `import pandas`. Chuông này cố ý KHÔNG cài requirements.txt, nên đường
    import qua package chết ngay tại dòng pandas.

    Đã xảy ra thật, không phải giả định: run 32998375558 (26/08/2026) chết với
    `ModuleNotFoundError: No module named 'pandas'`. Cái độc lập mà file này
    tuyên bố ở đầu module đã bị một dòng import lặng lẽ phá, và test local không
    thấy vì máy phát triển nào cũng có sẵn pandas.

    `trading_calendar.py` tự nó chỉ dùng thư viện chuẩn ở mức module (pandas được
    import muộn bên trong `infer_last_session_from_dates`, hàm mà file này không
    gọi), nên nạp lẻ là hợp lệ.

    Xem test_freshness_alert.test_runs_without_pandas — nó chặn pandas rồi chạy
    lại, tức ghim đúng lỗi trên.
    """
    path = Path(__file__).resolve().parent / 'scanner' / 'trading_calendar.py'
    spec = importlib.util.spec_from_file_location('_freshness_trading_calendar', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'không nạp được lịch giao dịch từ {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_tc = _load_trading_calendar()

has_holiday_table = _tc.has_holiday_table
is_trading_day = _tc.is_trading_day
previous_trading_day = _tc.previous_trading_day
trading_sessions_between = _tc.trading_sessions_between

EXIT_FRESH = 0
EXIT_STALE = 2

# Bốn file mà daily-scan ghi trong cùng một run. `latest.json` là file được chấm
# điểm; ba file kia chỉ đi kèm trong báo cáo để biết hỏng toàn cục hay cục bộ.
PRIMARY = 'web/data/latest.json'
COMPANIONS = (
    'web/data/golden_cross_long/latest.json',
    'web/data/golden_cross_short/latest.json',
    'web/data/ichimoku/latest.json',
)
# Nguồn dự phòng cho ngày phiên. `index.json` mang khoá `latest` được ghi từ
# CHÍNH `session_date` (xem run_daily.write_strategy_outputs), nên nó cũng suy từ
# dữ liệu chứ không phải đồng hồ của runner.
ARCHIVE_INDEX = 'web/data/archive/index.json'

# Việt Nam UTC+7, không DST từ 1975 — offset cố định là chính xác và không phụ
# thuộc gói tzdata của máy chạy.
ICT = timezone(timedelta(hours=7), name='ICT')

# Hai mốc dưới đây LẶP LẠI giá trị của run_daily.ARCHIVE_CUTOFF_ICT và giờ mở
# cửa HOSE. Cố ý không `from run_daily import ...`: run_daily kéo theo pandas và
# cả gói scanner, mà chuông này chạy trên runner KHÔNG cài requirements.txt —
# đúng lỗi đã giết run 32998375558. Trùng lặp ở đây rẻ hơn một dependency.
# Nếu run_daily đổi mốc 15:15 thì phải đổi cả ở đây.
MARKET_OPEN_ICT = dtime(9, 0)
ARCHIVE_CUTOFF_ICT = dtime(15, 15)

# Câu giải thích khi trục 2 không áp dụng vì thiếu khoá. Tách hằng số để test
# ghim đúng chuỗi này thay vì ghim một mẩu văn bản dễ trôi.
AXIS2_MISSING_KEY = ('trục 2 không áp dụng — latest.json thiếu archive_written, '
                     'file do code trước 27/08 ghi')


def expected_session(today: date) -> date:
    """
    Phiên mà dữ liệu ĐÁNG LẼ phải có, tính tại thời điểm kiểm buổi sáng sớm.

    Luôn là phiên giao dịch gần nhất TRƯỚC `today`, kể cả khi `today` là ngày
    giao dịch: lúc job này chạy (~08:00 ICT) HOSE còn chưa mở cửa (09:00), nên
    phiên hôm nay chưa tồn tại. Dùng `last_trading_session` (có tính cả hôm nay)
    sẽ đòi một phiên chưa diễn ra và báo động sai mỗi sáng.

    Cuối tuần và nghỉ lễ rơi vào cùng một công thức: sáng Thứ Bảy → Thứ Sáu,
    sáng Thứ Hai → Thứ Sáu, sáng đầu tiên sau Tết → phiên cuối trước Tết.
    """
    return previous_trading_day(today)


def read_session_date(path: Path) -> tuple[Optional[str], dict]:
    """
    Đọc `metadata.session_date`. Trả về (session_date | None, ngữ cảnh để in).

    Mọi đường hỏng đều trả None — file mất, JSON vỡ, thiếu khoá, ngày không phải
    ISO. Cả bốn đều nghĩa là "không chứng minh được dữ liệu tươi", và cái chuông
    này FAIL CLOSED: không chứng minh được thì kêu.
    """
    ctx: dict = {'path': str(path), 'readable': False}
    if not path.exists():
        ctx['error'] = 'file không tồn tại'
        return None, ctx
    try:
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        ctx['error'] = f'không đọc được JSON: {type(e).__name__}: {e}'
        return None, ctx

    if not isinstance(payload, dict):
        ctx['error'] = f'JSON không phải object mà là {type(payload).__name__}'
        return None, ctx

    ctx['readable'] = True
    meta = payload.get('metadata') or {}
    ctx['generated_at'] = payload.get('generated_at')
    ctx['total'] = payload.get('total')
    ctx['run_type'] = meta.get('run_type')
    ctx['written_at_ict'] = meta.get('written_at_ict')
    ctx['session_complete'] = meta.get('session_complete')
    ctx['fetch_stop_reason'] = meta.get('fetch_stop_reason')
    ctx['fetch_coverage'] = meta.get('fetch_coverage')
    # Phân biệt THIẾU KHOÁ với GIÁ TRỊ False — hai thứ này dẫn tới hai kết luận
    # ngược nhau ở trục 2, và `.get()` trả None cho cả hai.
    ctx['has_archive_written'] = 'archive_written' in meta
    ctx['archive_written'] = meta.get('archive_written')
    ctx['archive_gates_failed'] = meta.get('archive_gates_failed') or []
    ctx['archive_gate'] = meta.get('archive_gate')

    raw = meta.get('session_date')
    if not raw:
        ctx['error'] = 'metadata.session_date rỗng hoặc thiếu'
        return None, ctx
    try:
        date.fromisoformat(str(raw))
    except ValueError:
        ctx['error'] = f'metadata.session_date không phải ngày ISO: {raw!r}'
        return None, ctx
    return str(raw), ctx


def read_archive_latest(path: Path) -> Optional[str]:
    """
    Ngày phiên dự phòng, lấy từ `archive/index.json` khoá `latest`.

    Vì sao cần dự phòng: các file `latest.json` sinh ra TRƯỚC khi
    `build_metadata` có khoá `session_date` (tức mọi file commit trước 27/08/2026)
    chỉ mang `run_type` / `run_date_ict`. Không có dự phòng thì cái chuông sẽ kêu
    ngay lần chạy đầu vì LỆCH SCHEMA chứ không phải vì dữ liệu cũ — mà một cái
    chuông kêu oan ngay hôm đầu thì hôm sau không còn ai nghe.

    Chọn `index.json` chứ KHÔNG chọn `run_date_ict` hay `generated_at`: hai cái
    sau là đồng hồ của runner, và bản EOD chạy 23:05 ICT vắt qua nửa đêm UTC sẽ
    cho ngày lệch một hôm — đúng lỗi mà `session_date_from_data` đã sửa. `latest`
    trong index thì được ghi từ chính `session_date`, vẫn suy từ dữ liệu.

    Điểm yếu đã biết: index chỉ được cập nhật khi cổng archive mở (sau 15:15
    ICT), nên ngày nào chỉ có ca intraday chạy được thì nó đứng yên. Chấp nhận
    được vì đây chỉ là đường lùi tạm thời; ca scan thành công kế tiếp sẽ ghi
    `session_date` vào latest.json và đường lùi này không còn được dùng nữa.
    """
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            idx = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(idx, dict):
        return None
    raw = idx.get('latest')
    if not raw:
        return None
    try:
        date.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None
    return str(raw)


def evaluate_settled(ctx: dict, now_ict: datetime) -> dict:
    """
    TRỤC 2 — phiên mới nhất đã CHỐT chưa. Độc lập hoàn toàn với trục 1 (ngày
    phiên), và không tha phiên nào: lệch là kêu ngay.

    Vì sao không tha, khác trục 1: trục 1 tha 1 phiên vì một ca hỏng lẻ tự lành
    ở ca sau. Trục 2 KHÔNG tự lành — nếu ca EOD đêm qua trượt, ca intraday trưa
    nay sẽ ghi đè latest.json bằng dữ liệu giữa phiên và giá đóng cửa phiên
    trước mất vĩnh viễn. Chờ thêm một vòng là mất luôn thứ đang cần cứu.

    Đo bằng `archive_written` chứ không bằng `run_type`: `run_type` là nhãn dán
    lúc job KHỞI ĐỘNG rồi đóng băng, sai cả hai chiều — chính run_daily
    .get_run_type() cấm dùng nó làm cổng. `archive_written` là phán quyết của
    pipeline dựa trên đồng hồ LÚC GHI cộng độ phủ, tức đã đi qua cả hai cổng.

    Nó cũng bắt luôn ca EOD chạy nhưng độ phủ mỏng — vẫn là sự cố đáng kêu, chỉ
    khác nguyên nhân; `archive_gates_failed` cho biết cổng nào hỏng.

    Hai trường hợp trục này TỰ TẮT:

      (c) Giờ chạy nằm trong 09:00–15:15 ICT. Lúc đó bản intraday chưa chốt là
          ĐÚNG THIẾT KẾ, không phải sự cố. Đọc đồng hồ thật, không đọc nhãn.
          Ở khung chạy theo lịch (08:07 ICT) điều kiện này không bao giờ chạm:
          ca EOD đêm qua đáng lẽ xong từ 23:05, ca intraday hôm nay chưa xảy ra,
          HOSE chưa mở cửa. Nên lúc 08:07 mà latest.json chưa chốt thì chỉ có
          một cách đọc — ca EOD đã không chạy.

      (b) latest.json thiếu hẳn khoá `archive_written` (mọi file do code trước
          27/08 ghi). Vắng mặt khoá là lệch schema, không phải bằng chứng chưa
          chốt — nên không kêu. Nhưng KHÔNG im: lý do được ghi lại để người đọc
          biết trục này đã không chấm gì.
    """
    t = now_ict.timetz().replace(tzinfo=None)

    if MARKET_OPEN_ICT <= t < ARCHIVE_CUTOFF_ICT:
        return {
            'applies': False, 'stale': False,
            'note': (f"trục 2 bỏ qua — chuông chạy lúc {t:%H:%M} ICT, trong khung "
                     f"{MARKET_OPEN_ICT:%H:%M}–{ARCHIVE_CUTOFF_ICT:%H:%M} giữa phiên; "
                     f"bản chưa chốt lúc này là đúng thiết kế"),
        }

    if not ctx.get('has_archive_written'):
        return {'applies': False, 'stale': False, 'note': AXIS2_MISSING_KEY}

    written = ctx.get('archive_written')
    failed = ctx.get('archive_gates_failed') or []
    if written is True:
        return {'applies': True, 'stale': False,
                'note': 'trục 2: archive_written = true — phiên đã chốt'}

    gates = f" — cổng hỏng: {', '.join(failed)}" if failed else ''
    return {
        'applies': True, 'stale': True,
        'note': (f"trục 2: archive_written = {written!r} — phiên mới nhất CHƯA "
                 f"CHỐT, mà lúc {t:%H:%M} ICT thì đáng lẽ đã chốt{gates}"),
    }


def evaluate(repo_root: Path, today: date, max_lag: int = 1,
             now_ict: Optional[datetime] = None) -> dict:
    """
    Chấm độ tươi. `max_lag` là số phiên được phép trễ mà KHÔNG báo động.

    HAI TRỤC PHÁN QUYẾT, ĐỘC LẬP. Kêu nếu BẤT KỲ trục nào lệch:

      trục 1 — NGÀY PHIÊN. Tha tới `max_lag` phiên. max_lag = 1 (mặc định):
               một ca hỏng đơn lẻ thì im — GitHub thỉnh thoảng bỏ tick cron, và
               một phiên trễ sẽ được ca sau vá lại. Trễ từ 2 phiên trở lên là
               hỏng có hệ thống. Trong sự cố 17-20/08, ngưỡng này kêu sáng 19/08.

      trục 2 — PHIÊN ĐÃ CHỐT CHƯA. Không tha phiên nào. Xem evaluate_settled().

    Vì sao cần trục 2: sáng 27/08 latest.json mang phiên 26/08 đúng bằng phiên
    kỳ vọng nên trục 1 im — hợp lệ. Nhưng phiên 26/08 đó chỉ có ảnh chụp giữa
    phiên lúc 13:00 ICT vì ca EOD không chạy. Trục 1 đo NGÀY phiên, không đo
    CHẤT LƯỢNG phiên, nên nó không thể thấy lỗ đó.

    `now_ict` chỉ dùng cho trục 2 (khung 09:00–15:15). None = đồng hồ thật.
    """
    primary = repo_root / PRIMARY
    session_date, ctx = read_session_date(primary)
    expected = expected_session(today)
    source = 'metadata.session_date'

    # File đọc được nhưng thiếu `session_date` (schema cũ) → lùi về archive index.
    # File MẤT hoặc VỠ thì không lùi: dashboard đọc chính latest.json, nên trạng
    # thái đó vẫn phải kêu.
    if session_date is None and ctx.get('readable'):
        fallback = read_archive_latest(repo_root / ARCHIVE_INDEX)
        if fallback is not None:
            session_date = fallback
            source = f'{ARCHIVE_INDEX}:latest (dự phòng — latest.json thiếu session_date)'

    result = {
        'today': today.isoformat(),
        'expected': expected.isoformat(),
        'today_is_trading_day': is_trading_day(today),
        'holiday_table_known': has_holiday_table(today.year),
        'max_lag': max_lag,
        'session_date': session_date,
        'session_date_source': source,
        'primary': ctx,
        'companions': [],
    }

    for rel in COMPANIONS:
        sd, cctx = read_session_date(repo_root / rel)
        result['companions'].append({'file': rel, 'session_date': sd,
                                     'error': cctx.get('error')})

    # ── TRỤC 2 — chấm độc lập, không phụ thuộc kết quả trục 1 ────────────
    axis2 = evaluate_settled(ctx, now_ict or datetime.now(ICT))
    result['axis2_applies'] = axis2['applies']
    result['axis2_stale'] = axis2['stale']
    result['axis2_note'] = axis2['note']
    result['archive_written'] = ctx.get('archive_written')
    result['archive_gates_failed'] = ctx.get('archive_gates_failed') or []
    result['now_ict'] = (now_ict or datetime.now(ICT)).strftime('%Y-%m-%d %H:%M %Z')

    if session_date is None:
        result['axis1_stale'] = True
        result['stale'] = True
        result['lag'] = None
        result['session_date_source'] = None
        result['reason'] = (ctx.get('error', 'không xác định được ngày phiên')
                            + ' | ' + axis2['note'])
        return result

    sd = date.fromisoformat(session_date)
    # sd >= expected: dữ liệu tươi bằng hoặc hơn kỳ vọng (job chạy muộn hơn dự
    # tính và đã có phiên mới). trading_sessions_between trả 0, không phải lỗi.
    lag = trading_sessions_between(sd, expected)
    result['lag'] = lag
    axis1_stale = lag > max_lag
    result['axis1_stale'] = axis1_stale
    axis1_note = (
        f'dữ liệu dừng ở phiên {session_date}, đáng lẽ phải có phiên {expected} '
        f'— trễ {lag} phiên (ngưỡng {max_lag})'
        if axis1_stale else
        f'phiên {session_date} so với kỳ vọng {expected} — trễ {lag} phiên, '
        f'trong ngưỡng {max_lag}'
    )
    # HOẶC, không phải VÀ: mỗi trục bắt một kiểu hỏng khác nhau.
    result['stale'] = axis1_stale or axis2['stale']
    result['reason'] = axis1_note + ' | ' + axis2['note']
    return result


def render_issue(result: dict) -> tuple[str, str]:
    """Tiêu đề + thân issue báo động."""
    lag = result['lag']
    lag_txt = f"{lag} phiên" if lag is not None else 'không đo được'
    if result.get('axis2_stale') and not result.get('axis1_stale'):
        title = (f"[data] phiên {result['session_date']} CHƯA CHỐT — "
                 f"archive_written = {result.get('archive_written')!r}")
    else:
        title = (f"[data] latest.json trễ {lag_txt} — dừng ở "
                 f"{result['session_date'] or 'KHÔNG RÕ'}, kỳ vọng {result['expected']}")

    ctx = result['primary']
    lines = [
        '## Dữ liệu dashboard không còn tươi',
        '',
        f"- **Ngày kiểm:** {result['today']}",
        f"- **Phiên kỳ vọng:** {result['expected']}",
        f"- **Phiên trong `{PRIMARY}`:** {result['session_date'] or '— không đọc được —'}",
        f"- **Nguồn ngày phiên:** {result.get('session_date_source') or '— không có —'}",
        f"- **Độ trễ:** {lag_txt} (ngưỡng cho phép: {result['max_lag']} phiên)",
        '',
        '### Hai trục phán quyết',
        '',
        '| trục | kết quả | |',
        '| --- | --- | --- |',
        (f"| 1 — ngày phiên | {'LỆCH' if result.get('axis1_stale') else 'đạt'} "
         f"| trễ {lag_txt}, ngưỡng {result['max_lag']} |"),
        (f"| 2 — phiên đã chốt | "
         f"{'LỆCH' if result.get('axis2_stale') else ('đạt' if result.get('axis2_applies') else 'không áp dụng')} "
         f"| `archive_written` = {result.get('archive_written')!r} |"),
        '',
        f"- `archive_gates_failed`: **{result.get('archive_gates_failed') or '(rỗng)'}**",
        f"- giờ chuông chạy: {result.get('now_ict')}",
        f"- ghi chú trục 2: {result.get('axis2_note')}",
        '',
        f"- **Kết luận:** {result['reason']}",
        '',
        '### Bằng chứng trong file',
        '',
        f"- `generated_at`: {ctx.get('generated_at')}",
        f"- `metadata.run_type`: {ctx.get('run_type')}",
        f"- `metadata.written_at_ict`: {ctx.get('written_at_ict')}",
        f"- `metadata.session_complete`: {ctx.get('session_complete')}",
        f"- `total` tín hiệu: {ctx.get('total')}",
    ]
    if ctx.get('fetch_stop_reason'):
        lines.append(f"- `metadata.fetch_stop_reason`: **{ctx['fetch_stop_reason']}** "
                     f"(coverage {ctx.get('fetch_coverage')})")
    if ctx.get('error'):
        lines.append(f"- LỖI ĐỌC FILE: {ctx['error']}")

    lines += ['', '### Ba file chiến lược còn lại', '',
              '| file | session_date |', '| --- | --- |']
    for c in result['companions']:
        val = c['session_date'] or f"— {c['error']} —"
        lines.append(f"| `{c['file']}` | {val} |")

    lines += [
        '',
        '### Kiểm tiếp',
        '',
        '```',
        'gh run list --workflow=daily-scan.yml --limit 10 \\',
        '  --json databaseId,conclusion,createdAt,event',
        'gh run view <id> --log | grep -E "ERROR|timed out"',
        '```',
        '',
        'Ba nguyên nhân đã gặp trên repo này:',
        '',
        '1. step `Run daily scan` hết 60 phút vì upstream vnstock trả lỗi lai rai '
        '(mỗi mã 3 lần thử rồi bỏ, ~26s/mã);',
        '2. `trading.vietcap.com.vn` read-timeout 30s/lần;',
        '3. GitHub bỏ hẳn tick cron nên KHÔNG có run nào được tạo — trường hợp này '
        '`gh run list` sẽ không có dòng nào cho ca đó, không phải dòng đỏ.',
        '',
        '---',
        '',
        '_Issue này do `.github/workflows/data-freshness-alert.yml` mở tự động. '
        'Nó chạy độc lập với `daily-scan`, không đụng mạng, và sẽ tự đóng issue '
        'khi dữ liệu tươi trở lại._',
    ]
    return title, '\n'.join(lines)


def render_recovery_comment(result: dict) -> str:
    """Bình luận đóng issue khi dữ liệu tươi lại."""
    return '\n'.join([
        '## Dữ liệu đã tươi trở lại',
        '',
        f"- **Ngày kiểm:** {result['today']}",
        f"- **Phiên kỳ vọng:** {result['expected']}",
        f"- **Phiên hiện có:** {result['session_date']} "
        f"(nguồn: {result.get('session_date_source')})",
        f"- **Độ trễ:** {result['lag']} phiên (ngưỡng {result['max_lag']})",
        '',
        '_Tự đóng bởi `data-freshness-alert.yml`._',
    ])


def _emit_github_output(**kv) -> None:
    """Ghi biến ra $GITHUB_OUTPUT nếu đang chạy trong Actions."""
    path = os.environ.get('GITHUB_OUTPUT')
    if not path:
        return
    with open(path, 'a', encoding='utf-8') as f:
        for k, v in kv.items():
            f.write(f'{k}={v}\n')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Kiểm độ tươi của web/data/latest.json theo lịch giao dịch.')
    parser.add_argument('--repo-root', default='.',
                        help='Thư mục gốc repo (chứa web/data/)')
    parser.add_argument('--max-lag', type=int, default=1,
                        help='Số phiên được phép trễ mà không báo động (mặc định 1)')
    parser.add_argument('--today', default=None,
                        help='Ghi đè ngày kiểm dạng ISO — dùng khi thử tay. Kéo '
                             'theo giờ 08:07 ICT (đúng khung chạy theo lịch) cho '
                             'trục 2, trừ khi có --now-ict.')
    parser.add_argument('--now-ict', default=None,
                        help='Ghi đè ĐỒNG HỒ dạng "YYYY-MM-DD HH:MM" giờ ICT. '
                             'Chỉ ảnh hưởng trục 2 (khung 09:00-15:15).')
    parser.add_argument('--body-out', default=None,
                        help='Ghi thân issue ra file này khi phát hiện lệch')
    parser.add_argument('--recovery-out', default=None,
                        help='Ghi bình luận hồi phục ra file này khi dữ liệu tươi')
    parser.add_argument('--json-out', default=None,
                        help='Ghi toàn bộ kết quả dạng JSON ra file này')
    args = parser.parse_args(argv)

    # Console Windows mặc định cp1252 còn báo cáo thì có tiếng Việt: in thẳng sẽ
    # nổ UnicodeEncodeError và cái chuông chết vì lý do chẳng liên quan gì tới dữ
    # liệu. Không dựa vào PYTHONIOENCODING vì người chạy tay sẽ không đặt nó.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

    if args.now_ict:
        now_ict = datetime.strptime(args.now_ict, '%Y-%m-%d %H:%M').replace(tzinfo=ICT)
    elif args.today:
        # `--today X` nghĩa là "giả lập lần kiểm theo lịch của ngày X", mà lịch
        # chạy 08:07 ICT. Dùng đồng hồ thật ở đây sẽ cho kết quả đổi theo lúc gõ
        # lệnh — thử tay mà không tái lập được thì vô dụng.
        now_ict = datetime.strptime(args.today + ' 08:07', '%Y-%m-%d %H:%M').replace(tzinfo=ICT)
    else:
        now_ict = datetime.now(ICT)

    today = date.fromisoformat(args.today) if args.today else now_ict.date()
    result = evaluate(Path(args.repo_root), today, max_lag=args.max_lag,
                      now_ict=now_ict)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"Ngay kiem        : {result['today']}")
    print(f"Phien ky vong    : {result['expected']}")
    print(f"Phien trong file : {result['session_date']}")
    print(f"Nguon ngay phien : {result['session_date_source']}")
    print(f"Do tre           : {result['lag']} phien (nguong {result['max_lag']})")
    print(f"Truc 1 ngay phien: {'LECH' if result.get('axis1_stale') else 'dat'}")
    print(f"Truc 2 da chot   : "
          f"{'LECH' if result.get('axis2_stale') else ('dat' if result.get('axis2_applies') else 'khong ap dung')}"
          f"  (archive_written={result.get('archive_written')!r})")
    print(f"  {result.get('axis2_note')}")
    print(f"Ket luan         : {result['reason']}")
    if not result['holiday_table_known']:
        print(f"CHU Y: chua co bang nghi le cho nam {today.year} trong "
              f"trading_calendar.HOLIDAYS - lich chi dua vao cuoi tuan.")

    if result['stale']:
        title, body = render_issue(result)
        if args.body_out:
            Path(args.body_out).write_text(body, encoding='utf-8')
        _emit_github_output(stale='true', title=title)
        print('\n=> LECH: can bao dong.')
        return EXIT_STALE

    if args.recovery_out:
        Path(args.recovery_out).write_text(
            render_recovery_comment(result), encoding='utf-8')
    _emit_github_output(stale='false', title='')
    print('\n=> Du lieu tuoi.')
    return EXIT_FRESH


if __name__ == '__main__':
    sys.exit(main())
