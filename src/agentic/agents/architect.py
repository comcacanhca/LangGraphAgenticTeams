"""Kiến trúc sư: phân rã yêu cầu, đề xuất thiết kế, sửa thiết kế theo phản biện.

Đây là tác tử chịu trách nhiệm lớn nhất nên đòi hỏi cứng nhất:
  - thiết kế phải kèm quyết định, mỗi quyết định phải kèm lý do
  - câu trả lời phải hữu ích khi đưa cho bạn đọc trong design.html
  - phải SỬA ĐƯỢC thiết kế cũ, không chỉ đề xuất mới

Điểm thiết kế quan trọng: revise() nhận phản biện của 3 tác tử khác và
bắt buộc trả về thiết kế đã sửa. Không có đường tắt "giữ nguyên thiết kế"
— nếu vậy vòng tranh luận sẽ không bao giờ tiến triển.
"""

from __future__ import annotations

from typing import Any

from agentic.agents.base import Agent, build_agent

ROLE = "Kiến trúc sư trưởng"


def propose(agent: Agent, requirement: str, context: str = "") -> dict[str, Any]:
    """Đề xuất thiết kế ban đầu từ yêu cầu của bạn."""
    parts = [f"YÊU CẦU:\n{requirement}"]
    if context:
        parts.append(f"BỐI CẢNH:\n{context}")
    parts.append(
        "Hãy đề xuất thiết kế tổng thể cho ứng dụng Android này.\n"
        "Ghi rõ các quyết định kiến trúc kèm lý do cụ thể."
    )
    return agent.ask("\n\n".join(parts))


def revise(agent: Agent, design: str, critiques: list[str]) -> dict[str, Any]:
    """Sửa thiết kế dựa trên phản biện của các tác tử khác.

    critiques là danh sách chuỗi, mỗi phần tử mô tả một vấn đề kèm vai
    trò nêu ra. Yêu cầu bắt buộc model ĐỂ LÝ DO đã sửa gì trong `reason`
    của từng quyết định — đó là thứ bạn đọc được trong design.html.
    """
    if not critiques:
        raise ValueError(
            "revise() cần ít nhất một phản biện. "
            "Gọi revise() khi không có gì phản biện là vô nghĩa — "
            "hãy dùng propose() nếu thiết kế đã ổn."
        )

    listed = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(critiques))
    prompt = f"""THIẾT KẾ HIỆN TẠI:
{design}

PHẢN BIỆN NHẬN ĐƯỢC:
{listed}

Hãy viết lại thiết kế đã đáp ứng các phản biện trên.

Với mỗi quyết định bạn đưa ra, `reason` phải nói rõ đã xử lý phản biện
nào và bằng cách nào. Đây là thông tin người đọc bản thiết kế cần nhất.

Nếu có phản biện nào bạn không chấp nhận, ghi rõ lý do bác bỏ trong
`reason` — bỏ qua im lặng sẽ khiến vòng tranh luận lặp vô hạn."""

    result = agent.ask(prompt)

    # Bắt buộc thiết kế phải khác thiết kế cũ, nếu không vòng lặp kẹt.
    if result["design"].strip() == design.strip():
        raise ValueError(
            "Thiết kế không thay đổi sau khi nhận phản biện.\n"
            "Đây là dấu hiệu model không đọc kỹ. Cần thay đổi thật, "
            "kể cả khi chỉ là điều chỉnh nhỏ."
        )
    return result


