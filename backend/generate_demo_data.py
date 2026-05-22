"""
Generate sample data for the web dashboard demo.
Creates fake but realistic-looking pre-breakout signals across HOSE/HNX/UPCOM
for the last 14 trading days, so the date picker has data to show.
"""
import json
import random
from datetime import datetime, timedelta, date
from pathlib import Path

random.seed(2026)

TICKERS = [
    ('FPT', 'HOSE', 138.5), ('VCB', 'HOSE', 92.3), ('VHM', 'HOSE', 48.7),
    ('HPG', 'HOSE', 28.4), ('MWG', 'HOSE', 62.1), ('VIC', 'HOSE', 41.9),
    ('TCB', 'HOSE', 27.8), ('VPB', 'HOSE', 21.5), ('MBB', 'HOSE', 26.7),
    ('DGC', 'HOSE', 118.2), ('PNJ', 'HOSE', 102.0), ('GAS', 'HOSE', 76.4),
    ('MSN', 'HOSE', 81.6), ('STB', 'HOSE', 32.1), ('SSI', 'HOSE', 35.2),
    ('VND', 'HOSE', 22.9), ('VCI', 'HOSE', 47.3), ('HCM', 'HOSE', 28.6),
    ('REE', 'HOSE', 71.4), ('GMD', 'HOSE', 84.2), ('PHR', 'HOSE', 56.7),
    ('DPM', 'HOSE', 36.5), ('DCM', 'HOSE', 39.8), ('HSG', 'HOSE', 21.3),
    ('NKG', 'HOSE', 24.1), ('VRE', 'HOSE', 18.7), ('GVR', 'HOSE', 36.2),
    ('SHS', 'HNX', 18.9), ('CEO', 'HNX', 24.3), ('IDC', 'HNX', 64.8),
    ('PVS', 'HNX', 41.2), ('TNG', 'HNX', 27.5), ('MBS', 'HNX', 30.4),
    ('VCS', 'HNX', 76.3), ('PVI', 'HNX', 51.8),
    ('ACV', 'UPCOM', 119.4), ('VEA', 'UPCOM', 42.8), ('VTP', 'UPCOM', 88.6),
    ('BSR', 'UPCOM', 22.3), ('QNS', 'UPCOM', 51.2), ('MCH', 'UPCOM', 165.0),
]

UPCOMING_EVENTS = {
    'FPT': {'type': 'cash_dividend', 'ex_date_offset': 12, 'ratio': 2000},
    'HPG': {'type': 'stock_dividend', 'ex_date_offset': 8, 'ratio': 0.05},
    'VCB': {'type': 'cash_dividend', 'ex_date_offset': 25, 'ratio': 2500},
    'DGC': {'type': 'stock_dividend', 'ex_date_offset': 4, 'ratio': 0.15},
    'STB': {'type': 'cash_dividend', 'ex_date_offset': 18, 'ratio': 1500},
}


