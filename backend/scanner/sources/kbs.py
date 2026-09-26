"""
KBS: danh sách mã theo sàn, và NIM ngân hàng.

NIM lấy từ KBS vì bảng chỉ số của VCI dừng ở 2018 (BLUEPRINT_v4 §5.4, D24).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from .http import SourceError, request_json
from .naming import english_to_snake

IIS_URL = 'https://kbbuddywts.kbsec.com.vn/iis-server/investment'

EXCHANGES = {'HOSE', 'HNX', 'UPCOM'}

# item_id của dòng NIM trong nhóm chỉ số KBS (đã xác thực 24/09/2026, D24).
NIM_ITEM_ID = 'net_interest_margin_nim'


def listing() -> pd.DataFrame:
    """
    Mọi mã đang có trên KBS: cột symbol, exchange ('HOSE'/'HNX'/'UPCOM'),
    type ('stock', 'etf', …), organ_name. Rỗng nếu nguồn không trả gì.
    """
    resp = request_json('GET', f'{IIS_URL}/stock/search/data')
    rows = resp.get('data') if isinstance(resp, dict) else resp
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame(columns=['symbol', 'exchange', 'type', 'organ_name'])
    df = pd.DataFrame(rows).rename(columns={'name': 'organ_name'})
    for col in ('symbol', 'exchange', 'type', 'organ_name'):
        if col not in df.columns:
            df[col] = None
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    df['exchange'] = df['exchange'].astype(str).str.upper().str.strip()
    df['type'] = df['type'].astype(str).str.lower().str.strip()
    return df[['symbol', 'exchange', 'type', 'organ_name']].reset_index(drop=True)


def _finance_info(symbol: str, report_type: str, term_type: int, page_size: int) -> Dict[str, Any]:
    params = {
        'page': 1,
        'pageSize': page_size,
        'type': report_type,
        'unit': 1000,
        'termtype': term_type,
        'languageid': 1,
    }
    resp = request_json('GET', f'{IIS_URL}/stock/finance-info/{symbol.upper()}', params=params)
    if not isinstance(resp, dict):
        raise SourceError(f'KBS finance-info {symbol}: phản hồi không phải object')
    return resp


def bank_nim(symbol: str, years: int = 4) -> Optional[Dict[int, float]]:
    """
    NIM theo năm, đơn vị PHẦN TRĂM đúng như nguồn trả: {2025: 2.64, 2024: 2.86, …}.
    Mặc định 4 năm — đúng số kỳ vnstock 4.0.7 trả (2022–2025), để điểm Chất
    lượng không đổi chỉ vì đổi nguồn. None nếu không có dòng NIM.
    """
    resp = _finance_info(symbol, 'CSTC', term_type=1, page_size=years)
    return _parse_nim(resp)


def _parse_nim(resp: Dict[str, Any]) -> Optional[Dict[int, float]]:
    heads: List[Dict[str, Any]] = sorted(
        (h for h in resp.get('Head') or [] if isinstance(h, dict)),
        key=lambda h: h.get('ID', 0))
    content = resp.get('Content') or {}
    rows = [r for key, group in content.items() if 'Nhóm chỉ số' in str(key)
            for r in (group or []) if isinstance(r, dict)]
    for row in rows:
        if english_to_snake(row.get('NameEn') or '') != NIM_ITEM_ID:
            continue
        out: Dict[int, float] = {}
        for i, head in enumerate(heads, 1):
            m = re.match(r'^(\d{4})', str(head.get('YearPeriod', '')))
            v = row.get(f'Value{i}')
            if not m or v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f:  # bỏ NaN
                # Năm trùng: giá trị SAU thắng, như fetch_bank_ratios cũ đọc
                # bảng vnstock ('2025', '2025_1' cùng ra năm 2025).
                out[int(m.group(1))] = f
        return out or None
    return None