def decompose(agent: Agent, requirement: str, design: str) -> dict[str, Any]:
    """Tách yêu cầu thành user story có tiêu chí nghiệm thu rõ ràng.

    Dùng contract `backlog`, KHÔNG phải `architect` — hàm này cần trả
    về danh sách stories, không phải design + decisions.

    Tiêu chí nghiệm thu phải CỤ THỂ và ĐO ĐƯỢC. "Giao diện đẹp" không
    kiểm được — đó chính là nơi hệ thống sau này sẽ hỏng.
    """
    prompt = f"""YÊU CẦU:
{requirement}

THIẾT KẾ ĐÃ THỐNG NHẤT:
{design}

Hãy tách yêu cầu thành các user story.

Mỗi tiêu chí nghiệm thu phải kiểm chứng được bằng test tự động.
Những tiêu chí sau đây KHÔNG dùng được:
  ✗ "giao diện đẹp, dễ thương"    → không đo được
  ✓ "nút có bo góc 24dp, màu #F8A5C2"  → đo được
  ✗ "phản hồi nhanh"
  ✓ "mở màn hình chính dưới 200ms"

Đây là mốc chặn "quên nhiệm vụ" của cả hệ thống, nên tiêu chí phải cụ thể.

Trả về JSON đúng cấu trúc sau, không thêm gì khác:
{{
  "stories": [
    {{
      "id": "US-001",
      "title": "tên user story ngắn gọn",
      "acceptance_criteria": [
        "AC1 cụ thể, kiểm chứng được",
        "AC2 cụ thể, kiểm chứng được"
      ]
    }}
  ]
}}"""

    return agent.ask(prompt, contract="backlog")


def blueprint_prompt(requirement: str, design: str) -> str:
    """Dựng prompt bản vẽ.

    Tách riêng khỏi blueprint() để công cụ chẩn đoán tái dùng đúng prompt
    này — nếu test prompt riêng thì không phát hiện được lệch phiên bản.
    """
    return f"""YÊU CẦU:
{requirement}

THIẾT KẾ ĐÃ THỐNG NHẤT:
{design}

Hãy vẽ bản thiết kế chi tiết cho ứng dụng này.

## 1. overview (bắt buộc ≥100 ký tự)
Giải thích đầy đủ: app làm gì, luồng người dùng chính ra sao, dữ liệu
lưu ở đâu, vì sao chọn kiến trúc đó. Đây là phần bạn đọc để hiểu hệ
thống — viết cho người không rành code.

## 2. architecture_diagram — Mermaid, BẮT ĐẦU bằng `graph TD`
Sơ đồ kiến trúc tầng: UI → ViewModel → Repository → DataSource.
Dùng cú pháp Mermaid `graph TD`. Ghi nhãn tiếng Việt có dấu trong ngoặc
vuông, ví dụ:

graph TD
  A[Màn hình chính Compose] --> B[ViewModel]
  B --> C[Repository]
  C --> D[(DataStore hoặc SQLite)]

## 3. data_model — Mermaid, BẮT ĐẦU bằng `erDiagram`
Cấu trúc dữ liệu. Ví dụ:

erDiagram
  NhatKy {{
    string id PK
    string noiDung
    date ngayTao
  }}

## 4. screens — danh sách màn hình
Mỗi màn hình: {{"name": ..., "purpose": ..., "elements": [...]}}
`elements` là danh sách phần tử hiển thị (nút, thẻ, danh sách, ô nhập…)
— đây là dữ liệu dùng dựng mockup UI, nên phải cụ thể.

## 5. risks — rủi ro kỹ thuật
Mỗi rủi ro: {{"risk": ..., "impact": "cao|trung bình|thấp", "mitigation": ...}}

LƯU Ý: dùng ```json ... ``` bao quanh JSON, không thêm chữ nào khác."""


def blueprint(agent: Agent, requirement: str, design: str) -> dict[str, Any]:
    """Sinh bản vẽ chi tiết: sơ đồ kiến trúc, mô hình dữ liệu, luồng màn hình.

    Đây là hàm SINH SƠ ĐỒ, dùng contract `blueprint`. Nó bổ sung cho
    propose() chứ không thay thế: propose cho quyết định và lý do,
    blueprint cho thứ nhìn thấy được.

    Vì sao dùng Mermaid chứ không vẽ ảnh:
      - LangGraph không tạo ảnh, và máy không đủ VRAM cho model ảnh
      - Model sinh code Mermaid đáng tin hơn sinh SVG thẳng
      - Mermaid là TEXT nên validate được trước khi render
      - mermaid.js đã bundle sẵn → mở file offline vẫn vẽ được
    """
    return agent.ask(blueprint_prompt(requirement, design), contract="blueprint")


def make(agent: Agent | None = None, cfg=None):
    """Dựng tác tử kiến trúc từ cấu hình."""
    if agent is not None:
        return agent
    from agentic.config import get_config

    return build_agent("architect", cfg or get_config())
