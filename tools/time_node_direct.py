"""Chạy architect_node trực tiếp, đo thời gian, không qua LangGraph.

Cần để tách hai khả năng: node chậm vì model, hay graph chậm vì cơ chế
LangGraph/checkpointer. Gọi trực tiếp node loại trừ khả năng thứ hai.

Cách dùng:
    python tools\\time_node_direct.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.config import get_config  # noqa: E402
from agentic.graph.design_council import architect_node  # noqa: E402


def main() -> int:
    cfg = get_config()
    state = {
        "requirement": (
            "Ung dung ghi nhat ky sinh nhat cua nguoi yeu: "
            "xem so ngay con lai, ghi nhat ky, xem lich su"
        ),
        "debate_round": 0,
        "design": {},
        "pending_critiques": [],
        "transcript": [],
        "remaining_steps": 99,
    }

    t = time.perf_counter()
    out = architect_node(state, cfg)
    elapsed = time.perf_counter() - t

    print(f"architect_node: {elapsed:.1f}s")
    design = out.get("design", {})
    print(f"  design   : {len(design.get('design', ''))} ky tu")
    print(f"  decisions: {len(design.get('decisions', []))}")
    for entry in out.get("transcript", []):
        print(f"  action   : {entry.get('action')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())