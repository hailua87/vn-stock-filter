"""
FastAPI server exposing scanner results as REST endpoints.
Run:
    uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

DATA_DIR = Path(__file__).resolve().parent / 'data' / 'results'

app = FastAPI(
    title="VN Breakout Scanner API",
    description="REST API for pre-breakout signals on HOSE/HNX/UPCOM",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_latest() -> dict:
    """Load the most recent signals JSON."""
    if not DATA_DIR.exists():
        return {'generated_at': None, 'signals': [], 'total': 0}
    files = sorted(DATA_DIR.glob('signals_*.json'))
    if not files:
        return {'generated_at': None, 'signals': [], 'total': 0}
    with open(files[-1], 'r', encoding='utf-8') as f:
        return json.load(f)


@app.get("/")
def root():
    return {
        "name": "VN Breakout Scanner",
        "version": "0.1.0",
        "endpoints": {
            "/api/signals/latest": "Get latest signals",
            "/api/signals/{date}": "Signals for specific date (YYYY-MM-DD)",
            "/api/signals/ticker/{ticker}": "Historical signals for a ticker",
            "/api/health": "Health check",
            "/api/excel/latest": "Download latest Excel file",
        }
    }


@app.get("/api/health")
def health():
    data = _load_latest()
    return {
        "status": "ok",
        "last_scan": data.get('generated_at'),
        "signal_count": data.get('total', 0),
    }


@app.get("/api/signals/latest")
def latest_signals(
    min_score: int = Query(0, ge=0, le=10),
    rating: Optional[str] = Query(None, regex="^(A\\+|A|B|C)$"),
    exchange: Optional[str] = Query(None, regex="^(HOSE|HNX|UPCOM)$"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get the latest scan results with optional filters."""
    data = _load_latest()
    signals = data.get('signals', [])

    if min_score > 0:
        signals = [s for s in signals if s.get('total_score', 0) >= min_score]
    if rating:
        signals = [s for s in signals if s.get('rating') == rating]
    if exchange:
        signals = [s for s in signals if s.get('exchange') == exchange]

    signals = signals[:limit]
    return {
        'generated_at': data.get('generated_at'),
        'total': len(signals),
        'filters': {'min_score': min_score, 'rating': rating, 'exchange': exchange},
        'signals': signals,
    }


@app.get("/api/signals/{date}")
def signals_by_date(date: str):
    """Get signals for a specific date (YYYY-MM-DD)."""
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        raise HTTPException(400, "Date must be YYYY-MM-DD")
    f = DATA_DIR / f'signals_{date}.json'
    if not f.exists():
        raise HTTPException(404, f"No data for {date}")
    with open(f, 'r', encoding='utf-8') as fp:
        return json.load(fp)


@app.get("/api/signals/ticker/{ticker}")
def ticker_history(ticker: str, days: int = Query(30, ge=1, le=365)):
    """Get historical scan results for a ticker."""
    ticker = ticker.upper()
    history = []
    if not DATA_DIR.exists():
        return {'ticker': ticker, 'history': []}
    files = sorted(DATA_DIR.glob('signals_*.json'))[-days:]
    for f in files:
        with open(f, 'r', encoding='utf-8') as fp:
            d = json.load(fp)
        for s in d.get('signals', []):
            if s.get('ticker') == ticker:
                history.append(s)
                break
    return {'ticker': ticker, 'history': history}


@app.get("/api/excel/latest")
def latest_excel():
    """Download the most recent Excel report."""
    files = sorted(DATA_DIR.glob('signals_*.xlsx'))
    if not files:
        raise HTTPException(404, "No Excel files available")
    return FileResponse(
        files[-1],
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=files[-1].name,
    )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
