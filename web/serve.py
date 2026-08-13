#!/usr/bin/env python3
"""
Máy chủ tĩnh cho phát triển — TẮT HOÀN TOÀN CACHE.

Vì sao cần thay cho `python -m http.server`:
  http.server gửi `Last-Modified` và trình duyệt tự suy ra thời gian còn "tươi"
  theo heuristic, nên sau khi sửa app.js/styles.css bạn vẫn nhận file cũ cho tới
  khi hard-refresh. Trong lúc đang lặp nhanh trên giao diện, điều này khiến ta
  mất thời gian nghi ngờ code trong khi lỗi chỉ nằm ở cache.

  Máy chủ này gửi `Cache-Control: no-store` cho mọi phản hồi ⇒ F5 thường là đủ.

Usage:
    python web/serve.py            # cổng 8080
    python web/serve.py 8090
"""
from __future__ import annotations

import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Console Windows mặc định là cp1252, không in được tiếng Việt → script tự chết
# ngay dòng print đầu tiên. Ép UTF-8 tại đây để không phải nhớ đặt PYTHONIOENCODING.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

WEB_DIR = Path(__file__).resolve().parent


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, fmt, *args):
        # Chỉ log lỗi; log mọi request làm nhiễu terminal
        status = args[1] if len(args) > 1 else ''
        if str(status).startswith(('4', '5')):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    handler = partial(NoCacheHandler, directory=str(WEB_DIR))
    server = HTTPServer(('127.0.0.1', port), handler)
    print(f"Dashboard : http://127.0.0.1:{port}/index.html")
    print(f"Định giá  : http://127.0.0.1:{port}/valuation/index.html")
    print("Cache đã tắt hoàn toàn — F5 thường là đủ để thấy thay đổi.")
    print("Ctrl+C để dừng.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")


if __name__ == '__main__':
    main()
