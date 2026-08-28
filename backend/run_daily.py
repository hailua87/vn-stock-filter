#!/usr/bin/env python3
"""
Daily multi-strategy scan runner.

Runs 3 different scanning strategies and writes JSON for each:
  - Pre-Breakout      → web/data/latest.json + archive/
  - Golden Cross      → web/data/golden_cross/latest.json + archive/
  - Ichimoku          → web/data/ichimoku/latest.json + archive/
"""
import argparse
import json
import os
import logging
import sys
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import BreakoutScanner
from scanner.exporter import to_excel, to_json, to_html, write_json
from scanner.data_fetcher import (
    CHECKPOINT_PATH, get_ticker_universe, fetch_universe, fetch_vnindex,
)
from scanner.corporate_actions import apply_event_filter
from scanner.market_regime import (
    compute_regime, compute_breadth, compute_relative_strength, annotate_results,
)
from scanner.strategies import golden_cross, ichimoku
from scanner.trading_calendar import last_trading_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('daily')


# Việt Nam ở UTC+7 và không có DST từ 1975, nên offset cố định là chính xác và
# không phụ thuộc gói tzdata của máy chạy. `datetime.now()` trần KHÔNG dùng được:
# runner của GitHub Actions chạy giờ UTC, nên nó vừa lệch 7 tiếng vừa đặt sai tên
# file archive mỗi khi bản EOD chạy qua nửa đêm ICT.
ICT = timezone(timedelta(hours=7), name='ICT')

# Vì sao 15:15 ICT: HOSE khớp ATC lúc 14:45, nhưng khối lượng chỉ chốt hẳn sau đó
# ~20-25 phút (thoả thuận + báo cáo muộn). Đo trên 223 quan sát tháng 7-8/2026,
# so khối lượng trong archive với khối lượng lấy về sau cùng phiên:
#     ghi lúc 14:45 → 72% số mã còn thiếu, trung vị 0,905
#     ghi lúc 14:59 → 44% còn thiếu
#     ghi lúc 15:08 trở đi → 0% thiếu, khớp 100%
# 15:15 là mốc chốt đó cộng biên an toàn.
ARCHIVE_CUTOFF_ICT = dtime(15, 15)

# Trần thời gian cho vòng fetch, giây. 45 phút — cố ý thấp hơn `timeout-minutes:
# 60` của workflow 15 phút.
#
# Khoảng chênh đó không phải cho đẹp: 17-20/08/2026 cả 8 ca đều bị runner giết ở
# đúng phút 60 giữa lúc đang fetch, tức chết TRƯỚC mọi bước ghi file, nên ~140 mã
# đã lấy về không thành cái gì cả. Tự dừng ở phút 45 thì phần chấm điểm, ghi JSON
# và commit vẫn còn 15 phút để chạy — hỏng có kiểm soát thay vì bị chặt ngang.
FETCH_BUDGET_S = int(os.environ.get('FETCH_BUDGET_S', 45 * 60))

# Độ phủ tối thiểu để bản quét được coi là đại diện cho cả phiên. Dưới mức này,
# archive bị chặn: một file archive mỏng là VĨNH VIỄN (không ai chạy lại phiên
# cũ), còn latest.json thì ca sau ghi đè được.
MIN_COVERAGE_FOR_ARCHIVE = float(os.environ.get('MIN_COVERAGE_FOR_ARCHIVE', 0.8))

# Tỷ lệ mã bị đóng dấu StaleCache mà trên mức đó, kết quả quét không còn là kết
# quả nữa — nó là triệu chứng của một lỗi ở tầng dữ liệu.
#
# Vì sao 0,95: mức nền quan sát được ngày 28/08/2026 là ~0,19 (96/500 mã stale
# thật, tức số mã vnstock quả thực chưa cập nhật). Ca hỏng hôm đó cho 1,00 —
# cả 500 mã, trong đó 404 mã có dữ liệu hoàn toàn tươi cho phiên đã chốt.
# Khoảng 0,19 → 0,95 đủ rộng để không ca bình thường nào chạm tới; để dưới 1,0
# để vài mã lẻ tình cờ có nến hôm nay không vô hiệu hoá được cổng chặn.
MAX_STALE_RATIO = float(os.environ.get('MAX_STALE_RATIO', 0.95))


