"""Thiết kế giao diện: xuất design token dạng JSON.

Tách riêng khỏi Architect vì ngôn ngữ khác hẳn: Architect nói về kiến
trúc và luồng dữ liệu, Designer nói về màu sắc và khoảng cách. Để chung
một tác tử sẽ khiến cả hai đều nông.

Điểm quan trọng: Designer KHÔNG mô tả bằng lời ("màu pastel dễ thương")
mà xuất giá trị máy đọc được (#F8A5C2). Lý do — Developer cần viết
`Color(0xFFF8A5C2)` trong Compose; mô tả bằng lời thì code không biên
dịch được. Ranh giới này do validator trong llm/schema.py bảo đảm.
"""

from __future__ import annotations

from typing import Any

from agentic.agents.base import Agent, build_agent

# Palette dự phòng khi model trả về màu sai. Dùng để sprint không bị
# chặn vì một lỗi hình thức — nhưng LUÔN ghi cờ để bạn biết đã dùng
# dự phòng, tránh tưởng là model tự thiết kế được.
FALLBACK_PALETTE = {
    "primary": "#F8A5C2",
    "secondary": "#B8E0D2",
    "background": "#FFF9F5",
    "surface": "#FFFFFF",
    "text": "#3D3A45",
    "accent": "#FFD166",
}


def design_tokens(
    agent: Agent,
    app_purpose: str,
    mood: str = "đơn giản, dễ thương",
    screens: list[str] | None = None,
) -> dict[str, Any]:
    """Xuất design token cho ứng dụng."""
    parts = [
        f"MỤC ĐÍCH ỨNG DỤNG:\n{app_purpose}",
        f"PHONG CÁCH:\n{mood}",
    ]
    if screens:
        parts.append("CÁC MÀN HÌNH CẦN THIẾT KẾ:\n- " + "\n- ".join(screens))

    parts.append(
        "Hãy xuất bộ design token cho ứng dụng này.\n\n"
        "NHỚ: mọi màu phải là mã hex 6 chữ số bắt đầu bằng dấu #.\n"
        "Palette phải có đủ 6 màu: primary, secondary, background, "
        "surface, text, accent.\n"
        "Bo góc lớn (16-28) tạo cảm giác mềm mại."
    )

    result = agent.ask("\n\n".join(parts))

    # Schema đã chặn màu sai định dạng. Nhưng thiếu màu thì vẫn có thể xảy
    # ra — bù bằng palette dự phòng và ghi cờ.
    palette = result.get("palette", {})
    missing = [k for k in FALLBACK_PALETTE if k not in palette]
    if missing:
        for key in missing:
            palette[key] = FALLBACK_PALETTE[key]
        result["palette"] = palette
        result["fallback_used"] = missing

    result.setdefault("typography", {"heading_size": 28, "body_size": 16})
    result.setdefault("spacing_unit", 8)
    result.setdefault("shape", {"corner_radius": 24, "button_style": "rounded"})
    return result


def revise_tokens(agent: Agent, tokens: dict[str, Any], feedback: str) -> dict[str, Any]:
    """Chỉnh lại token theo ý kiến của bạn ở GATE 1."""
    import json

    prompt = f"""TOKEN HIỆN TẠI:
{json.dumps(tokens, ensure_ascii=False, indent=2)}

Ý KIẾN CẦN SỬA:
{feedback}

Hãy xuất lại bộ design token đã sửa theo ý kiến trên.
Giữ nguyên những phần không bị yêu cầu thay đổi."""

    return agent.ask(prompt)


def make(agent: Agent | None = None, cfg=None):
    if agent is not None:
        return agent
    from agentic.config import get_config

    return build_agent("designer", cfg or get_config())
