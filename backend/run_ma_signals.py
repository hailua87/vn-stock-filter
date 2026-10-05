#!/usr/bin/env python3
"""
Loc co phieu theo bo tin hieu MA7 x MA25 (scanner/strategies/ma7_25.py).

Vi du:
    # Quet ca ro (lay du lieu moi, dung cache parquet co san)
    python backend/run_ma_signals.py

    # Chi doc cache, khong goi mang — nhanh, dung sau khi run_daily da chay
    python backend/run_ma_signals.py --cache-only

    # Mot vai ma + danh muc dang giu de kiem tra cat lo / tin hieu thoat
    python backend/run_ma_signals.py --tickers FPT,HPG,VIB --holdings danh_muc.csv

Tep danh muc (CSV, UTF-8): hai cot `ma,gia_mua`, gia theo NGHIN dong nhu bang
dien (VIB mua 18.500d -> 18.5). Nhap nham theo dong (18500) van duoc — script
tu nhan ra va quy doi, kem canh bao.

Ket qua: in ra man hinh theo nhom tin hieu, va ghi CSV
backend/data/results/ma7_25_<ngay phien>.csv (mo duoc bang Excel).

Gioi han da biet: --cache-only khong co san cua ma (cache khong luu), nen bien
do mac dinh theo HOSE 7% — canh bao tran/san va "nghi gia chua dieu chinh" co
the bao oan cho ma HNX/UPCoM. Che do lay du lieu thuong khong bi.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import base_conditions as BC
from scanner.data_fetcher import (
    CACHE_DIR, VNINDEX_CACHE, get_ticker_universe, fetch_universe, fetch_vnindex,
)
from scanner.market_regime import compute_regime
from scanner.price_units import vnd_to_quote
from scanner.strategies import ma7_25
from scanner.trading_calendar import last_expected_session, now_ict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('ma7_25')

# 400 ngay lich ~ 270 phien: du MA99 va du ~245 diem Gap cho phan vi 90.
# Thap hon thi CHOT_LOI tat lang le (gap_hist_min) — xem ma7_25.DEFAULT_CONFIG.
DEFAULT_LOOKBACK = 400

SECTION_ORDER = [
    ('THOAT', 'THOAT HET — MA7 cat xuong MA25 / cham cat lo'),
    ('GIAM', 'GIAM TY TRONG — dong cua duoi MA25, KL lon'),
    ('CHOT_LOI', 'CHOT LOI 30-50% — Gap vua qua dinh vung phan vi 90'),
    ('MUA_1', 'MUA 1 — giao cat da xac nhan'),
    ('MUA_2', 'MUA 2 — nhip chinh trong xu huong tang'),
    ('GIU', 'DANG GIU — chua co tin hieu'),
]


def load_holdings(path: Path) -> dict:
    """{ma: gia_mua} theo nghin dong. Chap nhan cot ma/ticker va gia_mua/entry."""
    df = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in df.columns}
    tk_col = cols.get('ma') or cols.get('ticker')
    px_col = cols.get('gia_mua') or cols.get('entry') or cols.get('entry_price')
    if not tk_col or not px_col:
        raise SystemExit(f"{path}: can cot `ma,gia_mua` (hien co: {list(df.columns)})")
    out = {}
    for _, r in df.iterrows():
        tk = str(r[tk_col]).strip().upper()
        if not tk or pd.isna(r[px_col]):
            continue
        out[tk] = float(r[px_col])
    return out


def load_cache_only(tickers: list | None) -> pd.DataFrame:
    """Doc parquet cache, danh dau StaleCache theo lich giao dich — khong goi mang."""
    from run_backtest import load_universe_from_cache
    by_ticker = load_universe_from_cache(CACHE_DIR)
    if tickers:
        by_ticker = {t: d for t, d in by_ticker.items() if t in set(tickers)}
    expected = last_expected_session(now_ict())
    frames = []
    for tk, d in by_ticker.items():
        d = d.copy()
        d['Ticker'] = tk
        if 'Exchange' not in d.columns:
            d['Exchange'] = ''
        # Cache khong mang co stale — tu tinh lai, cung moc voi fetch_with_cache
        d['StaleCache'] = d['Date'].max().date() < expected
        frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_vnindex(cache_only: bool) -> pd.DataFrame | None:
    if cache_only:
        if not VNINDEX_CACHE.exists():
            return None
        idx = pd.read_parquet(VNINDEX_CACHE)
        idx['Date'] = pd.to_datetime(idx['Date'])
        return idx
    return fetch_vnindex(lookback_days=DEFAULT_LOOKBACK)


def normalize_entry(tk: str, entry: float, close: float) -> float:
    # Gia mua nhap theo dong (18500) trong khi gia du lieu theo nghin dong (18.5):
    # ty le ~1000 la dau hieu khong the nham voi bien dong gia that.
    if close > 0 and entry / close > 100:
        q = vnd_to_quote(entry)
        log.warning(f"  {tk}: gia_mua {entry:,.0f} co ve theo dong — doi thanh {q:g} nghin dong")
        return q
    return entry


def print_section(title: str, rows: list) -> None:
    print(f"\n=== {title} ({len(rows)} ma) ===")
    if not rows:
        print("  (khong co)")
        return
    hdr = f"  {'Ma':<5}{'San':<6}{'Gia':>9}{'MA7':>9}{'MA25':>9}{'Gap':>7}{'P90':>7}" \
          f"{'KL/TB20':>9}{'GTGD ty':>9}  Ghi chu"
    print(hdr)
    for r in rows:
        m = r.metrics
        notes = []
        if r.signal_age is not None:
            notes.append('hom nay' if r.signal_age == 0 else f"{r.signal_age} phien truoc")
        if r.position:
            p = r.position
            notes.append(f"mua {p['gia_mua']:g} ({p['lai_lo_pct']:+.1f}%), cat lo {p['gia_cat_lo']:g}"
                         + (" — DA CHAM" if p['cham_cat_lo'] else ""))
        if m.get('cat_lo_goi_y'):
            notes.append(f"cat lo goi y {m['cat_lo_goi_y']:g}")
        if m.get('tradable_warning'):
            notes.append(m['tradable_warning'])
        if m.get('suspicious_data'):
            notes.append("NGHI GIA CHUA DIEU CHINH")
        fmt = lambda v, nd=2: '—' if v is None else f"{v:.{nd}f}"
        print(f"  {r.ticker:<5}{r.exchange[:5]:<6}{r.close:>9.2f}{fmt(m['ma7']):>9}"
              f"{fmt(m['ma25']):>9}{fmt(m['gap']):>7}{fmt(m['gap_p90']):>7}"
              f"{fmt(m['vol_ratio']):>9}{fmt(m['avg_value20_ty'], 1):>9}  {'; '.join(notes)}")


def main() -> int:
    ap = argparse.ArgumentParser(description='Loc co phieu theo tin hieu MA7 x MA25')
    ap.add_argument('--exchanges', default='HOSE,HNX,UPCOM')
    ap.add_argument('--tickers', default=None, help='Danh sach ma, cach nhau dau phay')
    ap.add_argument('--limit', type=int, default=None, help='So ma toi da (theo thanh khoan)')
    ap.add_argument('--lookback', type=int, default=DEFAULT_LOOKBACK)
    ap.add_argument('--cache-only', action='store_true', help='Chi doc cache, khong goi mang')
    ap.add_argument('--holdings', type=Path, default=None, help='CSV danh muc: ma,gia_mua')
    ap.add_argument('--min-avg-value', type=float, default=BC.MIN_AVG_VALUE_20D,
                    help='Nguong GTGD TB20 (dong), mac dinh 10 ty')
    ap.add_argument('--ignore-market', action='store_true',
                    help='Van hien tin hieu mua khi VN-Index duoi MA50 (van danh dau)')
    ap.add_argument('--show-blocked', action='store_true',
                    help='In ca tin hieu mua bi bo loc chan')
    ap.add_argument('--out-dir', type=Path,
                    default=Path(__file__).resolve().parent / 'data' / 'results')
    args = ap.parse_args()

    holdings = load_holdings(args.holdings) if args.holdings else {}
    tickers = [t.strip().upper() for t in args.tickers.split(',')] if args.tickers else None
    if tickers and holdings:
        tickers = sorted(set(tickers) | set(holdings))

    # ---- Du lieu gia
    if args.cache_only:
        df_all = load_cache_only(tickers)
    else:
        if tickers:
            universe = get_ticker_universe(tuple(args.exchanges.split(',')))
            universe = universe[universe['ticker'].isin(tickers)].reset_index(drop=True)
            missing = set(tickers) - set(universe['ticker'])
            if missing:
                log.warning(f"Khong thay trong danh sach san: {sorted(missing)}")
        else:
            universe = get_ticker_universe(tuple(args.exchanges.split(',')), limit=args.limit)
            if holdings:
                extra = set(holdings) - set(universe['ticker'])
                if extra:
                    full = get_ticker_universe(tuple(args.exchanges.split(',')))
                    universe = pd.concat([universe, full[full['ticker'].isin(extra)]],
                                         ignore_index=True)
        log.info(f"Lay du lieu {len(universe)} ma (lookback {args.lookback} ngay)...")
        df_all = fetch_universe(universe, lookback_days=args.lookback)

    if df_all is None or df_all.empty:
        log.error("Khong co du lieu gia — dung lai.")
        return 1

    # ---- Bo loc thi truong
    regime = compute_regime(load_vnindex(args.cache_only))
    market_ok = regime.get('above_ma50') if regime.get('available') else None
    if args.ignore_market:
        market_ok = True
    if regime.get('available'):
        log.info(f"VN-Index {regime['close']} | MA50 {regime['ma50']} -> "
                 f"{'TREN' if regime['above_ma50'] else 'DUOI'} MA50")
    else:
        log.warning("Khong co VN-Index — tin hieu MUA se bi chan (khong ro boi canh)")

    cfg = {'min_avg_value': args.min_avg_value}

    # ---- Danh gia
    results, skipped = [], 0
    for tk, g in df_all.groupby('Ticker', sort=False):
        g = g.sort_values('Date').reset_index(drop=True)
        entry = holdings.get(tk)
        if entry:
            entry = normalize_entry(tk, entry, float(g['Close'].iloc[-1]))
        res = ma7_25.evaluate(g, tk, config=cfg, market_ok=market_ok, entry_price=entry)
        if res is None:
            skipped += 1
            if tk in holdings:
                log.warning(f"  {tk} (dang giu): khong danh gia duoc — du lieu stale hoac thieu lich su")
            continue
        if res.signal is not None:
            results.append(res)

    session = df_all['Date'].max().date()
    print(f"\nTIN HIEU MA7 x MA25 — phien {session} | "
          f"{df_all['Ticker'].nunique()} ma, bo qua {skipped} (stale/thieu lich su)")
    if market_ok is False:
        print("!! VN-Index DUOI MA50: moi tin hieu MUA dang bi chan.")

    buckets = {k: [] for k, _ in SECTION_ORDER}
    blocked_buys = []
    for r in results:
        if r.signal in ma7_25.BUY_SIGNALS and r.blocked_by:
            blocked_buys.append(r)
            continue
        buckets[r.signal].append(r)

    for key, title in SECTION_ORDER:
        if key == 'GIU' and not holdings:
            continue
        rows = sorted(buckets[key], key=lambda r: -(r.metrics.get('avg_value20_ty') or 0))
        print_section(title, rows)

    if blocked_buys:
        reasons = pd.Series([b for r in blocked_buys for b in r.blocked_by]).value_counts()
        print(f"\n({len(blocked_buys)} tin hieu MUA bi bo loc chan: "
              + ', '.join(f"{k} {v}" for k, v in reasons.items()) + ")")
        if args.show_blocked:
            print_section('MUA BI CHAN', blocked_buys)

    # ---- Ghi CSV (ca tin hieu bi chan, de soi lai)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"ma7_25_{session}.csv"
    if results:
        pd.DataFrame([r.to_dict() for r in results]).to_csv(out, index=False, encoding='utf-8-sig')
        print(f"\nDa ghi {len(results)} dong -> {out}")
    print("\nLuu y: day la bo loc ky thuat, chua backtest. Nguong 0,5 / P90 / -7% "
          "la diem khoi dau, khong phai khuyen nghi dau tu.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
