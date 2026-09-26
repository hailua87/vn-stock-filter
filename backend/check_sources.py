"""
Kiểm lớp nguồn (`scanner/sources/`) trên API THẬT — cần mạng.

Chạy:  python backend/check_sources.py        (thoát 1 nếu có kiểm hỏng)

Vì sao cần: test đơn vị chỉ chạy trên phản hồi dựng tay, không chứng minh được
API thật trả đúng hình dạng đó. Script này là bằng chứng còn thiếu, và chạy
trong CI (job `sources-live`) mỗi lần có PR.

Phép kiểm mạnh nhất là so BCTC với fixture `tests/fixtures/vnstock407_*.json`:
đó là output của vnstock 4.0.7 đã dùng thật trong production (21–22/09/2026),
đã nhân FIXTURE_SCALE. Nếu lớp nguồn đọc cùng API cho ra cùng item_id, cùng
nhãn kỳ, cùng đơn vị ĐỒNG và cùng dấu, thì `live × FIXTURE_SCALE == fixture`
ở từng ô. Lệch vài ô là chuyện thường (doanh nghiệp sửa số liệu kỳ cũ); lệch
nhiều hoặc thiếu khoản mục là lớp nguồn đọc sai.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'tests'))

from fixture_scale import FIXTURE_SCALE  # noqa: E402
from scanner.sources import kbs, vci  # noqa: E402
from scanner.sources.http import with_retry  # noqa: E402

FIXTURES = HERE / 'tests' / 'fixtures'
TABLES = ('balance_sheet', 'income', 'cash_flow')

# Tỷ lệ ô được phép lệch fixture (số liệu kỳ cũ bị doanh nghiệp sửa lại).
MAX_MISMATCH_SHARE = 0.10

failures: list[str] = []


def check(ok: bool, what: str, detail: str = '') -> None:
    print(f"  [{'OK ' if ok else 'HỎNG'}] {what}" + (f' — {detail}' if detail else ''))
    if not ok:
        failures.append(what)


def check_prices() -> None:
    print('Giá ngày (VCI)')
    end = date.today()
    start = end - timedelta(days=30)
    df = with_retry(vci.ohlcv, 'FPT', str(start), str(end), tries=2)
    check(len(df) >= 10, 'FPT có >= 10 phiên trong 30 ngày', f'{len(df)} phiên')
    if len(df):
        c = float(df['close'].iloc[-1])
        # Nghìn đồng: FPT quanh vài chục tới vài trăm. Theo đồng sẽ ra hàng chục nghìn.
        check(5 < c < 1000, 'giá theo NGHÌN đồng', f'close={c}')
        check(list(df.columns) == vci.OHLCV_COLUMNS, 'đúng cột', str(list(df.columns)))
        check(df['time'].is_monotonic_increasing, 'ngày tăng dần')
    idx = with_retry(vci.ohlcv, 'VNINDEX', str(start), str(end), tries=2)
    check(len(idx) >= 10, 'VN-Index có dữ liệu', f'{len(idx)} phiên')
    if len(idx):
        c = float(idx['close'].iloc[-1])
        check(300 < c < 5000, 'VN-Index KHÔNG chia 1.000', f'close={c}')


def check_listing() -> None:
    print('Danh sách mã (KBS)')
    df = with_retry(kbs.listing, tries=2)
    stocks = df[df['type'] == 'stock']
    check(len(stocks) > 1000, '> 1.000 cổ phiếu', f'{len(stocks)}')
    ex = set(stocks['exchange'])
    check({'HOSE', 'HNX', 'UPCOM'} <= ex, 'có đủ 3 sàn', str(sorted(ex)))
    fpt = stocks[stocks['symbol'] == 'FPT']
    check(len(fpt) == 1 and fpt['exchange'].iloc[0] == 'HOSE', 'FPT ở HOSE',
          str(fpt[['symbol', 'exchange']].to_dict('records')))


def check_overview() -> None:
    print('Tổng quan công ty (VCI)')
    row = with_retry(vci.company_overview, 'VCB', tries=2) or {}
    for key in ('sector', 'icb_code_lv2', 'icb_code_lv4', 'issue_share'):
        check(row.get(key) not in (None, ''), f'VCB có `{key}`', repr(row.get(key)))
    check(str(row.get('icb_code_lv2')) == '8300', 'VCB thuộc ICB 8300 (Ngân hàng)',
          repr(row.get('icb_code_lv2')))


def check_statements() -> None:
    print('BCTC (VCI) so với fixture vnstock 4.0.7')
    for path in sorted(FIXTURES.glob('vnstock407_*.json')):
        ticker, period = path.stem.split('_')[1:3]
        fx = json.loads(path.read_text(encoding='utf-8'))
        for table in TABLES:
            label = f'{ticker} {period} {table}'
            # Mỗi bảng một try riêng, thử lại một lần: một lần mạng chập chờn
            # không được làm hỏng 17 bảng còn lại.
            try:
                live = with_retry(vci.financial_statement, ticker, table, period=period, tries=2)
            except Exception as e:
                check(False, label, f'{type(e).__name__}: {e}')
                continue
            if live.empty:
                check(False, label, 'rỗng')
                continue
            compare_table(label, fx[table], live)


def compare_table(label: str, fx_table: dict, live) -> None:
    fx_periods = fx_table['columns'][3:]
    no_en = int(live['item_en'].isna().sum())
    check(no_en == 0, f'{label}: mọi khoản mục có nhãn tiếng Anh',
          f'{no_en} dòng thiếu → item_id "0" (§5.4)' if no_en else '')
    missing = sorted({r[2] for r in fx_table['data']} - set(live['item_id']))
    check(not missing, f'{label}: đủ item_id', f'thiếu {missing[:5]}' if missing else '')

    # Ô so sánh: (item_id, kỳ) có ở cả hai phía. Lấy dòng ĐẦU của mỗi item_id
    # và cột ĐẦU của mỗi nhãn kỳ, như statement_to_records.
    first = live.drop_duplicates('item_id').set_index('item_id')
    first = first.loc[:, ~first.columns.duplicated()]
    periods = [c for c in first.columns if c not in ('item', 'item_en')]
    total = bad = 0
    for row in fx_table['data']:
        item_id = row[2]
        if item_id not in first.index:
            continue
        for p, v in zip(fx_periods, row[3:]):
            if p not in periods or v is None:
                continue
            try:
                lv = float(first.at[item_id, p])
            except (TypeError, ValueError):
                lv = float('nan')
            total += 1
            if not abs(lv * FIXTURE_SCALE - float(v)) <= max(1.0, abs(float(v)) * 1e-6):
                bad += 1
    shared = [p for p in fx_periods if p in periods]
    # Quý: fixture dừng ở 2026-Q2. Khi API chỉ trả 8 quý gần nhất, số kỳ chung
    # giảm dần theo thời gian — ngưỡng 4 đủ dùng tới khoảng giữa 2027.
    check(len(shared) >= min(4, len(fx_periods)), f'{label}: nhãn kỳ khớp',
          f'chung {len(shared)}/{len(fx_periods)} kỳ, live có {periods[:5]}')
    share = bad / total if total else 1.0
    check(total > 0 and share <= MAX_MISMATCH_SHARE, f'{label}: giá trị khớp',
          f'{total - bad}/{total} ô khớp')


def check_bank_nim() -> None:
    print('NIM ngân hàng (KBS)')
    nim = with_retry(kbs.bank_nim, 'VCB', tries=2) or {}
    check(len(nim) >= 3, 'VCB có NIM >= 3 năm', str(nim))
    check(all(0.5 < v < 10 for v in nim.values()), 'NIM theo PHẦN TRĂM', str(nim))


def check_events() -> None:
    print('Sự kiện quyền (VCI)')
    df = with_retry(vci.events, 'FPT', tries=2)
    check(not df.empty, 'FPT có sự kiện', f'{len(df)} dòng')
    if not df.empty:
        check('public_date' in df.columns, 'có cột public_date', str(list(df.columns)[:12]))


def main() -> int:
    for fn in (check_prices, check_listing, check_overview, check_statements,
               check_bank_nim, check_events):
        try:
            fn()
        except Exception as e:  # một nhóm hỏng không che các nhóm sau
            check(False, fn.__name__, f'{type(e).__name__}: {e}')
    print()
    if failures:
        print(f'HỎNG {len(failures)} kiểm:')
        for f in failures:
            print(f'  - {f}')
        return 1
    print('Tất cả kiểm đều qua.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
