"""
Vietcap (VCI): giá ngày, tổng quan công ty, BCTC, sự kiện quyền.

Mỗi hàm trả đúng hình dạng vnstock 4.0.7 trả cho cùng việc (xem docstring
từng hàm), để code gọi phía sau không đổi.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .http import SourceError, request_json
from .naming import camel_to_snake, english_to_snake

TRADING_URL = 'https://trading.vietcap.com.vn/api'
IQ_URL = 'https://iq.vietcap.com.vn/api/iq-insight-service'

HEADERS = {
    'Referer': 'https://trading.vietcap.com.vn/',
    'Origin': 'https://trading.vietcap.com.vn/',
}

# Mã chỉ số theo cách VCI gọi. Giá chỉ số KHÔNG chia 1.000 như giá cổ phiếu.
INDEX_SYMBOLS = {
    'VNINDEX': 'VNINDEX', 'VNI': 'VNINDEX',
    'VN30': 'VN30',
    'HNXINDEX': 'HNXIndex', 'HNX': 'HNXIndex',
    'UPCOMINDEX': 'HNXUpcomIndex', 'UPCOM': 'HNXUpcomIndex',
}

STATEMENT_SECTIONS = {
    'balance_sheet': 'BALANCE_SHEET',
    'income': 'INCOME_STATEMENT',
    'cash_flow': 'CASH_FLOW',
}

OHLCV_COLUMNS = ['time', 'open', 'high', 'low', 'close', 'volume']


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    return request_json('GET', url, headers=HEADERS, params=params)


def _data(resp: Any, what: str) -> Any:
    if not isinstance(resp, dict) or resp.get('data') is None:
        raise SourceError(f'VCI {what}: phản hồi không có "data"')
    return resp['data']


def _parse_day(s: str) -> datetime:
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f'Ngày không hợp lệ: {s!r} (cần YYYY-MM-DD)')


# ── Giá ngày ──────────────────────────────────────────────────────────────

def ohlcv(symbol: str, start: str, end: Optional[str] = None) -> pd.DataFrame:
    """
    Nến ngày từ `start` tới hết ngày `end` (mặc định hôm nay).

    Trả DataFrame cột time, open, high, low, close, volume; `time` là ngày theo
    giờ Việt Nam; giá cổ phiếu theo NGHÌN đồng làm tròn 2 số (ACB = 24.30), giá
    chỉ số giữ nguyên. Rỗng nếu nguồn không có dữ liệu.

    VCI trả giá đã điều chỉnh cổ tức/chia tách (backward-adjusted) — xem
    `data_fetcher.fetch_ohlcv`.
    """
    sym = symbol.upper().strip()
    is_index = sym in INDEX_SYMBOLS
    api_symbol = INDEX_SYMBOLS.get(sym, sym)

    start_dt = _parse_day(start)
    end_dt = (_parse_day(end) + timedelta(days=1)) if end else (datetime.now() + timedelta(days=1))
    if start_dt > end_dt:
        raise ValueError('start sau end')
    # API đếm lùi `countBack` nến từ `to`. Số ngày làm việc (tính cả ngày lễ)
    # luôn >= số phiên, nên đủ phủ từ `start`.
    count_back = len(pd.bdate_range(start=start_dt, end=end_dt)) + 1
    payload = {
        'timeFrame': 'ONE_DAY',
        'symbols': [api_symbol],
        'to': int(end_dt.timestamp()),
        'countBack': count_back,
    }
    resp = request_json('POST', f'{TRADING_URL}/chart/OHLCChart/gap-chart',
                        headers=HEADERS, payload=payload)
    return _ohlcv_frame(resp, is_index)


def _ohlcv_frame(resp: Any, is_index: bool) -> pd.DataFrame:
    rows = resp.get('data') if isinstance(resp, dict) else resp
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    series = rows[0]
    if not series.get('t'):
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    df = pd.DataFrame({k: series.get(k) for k in ('t', 'o', 'h', 'l', 'c', 'v')})
    df.columns = OHLCV_COLUMNS
    df['time'] = (pd.to_datetime(pd.to_numeric(df['time']).astype('int64'), unit='s', utc=True)
                  .dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None).dt.normalize())
    prices = ['open', 'high', 'low', 'close']
    df[prices] = df[prices].apply(pd.to_numeric, errors='coerce').astype('float64')
    if not is_index:
        df[prices] = df[prices] / 1000
    df[prices] = df[prices].round(2)
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype('int64')
    return df.reset_index(drop=True)


# ── Tổng quan công ty ─────────────────────────────────────────────────────

_OVERVIEW_RENAME = {
    'vi_organ_name': 'organ_name',
    'vi_organ_short_name': 'organ_short_name',
    'profile': 'company_profile',
    'number_of_shares_mkt_cap': 'issue_share',
    'ticker': 'symbol',
}


def company_overview(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Một bản ghi tổng quan công ty, khóa snake_case như vnstock 4.0.7:
    `symbol`, `sector` (tên ICB cấp 2 tiếng Anh, vd. 'Banks'), `icb_code_lv2`,
    `icb_code_lv4`, `issue_share`, … Bỏ trường tiếng Anh `en_*` và `sector_vn`
    (khi đã có `sector`). None nếu nguồn không có.
    """
    data = _data(_get(f'{IQ_URL}/v1/company/details', {'ticker': symbol.upper()}),
                 f'details {symbol}')
    if not isinstance(data, dict) or not data:
        return None
    row = {}
    for k, v in data.items():
        key = camel_to_snake(k)
        if re.search('en_', key, re.IGNORECASE) or '__' in key:
            continue
        row[key] = v
    if 'sector' in row:
        row.pop('sector_vn', None)
    for old, new in _OVERVIEW_RENAME.items():
        if old in row:
            row[new] = row.pop(old)
    return row