def now_ict() -> datetime:
    """Giờ ICT tại THỜI ĐIỂM GỌI — không phải nhãn dán lúc job khởi động."""
    return datetime.now(timezone.utc).astimezone(ICT)


def get_run_type() -> str:
    """
    Nhãn ca chạy do workflow dán (`SCAN_RUN_TYPE`), chỉ để GHI LẠI.

    Nhãn này được tính bằng giờ UTC lúc job KHỞI ĐỘNG rồi đóng băng, trong khi
    bước ghi file diễn ra sau đó 30-60 phút. Dùng nó làm cổng chặn thì sai cả hai
    chiều: bản khởi động 12:00 ICT mà ghi lúc 15:40 vẫn mang nhãn 'intraday' dù
    khối lượng đã chốt (vứt oan dữ liệu tốt), còn `workflow_dispatch` chọn tay
    'eod' lúc 12:00 thì mở toang cổng cho dữ liệu nửa phiên. Cổng thật đo đồng hồ
    tại lúc ghi — xem archive_decision().
    """
    return os.environ.get('SCAN_RUN_TYPE', '').strip().lower() or 'unknown'


def session_date_from_data(df_all: pd.DataFrame) -> Optional[str]:
    """
    Ngày phiên lấy từ CHÍNH dữ liệu, không lấy từ đồng hồ của máy chạy.

    Trước đây tên file archive là `datetime.now()` của runner (giờ UTC): bản EOD
    chạy 23:00 ICT tức 16:00 UTC, chỉ cần quét quá 60 phút là qua 17:00 UTC và
    ngày UTC lệch một ngày so với ngày phiên. `df['Date'].max()` không có vấn đề
    đó vì nó là ngày của chính cây nến cuối cùng.
    """
    if df_all is None or len(df_all) == 0 or 'Date' not in df_all.columns:
        return None
    last = pd.to_datetime(df_all['Date']).max()
    return None if pd.isna(last) else pd.Timestamp(last).strftime('%Y-%m-%d')


def session_completeness(by_ticker: dict) -> Optional[float]:
    """
    Trung vị chéo của (KL phiên cuối / trung vị KL 20 phiên trước đó).

    Phiên trọn vẹn cho ~1,0; ảnh chụp giữa phiên chiều cho ~0,64 (đo tháng 8/2026
    trên 63 quan sát). Đây là CỜ THÔNG TIN, cố ý KHÔNG dùng để chặn: chỉ số này
    cũng tụt trong phiên thật sự trầm lắng, nên tự nó không phân biệt được "chưa
    đóng cửa" với "thanh khoản thấp". Cổng chặn là đồng hồ; số này để hậu kiểm.
    """
    ratios = []
    for d in (by_ticker or {}).values():
        if d is None or len(d) < 21 or 'Volume' not in d.columns:
            continue
        base = float(d['Volume'].iloc[-21:-1].median())
        if base > 0:
            ratios.append(float(d['Volume'].iloc[-1]) / base)
    if not ratios:
        return None
    return round(float(pd.Series(ratios).median()), 3)


def stale_ratio(by_ticker: dict):
    """
    Tỷ lệ mã bị đóng dấu StaleCache ở DÒNG CUỐI — đúng dòng mọi strategy đọc.

    `fetch_with_cache` gắn cột 'StaleCache' cho từng mã; criteria.py:176,
    golden_cross.py:139 và ichimoku.py:143 đều reject thẳng nếu dòng cuối bật
    cờ. Nên đây chính là phần universe sẽ KHÔNG được chấm điểm.

    Trả (tỷ lệ, số mã stale, số mã xét, các ngày phiên cuối quan sát được).
    """
    stale = 0
    total = 0
    last_dates = set()
    for d in (by_ticker or {}).values():
        if d is None or len(d) == 0 or 'StaleCache' not in d.columns:
            continue
        total += 1
        if bool(d['StaleCache'].iloc[-1]):
            stale += 1
        if 'Date' in d.columns:
            last_dates.add(pd.Timestamp(d['Date'].iloc[-1]).strftime('%Y-%m-%d'))
    ratio = (stale / total) if total else 0.0
    return round(ratio, 3), stale, total, sorted(last_dates, reverse=True)