def make_signal(ticker, exchange, base_price, target_score, scan_date):
    criteria_keys = [
        'c1_atr_squeeze', 'c2_bb_squeeze', 'c3_near_high20',
        'c4_stealth_accum', 'c5_vol_surge', 'c6_upper_close',
        'c7_ma_align', 'c8_rsi_zone', 'c9_pocket_pivot', 'c10_no_gap_down',
    ]
    must_pass = {'c10_no_gap_down'}
    weights = {
        'c1_atr_squeeze': 0.6, 'c2_bb_squeeze': 0.55, 'c3_near_high20': 0.7,
        'c4_stealth_accum': 0.4, 'c5_vol_surge': 0.55, 'c6_upper_close': 0.65,
        'c7_ma_align': 0.8, 'c8_rsi_zone': 0.7, 'c9_pocket_pivot': 0.35,
        'c10_no_gap_down': 0.95,
    }
    scores = {}
    for k in criteria_keys:
        scores[k] = 1 if (k in must_pass or random.random() < weights[k]) else 0

    current = sum(scores.values())
    while current < target_score:
        zeros = [k for k, v in scores.items() if v == 0]
        if not zeros: break
        scores[random.choice(zeros)] = 1
        current = sum(scores.values())
    while current > target_score:
        ones = [k for k, v in scores.items() if v == 1 and k not in must_pass]
        if not ones: break
        scores[random.choice(ones)] = 0
        current = sum(scores.values())

    total = sum(scores.values())
    rating = 'A+' if total >= 8 else 'A' if total >= 6 else 'B' if total >= 4 else 'C'

    upcoming_event = None
    if ticker in UPCOMING_EVENTS:
        ev = UPCOMING_EVENTS[ticker]
        ex_date = scan_date + timedelta(days=ev['ex_date_offset'])
        upcoming_event = {
            'type': ev['type'],
            'ex_date': ex_date.isoformat(),
            'ratio': ev['ratio'],
        }

    return {
        'ticker': ticker, 'exchange': exchange,
        'date': scan_date.isoformat(),
        'close': round(base_price, 2),
        'volume': random.randint(800_000, 8_000_000),
        'total_score': total, 'rating': rating,
        **scores,
        'm_change_5d_pct': round(random.uniform(0.5, 4.5), 2),
        'm_vol_ratio': round(random.uniform(1.0, 2.2), 2),
        'm_rsi14': round(random.uniform(52, 64), 1),
        'm_atr_pct': round(random.uniform(1.4, 2.8), 2),
        'm_dist_to_high20_pct': round(random.uniform(0.3, 2.9), 2),
        'm_high20': round(base_price * 1.02, 2),
        'm_ma10': round(base_price * 0.98, 2),
        'm_ma20': round(base_price * 0.96, 2),
        'm_suspicious_data': False,
        'm_upcoming_event': upcoming_event,
    }


def generate_for_date(scan_date: date, n_signals: int) -> dict:
    target_scores = []
    target_scores += [9] * (n_signals // 8)
    target_scores += [8] * (n_signals // 6)
    target_scores += [7] * (n_signals // 4)
    target_scores += [6] * (n_signals // 4)
    target_scores += [5] * (n_signals // 4)
    target_scores += [4] * max(0, n_signals - len(target_scores))
    random.shuffle(target_scores)

    chosen = random.sample(TICKERS, min(len(target_scores), len(TICKERS)))
    signals = []
    for i, (ticker, exchange, price) in enumerate(chosen[:len(target_scores)]):
        price_drift = price * random.uniform(0.97, 1.03)
        signals.append(make_signal(ticker, exchange, price_drift, target_scores[i], scan_date))

    signals.sort(key=lambda s: (-s['total_score'], s['ticker']))

    return {
        'generated_at': datetime.combine(scan_date, datetime.min.time().replace(hour=16, minute=5)).isoformat(),
        'total': len(signals),
        'metadata': {
            'min_score': 4,
            'exchanges': ['HOSE', 'HNX', 'UPCOM'],
            'total_scanned': random.randint(1520, 1580),
            'demo': True,
            'adjusted_prices': True,
            'corporate_actions_filtered': True,
        },
        'signals': signals,
    }


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def main():
    out_root = Path(__file__).resolve().parent.parent / 'web' / 'data'
    out_root.mkdir(parents=True, exist_ok=True)
    archive = out_root / 'archive'
    archive.mkdir(exist_ok=True)

    today = date(2026, 5, 15)  # Friday May 15, 2026
    days = []
    d = today
    while len(days) < 14:
        if is_business_day(d):
            days.append(d)
        d -= timedelta(days=1)

    for scan_date in days:
        n = random.randint(25, 38)
        data = generate_for_date(scan_date, n)
        path = archive / f'{scan_date.isoformat()}.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {scan_date.isoformat()}: {data['total']} signals")

    latest_path = out_root / 'latest.json'
    with open(archive / f'{days[0].isoformat()}.json') as f:
        latest_data = json.load(f)
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(latest_data, f, ensure_ascii=False, indent=2)

    index = {
        'latest': days[0].isoformat(),
        'dates': [d.isoformat() for d in days],
        'count': len(days),
    }
    with open(archive / 'index.json', 'w') as f:
        json.dump(index, f, indent=2)

    print(f"\n✓ Generated {len(days)} days of demo data")


if __name__ == '__main__':
    main()