# ── BCTC ──────────────────────────────────────────────────────────────────

_metrics_cache: Dict[str, Dict[str, Tuple[Optional[str], Optional[str]]]] = {}


def _statement_labels(symbol: str) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """{mã trường VCI: (nhãn Việt, nhãn Anh)} cho mọi khoản mục BCTC của mã."""
    sym = symbol.upper()
    if sym not in _metrics_cache:
        data = _data(_get(f'{IQ_URL}/v1/company/{sym}/financial-statement/metrics'),
                     f'metrics {sym}')
        labels: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for items in (data.values() if isinstance(data, dict) else []):
            for it in items or []:
                field = it.get('field')
                if field:
                    labels[field] = (it.get('titleVi'), it.get('titleEn'))
        _metrics_cache[sym] = labels
    return _metrics_cache[sym]


def _period_label(rec: Dict[str, Any], quarterly: bool) -> str:
    # Như vnstock: ưu tiên year/quarter nếu có, sau đó yearReport/lengthReport.
    year = rec['year'] if 'year' in rec else rec.get('yearReport')
    q = rec['quarter'] if 'quarter' in rec else rec.get('lengthReport')
    try:
        y, qn = int(year), int(q)
    except (TypeError, ValueError):
        return str(year) if year is not None else 'N/A'
    return f'{y}-Q{qn}' if (quarterly and qn < 5) else f'{y}'


def financial_statement(symbol: str, table: str, period: str = 'year') -> pd.DataFrame:
    """
    Một bảng BCTC dạng dài như vnstock 4.0.7: dòng = khoản mục
    (`item`, `item_en`, `item_id`), mỗi cột còn lại một kỳ ('2025' hoặc
    '2026-Q2'), giá trị theo ĐỒNG, ô trống = 0, bỏ kỳ toàn 0.

    table: 'balance_sheet' | 'income' | 'cash_flow'; period: 'year' | 'quarter'.
    """
    if table not in STATEMENT_SECTIONS:
        raise ValueError(f'table không hợp lệ: {table}')
    if period not in ('year', 'quarter'):
        raise ValueError(f'period không hợp lệ: {period}')
    sym = symbol.upper()
    data = _data(_get(f'{IQ_URL}/v1/company/{sym}/financial-statement',
                      {'section': STATEMENT_SECTIONS[table]}), f'{table} {sym}')
    records: List[Dict[str, Any]] = (data.get('years' if period == 'year' else 'quarters') or []
                                     if isinstance(data, dict) else [])
    if not records:
        return pd.DataFrame()
    return _statement_frame(records, _statement_labels(sym), quarterly=(period == 'quarter'))


