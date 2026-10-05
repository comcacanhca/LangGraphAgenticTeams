"""Kỹ sư phần mềm: viết và sửa code.

Tác tử này KHÔNG tự viết file — nó TRẢ VỀ JSON mô tả file cần sửa, và
tầng tool mới ghi. Lý do: tác tử không được tự ý chạm vào đĩa, mọi ghi
file đều phải đi qua sandbox.resolve_write_path().

Điều này cũng đảm bảo mọi thay đổi đều đi qua git và có thể xem lại.
"""

from __future__ import annotations

from typing import Any

from agentic.agents.base import Agent, build_agent


def implement(agent: Agent, task: str, design: str, tokens: str = "") -> dict:
    """Viết code cho một nhiệm vụ trong sprint."""
    parts = [
        f"NHIỆM VỤ:\n{task}",
        f"THIẾT KẾ:\n{design}",
    ]
    if tokens:
        parts.append(f"DESIGN TOKEN PHẢI DÙNG:\n{tokens}")

    parts.append(
        "Hãy viết code cho nhiệm vụ trên.\n\n"
        "QUY TẮC:\n"
        "- Báo cáo trung thực: chỉ liệt kê file bạn thật sự tạo/sửa\n"
        "- Đường dẫn tương đối với thư mục project, dùng dấu /\n"
        "- Jetpack Compose, Kotlin 2.0.21, Material3\n"
        "- Không sửa file ngoài thư mục project"
    )

    return agent.ask("\n\n".join(parts))


def fix(agent: Agent, task: str, errors: str, prior_attempt: str = "") -> dict:
    """Sửa lỗi biên dịch hoặc test thất bại.

    Rất quan trọng: chỉ yêu cầu sửa MỘT lỗi gốc mỗi lần. Sửa hàng loạt
    khi chưa hiểu lỗi gốc chỉ tạo thêm lỗi mới — đây là kỹ thuật sửa
    code hiệu quả nhất khi làm việc với model nhỏ.
    """
    parts = [f"NHIỆM VỤ ĐANG LÀM:\n{task}", f"LỖI:\n{errors}"]
    if prior_attempt:
        parts.append(f"BẠN ĐÃ THỬ SỬA:\n{prior_attempt}")

    parts.append(
        "Hãy xác định LỖI GỐC đầu tiên trong log trên và sửa riêng lỗi đó.\n\n"
        "Các lỗi phổ biến:\n"
        "- `Unresolved reference: X` → thiếu import, hoặc sai chính tả tên\n"
        "- `Expecting ...` → thiếu dấu phẩy, ngoặc, hoặc }\n"
        "- `Type mismatch` → kiểu dữ liệu không khớp khai báo\n"
        "- `Could not resolve X` → thiếu dependency trong build.gradle.kts\n\n"
        "CHỈ sửa một lỗi. Không sửa lan sang lỗi khác."
    )

    return agent.ask("\n\n".join(parts))


def write_tests(agent: Agent, acceptance_criteria: list[str], code_summary: str) -> dict:
    """Viết test cho một nhóm tiêu chí nghiệm thu.

    Đây là nửa quan trọng của cơ chế chống "quên nhiệm vụ": mỗi AC phải
    có test. Đưa danh sách AC vào prompt và yêu cầu model tự đánh dấu
    cái nào đã có test — dù model có tự đánh dấu đúng hay không thì
    tầng scrum cũng kiểm lại bằng đếm file thật.
    """
    listed = "\n".join(f"AC{i + 1}: {ac}" for i, ac in enumerate(acceptance_criteria))
    prompt = f"""TIÊU CHÍ NGHIỆM THU:
{listed}

CODE ĐÃ VIẾT:
{code_summary}

Hãy viết unit test cho các tiêu chí trên.

YÊU CẦU BẮT BUỘC:
- Mỗi AC phải có ít nhất một test bao phủ
- Test phải FAIL trước khi code được sửa (chứng minh test có tác dụng)
- Tên test mô tả hành vi, ví dụ testXoaLichSuCapNhatDanhSach
- Máy không có emulator: chỉ viết unit test thuần logic hoặc Robolectric
- Không viết Espresso hay instrumentation test

Trong `summary`, ghi rõ AC nào đã có test và AC nào chưa."""

    return agent.ask(prompt)


def make(agent: Agent | None = None, cfg=None):
    if agent is not None:
        return agent
    from agentic.config import get_config

    return build_agent("developer", cfg or get_config())
