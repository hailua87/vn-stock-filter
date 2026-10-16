"""
Gọi HTTP dùng chung cho VCI và KBS: header, timeout, điều tiết, lỗi, thử lại.

`request_json` KHÔNG tự thử lại: `data_fetcher.fetch_ohlcv` và
`financial_fetcher.fetch_financial_statements` đã có vòng thử lại riêng; thêm
một vòng ở tầng này sẽ nhân số lần gọi. Các lời gọi còn lại (tổng quan công
ty, VN-Index, danh sách mã, sự kiện, NIM) bọc bằng `with_retry` — thời vnstock
chúng được thư viện thử lại 3 lần, bỏ đi thì một lỗi lẻ có thể kéo dài cả tuần
(tổng quan rỗng nằm trong cache 7 ngày).
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional, TypeVar

import requests

# Ghi vào sổ snapshot BCTC thay cho phiên bản vnstock (khóa `vnstock` trong
# `revisions` giữ nguyên tên để đọc được sổ cũ). Tăng số khi đổi cách đọc API
# làm số liệu có thể khác — lúc đó mọi "revised" trong sổ quy được về đây.
SOURCE_VERSION = 'direct-1'

TIMEOUT = 30

# Giá ngày (OHLCV) chờ ngắn hơn. Đo trên runner GitHub 26/09/2026 (bài đo
# tạm, PR #46): lượt gọi thành công xong trong 0,3–2 s (trung vị 0,33 s, p90
# 1,8 s); lượt hỏng là TREO hẳn tới hết thời gian chờ, chờ lâu hơn cũng không
# ra.
#
# HẠ 10 -> 5 ngày 29/09/2026. Hai lượt quét theo lịch 28/09 đều dừng sớm vì
# hết ngân sách, và cả hai lần phần lớn thời gian là ngồi chờ lượt treo:
#
#     18:35 (3 lần thử): 208/500 = 41,6% — 88 mã treo cả ba lần
#     21:51 (2 lần thử): 368/500 = 73,6% — 144 mã treo cả hai lần
#
# Lượt sau đã tốt hơn hẳn nhờ bớt một lần thử (PR #61), nhưng vẫn dưới ngưỡng
# 80% nên KHÔNG ghi được bản lưu phiên — ba lượt liên tiếp như vậy, và nhật ký
# tín hiệu đứng yên ở 25/09.
#
# 144 mã × 2 lần × 10 s = 48 phút trong ngân sách 70 phút. Hạ còn 5 s cắt một
# nửa số đó (~24 phút), đủ để quét thêm ~125 mã ở nhịp 11,4 s/mã đã đo.
#
# 5 s vẫn gấp 2,8 lần p90 của lượt thành công, và gấp 15 lần trung vị.
OHLCV_TIMEOUT = float(os.environ.get('SOURCE_OHLCV_TIMEOUT', '5'))

# BCTC và tổng quan công ty (iq.vietcap.com.vn) cũng chờ ngắn hơn, cùng lý do
# với OHLCV ở trên. Đo trên runner GitHub 27/09/2026 (bài đo tạm, nhánh
# diag/fetch-parallel đã xoá), 144 lượt gọi, 0 lỗi:
#     trung vị 1,01 s   p90 2,05 s   tối đa 2,15 s
# Trần 30 s cũ gấp 15 lần p90 của lượt thành công, tức nó không bảo vệ lượt
# chậm — nó chỉ kéo dài lượt TREO. Đúng như OHLCV: lượt hỏng treo hết thời
# gian chờ, chờ lâu hơn cũng không ra dữ liệu.
#
# Ngày 27/09/2026, 7 mã (TNH, PVI, AST, ASM, BWE, DLG, NDN) treo toàn bộ 13
# lượt gọi, ngốn 41 phút — 34% ngân sách — mà trả về không gì cả. Gọi lại
# chính 7 mã đó trên runner hôm sau: cả 7 đều xong trong ~2 s với dữ liệu đủ.
# Nguồn không chậm; nó suy giảm theo đợt, và trần chờ dài biến mỗi đợt thành
# hàng chục phút.
#
# 10 s vẫn gấp 5 lần p90 của lượt thành công.
STATEMENT_TIMEOUT = float(os.environ.get('SOURCE_STATEMENT_TIMEOUT', '10'))

# Khoảng cách tối thiểu giữa hai lượt gọi, cho MỌI nguồn cộng lại.
#
# vnstock tự giới hạn 60 lượt/phút (bản có API key) ở phía máy khách. Bỏ
# vnstock là bỏ luôn giới hạn đó, nên đặt lại đúng mức cũ: 1 giây/lượt. Không
# phải để né chặn — để không gọi dồn dập hơn trước vào máy chủ của người khác.
MIN_INTERVAL = float(os.environ.get('SOURCE_MIN_INTERVAL', '1.0'))

_BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

# ĐỪNG đổi bộ header này cho "giống vnstock" — đã đo và nó TỆ HƠN NHIỀU.
#
# Đo trên runner GitHub 26/09/2026 (bài đo tạm, nhánh diag/vci-latency đã xoá;
# nhật ký lượt chạy CI 36240525756). Hai bộ header gọi XEN KẼ nhau trên cùng
# danh sách mã và cùng khoảng thời gian (`i % 2`), nên chênh lệch không phải do
# nguồn chập chờn theo đợt:
#
#     bộ này (BASE_HEADERS)       n=44  lỗi= 3  trung vị 0,33 s  p90  1,79 s
#     bộ kiểu vnstock (13 header) n=44  lỗi=18  trung vị 2,07 s  p90 16,07 s
#
# Bộ kiểu vnstock thêm Connection, Cache-Control, Pragma, DNT, ba header
# Sec-Fetch-*, và Accept-Language đặt en-US trước vi-VN.
#
# ĐỌC CON SỐ CHO ĐÚNG: 18 lỗi kia KHÔNG rải đều. Nhìn theo thứ tự lượt gọi thì
# từ lượt ~45 trở đi, GẦN NHƯ MỌI lượt của bộ vnstock đều ReadTimeout (~16 s)
# trong khi bộ này vẫn chạy bình thường. Tức dấu hiệu nghiêng về "máy chủ bắt
# đầu từ chối bộ header đó" hơn là "bộ header đó chậm đều". Kết luận an toàn
# rút ra được: bộ header hiện tại đi qua được, bộ kia thì không — chưa đủ cơ sở
# nói vì sao.
#
# Một lượt đo, n=44 mỗi bộ. Muốn chắc hơn thì đo lại, nhưng đừng đổi header
# TRƯỚC khi đo.
BASE_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    'Content-Type': 'application/json',
    'User-Agent': _BROWSER_UA,
}


class SourceError(Exception):
    """Nguồn trả lỗi hoặc dữ liệu không đọc được."""


class RateLimitError(SourceError):
    """Nguồn báo quá tần suất (HTTP 429) — nên chờ rồi mới thử lại."""


_lock = threading.Lock()
_last_call = 0.0
_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_local, 'session', None)
    if s is None:
        s = requests.Session()
        _local.session = s
    return s


# Nhịp gọi LIÊN TIẾN TRÌNH.
#
# `_lock` ở trên là `threading.Lock` — nó chỉ điều tiết trong MỘT tiến trình.
# Ngày 16/10/2026 có năm phiên làm việc song song trên kho này, mỗi phiên một
# worktree và một bộ tiến trình riêng, nên trần thật không còn là 1 lượt/giây
# mà là 1 lượt/giây × số phiên. Cache cũng không dùng chung giữa các worktree
# (nó bị `.gitignore` nên worktree mới sinh ra là rỗng) — đo được 591 / 200 /
# 1 / 1 / 0 tệp, tức cùng một dữ liệu bị tải lại nhiều lần.
#
# CLAUDE.md mục 3 dặn đừng NỚI `MIN_INTERVAL`, vì nó là mức cố ý chọn để không
# đập vào máy chủ của bên thứ ba. Chỗ này đi theo đúng lời dặn đó: khoá tệp làm
# cho năm tiến trình cộng lại vẫn là 1 lượt/giây, chứ không phải năm.
#
# Vì sao khoá TỆP mà không phải tệp PID: khoá tệp do hệ điều hành giữ, tiến
# trình chết thì nó tự nhả. Tệp PID thì để lại khoá mồ và phải tự dò chết/sống
# — một cơ chế an toàn mà có thể TREO cả lượt chạy là tệ hơn không có.
#
# Thời gian ghi trong tệp là thời gian TƯỜNG (`time.time`), không phải
# `monotonic`: monotonic của hai tiến trình khác nhau không so được với nhau.
# Bù lại phải chặn trên: đồng hồ nhảy lùi thì không được chờ quá MIN_INTERVAL.
def _bat_nhip_lien_tien_trinh(moi=None) -> bool:
    """
    Đọc cờ bật/tắt. Tách thành hàm để bộ test kiểm được mà KHÔNG phải
    `importlib.reload` module này.

    `reload` ở đây là thuốc độc: nó tạo lại `_lock`, `_session`, `_stats_lock`,
    còn các module đã `from .http import request_json` thì vẫn giữ tham chiếu
    cũ. Phép kiểm cờ bật/tắt bản đầu dùng `reload` và nó làm **4 phép kiểm
    trong `test_sources.py` đỏ** — nhưng chỉ khi chạy cả bộ, còn chạy riêng thì
    xanh. Đúng loại lỗi khó tìm nhất.
    """
    moi = os.environ if moi is None else moi
    return moi.get('SOURCE_CROSS_PROCESS_PACE', '1') != '0'


NHIP_LIEN_TIEN_TRINH = _bat_nhip_lien_tien_trinh()

# Dùng chung CẢ MÁY là cố ý: năm worktree phải cùng một mốc, nếu mỗi worktree
# một tệp thì khoá không chặn được gì. `SOURCE_PACE_LOCK` để bộ test trỏ ra
# `tmp_path` — bộ test chạy song song giữa các worktree mà dùng chung tệp thật
# thì chính nó lại đụng nhau, đúng cái lỗi đang vá.
_TEP_NHIP = (os.environ.get('SOURCE_PACE_LOCK')
             or os.path.join(tempfile.gettempdir(), 'vn-stock-filter-nhip.lock'))


def _khoa_doc_quyen(f) -> bool:
    """Giữ khoá độc quyền trên tệp đang mở. False nếu hệ này không làm được."""
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        return True
    except Exception:
        return False


def _nha_khoa(f) -> None:
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


def _nhip_lien_tien_trinh() -> bool:
    """
    Điều tiết theo mốc dùng chung giữa các tiến trình.

    True = đã điều tiết xong. False = không làm được, hãy dùng đường trong
    tiến trình (fail-open: thà gọi hơi dồn còn hơn đứng hẳn).
    """
    try:
        with open(_TEP_NHIP, 'a+') as f:
            if not _khoa_doc_quyen(f):
                return False
            try:
                f.seek(0)
                raw = f.read(64).strip()
                truoc = float(raw) if raw else 0.0
                cho = min(truoc + MIN_INTERVAL - time.time(), MIN_INTERVAL)
                if cho > 0:
                    time.sleep(cho)
                f.seek(0)
                f.truncate()
                f.write(repr(time.time()))
                f.flush()
            finally:
                _nha_khoa(f)
        return True
    except Exception:
        return False


def _throttle() -> None:
    global _last_call
    if MIN_INTERVAL <= 0:
        return
    with _lock:
        if NHIP_LIEN_TIEN_TRINH and _nhip_lien_tien_trinh():
            # Vẫn cập nhật mốc trong tiến trình: nếu đường liên tiến trình hỏng
            # giữa lượt chạy, đường dự phòng phải biết lượt gọi vừa rồi là lúc
            # nào, không thì nó cho gọi ngay lập tức.
            _last_call = time.monotonic()
            return
        wait = _last_call + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


# Đếm lượt gọi và lượt TREO, để biết nguồn đang tử tế hay đang dở chứng.
#
# Vì sao đếm tỷ lệ treo chứ không đo thời gian chạy: thời gian phụ thuộc nặng
# vào cache. Đo ngày 27-28/09/2026, cùng 200 mã, cùng bước chấm chất lượng:
#     cache ấm,  nguồn sạch : 37 giây
#     cache lạnh, nguồn sạch : 27 phút
#     cache ấm,  nguồn dở   : 70 phút (chạm trần, chỉ xong 165/200)
# Một ngưỡng theo thời gian sẽ báo động nhầm mỗi lần cache lạnh. Tỷ lệ treo thì
# không đổi theo cache — cùng hai ngày đó đo được 0,00 và 1,67 lượt treo mỗi mã.
#
# Đây cũng là chỗ sửa lại một điều tôi từng chốt nhầm vào chú thích: nguồn
# KHÔNG "treo ~1,7 lần mỗi mã" như một đặc tính cố định. Nó thất thường — có
# lượt sạch tuyệt đối. Nên phải đo mỗi lượt, không phải giả định.
_stats_lock = threading.Lock()
_stats = {'calls': 0, 'timeouts': 0}


def reset_stats() -> None:
    with _stats_lock:
        _stats.update(calls=0, timeouts=0)


def stats() -> Dict[str, Any]:
    """Bản chụp bộ đếm, kèm tỷ lệ treo. Người gọi tự chia cho số mã."""
    with _stats_lock:
        d = dict(_stats)
    d['timeout_ratio'] = round(d['timeouts'] / d['calls'], 4) if d['calls'] else 0.0
    return d


def request_json(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                 params: Optional[Dict[str, Any]] = None,
                 payload: Optional[Dict[str, Any]] = None,
                 timeout: float = TIMEOUT) -> Any:
    """Gọi và trả JSON đã parse. Mọi lỗi mạng/HTTP/JSON thành SourceError."""
    _throttle()
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    with _stats_lock:
        _stats['calls'] += 1
    try:
        r = _session().request(method, url, headers=h, params=params,
                               json=payload, timeout=timeout)
    except requests.RequestException as e:
        # Chỉ TREO mới tính, không tính mọi lỗi mạng: một 404 hay DNS hỏng nói
        # điều khác hẳn về nguồn so với việc nó nhận request rồi im lặng.
        if isinstance(e, requests.Timeout):
            with _stats_lock:
                _stats['timeouts'] += 1
        raise SourceError(f'{method} {url}: {type(e).__name__}: {e}') from e
    if r.status_code == 429:
        raise RateLimitError(f'{method} {url}: HTTP 429 (rate limit)')
    if r.status_code != 200:
        raise SourceError(f'{method} {url}: HTTP {r.status_code}')
    try:
        return r.json()
    except ValueError as e:
        raise SourceError(f'{method} {url}: phản hồi không phải JSON') from e


T = TypeVar('T')


def with_retry(fn: Callable[..., T], *args: Any, tries: int = 3, **kwargs: Any) -> T:
    """
    Gọi `fn`, thử lại khi nguồn lỗi: chờ 2 s, 4 s giữa các lần; bị 429 thì chờ
    65 s. Lỗi không phải của nguồn (ValueError do tham số sai …) ném ra ngay.
    Hết lượt thì ném lỗi cuối cùng.
    """
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except RateLimitError:
            if attempt == tries - 1:
                raise
            time.sleep(65)
        except SourceError:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError('unreachable')
