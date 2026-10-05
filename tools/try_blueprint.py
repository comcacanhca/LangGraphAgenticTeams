"""Gá»i architect.blueprint() má»™t láº§n vÃ  in lá»—i validate náº¿u cÃ³.

Khi graph cháº¡y lÃ¢u, log chung chá»‰ nÃ³i "Ä‘ang retry" â€” khÃ´ng biáº¿t model sai
á»Ÿ Ä‘Ã¢u. CÃ´ng cá»¥ nÃ y gá»i Ä‘Ãºng má»™t lÆ°á»£t vÃ  in thÃ´ng bÃ¡o SchemaError Ä‘áº§y Ä‘á»§,
Ä‘á»ƒ biáº¿t model 7B vi pháº¡m rÃ ng buá»™c nÃ o.

CÃ¡ch dÃ¹ng:
    python tools\try_blueprint.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.agents import architect  # noqa: E402
from agentic.agents.base import build_agent  # noqa: E402
from agentic.config import get_config  # noqa: E402
from agentic.llm.schema import SchemaError  # noqa: E402

REQUIREMENT = (
    "Ung dung ghi nhat ky sinh nhat cua nguoi yeu: "
    "xem so ngay con lai, ghi nhat ky, xem lich su"
)
DESIGN = (
    "Dung Jetpack Compose voi Material3. Luu du lieu bang Room. "
    "Ba man hinh: chinh, ghi nhat ky, lich su."
)


def main() -> int:
    cfg = get_config()
    agent = build_agent("architect", cfg)

    prompt = architect.blueprint_prompt(REQUIREMENT, DESIGN)
    print(f"prompt: {len(prompt)} ky tu")
    print("=" * 60, flush=True)

    try:
        data = architect.blueprint(agent, REQUIREMENT, DESIGN)
    except SchemaError as exc:
        print(f"\nLOI SCHEMA sau khi het retry:\n{exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\nLOI KHAC: {type(exc).__name__}: {exc}")
        return 1

    print("\nOK â€” schema hop le")
    _dump(data)
    return 0


def _dump(data: dict) -> None:
    print(f"overview      : {len(data.get('overview', ''))} ky tu")
    arch = data.get("architecture_diagram", "")
    print(f"arch dong 1   : {arch.splitlines()[:1]}")
    dm = data.get("data_model", "")
    print(f"data dong 1   : {dm.splitlines()[:1]}")
    print(f"screens       : {len(data.get('screens', []))}")
    for s in data.get("screens", [])[:4]:
        print(f"   - {s.get('name')} | {len(s.get('elements', []))} phan tu")
    print(f"risks         : {len(data.get('risks', []))}")


if __name__ == "__main__":
    sys.exit(main())
