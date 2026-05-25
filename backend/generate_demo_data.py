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

    # Mock Fibo swing: simulate that low was 90% of current, high was 110%
    swing_low = round(base_price * random.uniform(0.85, 0.92), 2)
    swing_high = round(base_price * random.uniform(1.05, 1.15), 2)
    swing_range = swing_high - swing_low
    swing = {
        'high': swing_high,
        'low': swing_low,
        'range': round(swing_range, 2),
        'direction': 'up',
        'high_date': (scan_date - timedelta(days=random.randint(5, 25))).isoformat(),
        'low_date': (scan_date - timedelta(days=random.randint(30, 55))).isoformat(),
    }

    # Compute Fibo levels
    fibo_ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    fibo_labels = {0.0: '0%', 0.236: '23.6%', 0.382: '38.2%', 0.5: '50%',
                   0.618: '61.8%', 0.786: '78.6%', 1.0: '100%'}
    all_fibo = []
    for ratio in fibo_ratios:
        price = round(swing_high - swing_range * ratio, 2)
        all_fibo.append({
            'ratio': ratio,
            'label': fibo_labels[ratio],
            'price': price,
            'is_golden': ratio == 0.618,
        })

    # Classify as support/resistance
    supports = []
    resistances = []
    for lv in all_fibo:
        enriched = {**lv, 'type': 'fibo'}
        if lv['price'] < base_price:
            enriched['distance_pct'] = round((base_price - lv['price']) / base_price * 100, 2)
            supports.append(enriched)
        elif lv['price'] > base_price:
            enriched['distance_pct'] = round((lv['price'] - base_price) / base_price * 100, 2)
            resistances.append(enriched)
    supports.sort(key=lambda x: -x['price'])
    resistances.sort(key=lambda x: x['price'])

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
        'm_supports': supports[:3],
        'm_resistances': resistances[:3],
        'm_fibo_swing': swing,
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


def make_gc_signal(ticker, exchange, base_price, scan_date):
    """Generate a Golden Cross signal (works for both long and short presets)."""
    keys = ['recent_cross', 'price_above_fast', 'ma_stacking', 'slow_rising', 'volume_confirm']
    # Must have recent_cross = 1
    scores = {'recent_cross': 1}
    for k in keys[1:]:
        scores[k] = 1 if random.random() < 0.65 else 0
    # Need at least 3/5 to pass filter
    while sum(scores.values()) < 3:
        zeros = [k for k, v in scores.items() if v == 0]
        if not zeros: break
        scores[random.choice(zeros)] = 1
    total = sum(scores.values())
    rating = 'A+' if total == 5 else 'A' if total == 4 else 'B' if total == 3 else 'C'

    # Fibo levels (simplified)
    swing_low = round(base_price * random.uniform(0.80, 0.88), 2)
    swing_high = round(base_price * random.uniform(1.05, 1.15), 2)
    swing_range = swing_high - swing_low
    fibo_levels = []
    for ratio in [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]:
        p = round(swing_high - swing_range * ratio, 2)
        fibo_levels.append({'price': p, 'label': f'{ratio*100:.1f}%' if ratio else '0%',
                            'ratio': ratio, 'is_golden': ratio == 0.618, 'type': 'fibo'})
    supports = sorted([{**lv, 'distance_pct': round((base_price - lv['price'])/base_price*100, 2)}
                       for lv in fibo_levels if lv['price'] < base_price],
                      key=lambda x: -x['price'])[:3]
    resistances = sorted([{**lv, 'distance_pct': round((lv['price']-base_price)/base_price*100, 2)}
                          for lv in fibo_levels if lv['price'] > base_price],
                         key=lambda x: x['price'])[:3]

    return {
        'ticker': ticker, 'exchange': exchange,
        'date': scan_date.isoformat(),
        'close': round(base_price, 2),
        'volume': random.randint(500_000, 5_000_000),
        'total_score': total, 'rating': rating,
        **{f'gc_{k}': v for k, v in scores.items()},
        'm_cross_days_ago': random.randint(0, 4),
        'm_fast_ma': round(base_price * 0.99, 2),
        'm_slow_ma': round(base_price * 0.93, 2),
        'm_slow_spread_pct': round(random.uniform(2, 12), 2),
        'm_change_5d_pct': round(random.uniform(0.5, 5), 2),
        'm_vol_ratio': round(random.uniform(1.0, 2.5), 2),
        'm_rsi14': round(random.uniform(55, 70), 1),
        'm_supports': supports,
        'm_resistances': resistances,
        'm_fibo_swing': {
            'high': swing_high, 'low': swing_low, 'range': swing_range,
            'direction': 'up',
            'high_date': (scan_date - timedelta(days=random.randint(5, 20))).isoformat(),
            'low_date': (scan_date - timedelta(days=random.randint(30, 60))).isoformat(),
        },
        'm_suspicious_data': False,
        'm_upcoming_event': None,
    }


