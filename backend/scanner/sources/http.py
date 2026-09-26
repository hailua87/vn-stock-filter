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
import threading
import time
from typing import Any, Callable, Dict, Optional, TypeVar

import requests

# Ghi vào sổ snapshot BCTC thay cho phiên bản vnstock (khóa `vnstock` trong
# `revisions` giữ nguyên tên để đọc được sổ cũ). Tăng số khi đổi cách đọc API
# làm số liệu có thể khác — lúc đó mọi "revised" trong sổ quy được về đây.
SOURCE_VERSION = 'direct-1'

TIMEOUT = 30

# Khoảng cách tối thiểu giữa hai lượt gọi, cho MỌI nguồn cộng lại.
#
# vnstock tự giới hạn 60 lượt/phút (bản có API key) ở phía máy khách. Bỏ
# vnstock là bỏ luôn giới hạn đó, nên đặt lại đúng mức cũ: 1 giây/lượt. Không
# phải để né chặn — để không gọi dồn dập hơn trước vào máy chủ của người khác.
MIN_INTERVAL = float(os.environ.get('SOURCE_MIN_INTERVAL', '1.0'))

_BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

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


def _throttle() -> None:
    global _last_call
    if MIN_INTERVAL <= 0:
        return
    with _lock:
        wait = _last_call + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def request_json(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                 params: Optional[Dict[str, Any]] = None,
                 payload: Optional[Dict[str, Any]] = None) -> Any:
    """Gọi và trả JSON đã parse. Mọi lỗi mạng/HTTP/JSON thành SourceError."""
    _throttle()
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    try:
        r = _session().request(method, url, headers=h, params=params,
                               json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:
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
