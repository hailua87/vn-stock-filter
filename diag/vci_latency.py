"""Chẩn đoán tạm (không merge): đo độ trễ/lỗi gọi giá ngày VCI theo 3 cách kết nối.
Kết quả in thành annotation ::notice để đọc qua API."""
import sys, time, statistics, json
from datetime import date, timedelta, datetime
import requests
sys.path.insert(0, 'backend')
from scanner.top_liquid import get_top_liquid_tickers

URL = 'https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart'
MINE = {'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Referer': 'https://trading.vietcap.com.vn/', 'Origin': 'https://trading.vietcap.com.vn/'}
FULL = dict(MINE, **{'Connection': 'keep-alive', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'DNT': '1',
                     'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-site',
                     'Accept-Language': 'en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7'})
sess = requests.Session()
end = datetime.now() + timedelta(days=1)
tickers = [t for t, _ in get_top_liquid_tickers()][:int(sys.argv[1]) if len(sys.argv) > 1 else 120]
res = {'A_session': [], 'B_fresh': [], 'C_fresh_fullhdr': []}
errs = []
t0 = time.time()
for i, tk in enumerate(tickers):
    mode = list(res)[i % 3]
    payload = {'timeFrame': 'ONE_DAY', 'symbols': [tk], 'to': int(end.timestamp()), 'countBack': 300}
    s = time.time()
    try:
        if mode == 'A_session':
            r = sess.post(URL, headers=MINE, json=payload, timeout=30)
        elif mode == 'B_fresh':
            r = requests.post(URL, headers=MINE, json=payload, timeout=30)
        else:
            r = requests.post(URL, headers=FULL, data=json.dumps(payload), timeout=30)
        ok = r.status_code == 200 and bool(r.json()) and bool(r.json()[0].get('t'))
        tag = r.status_code
    except Exception as e:
        ok, tag = False, type(e).__name__
    dt = time.time() - s
    res[mode].append((dt, ok))
    if not ok:
        errs.append(f'{i}:{tk}:{mode}:{tag}:{dt:.1f}s@{time.time()-t0:.0f}s')
    time.sleep(max(0, 2 - dt))
for m, v in res.items():
    lat = [d for d, _ in v]
    print(f"::notice title={m}::n={len(v)} fail={sum(not o for _, o in v)} "
          f"median={statistics.median(lat):.2f}s p90={sorted(lat)[int(len(lat)*.9)]:.2f}s max={max(lat):.2f}s")
print(f"::notice title=errors::{len(errs)} | " + ' ; '.join(errs[:25]))
s = time.time()
try:
    r = sess.post(URL, headers=MINE, json={'timeFrame': 'ONE_DAY', 'symbols': ['VNINDEX'], 'to': int(end.timestamp()), 'countBack': 300}, timeout=30)
    print(f"::notice title=VNINDEX::status={r.status_code} n={len(r.json()[0].get('t', [])) if r.status_code == 200 else '-'} {time.time()-s:.2f}s")
except Exception as e:
    print(f"::notice title=VNINDEX::{type(e).__name__} {time.time()-s:.2f}s")