def evaluate_archive_gates(now: datetime, fetch_summary: Optional[dict] = None,
                           min_coverage: Optional[float] = None) -> list:
    """
    Chấm TỪNG cổng archive độc lập, không dừng ở cái đầu tiên hỏng.

    Vì sao không đoản mạch: bản cũ trả về đúng một câu lý do, nên khi độ phủ
    mỏng thì log chỉ nói về độ phủ và không ai biết cổng giờ đã pass hay chưa —
    phải suy ngược từ `written_at_ict`. Với ca intraday có vòng fetch bị cắt,
    hai cổng cùng chặn mà chỉ thấy một; sửa xong cái này lại tưởng đã xong.

    Mỗi phần tử: {'name', 'passed', 'detail'}. `passed` là bool để tổng hợp;
    `detail` mang con số thật để đọc log không phải tra lại.

    Thứ tự trong danh sách là thứ tự trình bày, KHÔNG phải thứ tự ưu tiên — mọi
    cổng đều được chấm, kết quả không phụ thuộc thứ tự.
    """
    cutoff_str = ARCHIVE_CUTOFF_ICT.strftime('%H:%M')
    min_coverage = (MIN_COVERAGE_FOR_ARCHIVE if min_coverage is None
                    else min_coverage)

    # ── Cổng 1: đồng hồ tại lúc ghi ──────────────────────────────────────
    after_cutoff = now.time() >= ARCHIVE_CUTOFF_ICT
    gates = [{
        'name': 'gate_time',
        'passed': after_cutoff,
        'detail': (f'{now:%H:%M} ICT >= {cutoff_str} — khối lượng đã chốt'
                   if after_cutoff else
                   f'{now:%H:%M} ICT < {cutoff_str} — khối lượng chưa chốt'),
    }]

    # ── Cổng 2: độ phủ vòng fetch ────────────────────────────────────────
    coverage = (fetch_summary or {}).get('coverage')
    truncated = bool((fetch_summary or {}).get('truncated'))
    stop = (fetch_summary or {}).get('stop_reason')

    if coverage is None:
        # Không có số liệu thì cổng này không chặn được gì. Đánh dấu passed để
        # không chặn oan, nhưng nói thẳng trong detail là KHÔNG ĐO ĐƯỢC — khác
        # hẳn với "đã đo và đạt".
        gates.append({'name': 'gate_coverage', 'passed': True,
                      'detail': 'không có số liệu vòng fetch — cổng không đo được'})
    else:
        thin = coverage < min_coverage
        cov_str = f'{coverage:.0%}'
        thr_str = f'{min_coverage:.0%}'
        if truncated or thin:
            why = f'{cov_str} < {thr_str}' if thin else f'{cov_str} >= {thr_str}'
            gates.append({
                'name': 'gate_coverage', 'passed': False,
                'detail': (f'{why}, vòng fetch dừng sớm ({stop})' if truncated
                           else f'{why} — bản quét không đại diện cho phiên'),
            })
        else:
            gates.append({'name': 'gate_coverage', 'passed': True,
                          'detail': f'{cov_str} >= {thr_str}, vòng fetch chạy trọn'})

    return gates


def format_gates(gates: list) -> str:
    """`gate_time: pass (...) | gate_coverage: fail (...)` — một dòng cho log."""
    return ' | '.join(
        f"{g['name']}: {'pass' if g['passed'] else 'fail'} ({g['detail']})"
        for g in gates
    )


