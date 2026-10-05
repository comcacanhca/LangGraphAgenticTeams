"""Lưu trạng thái để dừng giữa chừng vẫn tiếp tục được.

Đây là ưu thế lớn nhất của hệ này so với một phiên chat thường:

    Bạn đóng máy giữa sprint 3, 2 tiếng sau mở lại →
    agent KHÔNG phải nhớ mình đang làm gì, checkpointer đã lưu.

Cơ chế: mỗi lần LangGraph chạy xong một node, toàn bộ state được ghi
vào SQLite. Lần sau gọi lại với cùng thread_id, nó đọc đúng trạng thái
đó và chạy tiếp.

thread_id lấy từ project.name trong agents.yaml — phải GIỮ NGUYÊN giữa
các lần chạy, nếu đổi thì mất toàn bộ tiến độ.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from agentic.config import ROOT, Config


def build_checkpointer(cfg: Config):
    """Tạo checkpointer theo cấu hình.

    Trả InMemorySaver nếu cấu hình yêu cầu — hữu ích cho test vì không
    để lại file rác.
    """
    memory = cfg.memory

    if memory.get("checkpointer", "sqlite") == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()

    db_path = ROOT / memory.get("db_path", ".runtime/checkpoints.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False: LangGraph có thể gọi từ thread khác với
    # thread đã tạo kết nối (ví dụ khi stream kết quả).
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)


def thread_config(cfg: Config) -> dict:
    """Config truyền cho invoke/stream để biết nạp thread nào.

    Cùng thread_id → tiếp tục. Thread_id khác → bắt đầu mới.
    """
    return {"configurable": {"thread_id": cfg.thread_id}}


def history(db_path: Path, thread_id: str, limit: int = 20) -> list[dict]:
    """Đọc lịch sử các lần chạy để bạn xem tiến trình đã đi qua.

    Chỉ để BẠN đọc — không đưa vào context của tác tử.
    """
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            """
            SELECT checkpoint_id, step
            FROM checkpoints
            WHERE thread_id = ?
            ORDER BY checkpoint_id DESC
            LIMIT ?
            """,
            (thread_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"checkpoint": r[0], "step": r[1]} for r in rows]
    except sqlite3.Error:
        # Bảng chưa tồn tại (chưa chạy lần nào) — không phải lỗi.
        return []


def clear_thread(db_path: Path, thread_id: str) -> int:
    """Xoá checkpoint của một thread để chạy lại từ đầu.

    Cần khi bạn muốn thử lại với thiết kế khác: `interrupt` sẽ dừng ở
    GATE 1, và muốn quay lại GATE 1 với thiết kế mới thì phải xoá.
    """
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,)
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted
