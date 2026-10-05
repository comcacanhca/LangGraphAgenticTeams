"""Đo thời gian từng lượt gọi agent trong vòng tranh luận.

Cần biết node nào chậm và vì sao. Công cụ này gọi đúng các hàm mà graph
dùng, in thời gian và độ dài output.

Cách dùng:
    python tools\\time_nodes.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.agents import architect, designer, devops, qa  # noqa: E402
from agentic.agents.base import build_agent  # noqa: E402
from agentic.config import get_config  # noqa: E402

REQUIREMENT = (
    "Ung dung ghi nhat ky sinh nhat cua nguoi yeu: "
    "xem so ngay con lai, ghi nhat ky, xem lich su"
)
DESIGN = (
    "1. Dung Jetpack Compose voi Material3 cho giao dien. "
    "2. Luu du lieu bang Room database. "
    "3. Co ba man hinh: chinh, ghi nhat ky, lich su."
)


def _run(label, fn) -> None:
    t0 = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001
        print(f"{label:22} {time.perf_counter() - t0:6.1f}s  "
              f"LOI {type(exc).__name__}: {str(exc)[:60]}", flush=True)
        return
    size = len(str(result))
    print(f"{label:22} {time.perf_counter() - t0:6.1f}s  OK ({size} chars)",
          flush=True)


def main() -> int:
    cfg = get_config()

    _run("architect.propose",
         lambda: architect.propose(build_agent("architect", cfg), REQUIREMENT, ""))

    design = DESIGN
    for name, mod in (("developer", None), ("qa", qa), ("devops", devops)):
        agent = build_agent(name, cfg)
        if name == "developer":
            from agentic.graph.design_council import _DeveloperCritic

            fn = lambda a=agent: _DeveloperCritic.critique_design(a, design)
        else:
            fn = lambda a=agent, m=mod: m.critique_design(a, design)
        _run(f"{name}.critique_design", fn)

    _run("designer.design_tokens",
         lambda: designer.design_tokens(
             build_agent("designer", cfg), app_purpose=design
         ))

    _run("architect.blueprint",
         lambda: architect.blueprint(
             build_agent("architect", cfg), REQUIREMENT, design
         ))

    return 0


if __name__ == "__main__":
    sys.exit(main())