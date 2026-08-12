#!/usr/bin/env python3
"""
BACKFILL LỊCH SỬ OHLCV — điều kiện tiên quyết để hiệu chỉnh trọng số
================================================================================
Vì sao cần:
  Cache hiện tại chỉ giữ ~400 phiên (`run_daily.py --lookback 400`) ≈ 1,6 năm.
  Với chân trời 20 phiên, một năm chỉ cho ~12 kỳ ĐỘC LẬP ⇒ 1,6 năm ≈ 19 kỳ.
  Muốn kết luận có ý nghĩa về 10 tiêu chí cần tối thiểu 5-7 năm.

  Chạy `run_weight_calibration.py` trên cache 400 phiên sẽ cho ra những con số
  trông rất thuyết phục nhưng hoàn toàn là nhiễu.

SURVIVORSHIP BIAS — điểm quan trọng nhất của script này:
  Nếu chỉ backfill các mã ĐANG niêm yết hôm nay, bạn đã loại bỏ toàn bộ mã bị
  huỷ niêm yết, đình chỉ, hoặc rơi khỏi rổ thanh khoản — tức là loại đúng những
  mã có kết cục xấu nhất. Mọi thống kê sau đó sẽ đẹp lên một cách giả tạo, và
  backtest sẽ hứa hẹn lợi nhuận không tồn tại.

  Script hỗ trợ nạp danh sách mã lịch sử qua `--extra-tickers` (file txt, mỗi
  dòng một mã) để bổ sung các mã đã rời sàn. Hãy dùng nó.

Usage:
    # Backfill 6 năm cho 400 mã thanh khoản nhất
    python backend/backfill_history.py --years 6 --limit 400

    # Bổ sung mã đã huỷ niêm yết
    python backend/backfill_history.py --years 6 --extra-tickers delisted.txt

    # Chạy tiếp sau khi bị ngắt (script tự bỏ qua mã đã đủ dữ liệu)
    python backend/backfill_history.py --years 6 --resume
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.data_fetcher import (
    CACHE_DIR, setup_api_key, fetch_ohlcv, fetch_vnindex, get_ticker_universe,
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('backfill')

VNINDEX_CACHE = Path(__file__).resolve().parent / 'data' / 'vnindex_cache.parquet'

# vnstock giới hạn khoảng thời gian mỗi request; chia nhỏ theo năm cho an toàn
CHUNK_DAYS = 365


def _cache_file(ticker: str) -> Path:
    return CACHE_DIR / f'{ticker}_adj.parquet'


def _existing_span(ticker: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None, int]:
    f = _cache_file(ticker)
    if not f.exists():
        return None, None, 0
    try:
        df = pd.read_parquet(f)
        d = pd.to_datetime(df['Date'])
        return d.min(), d.max(), len(df)
    except Exception:
        return None, None, 0


def backfill_ticker(ticker: str, start: datetime, end: datetime,
                    delay: float = 2.0, resume: bool = True) -> tuple[str, int]:
    """
    Kéo lịch sử một mã theo từng đoạn 1 năm rồi gộp vào cache.

    Trả về (trạng thái, số phiên). Trạng thái:
      'skip'   — đã đủ dữ liệu
      'ok'     — kéo thành công
      'partial'— kéo được nhưng ngắn hơn yêu cầu (mã mới lên sàn / đã rời sàn)
      'fail'   — không lấy được gì
    """
    first, last, n_existing = _existing_span(ticker)

    if resume and first is not None and first <= pd.Timestamp(start) + pd.Timedelta(days=10):
        return 'skip', n_existing

    frames = []
    if first is not None:
        try:
            frames.append(pd.read_parquet(_cache_file(ticker)))
        except Exception:
            pass

    # Chỉ kéo phần CÒN THIẾU ở phía trước, tránh tải lại dữ liệu đã có
    fetch_until = min(first, pd.Timestamp(end)) if first is not None else pd.Timestamp(end)

    cursor = pd.Timestamp(start)
    while cursor < fetch_until:
        chunk_end = min(cursor + pd.Timedelta(days=CHUNK_DAYS), fetch_until)
        try:
            part = fetch_ohlcv(ticker, str(cursor.date()), str(chunk_end.date()))
            if part is not None and not part.empty:
                frames.append(part)
        except Exception as e:
            log.debug(f"  {ticker} [{cursor.date()}..{chunk_end.date()}]: {e}")
        cursor = chunk_end + pd.Timedelta(days=1)
        time.sleep(delay)

    if not frames:
        return 'fail', 0

    df = (pd.concat(frames, ignore_index=True)
          .drop_duplicates('Date')
          .sort_values('Date')
          .reset_index(drop=True))
    df['Date'] = pd.to_datetime(df['Date'])

    try:
        df.to_parquet(_cache_file(ticker), index=False)
    except Exception as e:
        log.warning(f"  {ticker}: ghi cache thất bại: {e}")
        return 'fail', 0

    expected = (end - start).days * 250 / 365 * 0.7      # ~70% số phiên lý thuyết
    return ('ok' if len(df) >= expected else 'partial'), len(df)


def load_extra_tickers(path: str | None) -> list[str]:
    """Đọc danh sách mã bổ sung (thường là mã đã huỷ niêm yết)."""
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        log.warning(f"  Không tìm thấy {p} — bỏ qua danh sách bổ sung")
        return []
    tickers = [ln.strip().upper() for ln in p.read_text(encoding='utf-8').splitlines()
               if ln.strip() and not ln.startswith('#')]
    log.info(f"  Nạp thêm {len(tickers)} mã từ {p}")
    return tickers


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=float, default=6.0,
                   help='Số năm lịch sử cần có (khuyến nghị >= 5)')
    p.add_argument('--limit', type=int, default=400,
                   help='Số mã thanh khoản nhất cần backfill')
    p.add_argument('--exchanges', type=str, default='HOSE,HNX,UPCOM')
    p.add_argument('--extra-tickers', type=str, default=None,
                   help='File txt chứa mã bổ sung (mã đã huỷ niêm yết) — QUAN TRỌNG '
                        'để tránh survivorship bias')
    p.add_argument('--delay', type=float, default=2.0,
                   help='Giây nghỉ giữa các request (tôn trọng rate limit vnstock)')
    p.add_argument('--resume', action='store_true', default=True,
                   help='Bỏ qua mã đã đủ lịch sử (mặc định bật)')
    p.add_argument('--no-resume', dest='resume', action='store_false')
    p.add_argument('--tickers', type=str, default=None,
                   help='Chỉ backfill danh sách này (phân tách bằng dấu phẩy)')
    args = p.parse_args()

    setup_api_key()
    end = datetime.now()
    start = end - timedelta(days=int(args.years * 365))
    log.info(f"Backfill {args.years} năm: {start.date()} → {end.date()}")

    # ── VN-Index trước tiên: không có nó thì không tính được alpha/RS ──────
    log.info("Kéo VN-Index...")
    idx = fetch_vnindex(lookback_days=int(args.years * 365) + 30)
    if idx is not None and not idx.empty:
        VNINDEX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        idx.to_parquet(VNINDEX_CACHE, index=False)
        log.info(f"  ✓ VN-Index: {len(idx)} phiên → {VNINDEX_CACHE}")
    else:
        log.error("  ✗ Không lấy được VN-Index — alpha và RS sẽ không tính được")

    # ── Danh sách mã ──────────────────────────────────────────────────────
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
    else:
        exchanges = tuple(args.exchanges.split(','))
        universe = get_ticker_universe(exchanges, limit=args.limit)
        tickers = universe['ticker'].tolist()

    extra = load_extra_tickers(args.extra_tickers)
    if not extra and not args.tickers:
        log.warning(
            "⚠️  Không có danh sách mã huỷ niêm yết (--extra-tickers). Kết quả "
            "hiệu chỉnh trọng số sẽ dính SURVIVORSHIP BIAS: chỉ học từ những mã "
            "sống sót tới hôm nay, tức đã loại sẵn các kết cục xấu nhất."
        )
    tickers = list(dict.fromkeys(tickers + extra))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Bắt đầu backfill {len(tickers)} mã "
             f"(ước tính {len(tickers) * args.years * args.delay / 60:.0f} phút)")

    stats = {'ok': 0, 'partial': 0, 'skip': 0, 'fail': 0}
    partial_list, fail_list = [], []

    for i, ticker in enumerate(tickers, 1):
        try:
            status, n = backfill_ticker(ticker, start, end, args.delay, args.resume)
        except KeyboardInterrupt:
            log.warning("Bị ngắt — chạy lại với --resume để tiếp tục")
            break
        except Exception as e:
            status, n = 'fail', 0
            log.debug(f"  {ticker}: {type(e).__name__}: {e}")

        stats[status] += 1
        if status == 'partial':
            partial_list.append(f'{ticker}({n})')
        elif status == 'fail':
            fail_list.append(ticker)

        if i % 20 == 0 or i == len(tickers):
            log.info(f"  {i}/{len(tickers)} — ok={stats['ok']} partial={stats['partial']} "
                     f"skip={stats['skip']} fail={stats['fail']}")

    log.info("=" * 70)
    log.info(f"Hoàn tất: {stats}")
    if partial_list:
        log.info(f"  Lịch sử ngắn ({len(partial_list)} mã — mã mới lên sàn hoặc đã rời sàn): "
                 f"{', '.join(partial_list[:20])}")
    if fail_list:
        log.info(f"  Thất bại ({len(fail_list)}): {', '.join(fail_list[:20])}")

    log.info("")
    log.info("Bước tiếp theo:")
    log.info("  python backend/run_weight_calibration.py --horizons 5,10,20,40")


if __name__ == '__main__':
    main()