def make_ich_signal(ticker, exchange, base_price, scan_date):
    """Generate an Ichimoku signal (flexible mode: score >= 3)."""
    # 5 criteria now (recent_tk_cross added as the 5th)
    keys = ['tk_bullish', 'recent_tk_cross', 'price_above_cloud', 'cloud_bullish', 'chikou_free']
    # If tk_bullish is on, recent_tk_cross has higher chance of being on too
    scores = {}
    scores['tk_bullish'] = 1 if random.random() < 0.80 else 0
    # recent_tk_cross only valid if tk_bullish=1; lower prob to make it special
    scores['recent_tk_cross'] = 1 if (scores['tk_bullish'] and random.random() < 0.35) else 0
    scores['price_above_cloud'] = 1 if random.random() < 0.7 else 0
    scores['cloud_bullish'] = 1 if random.random() < 0.7 else 0
    scores['chikou_free'] = 1 if random.random() < 0.7 else 0

    # Filter: flexible mode requires at least 3 to be in results
    while sum(scores.values()) < 3:
        zeros = [k for k, v in scores.items() if v == 0 and k != 'recent_tk_cross']
        if not zeros: break
        scores[random.choice(zeros)] = 1
    total = sum(scores.values())
    rating = 'A+' if total >= 4 else 'A' if total == 3 else 'C'

    # If recent_tk_cross is on, days_ago is 0-5; otherwise older or None
    if scores['recent_tk_cross']:
        tk_cross_days_ago = random.randint(0, 5)
    else:
        tk_cross_days_ago = random.randint(8, 30) if random.random() < 0.5 else None

    # Turnaround STRICT: TK ≤2 ngày + giá gần cloud_top + vol ≥1.5× + change ≥2.5%
    # ~25% of recent_tk_cross signals (chặt hơn → ít signals hơn)
    is_turnaround = (
        scores['recent_tk_cross'] == 1
        and tk_cross_days_ago is not None
        and tk_cross_days_ago <= 2
        and random.random() < 0.40
    )
    turnaround_reasons = []
    if is_turnaround:
        change_3d = random.uniform(2.5, 5.0)
        vol_r = random.uniform(1.5, 2.8)
        turnaround_reasons = [
            f'TK cross {tk_cross_days_ago} phiên trước',
            'Giá chuẩn bị break cloud',
            f'Nến tăng {change_3d:.1f}% trong 3 phiên',
            f'Volume {vol_r:.1f}× MA20',
        ]

    cloud_top = round(base_price * random.uniform(0.92, 0.99), 2)
    cloud_bottom = round(cloud_top * random.uniform(0.95, 0.99), 2)

    swing_low = round(base_price * random.uniform(0.80, 0.88), 2)
    swing_high = round(base_price * random.uniform(1.05, 1.15), 2)
    swing_range = swing_high - swing_low
    fibo_levels = []
    for ratio in [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]:
        p = round(swing_high - swing_range * ratio, 2)
        fibo_levels.append({'price': p, 'label': f'{ratio*100:.1f}%' if ratio else '0%',
                            'ratio': ratio, 'is_golden': ratio == 0.618, 'type': 'fibo'})
    supports = sorted([{**lv, 'distance_pct': round((base_price - lv['price'])/base_price*100, 2)}
                       for lv in fibo_levels if lv['price'] < base_price],
                      key=lambda x: -x['price'])[:3]
    resistances = sorted([{**lv, 'distance_pct': round((lv['price']-base_price)/base_price*100, 2)}
                          for lv in fibo_levels if lv['price'] > base_price],
                         key=lambda x: x['price'])[:3]

    return {
        'ticker': ticker, 'exchange': exchange,
        'date': scan_date.isoformat(),
        'close': round(base_price, 2),
        'volume': random.randint(500_000, 5_000_000),
        'total_score': total, 'rating': rating,
        **{f'ich_{k}': v for k, v in scores.items()},
        'm_tenkan': round(base_price * 0.99, 2),
        'm_kijun': round(base_price * 0.97, 2),
        'm_senkou_a': cloud_top,
        'm_senkou_b': cloud_bottom,
        'm_cloud_top': cloud_top,
        'm_cloud_bottom': cloud_bottom,
        'm_cloud_distance_pct': round((base_price - cloud_top) / cloud_top * 100, 2),
        'm_tk_cross_days_ago': tk_cross_days_ago,
        'm_is_turnaround': is_turnaround,
        'm_turnaround_reasons': turnaround_reasons,
        'm_change_5d_pct': round(random.uniform(0.5, 5), 2),
        'm_vol_ratio': round(random.uniform(1.0, 2.5), 2),
        'm_rsi14': round(random.uniform(50, 70), 1),
        'm_supports': supports,
        'm_resistances': resistances,
        'm_fibo_swing': {
            'high': swing_high, 'low': swing_low, 'range': swing_range,
            'direction': 'up',
            'high_date': (scan_date - timedelta(days=random.randint(5, 20))).isoformat(),
            'low_date': (scan_date - timedelta(days=random.randint(30, 60))).isoformat(),
        },
        'm_suspicious_data': False,
        'm_upcoming_event': None,
    }


