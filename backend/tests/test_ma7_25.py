"""
Test chien luoc MA7 x MA25 (scanner/strategies/ma7_25.py) va CLI run_ma_signals.

Du lieu la duong gia tuyen tinh tung doan, dung `path()` — vi tri tung tin hieu
da do tren chinh cac duong nay va ghi lai thanh hang so. Gia doi thi test doi:
do la muc dich, de khong ai doi luat ma khong thay.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from scanner.strategies import ma7_25


def path(segs, start=20.0, base_vol=1_000_000):
    """segs: [(so phien, buoc gia, he so KL)]. Gia theo nghin dong."""
    c, v = [start], [base_vol]
    for n, step, vm in segs:
        for _ in range(n):
            c.append(c[-1] + step)
            v.append(base_vol * vm)
    c = np.array(c)
    return pd.DataFrame({
        'Date': pd.bdate_range('2025-01-01', periods=len(c)),
        'Open': c, 'High': c + 0.15, 'Low': c - 0.15, 'Close': c,
        'Volume': v, 'Exchange': 'HOSE',
    })


# Uptrend dai -> dip ngan (MA7 cat xuong) -> hoi phuc KL lon (MA7 cat len).
# Do tren duong nay: cat xuong o bar 208 (df dai 209), cat len o bar 218 (dai 219).
MUA1_SEGS = [(200, 0.05, 1), (10, -0.10, 0.8), (15, 0.15, 2.5)]
CROSS_DOWN_LEN, CROSS_UP_LEN = 209, 219

# Uptrend -> tang nhanh (Gap nong, dinh ~ bar 224) -> chinh nhe KL thap -> quay len.
MUA2_SEGS = [(200, 0.05, 1), (25, 0.06, 1.2), (10, -0.02, 0.6), (4, 0.10, 1.2)]
MUA2_LEN = 239

# Uptrend -> 3 phien giam manh KL lon: dong cua thung MA25 khi MA7 van tren.
GIAM_SEGS = [(200, 0.05, 1), (6, 0.10, 1), (3, -0.35, 2.5)]
GIAM_LEN = 210


def ev(df, n, **kw):
    kw.setdefault('market_ok', True)
    return ma7_25.evaluate(df.iloc[:n], 'TEST', **kw)


def signals_over(df, lo, hi, **kw):
    out = {}
    for n in range(lo, hi + 1):
        r = ev(df, n, **kw)
        if r and r.signal:
            out[n] = (r.signal, r.signal_age)
    return out


# ---------------------------------------------------------------- MUA_1

def test_mua1_song_dung_1_den_3_phien_sau_cat_len():
    df = path(MUA1_SEGS)
    # Phien cat (tuoi 0) chua xac nhan -> khong mua
    r0 = ev(df, CROSS_UP_LEN)
    assert r0.metrics['ma7'] > r0.metrics['ma25'], 'hang so CROSS_UP_LEN lech khoi diem cat'
    assert r0.signal != 'MUA_1'
    for age in (1, 2, 3):
        r = ev(df, CROSS_UP_LEN + age)
        assert (r.signal, r.signal_age) == ('MUA_1', age)
        assert r.actionable
        assert r.metrics['cat_lo_goi_y'] == pytest.approx(r.close * 0.93, abs=0.01)
    # Qua 3 phien: het hieu luc
    assert ev(df, CROSS_UP_LEN + 4).signal != 'MUA_1'


def test_mua1_can_kl_phien_cat():
    segs = [s if s[1] != 0.15 else (15, 0.15, 1.0) for s in MUA1_SEGS]
    r = ev(path(segs), CROSS_UP_LEN + 1)
    assert r.signal != 'MUA_1'
    assert r.checks['m1_kl_phien_cat'] is False


# ---------------------------------------------------------------- MUA_2

def test_mua2_la_su_kien_ban_mot_lan():
    df = path(MUA2_SEGS)
    hits = {n: s for n, s in signals_over(df, 228, 250).items() if s[0] == 'MUA_2'}
    assert list(hits) == [MUA2_LEN]
    r = ev(df, MUA2_LEN)
    assert r.metrics['gap'] > 0
    assert r.checks['m2_ma7_quay_len'] and r.checks['m2_kl_can']


def test_mua2_khong_ban_lai_khi_ma7_cu_tiep_tuc_tang():
    """Sau phien quay len, MA7 tang tiep voi KL thap van giu Gap thap: day la
    TRANG THAI, khong phai SU KIEN quay dau — khong duoc bao mua lai moi ngay."""
    df = path(MUA2_SEGS + [(8, 0.02, 0.5)])
    hits = [n for n, s in signals_over(df, 228, len(df)).items() if s[0] == 'MUA_2']
    assert hits == [MUA2_LEN]


def test_mua2_can_kl_can_trong_nhip_chinh():
    segs = [s if s[1] != -0.02 else (10, -0.02, 1.5) for s in MUA2_SEGS]
    r = ev(path(segs), MUA2_LEN)
    assert r.signal != 'MUA_2'
    assert r.checks['m2_kl_can'] is False


# ---------------------------------------------------------------- CHOT_LOI

def test_chot_loi_toi_da_3_phien_moi_dinh():
    got = {n: s for n, s in signals_over(path(MUA2_SEGS), 220, 238).items()
           if s[0] == 'CHOT_LOI'}
    assert [s[1] for s in got.values()] == [1, 2, 3]
    # Gap tiep tuc giam sau 3 phien: khong duoc ban CHOT_LOI moi ngay
    assert max(got) - min(got) == 2


def test_xu_huong_tang_deu_khong_chot_loi():
    """Gap gan nhu hang so -> bang P90, khong phai cang bat thuong."""
    df = path([(260, 0.05, 1)])
    assert not any(s[0] == 'CHOT_LOI' for s in signals_over(df, 150, 261).values())


def test_gap_chi_bang_p90_khong_phai_chot_loi():
    """Gap di ngang (= P90) roi giam vi gia chung lai: Gap chua tung cang hon
    muc thuong ngay cua chinh ma do, nen khong co gi de chot."""
    df = path([(260, 0.05, 1), (6, 0.0, 1)])
    assert not any(s[0] == 'CHOT_LOI' for s in signals_over(df, 255, len(df)).values())


def test_chot_loi_tat_khi_thieu_lich_su_gap():
    df = path([(139, 0.05, 1)])         # 140 phien -> ~115 diem Gap < 120
    r = ev(df, 140)
    assert r.metrics['gap_p90'] is None


# ---------------------------------------------------------------- GIAM / THOAT

def test_giam_ty_trong_khi_thung_ma25_kl_lon():
    r = ev(path(GIAM_SEGS), GIAM_LEN)
    assert r.signal == 'GIAM'
    assert r.metrics['ma7'] > r.metrics['ma25'] > r.close


def test_thoat_khi_cat_xuong_va_khong_bi_bo_loc_chan():
    df = path(MUA1_SEGS)
    for age in (0, 1, 2):
        r = ev(df, CROSS_DOWN_LEN + age, market_ok=False)
        assert (r.signal, r.signal_age) == ('THOAT', age)
        assert r.actionable and r.blocked_by == []
    assert ev(df, CROSS_DOWN_LEN + 3).signal is None


# ---------------------------------------------------------------- Bo loc

def test_mua_bi_chan_khi_vnindex_duoi_ma50_hoac_khong_ro():
    df = path(MUA1_SEGS)
    r = ev(df, CROSS_UP_LEN + 1, market_ok=False)
    assert r.signal == 'MUA_1' and not r.actionable
    assert r.blocked_by == ['vnindex_duoi_ma50']
    r = ev(df, CROSS_UP_LEN + 1, market_ok=None)
    assert r.blocked_by == ['khong_ro_vnindex']


def test_mua_bi_chan_khi_thanh_khoan_thap():
    # ~30 nghin dong x 100.000 cp ~ 3 ty/phien < 10 ty
    r = ev(path(MUA1_SEGS, base_vol=100_000), CROSS_UP_LEN + 1)
    assert r.signal == 'MUA_1'
    assert 'thanh_khoan_thap' in r.blocked_by


def test_mua_bi_chan_khi_gia_duoi_ma99():
    # Downtrend dai roi hoi: MA7 cat len MA25 nhung gia van duoi MA99
    segs = [(200, -0.03, 1), (10, -0.10, 0.8), (15, 0.15, 2.5)]
    df = path(segs, start=30.0)
    hits = {n: s for n, s in signals_over(df, 212, 226).items() if s[0] == 'MUA_1'}
    assert hits, 'duong gia khong con tao MUA_1 — test se xanh ma khong kiem gi'
    for n in hits:
        assert 'duoi_ma99' in ev(df, n).blocked_by


# ---------------------------------------------------------------- Danh muc

def test_dang_giu_cham_cat_lo_thi_thoat():
    df = path(MUA1_SEGS)
    r = ev(df, 205)                     # dang dip, chua cat xuong
    assert r.signal is None
    held = ev(df, 205, entry_price=r.close / 0.92)  # lo ~8%
    assert held.signal == 'THOAT' and held.position['cham_cat_lo']


def test_dang_giu_ma7_duoi_ma25_qua_cua_so_van_thoat():
    df = path(MUA1_SEGS)
    n = CROSS_DOWN_LEN + 5             # cat xuong 5 phien truoc, van duoi
    assert ev(df, n).signal is None
    held = ev(df, n, entry_price=ev(df, n).close)
    assert held.signal == 'THOAT'


def test_dang_giu_khong_tin_hieu_la_giu():
    df = path([(260, 0.05, 1)])
    r = ev(df, 240, entry_price=25.0)
    assert r.signal == 'GIU'
    assert r.position['lai_lo_pct'] > 0


# ---------------------------------------------------------------- Du lieu

def test_stale_va_thieu_lich_su_tra_none():
    df = path(MUA1_SEGS)
    stale = df.iloc[:CROSS_UP_LEN + 1].copy()
    stale['StaleCache'] = False
    stale.loc[stale.index[-1], 'StaleCache'] = True
    assert ma7_25.evaluate(stale, 'T', market_ok=True) is None
    assert ma7_25.evaluate(df.iloc[:129], 'T', market_ok=True) is None


def test_to_dict_co_cot_chinh():
    d = ev(path(MUA1_SEGS), CROSS_UP_LEN + 1).to_dict()
    for k in ('ticker', 'signal', 'signal_age', 'actionable', 'blocked_by',
              'c_mua_1', 'm_gap', 'm_gap_p90', 'm_ma99', 'm_avg_value20_ty'):
        assert k in d


# ---------------------------------------------------------------- Entrypoint

def test_cli_cache_only_tu_dau_den_cuoi(tmp_path, monkeypatch, capsys):
    """Di qua run_ma_signals.main: doc cache -> loc VN-Index -> CSV."""
    import run_ma_signals as cli

    cache = tmp_path / 'cache'
    cache.mkdir()
    mua = path(MUA1_SEGS).iloc[:CROSS_UP_LEN + 1]
    thoat = path(MUA1_SEGS).iloc[:CROSS_DOWN_LEN]
    # Cung ngay phien cuoi cho ca ro, nhu du lieu that
    thoat = thoat.assign(Date=mua['Date'].iloc[-len(thoat):].values)
    mua.drop(columns='Exchange').to_parquet(cache / 'AAA_adj.parquet', index=False)
    thoat.drop(columns='Exchange').to_parquet(cache / 'BBB_adj.parquet', index=False)
    idx = pd.DataFrame({'Date': mua['Date'], 'Close': np.linspace(1000, 1300, len(mua))})
    idx.to_parquet(cache / 'vnindex.parquet', index=False)

    last = mua['Date'].iloc[-1].date()
    monkeypatch.setattr(cli, 'CACHE_DIR', cache)
    monkeypatch.setattr(cli, 'VNINDEX_CACHE', cache / 'vnindex.parquet')
    monkeypatch.setattr(cli, 'last_expected_session', lambda _now: last)
    out_dir = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv', ['run_ma_signals.py', '--cache-only',
                                      '--out-dir', str(out_dir)])

    assert cli.main() == 0
    csv = pd.read_csv(out_dir / f'ma7_25_{last}.csv')
    assert dict(zip(csv['ticker'], csv['signal'])) == {'AAA': 'MUA_1', 'BBB': 'THOAT'}
    printed = capsys.readouterr().out
    assert 'MUA 1' in printed and 'AAA' in printed


def test_cli_vnindex_duoi_ma50_chan_mua(tmp_path, monkeypatch, capsys):
    import run_ma_signals as cli

    cache = tmp_path / 'cache'
    cache.mkdir()
    mua = path(MUA1_SEGS).iloc[:CROSS_UP_LEN + 1]
    mua.to_parquet(cache / 'AAA_adj.parquet', index=False)
    idx = pd.DataFrame({'Date': mua['Date'], 'Close': np.linspace(1300, 1000, len(mua))})
    idx.to_parquet(cache / 'vnindex.parquet', index=False)

    last = mua['Date'].iloc[-1].date()
    monkeypatch.setattr(cli, 'CACHE_DIR', cache)
    monkeypatch.setattr(cli, 'VNINDEX_CACHE', cache / 'vnindex.parquet')
    monkeypatch.setattr(cli, 'last_expected_session', lambda _now: last)
    monkeypatch.setattr(sys, 'argv', ['run_ma_signals.py', '--cache-only',
                                      '--out-dir', str(tmp_path / 'out')])

    assert cli.main() == 0
    printed = capsys.readouterr().out
    assert 'VN-Index DUOI MA50' in printed
    assert '1 tin hieu MUA bi bo loc chan: vnindex_duoi_ma50 1' in printed
    csv = pd.read_csv(tmp_path / 'out' / f'ma7_25_{last}.csv')
    assert csv.loc[0, 'actionable'] == False  # noqa: E712