def archive_decision(force: bool = False, now: Optional[datetime] = None,
                     fetch_summary: Optional[dict] = None,
                     min_coverage: Optional[float] = None) -> dict:
    """
    Có được ghi archive không — tổng hợp từ TẤT CẢ các cổng đã chấm.

    Hai cổng, chặn hai thứ khác nhau:

      gate_time     — đồng hồ TẠI LÚC GHI, không phải nhãn `SCAN_RUN_TYPE` dán
                      lúc job khởi động. Nhãn đó sai cả hai chiều: bản khởi động
                      12:00 ICT mà ghi lúc 15:40 vẫn mang nhãn 'intraday' dù khối
                      lượng đã chốt, còn `workflow_dispatch` chọn tay 'eod' lúc
                      12:00 thì mở toang cổng cho dữ liệu nửa phiên.
      gate_coverage — độ phủ vòng fetch. File archive là VĨNH VIỄN: không ca nào
                      chạy lại phiên cũ để sửa, và backtest sau này đọc nó như dữ
                      liệu thật. Bản quét 140/500 mã là một lát cắt, không phải
                      phiên đó. latest.json thì khác, ca sau ghi đè được.

    Thiếu thông tin thì ĐÓNG. Bản cũ nhất hỏi `env == 'intraday'`, nên thiếu biến
    môi trường sẽ trả False và archive được ghi vô điều kiện — hỏng theo hướng MỞ.

    `--force-archive` ép qua mọi cổng đang hỏng, và mọi lần ép đều bị đánh dấu
    `forced=True` kèm tên cổng bị ép trong `reason`. Không đánh dấu thì một file
    archive dựng từ 140/500 mã trông y hệt file dựng từ 500/500.
    """
    now = now or now_ict()
    gates = evaluate_archive_gates(now, fetch_summary, min_coverage)
    failed = [g['name'] for g in gates if not g['passed']]

    write = (not failed) or force
    forced = bool(failed) and force

    reason = format_gates(gates)
    if forced:
        reason += f" — ÉP GHI bằng --force-archive qua: {', '.join(failed)}"

    return {
        'write': write,
        'forced': forced,
        'run_type': get_run_type(),
        'written_at_ict': now.strftime('%Y-%m-%d %H:%M:%S%z'),
        'gates': gates,
        'gates_failed': failed,
        'reason': reason,
    }


def build_metadata(min_score, exchanges, total_scanned, market_context,
                   session_date, decision, completeness,
                   fetch_summary: Optional[dict] = None) -> dict:
    """
    Metadata dùng chung cho latest.json VÀ file archive.

    Trước đây `run_type` chỉ được bước jq của workflow vá vào 4 file latest.json,
    không vá bản archive — nên nhìn một file archive không cách nào biết nó là
    bản giữa phiên hay bản chính thức, phải suy ngược từ `generated_at`. Nay ba
    trường bằng chứng đi kèm mọi file.
    """
    return {
        'min_score': min_score,
        'exchanges': list(exchanges),
        'total_scanned': total_scanned,
        'market_context': market_context or {},
        'session_date': session_date,
        'written_at_ict': decision['written_at_ict'],
        'run_type': decision['run_type'],
        'session_complete': completeness,
        'archive_written': decision['write'],
        'archive_forced': decision['forced'],
        # `archive_gate` giu nguyen la chuoi mot dong (web/app.js va buoc Verify
        # cua workflow doc no); `archive_gates` la ban co cau truc, liet ke MOI
        # cong da cham kem ket qua tung cai. Nhin mot file archive ba thang sau
        # van biet duoc cong nao chan, cong nao pass, con so bao nhieu.
        'archive_gate': decision['reason'],
        'archive_gates': decision.get('gates', []),
        'archive_gates_failed': decision.get('gates_failed', []),
        # Bằng chứng về vòng fetch. `fetch_truncated` là trường mà chuông báo độ
        # tươi (check_freshness.py) và người đọc dashboard cần thấy: một file
        # sinh ra từ 140/500 mã trông y hệt file sinh ra từ 500/500 nếu không nói
        # ra. `fetch_stop_reason` là None khi vòng lặp chạy trọn.
        'fetch_truncated': bool((fetch_summary or {}).get('truncated')),
        'fetch_stop_reason': (fetch_summary or {}).get('stop_reason'),
        'fetch_coverage': (fetch_summary or {}).get('coverage'),
        'fetch_elapsed_s': (fetch_summary or {}).get('elapsed_s'),
        # Giữ khoá cũ: web/app.js:373 đọc `metadata.intraday` làm nguồn dự phòng
        # khi thiếu `run_type`.
        'intraday': decision['run_type'] == 'intraday',
    }


