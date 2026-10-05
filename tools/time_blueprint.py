"""Đo riêng lượt gọi blueprint, in thời gian từng lần thử.

Nghi vấn: blueprint chạy ~20s khi gọi trực tiếp nhưng treo 15 phút trong
graph. Cần biết chính xác thời gian mỗi lượt và lỗi schema từng lần thử
để phân biệt "model chậm" với "retry mãi".

Cách dùng:
    python tools\time_blueprint.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.agents import architect  # noqa: E402
from agentic.agents.base import build_agent  # noqa: E402
from agentic.config import get_config  # noqa: E402
from agentic.llm.schema import SchemaError, validate  # noqa: E402

# Dùng đúng nội dung state thật, gồm transcript, để tái hiện đúng tình
# huống chứ không phải prompt rút gọn.
REQUIREMENT = (
    "Ung dung ghi nhat ky sinh nhat cua nguoi yeu: "
    "xem so ngay con lai, ghi nhat ky, xem lich su"
)
DESIGN = (
    "1. Dung Jetpack Compose voi Material3 cho giao dien. "
    "2. Luu du lieu bang Room database. "
    "3. Co ba man hinh: chinh, ghi nhat ky, lich su."
)


def main() -> int:
    cfg = get_config()
    agent = build_agent("architect", cfg)
    client = agent.client
    prompt = architect.blueprint_prompt(REQUIREMENT, DESIGN)

    print(f"max_retries = {client.max_retries}", flush=True)
    print(f"num_ctx     = {client.num_ctx}", flush=True)
    print(f"prompt      = {len(prompt)} ky tu", flush=True)
    print("=" * 64, flush=True)

    payload = {
        "model": client.model,
        "stream": False,
        "format": "json",
        "keep_alive": client.keep_alive,
        "messages": [
            {"role": "system", "content": agent.system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "num_ctx": client.num_ctx,
            "temperature": client.temperature,
            "top_p": client.top_p,
        },
    }

    user_prompt = prompt
    for attempt in range(1, client.max_retries + 1):
        payload["messages"][1]["content"] = user_prompt
        t0 = time.perf_counter()
        print(f"\n--- lan {attempt} ---", flush=True)
        try:
            raw = client._invoke(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"  LOI: {type(exc).__name__}: {exc} "
                  f"({time.perf_counter() - t0:.1f}s)", flush=True)
            return 1

        elapsed = time.perf_counter() - t0
        print(f"  raw = {len(raw)} ky tu trong {elapsed:.1f}s", flush=True)
        print(f"  raw[:300] = {raw[:300]!r}", flush=True)

        try:
            data = validate("blueprint", raw)
        except SchemaError as exc:
            print(f"  SCHEMA LOI: {exc}", flush=True)
            user_prompt = (
                f"{prompt}\n\nLƯU Ý: lần trước JSON sai định dạng. "
                "Chỉ trả về JSON hợp lệ, không thêm chữ nào khác."
            )
            continue

        print(f"  OK: {len(data.get('screens', []))} man hinh", flush=True)
        return 0

    print("\nhet so lan thu", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())