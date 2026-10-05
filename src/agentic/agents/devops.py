"""Kỹ sư DevOps: đóng gói, CI/CD, và bảo mật.

Trách nhiệm nặng nhất về AN TOÀN. Keystore lọt vào git thì mất khoá app
vĩnh viễn — không thu hồi được, không có cách nào khắc phục ngoài việc
tạo app mới. Vì vậy secret_scanner ở đây là chốt chặn cứng, không phụ
thuộc vào việc model có "nhớ" hay không.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from agentic.agents.base import Agent, build_agent


class SecretLeakError(RuntimeError):
    """Phát hiện file bí mật sắp được commit — phải chặn tuyệt đối."""


def scan_for_secrets(root: Path, patterns: list[str]) -> list[str]:
    """Tìm file bí mật trong thư mục dự án.

    Chạy bằng CODE chứ không phải bằng lời nhắc model: LLM có thể bị
    prompt-injection bảo "bỏ qua kiểm tra này", còn code thì không.
    """
    leaks: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if any(fnmatch.fnmatch(name, pat) for pat in patterns):
            leaks.append(str(path.relative_to(root)))
    return leaks


def assert_no_secrets(root: Path, patterns: list[str]) -> None:
    """Ném lỗi nếu phát hiện file bí mật. Gọi trước mỗi lần commit."""
    leaks = scan_for_secrets(root, patterns)
    if leaks:
        raise SecretLeakError(
            "Phát hiện file bí mật trong thư mục dự án:\n"
            + "\n".join(f"  - {name}" for name in leaks)
            + "\n\nXoá hoặc thêm vào .gitignore trước khi commit.\n"
            "Keystore lọt vào git = mất khoá app vĩnh viễn."
        )


def ci_plan(agent: Agent, config_summary: str) -> dict:
    """Thiết kế pipeline CI/CD cho dự án."""
    prompt = f"""CẤU HÌNH DỰ ÁN:
{config_summary}

Hãy thiết kế pipeline CI/CD chạy trên GitHub Actions.

LƯU Ý QUAN TRỌNG:
- Runner là windows-latest (khớp máy dev) → lệnh Gradle là `gradlew.bat`
- Java 17 trên CI
- Chỉ cần xuất APK, KHÔNG publish lên Google Play
- CI chạy mỗi lần push
- Dự án có thể không có emulator → test bằng JVM unit test

Nêu rõ các bước cần chạy và rủi ro có thể gặp."""

    return agent.ask(prompt)


def release_plan(agent: Agent, project_name: str, config_summary: str) -> dict:
    """Lập kế hoạch đóng gói bản phát hành."""
    prompt = f"""DỰ ÁN: {project_name}

CẤU HÌNH:
{config_summary}

Hãy lập kế hoạch đóng gói bản phát hành (APK/AAB).

Ghi rõ các lệnh cần chạy, file sinh ra, và cách kiểm tra file đó hợp lệ.
Chỉ dừng ở APK — không cần Google Play."""

    return agent.ask(prompt)


def critique_design(agent: Agent, design: str) -> dict:
    """Phản biện thiết kế theo góc nhìn triển khai.

    Dùng contract `critic` (concerns + severity) — phản biện thiết kế
    không có khái niệm "verdict pass/fail", đó là của schema qa.
    """
    prompt = f"""THIẾT KẾ CẦN ĐÁNH GIÁ:
{design}

Hãy phản biện với vai trò kỹ sư DevOps. Tập trung vào:

1. Có gì hỏng khi build trên máy CI không? (dung lượng, phiên bản, cache)
2. Có cần emulator để kiểm thử không — và điều đó có khả thi không?
3. Bước nào trong quy trình này phụ thuộc vào thứ chưa có sẵn?
4. Có rủi ro rò rỉ secret nào không?

Nếu không có vấn đề nghiêm trọng, để concerns rỗng.

Trả về JSON dạng:
{{"concerns": [{{"issue": "mô tả vấn đề", "severity": "low|medium|high|blocker"}}]}}"""

    return agent.ask(prompt, contract="critic")


def make(agent: Agent | None = None, cfg=None):
    if agent is not None:
        return agent
    from agentic.config import get_config

    return build_agent("devops", cfg or get_config())