def write_strategy_outputs(results, web_subdir, session_date, min_score,
                           exchanges, total_scanned, strategy_label,
                           market_context=None, decision=None, completeness=None,
                           fetch_summary=None):
    """Write latest.json + archive/<date>.json + archive/index.json for one strategy."""
    web_subdir.mkdir(parents=True, exist_ok=True)
    archive_dir = web_subdir / 'archive'
    archive_dir.mkdir(exist_ok=True)

    signals = []
    for r in results:
        if r is None: continue
        if r.total_score >= min_score:
            signals.append(r.to_dict())
    signals.sort(key=lambda s: -s['total_score'])

    payload = {
        'generated_at': datetime.now().isoformat(),
        'strategy': strategy_label,
        'total': len(signals),
        'metadata': build_metadata(min_score, exchanges, total_scanned,
                                   market_context, session_date, decision,
                                   completeness, fetch_summary),
        'signals': signals,
    }

    latest = web_subdir / 'latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"  [{strategy_label}] {len(signals)} signals → {latest}")

    if not decision['write']:
        log.warning(f"  [{strategy_label}] KHÔNG ghi archive — {decision['reason']}")
        return
    if session_date is None:
        log.warning(f"  [{strategy_label}] KHÔNG ghi archive — không xác định được "
                    f"ngày phiên từ dữ liệu")
        return

    # compact=True: archive chỉ máy đọc, giảm ~35% dung lượng repo
    write_json(payload, archive_dir / f'{session_date}.json', compact=True)

    available_dates = sorted([
        f.stem for f in archive_dir.glob('*.json') if f.stem != 'index'
    ], reverse=True)
    with open(archive_dir / 'index.json', 'w') as f:
        json.dump({'latest': session_date, 'dates': available_dates[:90],
                   'count': len(available_dates)}, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-score', type=int, default=5,
                        help='Pre-breakout min score (0-10)')
    parser.add_argument('--min-score-goldencross', type=int, default=2,
                        help='Golden Cross min score (0-5)')
    parser.add_argument('--min-score-ichimoku', type=int, default=3,
                        help='Ichimoku min score (3-4, flexible mode)')
    parser.add_argument('--exchanges', type=str, default='HOSE,HNX,UPCOM')
    parser.add_argument('--lookback', type=int, default=400)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--web-data-dir', type=str, default='web/data')
    parser.add_argument('--output-dir', type=str, default='backend/data/results')
    parser.add_argument('--no-corporate-actions', action='store_true',
                        help='Bỏ qua bộ lọc sự kiện quyền (nhanh hơn, dùng khi test)')
    parser.add_argument('--fetch-budget', type=int, default=FETCH_BUDGET_S,
                        help='Trần thời gian cho vòng fetch, giây (0 = bỏ trần). '
                             'Mặc định %(default)s, cố ý thấp hơn timeout-minutes '
                             'của workflow để còn kịp ghi file.')
    parser.add_argument('--max-consecutive-failures', type=int, default=20,
                        help='Số mã hỏng LIÊN TIẾP thì nhả cầu dao và dừng vòng '
                             'fetch (0 = tắt cầu dao). Mặc định %(default)s.')
    parser.add_argument('--force-archive', action='store_true',
                        help='Ghi archive kể cả khi chưa qua %s ICT. Chỉ dùng khi '
                             'biết rõ dữ liệu đã đủ; lần ghi đè sẽ được đánh dấu '
                             'archive_forced=true trong metadata.'
                             % ARCHIVE_CUTOFF_ICT.strftime('%H:%M'))
    args = parser.parse_args()

    exchanges = tuple(args.exchanges.split(','))
    web_dir = Path(args.web_data_dir)
    web_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"VN Multi-Strategy Scanner -- Daily Run "
             f"{now_ict():%Y-%m-%d %H:%M} ICT")
    log.info(f"  Exchanges: {exchanges}, limit={args.limit}")

    universe = get_ticker_universe(exchanges, limit=args.limit)
    log.info(f"  Universe: {len(universe)} tickers")

    df_all_raw = fetch_universe(
        universe,
        lookback_days=args.lookback,
        time_budget_s=args.fetch_budget,
        max_consecutive_failures=args.max_consecutive_failures,
        checkpoint_path=CHECKPOINT_PATH,
    )
    fetch_summary = df_all_raw.attrs.get('fetch_summary', {})

    if df_all_raw.empty:
        log.error("No data fetched from vnstock "
                  f"(stop_reason={fetch_summary.get('stop_reason')})")
        sys.exit(1)

    total_scanned = df_all_raw['Ticker'].nunique()
    log.info(f"  Fetched data for {total_scanned} tickers")

    # Vòng fetch dừng sớm là chuyện phải nói to. Bản cũ chết lặng ở phút 60 và
    # không ai biết cho tới khi soi log; nay nó tự dừng, giữ lại phần đã lấy, và
    # đóng dấu vào metadata của cả 4 file để dashboard lẫn chuông báo đều thấy.
    if fetch_summary.get('truncated'):
        log.error(
            f"  VÒNG FETCH BỊ CẮT ({fetch_summary.get('stop_reason')}): "
            f"{fetch_summary.get('ok')}/{fetch_summary.get('total')} mã "
            f"(độ phủ {fetch_summary.get('coverage', 0):.1%}) sau "
            f"{fetch_summary.get('elapsed_s')}s. Checkpoint: {CHECKPOINT_PATH}"
        )
        log.error("  Kết quả phiên này là MỘT LÁT CẮT, không phải bản quét đầy đủ.")

    # -------- Bối cảnh thị trường (regime + breadth + relative strength) -----
    # Trước đây `fetch_vnindex` được import nhưng không dùng ở đâu: hệ thống bắn
    # tín hiệu mua giống hệt nhau trong uptrend lẫn downtrend, và không có
    # relative strength — yếu tố dự báo mạnh nhất trong momentum.
    log.info("Đánh giá bối cảnh thị trường (VN-Index)...")
    index_df = fetch_vnindex(lookback_days=max(args.lookback, 400))
    regime = compute_regime(index_df)
    log.info(f"  Regime: {regime.get('regime')} — {regime.get('label')}")

    # Cắt DataFrame theo mã MỘT LẦN rồi tái sử dụng cho mọi strategy.
    # Trước đây mỗi strategy tự lọc `df_all_raw[df_all_raw['Ticker'] == t]` trong
    # vòng lặp → quét lại toàn bộ frame 3 × N lần.
    by_ticker = {tk: g.sort_values('Date').reset_index(drop=True)
                 for tk, g in df_all_raw.groupby('Ticker', sort=False)}

    # -------- Cổng chặn: gần như toàn bộ universe bị đóng dấu stale --------
    # Vì sao là cổng RIÊNG chứ không dùng decision['write']: cổng archive fail
    # theo thiết kế ở MỌI ca intraday (chưa qua 15:15 ICT), nên nó không phân
    # biệt nổi "ca intraday bình thường" với "tầng dữ liệu hỏng". Cổng này đo
    # một thứ khác hẳn.
    #
    # Vì sao đứng ở ĐÂY: nó phải chặn TRƯỚC mọi lệnh ghi, kể cả latest.json —
    # thứ duy nhất ca intraday được phép ghi, và cũng chính là thứ đã bị đè
    # bằng file rỗng ngày 28/08. Dừng hẳn thì dữ liệu ca trước còn nguyên.
    ratio, n_stale, n_total, observed = stale_ratio(by_ticker)
    log.info(f"  Tỷ lệ mã stale: {ratio:.1%} ({n_stale}/{n_total} mã)")
    if ratio >= MAX_STALE_RATIO:
        # TRÙNG LẶP CÓ CHỦ Ý với data_fetcher.py:440-442. Dựng lại
        # đúng phép tính đã gây STALE để thông báo lỗi không nói dối.
        # Bước sau sẽ xoá bản sao này: data_fetcher đóng dấu
        # last_session vào fetch_summary, cổng đọc từ đó. Sửa
        # data_fetcher mà quên chỗ này => thông báo lỗi báo sai
        # expected.
        expected = last_trading_session(datetime.now().date())
        log.error(f"  GẦN NHƯ TOÀN BỘ UNIVERSE STALE: {ratio:.1%} "
                  f"({n_stale}/{n_total} mã) >= ngưỡng {MAX_STALE_RATIO:.0%}")
        log.error(f"  df.last quan sát được: {', '.join(observed[:5])}"
                  + (f" (+{len(observed) - 5} ngày khác)" if len(observed) > 5 else "")
                  + f"  |  last_session kỳ vọng: {expected}")
        log.error("  Mọi strategy sẽ reject sạch và ghi ra file RỖNG. Dừng tại "
                  "đây, không ghi gì cả, giữ nguyên dữ liệu ca trước.")
        sys.exit(1)

    breadth = compute_breadth(by_ticker)
    rs_map = compute_relative_strength(by_ticker, index_df)
    log.info(f"  Breadth: {breadth.get('pct_above_ma50')}% số mã trên MA50 "
             f"(n={breadth.get('sample_size')}) | RS tính cho {len(rs_map)} mã")

    market_context = {**regime, 'breadth': breadth}

    # -------- Cổng archive: quyết định bằng đồng hồ TẠI LÚC GHI --------
    session_date = session_date_from_data(df_all_raw)
    completeness = session_completeness(by_ticker)
    decision = archive_decision(force=args.force_archive,
                                fetch_summary=fetch_summary)
    log.info(f"  Ngày phiên (từ dữ liệu): {session_date}")
    log.info(f"  Độ trọn vẹn phiên: {completeness} "
             f"(cờ thông tin, không dùng để chặn)")
    log.info(f"  Độ phủ vòng fetch: {fetch_summary.get('coverage')} "
             f"(ngưỡng archive {MIN_COVERAGE_FOR_ARCHIVE})")
    # In TỪNG cổng một dòng, kể cả cổng đã pass. Bản cũ chỉ in lý do của cổng
    # hỏng đầu tiên, nên ca intraday có vòng fetch bị cắt sẽ chỉ thấy một trong
    # hai cổng đang chặn — sửa xong cái đó lại tưởng đã xong.
    log.info("  ── Cổng archive ──")
    for g in decision['gates']:
        line = f"  {g['name']:14} : {'PASS' if g['passed'] else 'FAIL'}  ({g['detail']})"
        (log.info if g['passed'] else log.warning)(line)
    if decision['write']:
        log.info(f"  => Archive: GHI"
                 + (f" (ÉP qua {', '.join(decision['gates_failed'])})"
                    if decision['forced'] else ""))
        if decision['forced']:
            log.warning("  Archive bị ép ghi bằng --force-archive; "
                        "metadata.archive_forced = true")
    else:
        log.warning(f"  => Archive: BỎ QUA — hỏng ở "
                    f"{', '.join(decision['gates_failed'])}")

    # -------- Pre-Breakout --------
    log.info("Running Pre-Breakout strategy...")
    scanner = BreakoutScanner(exchanges=exchanges,
                              fetch_corporate_actions=not args.no_corporate_actions)
    df_pb = scanner.scan_from_dataframe(df_all_raw)
    if not df_pb.empty:
        # Gắn RS vào bảng kết quả Pre-Breakout (scanner trả về DataFrame)
        if rs_map:
            df_pb['m_rs_score'] = df_pb['ticker'].map(
                lambda t: (rs_map.get(t) or {}).get('rs_score'))
            df_pb['m_rs_rank'] = df_pb['ticker'].map(
                lambda t: (rs_map.get(t) or {}).get('rs_rank'))

        pb_signals = df_pb[df_pb['total_score'] >= args.min_score].copy()
        log.info(f"  Pre-Breakout: {len(pb_signals)} signals")

        pb_meta = build_metadata(args.min_score, exchanges, total_scanned,
                                 market_context, session_date, decision,
                                 completeness, fetch_summary)
        to_json(pb_signals, web_dir / 'latest.json', metadata=pb_meta)

        if decision['write'] and session_date is not None:
            archive = web_dir / 'archive'
            archive.mkdir(exist_ok=True)
            to_json(pb_signals, archive / f'{session_date}.json', metadata=pb_meta,
                    compact=True)
            available = sorted([f.stem for f in archive.glob('*.json') if f.stem != 'index'],
                               reverse=True)
            with open(archive / 'index.json', 'w') as f:
                json.dump({'latest': session_date, 'dates': available[:90],
                           'count': len(available)}, f, indent=2)
        else:
            log.warning(f"  [pre_breakout] KHÔNG ghi archive — "
                        f"{decision['reason'] if session_date else 'thiếu ngày phiên'}")

        if not pb_signals.empty:
            try:
                to_excel(pb_signals, out_dir / f'signals_{session_date}.xlsx')
            except Exception as e:
                log.warning(f"  Excel export failed: {e}")

    def run_strategy(label, fn):
        """Chấm điểm toàn bộ mã → gắn RS → áp bộ lọc sự kiện quyền."""
        results = []
        n_raised = 0
        for ticker, df_t in by_ticker.items():
            try:
                res = fn(df_t, ticker)
                if res:
                    results.append(res)
            except Exception as e:
                # Trước đây là log.debug: ở mức INFO của workflow, mã hỏng biến
                # mất không dấu vết, nên "0 candidates" đọc y hệt nhau dù là
                # thị trường không có tín hiệu hay 500 mã cùng nổ.
                n_raised += 1
                log.warning(f"  {label} {ticker}: {type(e).__name__}: {e}")
        if n_raised:
            log.warning(f"  {label}: {n_raised}/{len(by_ticker)} mã raise exception "
                        f"— không mã nào trong số đó vào được kết quả")
        else:
            log.info(f"  {label}: 0/{len(by_ticker)} mã raise exception")
        log.info(f"  {label}: {len(results)} candidates")
        annotate_results(results, rs_map)
        if not args.no_corporate_actions:
            results = apply_event_filter(results)
        return results

    # -------- Golden Cross — LONG preset (MA50 × MA200) --------
    log.info("Running Golden Cross strategy (LONG: MA50×MA200)...")
    gc_long_results = run_strategy(
        'GC-long', lambda df_t, tk: golden_cross.evaluate(df_t, tk, preset='long'))
    write_strategy_outputs(gc_long_results, web_dir / 'golden_cross_long', session_date,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_long', market_context, decision, completeness,
                           fetch_summary)

    # -------- Golden Cross — SHORT preset (MA10 × MA20) --------
    log.info("Running Golden Cross strategy (SHORT: MA10×MA20)...")
    gc_short_results = run_strategy(
        'GC-short', lambda df_t, tk: golden_cross.evaluate(df_t, tk, preset='short'))
    write_strategy_outputs(gc_short_results, web_dir / 'golden_cross_short', session_date,
                           args.min_score_goldencross, exchanges, total_scanned,
                           'golden_cross_short', market_context, decision, completeness,
                           fetch_summary)

    # -------- Ichimoku --------
    log.info("Running Ichimoku strategy...")
    ich_results = run_strategy('Ichimoku', lambda df_t, tk: ichimoku.evaluate(df_t, tk))
    write_strategy_outputs(ich_results, web_dir / 'ichimoku', session_date,
                           args.min_score_ichimoku, exchanges, total_scanned,
                           'ichimoku', market_context, decision, completeness,
                           fetch_summary)

    log.info(f"All strategies complete for session {session_date}")


if __name__ == '__main__':
    main()
