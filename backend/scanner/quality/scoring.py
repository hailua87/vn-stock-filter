"""
Percentile trong cung mo hinh + diem tung chieu kem do phu.

Percentile la THU HANG TRONG UNIVERSE Module B (top N thanh khoan), khong phai
toan thi truong. Diem 80 nghia la "hon 80% ma cung mo hinh trong universe",
khong phai "tot theo nghia tuyet doi".
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import config as C


def _quantile(sorted_vals: List[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def percentiles(values: Dict[str, Optional[float]], higher_better: bool) -> Dict[str, Optional[float]]:
    """{ticker: gia tri} -> {ticker: percentile 0-100}. Nhom co gia tri < MIN_PEER_GROUP
    tra toan None: percentile tren 5 ma dao dong qua manh de dung lam diem."""
    present = {t: v for t, v in values.items() if v is not None}
    out = {t: None for t in values}
    n = len(present)
    if n < C.MIN_PEER_GROUP:
        return out

    vals = dict(present)
    if n >= C.WINSOR_MIN_GROUP:
        s = sorted(vals.values())
        lo, hi = _quantile(s, C.WINSOR_P[0] / 100), _quantile(s, C.WINSOR_P[1] / 100)
        vals = {t: min(max(v, lo), hi) for t, v in vals.items()}

    # Hang trung binh cho gia tri bang nhau: winsorize tao nhieu gia tri trung
    # o hai dau, xep hang tuy y se thuong/phat ngau nhien cac ma do.
    ordered = sorted(vals.items(), key=lambda kv: kv[1])
    ranks, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        avg = (i + j) / 2
        for k in range(i, j + 1):
            ranks[ordered[k][0]] = avg
        i = j + 1

    for t, r in ranks.items():
        p = r / (n - 1) * 100
        out[t] = round(p if higher_better else 100 - p, 1)
    return out


def dimension(metric_pcts: Dict[str, Optional[float]], spec: list) -> dict:
    """Diem 1 chieu cho 1 ma. Do phu tinh theo TRONG SO, khong theo so chi tieu."""
    total = sum(w for _, w, _ in spec)
    have = [(k, w, metric_pcts.get(k)) for k, w, _ in spec if metric_pcts.get(k) is not None]
    coverage = sum(w for _, w, _ in have) / total if total else 0.0
    missing = [k for k, _, _ in spec if metric_pcts.get(k) is None]
    score = None
    if coverage >= C.COVERAGE_MIN and have:
        score = round(sum(w * p for _, w, p in have) / sum(w for _, w, _ in have), 1)
    return {'score': score, 'coverage': round(coverage, 3), 'missing': missing}


def score_group(model: str, metrics_by_ticker: Dict[str, dict]) -> Dict[str, dict]:
    """Cham 3 chieu dinh luong (quality/growth/resilience) cho moi ma trong 1 mo hinh.
    Quan tri tinh rieng o governance.py vi khong dua tren percentile."""
    spec = C.MODELS[model]
    pct: Dict[str, Dict[str, Optional[float]]] = {t: {} for t in metrics_by_ticker}
    for dim_specs in spec.values():
        for key, _, higher in dim_specs:
            col = percentiles({t: m.get(key) for t, m in metrics_by_ticker.items()}, higher)
            for t, p in col.items():
                pct[t][key] = p

    return {
        t: {
            'percentiles': pct[t],
            **{dim: dimension(pct[t], dim_specs) for dim, dim_specs in spec.items()},
        }
        for t in metrics_by_ticker
    }
