"""
Sổ đăng ký snapshot BCTC — point-in-time cho Module B (audit F3, blueprint §5.2).

vnstock chỉ trả phiên bản số liệu MỚI NHẤT, nên nếu không tự ghi lại thì không
bao giờ biết được "ngày X hệ thống đã thấy kỳ nào, với nội dung nào". Sổ này
ghi cho mỗi (mã, loại kỳ, kỳ):

    first_seen   ngày đầu tiên kỳ xuất hiện       → cờ "công bố chậm", veto
                                                     "thiếu hai quý", độ trễ backtest
    last_seen    ngày gần nhất còn thấy
    hash         sha256 nội dung kỳ (3 bảng BCTC)  → phát hiện số liệu bị sửa
    revisions    [{date, hash, vnstock}] mỗi lần nội dung đổi. Khóa `vnstock`
                 giữ tên cũ; từ 26/09/2026 giá trị là phiên bản lớp nguồn
                 (`sources.http.SOURCE_VERSION`, vd. 'direct-1') thay cho
                 phiên bản vnstock, nên "revised" ngay sau lúc đổi nguồn là
                 dấu hiệu lớp nguồn đọc số khác vnstock — cần kiểm.

CHỈ lưu metadata, KHÔNG lưu số liệu: repo public và blueprint §4.2 không cho
phân phối lại dữ liệu thô của bên thứ ba. Số liệu đã chuẩn hóa được lưu ở
Phase 1 (web/data/quality/archive/).

Độ phân giải ngày bị giới hạn bởi TTL cache fundamentals (7 ngày) và lịch chạy
weekly: `first_seen` là "chậm nhất là ngày này", không phải ngày công bố.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Dict, Optional

REGISTRY_SCHEMA = 1
STATEMENT_TABLES = ('balance_sheet', 'income', 'cash_flow')


def period_hashes(result: Dict) -> Dict[str, str]:
    """{kỳ: sha256} trên nội dung 3 bảng BCTC của kỳ đó (record theo kỳ, tỷ đồng).

    Làm tròn 6 chữ số thập phân (tỷ đồng → chính xác tới đồng) để hash không
    đổi vì sai số dấu phẩy động giữa các lần chia 1e9.
    """
    by_period: Dict[str, Dict] = {}
    for table in STATEMENT_TABLES:
        for rec in result.get(table) or []:
            period = rec.get('period')
            if not period:
                continue
            by_period.setdefault(str(period), {})[table] = {
                k: round(v, 6) if isinstance(v, float) else v
                for k, v in rec.items() if k != 'period'
            }
    return {
        p: hashlib.sha256(json.dumps(content, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        for p, content in by_period.items()
    }


def load_registry(path: Path) -> Dict:
    try:
        with open(path, encoding='utf-8') as f:
            reg = json.load(f)
        if reg.get('schema') == REGISTRY_SCHEMA:
            return reg
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {'schema': REGISTRY_SCHEMA, 'tickers': {}}


def record_snapshot(result: Dict, path: Path, today: Optional[str] = None) -> Dict[str, int]:
    """Cập nhật sổ với một lần fetch. Trả {'new': n, 'revised': n} để log."""
    ticker, period_type = result.get('ticker'), result.get('period', 'year')
    hashes = period_hashes(result)
    if not ticker or not hashes:
        return {'new': 0, 'revised': 0}

    today = today or date.today().isoformat()
    version = result.get('vnstock_version')
    reg = load_registry(path)
    entries = reg['tickers'].setdefault(ticker, {}).setdefault(period_type, {})

    new = revised = 0
    for period, h in hashes.items():
        e = entries.get(period)
        if e is None:
            entries[period] = {'first_seen': today, 'last_seen': today, 'hash': h,
                               'revisions': [{'date': today, 'hash': h, 'vnstock': version}]}
            new += 1
            continue
        e['last_seen'] = today
        if e['hash'] != h:
            e['hash'] = h
            e['revisions'].append({'date': today, 'hash': h, 'vnstock': version})
            revised += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(reg, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return {'new': new, 'revised': revised}
