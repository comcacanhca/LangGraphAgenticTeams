"""Chặn payload thật gửi tới llama-server để xem server nhận gì.

Cần khi nghi ngờ tham số không tới được server: đọc code thấy gửi
`num_predict` nhưng thời gian thực tế không đổi, nghĩa là server có thể
đang bỏ qua.

Cách dùng:
    python tools\\trace_payload.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.agents import architect  # noqa: E402
from agentic.agents.base import build_agent  # noqa: E402
from agentic.config import get_config  # noqa: E402


def main() -> int:
    cfg = get_config()
    agent = build_agent("architect", cfg)
    client = agent.client

    original = client._post

    def spy(payload: dict) -> dict:
        print("=== PAYLOAD GUI DI ===", flush=True)
        print("model      :", payload.get("model"), flush=True)
        print("format     :", payload.get("format"), flush=True)
        print("options    :", json.dumps(payload.get("options"),
                                         ensure_ascii=False), flush=True)
        for m in payload.get("messages", []):
            body = m.get("content", "")
            print(f"  [{m.get('role')}] {len(body)} ky tu", flush=True)
        print("=== goi that ===", flush=True)
        result = original(payload)
        content = (
            result.get("message", {}).get("content", "")
            or result.get("response", "")
        )
        print(f"=== NHAN {len(content)} ky tu ===", flush=True)
        print(content[:400], flush=True)
        return result

    client._post = spy

    architect.propose(
        agent,
        "Ung dung ghi nhat ky sinh nhat cua nguoi yeu: "
        "xem so ngay con lai, ghi nhat ky, xem lich su",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())