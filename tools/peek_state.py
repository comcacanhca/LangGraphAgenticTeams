"""Xem graph đang dừng ở node nào và state đã tới đâu.

Khi một lần chạy lâu bất thường, câu hỏi quan trọng nhất là "đang mắc
kẹt ở đâu" — đọc code không trả lời được, phải hỏi chính LangGraph.

Cách dùng:
    python tools/peek_state.py            # thread hiện tại
    python tools/peek_state.py --task     # kèm thông tin task đang chạy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.config import get_config  # noqa: E402
from agentic.graph.builder import build_graph  # noqa: E402
from agentic.memory.checkpointer import thread_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task", action="store_true", help="in chi tiết task dang chay"
    )
    args = parser.parse_args(argv)

    cfg = get_config()
    state = build_graph(cfg).get_state(thread_config(cfg))

    if not state.values:
        print("Chua chay gi. Bat dau bang: agentic design \"<yeu cau>\"")
        return 0

    v = state.values
    print(f"thread   : {cfg.thread_id}")
    print(f"node tiep : {state.next}")
    print(f"interrupt : {bool(state.interrupts)}")
    print(f"vong     : {v.get('debate_round')}  blocking={v.get('blocking_count')}")

    design = v.get("design") or {}
    print(
        f"design    : {len(design.get('design', ''))} ky tu | "
        f"{len(design.get('decisions', []))} quyet dinh | "
        f"{len((design.get('tokens') or {}).get('palette', {}))} mau"
    )

    bp = v.get("blueprint") or {}
    if bp:
        arch = (bp.get("architecture_diagram") or "").splitlines()
        print(
            f"blueprint : {len(bp.get('screens', []))} man hinh | "
            f"{len(bp.get('risks', []))} rui ro | arch_dong_dau={arch[:1]}"
        )
    else:
        print("blueprint : (chua co)")

    print(f"stories   : {len(v.get('stories', []))}")
    print(f"luot      : {len(v.get('transcript', []))}")

    if args.task:
        for task in state.tasks:
            print(f"  task: {task}")

    return 0


if __name__ == "__main__":
    sys.exit(main())