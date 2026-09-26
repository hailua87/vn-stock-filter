"""
Đổi tên trường của API sang snake_case — đúng quy tắc vnstock 4.0.7 dùng,
vì `item_id` sinh ra ở đây là khóa mà adapter chất lượng, normalizer định giá
và fixture đọc theo (vd. 'Net profit/(loss) after tax' → 'net_profit_loss_after_tax').

Đổi quy tắc ở đây là đổi khóa của mọi khoản mục BCTC: test
`test_sources.py::test_item_ids_match_vnstock_407_fixtures` giữ nó lại.
"""
from __future__ import annotations

import re
import unicodedata


def camel_to_snake(name: str) -> str:
    """'icbCodeLv2' → 'icb_code_lv2'; 'numberOfSharesMktCap' → 'number_of_shares_mkt_cap'."""
    s = re.sub(r'[\s.\-]+', '_', str(name))
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
    s = re.sub(r'([A-Z])([A-Z][a-z])', r'\1_\2', s)
    s = re.sub(r'_+', '_', s.lower())
    return s.strip('_')


def english_to_snake(text: str) -> str:
    """
    Nhãn tiếng Anh của khoản mục → item_id.

    'A. ASSETS' → 'assets'; "Owner's Equity" → 'owners_equity';
    'Cash & cash equivalents' → 'cash_and_cash_equivalents';
    'Financial assets at fair value through profit or loss (FVTPL)'
        → 'financial_assets_at_fair_value_through_profit_or_loss_fvtpl'.
    """
    if not text or not str(text).strip():
        return ''
    original = str(text)
    s = unicodedata.normalize('NFKD', original).encode('ascii', 'ignore').decode('ascii')
    # Bỏ tiền tố đánh số: '1.', '1.2.', 'IV.', 'A.'
    s = re.sub(r'^\d+(\.\d+)*\.\s*', '', s)
    s = re.sub(r'^[IVXivx]+(\.\d+)*\.\s*', '', s)
    s = re.sub(r'^[A-Za-z]\.\s*', '', s)
    s = s.lower()
    s = re.sub(r'\s*&\s*', ' and ', s)
    s = re.sub(r'^&', 'and ', s)
    s = re.sub(r'&$', ' and', s)
    s = re.sub(r"['\"`]", '', s)
    s = re.sub(r'[^a-z0-9\s_-]', ' ', s)
    s = re.sub(r'[\s\-/\\]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = f'n_{s}'
    if not s:
        fallback = re.sub(r'[^a-zA-Z0-9]', '', original)
        s = fallback.lower()[:20]
    return s
