"""Ép stdout/stderr dùng UTF-8 cho mọi entry point.

Console Windows mặc định dùng cp1252, không có ký tự tiếng Việt có dấu.
Không ép thì bất kỳ thông báo tiếng Việt nào cũng ném UnicodeEncodeError
và CLI sập trước khi kịp làm việc gì.

Nằm ở module riêng vì cả config.py lẫn cli.py đều cần, mà config được
import từ cli — nếu đặt trong cli thì config sẽ in cảnh báo sai encoding
trước khi cli kịp cấu hình.
"""

from __future__ import annotations

import sys


def force_utf8() -> None:
    """Cấu hình lại stdout/stderr sang UTF-8, bỏ qua nếu không được."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Console cũ không hỗ trợ — chấp nhận in phần ASCII được.
            pass
