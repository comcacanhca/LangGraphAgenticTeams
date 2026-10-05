"""Kỹ sư QA: viết test SONG SONG với Developer và phản biện thiết kế.

QA đóng hai vai:
  1. TESTER — viết unit test từ danh sách tiêu chí nghiệm thu, đọc CÙNG
     SPRINT.md với Developer. Đây là cách hai vai trò giữ đồng bộ.
  2. CRITIC — phản biện tính khả thi kiểm thử của thiết kế.

Điểm quan trọng: QA KHÔNG BAO GIỜ tự tuyên PASS nếu chưa chạy test.
verify() ở đây chỉ ghi kế hoạch và đánh giá rủi ro; nguồn sự thật là
`done_validator` ở tầng scrum chạy gradlew thật.
"""

from __future__ import annotations

from typing import Any

from agentic.agents.base import Agent, build_agent

# Mức độ nghiêm trọng QA dùng, khớp với validator trong llm/schema.py.
SEVERITIES = {"low", "medium", "high", "blocker"}


def test_plan(agent: Agent, acceptance_criteria: list[str], sprint_context: str = "") -> dict:
    """Lập kế hoạch test cho các tiêu chí nghiệm thu của sprint."""
    listed = "\n".join(f"AC{i + 1}: {ac}" for i, ac in enumerate(acceptance_criteria))
    parts = [
        f"TIÊU CHÍ NGHIỆM THU:\n{listed}",
    ]
    if sprint_context:
        parts.append(f"BỐI CẢNH SPRINT:\n{sprint_context}")

    parts.append(
        "Hãy lập kế hoạch kiểm thử cho các tiêu chí trên.\n"
        "Máy KHÔNG có emulator: chỉ dùng được unit test JVM và Robolectric.\n"
        "Nêu rõ trường hợp biên cần kiểm (danh sách rỗng, sai kiểu, "
        "quá nhiều phần tử)."
    )
    return agent.ask("\n\n".join(parts))


def critique_design(agent: Agent, design: str) -> dict:
    """Phản biện thiết kế theo góc nhìn kiểm thử.

    Dùng contract `critic` (concerns + severity), KHÔNG dùng contract
    `qa` — schema qa đòi verdict/tests/defects vốn dành cho duyệt test.
    Phản biện thiết kế thì không có "kết luận pass/fail".

    Giá trị nhất của QA trong vòng tranh luận: tìm những tiêu chí mơ hồ
    không kiểm chứng được. "Giao diện dễ thương" thì test bằng cách nào?
    Đó là loại vấn đề mà Architect thường bỏ sót.
    """
    prompt = f"""THIẾT KẾ CẦN ĐÁNH GIÁ:
{design}

Hãy phản biện với vai trò kỹ sư QA. Tập trung vào:

1. Tiêu chí nghiệm thu nào MƠ HỒ, không kiểm chứng tự động được?
2. Hành vi nào khó kiểm thử trên Compose mà không có emulator?
3. Trường hợp biên nào dễ bị tác giả quên?

Đừng phản biện cho có. Nếu thiết kế thực sự kiểm thử được, hãy nói
rõ và để concerns rỗng.

Trả về JSON dạng:
{{"concerns": [{{"issue": "mô tả vấn đề", "severity": "low|medium|high|blocker"}}]}}"""

    return agent.ask(prompt, contract="critic")


def review_code(agent: Agent, code_snippets: str, acceptance_criteria: list[str]) -> dict:
    """Review code Developer vừa viết."""
    listed = "\n".join(f"AC{i + 1}: {ac}" for i, ac in enumerate(acceptance_criteria))
    prompt = f"""TIÊU CHÍ NGHIỆM THU:
{listed}

CODE CẦN REVIEW:
{code_snippets}

Hãy review code trên.

Tập trung vào:
- Lỗi logic (sai điều kiện, thiếu nhánh, xử lý sai biên)
- AC nào CHƯA được code đáp ứng
- Test nào còn thiếu

Nếu code đúng và đủ, trả verdict = PASS.
Nếu có lỗi, trả verdict = FAIL và liệt kê defect cụ thể."""

    return agent.ask(prompt)


def make(agent: Agent | None = None, cfg=None):
    if agent is not None:
        return agent
    from agentic.config import get_config

    return build_agent("qa", cfg or get_config())