def _statement_frame(records: List[Dict[str, Any]],
                     labels: Dict[str, Tuple[Optional[str], Optional[str]]],
                     quarterly: bool) -> pd.DataFrame:
    report = pd.DataFrame(records)
    periods = [_period_label(r, quarterly) for r in records]
    # Giữ thứ tự trường như API trả: item_id trùng (vd. SSI hai dòng
    # short_term_borrowings) thì statement_to_records lấy dòng đầu.
    fields = [c for c in report.columns if c in labels]
    if not fields:
        return pd.DataFrame()
    raw = report[fields]
    numeric = raw.apply(pd.to_numeric, errors='coerce')
    # Ô trống (None/NaN) → 0 như vnstock (dropna=True làm fillna(0)). Ô có chữ
    # không phải số: vnstock giữ nguyên chuỗi, statement_to_records bỏ qua nó —
    # ở đây để NaN cho cùng kết quả, KHÔNG thành 0.
    text_cells = raw.notna() & numeric.isna()
    values = numeric.fillna(0.0).mask(text_cells).T
    values.columns = periods
    # Bỏ kỳ mà mọi khoản mục đều 0 (vnstock dropna=True làm vậy; ô chữ tính là
    # khác 0). iloc + mảng bool: nhãn kỳ có thể trùng, .loc với nhãn trùng sẽ lỗi.
    values = values.iloc[:, (values != 0).any(axis=0).to_numpy()]
    vi = [labels[f][0] for f in fields]
    en = [labels[f][1] for f in fields]
    # Không có nhãn tiếng Anh: vnstock cho item_id NaN rồi fillna(0) thành 0 —
    # giữ đúng '0' để hash sổ snapshot không đổi. Chưa gặp trên dữ liệu thật.
    ids = [english_to_snake(e) if e else '0' for e in en]
    out = pd.DataFrame({'item': vi, 'item_en': en, 'item_id': ids})
    return pd.concat([out, values.reset_index(drop=True)], axis=1)


# ── Sự kiện quyền ─────────────────────────────────────────────────────────

EVENT_CODES = 'DIV,ISS,DDIND,DDINS,DDRP,AGME,AGMR,EGME,AIS,MA,MOVE,NLIS,OTHE,RETU,SUSP'
_EVENT_DROP = {'organ_code', 'symbol', '__typename', 'is_event', 'event',
               'organ_name_en', 'organ_name_vi'}
_EVENT_DATES = ('public_date', 'issue_date', 'record_date', 'exright_date', 'display_date')


def events(symbol: str, size: int = 50) -> pd.DataFrame:
    """
    Sự kiện doanh nghiệp 10 năm gần nhất (tối đa `size` bản ghi), cột
    snake_case, cột ngày đổi sang 'YYYY-MM-DD' — như vnstock 4.0.7 `events()`.
    """
    today = datetime.now()
    params = {
        'ticker': symbol.upper(),
        'fromDate': (today - timedelta(days=365 * 10)).strftime('%Y%m%d'),
        'toDate': today.strftime('%Y%m%d'),
        'eventCode': EVENT_CODES,
        'page': 0,
        'size': size,
    }
    resp = _get(f'{IQ_URL}/v1/events', params)
    data = resp.get('data') if isinstance(resp, dict) else None
    content = data.get('content', []) if isinstance(data, dict) else []
    if not content:
        return pd.DataFrame()
    df = pd.DataFrame(content)
    df.columns = [camel_to_snake(c) for c in df.columns]
    df = df.drop(columns=[c for c in df.columns if c in _EVENT_DROP])
    for col in _EVENT_DATES:
        if col not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_datetime(df[col], unit='ms').dt.strftime('%Y-%m-%d')
        else:
            parsed = pd.to_datetime(df[col], errors='coerce')
            df[col] = parsed.dt.strftime('%Y-%m-%d').where(parsed.notna(), df[col])
    return df
