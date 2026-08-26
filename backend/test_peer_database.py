#!/usr/bin/env python3
"""
Test peer_database module: build → save → load → lookup.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tempfile

from scanner.peer_database import (
    build_peer_database,
    save_peer_database,
    load_peer_database,
    get_peer_median,
    get_peer_band,
)


try:
    import pytest

    @pytest.fixture(name='db')
    def _db_fixture():
        """
        Cho phép pytest chạy test_save_load/test_lookup — hai hàm này vốn viết
        theo kiểu script (nhận `db` từ main()). Không có fixture này, pytest coi
        `db` là fixture thiếu và báo ERROR khi CI quét cả thư mục backend.
        """
        return test_build_peer_db()
except ImportError:      # chạy bằng `python test_peer_database.py`
    pytest = None


def test_build_peer_db():
    print("=" * 70)
    print("TEST: BUILD PEER DATABASE")
    print("=" * 70)

    # Mô phỏng kết quả pass 1 của run_valuation cho 5 ngân hàng + 5 consumer + 3 thép
    mock_inputs = [
        # Banking
        {'ticker': 'VCB', 'industry': 'Banking', 'pe': 13.5, 'pb': 2.8, 'roe': 0.22},
        {'ticker': 'BID', 'industry': 'Banking', 'pe': 11.2, 'pb': 1.9, 'roe': 0.19},
        {'ticker': 'CTG', 'industry': 'Banking', 'pe': 9.8,  'pb': 1.6, 'roe': 0.18},
        {'ticker': 'MBB', 'industry': 'Banking', 'pe': 6.5,  'pb': 1.3, 'roe': 0.21},
        {'ticker': 'TCB', 'industry': 'Banking', 'pe': 7.2,  'pb': 1.2, 'roe': 0.17},
        {'ticker': 'VIB', 'industry': 'Banking', 'pe': 7.4,  'pb': 1.48, 'roe': 0.20},
        {'ticker': 'ACB', 'industry': 'Banking', 'pe': 8.1,  'pb': 1.5, 'roe': 0.23},
        {'ticker': 'HDB', 'industry': 'Banking', 'pe': 6.8,  'pb': 1.4, 'roe': 0.22},

        # Consumer Staples
        {'ticker': 'VNM', 'industry': 'Consumer_Staples', 'pe': 16.5, 'pb': 3.8, 'ev_ebitda': 11.0, 'roe': 0.24},
        {'ticker': 'SAB', 'industry': 'Consumer_Staples', 'pe': 19.2, 'pb': 4.1, 'ev_ebitda': 13.5, 'roe': 0.22},
        {'ticker': 'MSN', 'industry': 'Consumer_Staples', 'pe': 35.5, 'pb': 2.5, 'ev_ebitda': 9.8, 'roe': 0.08},
        {'ticker': 'KDC', 'industry': 'Consumer_Staples', 'pe': 22.1, 'pb': 1.5, 'ev_ebitda': 10.5, 'roe': 0.07},
        {'ticker': 'MCH', 'industry': 'Consumer_Staples', 'pe': 14.8, 'pb': 4.5, 'ev_ebitda': 9.2, 'roe': 0.30},

        # Steel (cyclical)
        {'ticker': 'HPG', 'industry': 'Steel_Metals', 'pe': 12.5, 'pb': 1.5, 'ev_ebitda': 7.2, 'roe': 0.12},
        {'ticker': 'HSG', 'industry': 'Steel_Metals', 'pe': 18.5, 'pb': 1.1, 'ev_ebitda': 8.5, 'roe': 0.06},
        {'ticker': 'NKG', 'industry': 'Steel_Metals', 'pe': 15.0, 'pb': 0.9, 'ev_ebitda': 7.8, 'roe': 0.06},
    ]

    db = build_peer_database(mock_inputs)

    print(f"  Total tickers   : {db['total_tickers']}")
    print(f"  Industries      : {len(db['industries'])}")
    for industry, stats in db['industries'].items():
        print(f"\n  ▶ {industry} (n={stats['ticker_count']})")
        for metric in ['pe', 'pb', 'ev_ebitda', 'roe']:
            m = stats.get(metric)
            if m:
                print(f"      {metric:<12} median={m['median']:>6}  "
                      f"P25={m['p25']:>6}  P75={m['p75']:>6}  n={m['n']}")
            else:
                print(f"      {metric:<12} N/A (not relevant or insufficient data)")

    # Verify Banking stats hợp lý
    banking = db['industries']['Banking']
    assert banking['ticker_count'] == 8
    assert 7 < banking['pe']['median'] < 10, f"Banking P/E median bất thường: {banking['pe']['median']}"
    assert 1.3 < banking['pb']['median'] < 2.0, f"Banking P/B median bất thường: {banking['pb']['median']}"

    # Steel KHÔNG có P/E (vì cyclical)
    steel = db['industries']['Steel_Metals']
    assert steel.get('pe') is None, "Steel không nên có peer P/E (cyclical)"
    assert steel['ev_ebitda'] is not None, "Steel phải có peer EV/EBITDA"

    print("\n  ✓ Banking stats trong dải hợp lý")
    print("  ✓ Steel_Metals đúng: không có P/E peer (cyclical), có EV/EBITDA")
    return db


def test_save_load(db):
    print("\n" + "=" * 70)
    print("TEST: SAVE & LOAD PEER DATABASE")
    print("=" * 70)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = Path(f.name)

    save_peer_database(db, path=temp_path)
    loaded = load_peer_database(path=temp_path)

    assert loaded is not None, "Failed to load saved DB"
    assert loaded['total_tickers'] == db['total_tickers']
    assert set(loaded['industries'].keys()) == set(db['industries'].keys())

    print(f"  ✓ Save/load round-trip works")
    print(f"  ✓ Loaded {loaded['total_tickers']} tickers from {temp_path}")

    temp_path.unlink()
    return loaded


def test_lookup(db):
    print("\n" + "=" * 70)
    print("TEST: PEER LOOKUP API")
    print("=" * 70)

    cases = [
        # (industry, metric, expected_in_range)
        ('Banking', 'pe', (7, 10)),
        ('Banking', 'pb', (1.3, 1.9)),
        ('Banking', 'roe', (0.18, 0.23)),
        ('Consumer_Staples', 'ev_ebitda', (9, 13)),
        ('Steel_Metals', 'ev_ebitda', (7, 9)),
        ('Steel_Metals', 'pe', None),  # Should return None
        ('NonExistentIndustry', 'pe', None),
    ]

    all_passed = True
    for industry, metric, expected_range in cases:
        median = get_peer_median(industry, metric, peer_db=db)
        if expected_range is None:
            passed = median is None
            status = "✓" if passed else "✗"
            print(f"  {status} {industry:<22} {metric:<12} → {median} (expected None)")
        else:
            lo, hi = expected_range
            passed = median is not None and lo <= median <= hi
            status = "✓" if passed else "✗"
            print(f"  {status} {industry:<22} {metric:<12} → {median} (expected {lo}-{hi})")
        all_passed = all_passed and passed

    band = get_peer_band('Banking', 'pe', peer_db=db)
    print(f"\n  Banking P/E full band: median={band['median']}, "
          f"P25={band['p25']}, P75={band['p75']}, n={band['n']}")

    return all_passed


if __name__ == '__main__':
    db = test_build_peer_db()
    test_save_load(db)
    lookup_pass = test_lookup(db)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  {'✓ ALL PASS' if lookup_pass else '✗ SOME FAILED'}")
    sys.exit(0 if lookup_pass else 1)
