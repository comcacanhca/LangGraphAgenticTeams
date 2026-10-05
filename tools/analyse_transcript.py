"""Phân tích transcript đã lưu để tìm vòng lặp trong vòng tranh luận.

Khi `agentic design` chạy rất lâu mà không có output, nghi vấn đầu tiên là
vòng tranh luận quay vòng vô hạn. Công cụ này đếm số lượt theo agent và
theo vòng để chứng minh hoặc bác bỏ nghi ngờ đó.

Cách dùng:
    python tools\\analyse_transcript.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.config import get_config  # noqa: E402
from agentic.graph.builder import build_graph  # noqa: E402
from agentic.memory.checkpointer import thread_config  # noqa: E402


def main() -> int:
    cfg = get_config()
    state = build_graph(cfg).get_state(thread_config(cfg))

    if not state.values:
        print("Chua co state.")
        return 1

    v = state.values
    trans = v.get("transcript") or []
    design = v.get("design") or {}

    print(f"thread       : {cfg.thread_id}")
    print(f"node tiep the: {state.next}")
    print(f"debate_round : {v.get('debate_round')}")
    print(f"converged    : {design.get('converged')}")
    print(f"gate1_result : {v.get('gate1_result')}")
    print(f"so luot      : {len(trans)}")
    per_round = Counter(e.get("round") for e in trans)
    rounds_sorted = sorted(per_round.items(), key=lambda kv: str(kv[0]))

    print(f"theo agent   : {dict(Counter(e.get('agent') for e in trans))}")
    print(f"theo vong    : {dict(rounds_sorted)}")

    bp = v.get("blueprint") or {}
    print(f"blueprint    : {len(bp.get('screens', []))} man hinh, "
          f"{len(bp.get('risks', []))} rui ro")
    print(f"stories      : {len(v.get('stories') or [])}")

    # architect chạy N lần mà debate_round không tăng → vòng lặp.
    n_arch = sum(1 for e in trans if e.get("agent") == "architect")
    if n_arch > 1 and v.get("debate_round", 0) == 0:
        print("\n=> VONG LAP: architect chay %d lan nhung debate_round van 0."
              % n_arch)
        print("   finalize_node chua chay → tranh luan khong bao gio hoi tu.")

    print("\n--- 12 luot gan nhat ---")
    for e in trans[-12:]:
        sev = e.get("concerns") or []
        detail = e.get("text") or e.get("action") or ""
        print(f"  r{e.get('round')} {e.get('agent'):9} "
              f"{len(sev)} concerns | {str(detail)[:70]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())