def generate_strategy_for_date(scan_date, n_signals, signal_maker, strategy_label):
    """Generic generator for any strategy."""
    sample_tickers = [
        ('VCB','HOSE'), ('FPT','HOSE'), ('HPG','HOSE'), ('MWG','HOSE'), ('VHM','HOSE'),
        ('VIC','HOSE'), ('VPB','HOSE'), ('TCB','HOSE'), ('CTG','HOSE'), ('MBB','HOSE'),
        ('NKG','HOSE'), ('PHR','HOSE'), ('SSI','HOSE'), ('SAB','HOSE'), ('VND','HOSE'),
        ('VRE','HOSE'), ('REE','HOSE'), ('PNJ','HOSE'), ('DGC','HOSE'), ('GMD','HOSE'),
        ('SHS','HNX'), ('CEO','HNX'), ('IDC','HNX'), ('PVS','HNX'), ('MBS','HNX'),
        ('TNG','HNX'), ('PVI','HNX'), ('VC3','HNX'), ('LAS','HNX'),
        ('ACV','UPCOM'), ('BSR','UPCOM'), ('VEA','UPCOM'), ('QNS','UPCOM'), ('VTP','UPCOM'),
        ('OIL','UPCOM'), ('MCH','UPCOM'), ('VGI','UPCOM'),
    ]
    random.seed(hash(f"{strategy_label}-{scan_date}"))
    chosen = random.sample(sample_tickers, min(n_signals, len(sample_tickers)))
    signals = []
    for ticker, exchange in chosen:
        price = random.uniform(20, 130)
        signals.append(signal_maker(ticker, exchange, price, scan_date))
    signals.sort(key=lambda s: -s['total_score'])

    return {
        'generated_at': datetime.combine(scan_date, datetime.min.time()).replace(hour=16, minute=5).isoformat(),
        'strategy': strategy_label,
        'total': len(signals),
        'metadata': {
            'min_score': 2,
            'exchanges': ['HOSE', 'HNX', 'UPCOM'],
            'total_scanned': 1533,
            'demo': True,
        },
        'signals': signals,
    }


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

    print(f"\n✓ Generated {len(days)} days of pre-breakout demo data")

    # Generate Golden Cross demo (both LONG and SHORT presets)
    # and Ichimoku demo
    strategy_configs = [
        ('golden_cross_long', make_gc_signal, (8, 18)),
        ('golden_cross_short', make_gc_signal, (12, 25)),  # short is more common
        ('ichimoku', make_ich_signal, (15, 30)),
    ]

    for strategy_label, signal_maker, (lo, hi) in strategy_configs:
        strat_dir = out_root / strategy_label
        strat_dir.mkdir(exist_ok=True)
        strat_archive = strat_dir / 'archive'
        strat_archive.mkdir(exist_ok=True)

        for scan_date in days:
            n = random.randint(lo, hi)
            data = generate_strategy_for_date(scan_date, n, signal_maker, strategy_label)
            with open(strat_archive / f'{scan_date.isoformat()}.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        # latest.json = first day
        with open(strat_archive / f'{days[0].isoformat()}.json') as f:
            latest_data = json.load(f)
        with open(strat_dir / 'latest.json', 'w', encoding='utf-8') as f:
            json.dump(latest_data, f, ensure_ascii=False, indent=2)

        # index.json
        with open(strat_archive / 'index.json', 'w') as f:
            json.dump({
                'latest': days[0].isoformat(),
                'dates': [d.isoformat() for d in days],
                'count': len(days),
            }, f, indent=2)

        print(f"✓ Generated {len(days)} days of {strategy_label} demo data")


if __name__ == '__main__':
    main()
