"""Xoá checkpoint của thread hiện tại để chạy lại từ đầu.

Cần khi bạn đổi cấu trúc graph mà checkpoint cũ vẫn trỏ tới node không còn
tồn tại — graph sẽ dừng ở node đó mà không báo lỗi rõ ràng.

Cách dùng:
    python tools\\reset_thread.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.config import get_config  # noqa: E402
from agentic.memory.checkpointer import clear_thread  # noqa: E402


def main() -> int:
    cfg = get_config()
    db_path = Path(cfg.memory["db_path"])
    deleted = clear_thread(db_path, cfg.thread_id)

    if deleted == 0:
        print(f"Khong co gi de xoa cho thread '{cfg.thread_id}'.")
        return 0

    print(f"Da xoa {deleted} dong cho thread '{cfg.thread_id}'.")
    print("Chay lai: agentic design \"<yeu cau>\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())