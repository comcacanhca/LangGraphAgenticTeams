"""Lớp base cho 6 tác tử.

Tách lớp base ra vì 6 tác tử có 90% logic giống nhau: nạp prompt, gọi
model, kiểm contract. Phần khác biệt thật sự chỉ là:
  - tên tác tử (quyết định prompt + validator nào dùng)
  - hàm dựng câu hỏi (vì mỗi vai trò cần đầu vào khác nhau)

Nguyên tắc chung: tác tử KHÔNG tự quyết định mình thành công hay thất
bại. Nó gọi model, trả về JSON đã qua validator, và để tầng trên quyết
định. Lý do: tác tử tự kết luận thì lỗi lan xuống mọi phase sau.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic.llm.client import LlmClient
from agentic.llm.schema import SchemaError, validate


class AgentError(RuntimeError):
    """Tác tử không tạo được đầu ra hợp lệ."""


@dataclass
class Agent:
    """Một tác tử: nạp prompt, gọi model, trả JSON đã kiểm."""

    name: str
    client: LlmClient
    prompt_dir: Path
    max_tokens: int = 4000

    _system_cache: str | None = None

    def system_prompt(self) -> str:
        """Nội dung file prompt của tác tử.

        Cache lại vì prompt được dùng mỗi lượt gọi, mà đọc file là việc
        I/O không cần thiết.
        """
        if self._system_cache is not None:
            return self._system_cache

        path = self.prompt_dir / f"{self.name}.md"
        if not path.exists():
            raise AgentError(
                f"Không có prompt cho tác tử '{self.name}': {path}\n"
                "Thiếu file prompt là lỗi cấu hình, không phải lỗi model."
            )

        self._system_cache = path.read_text(encoding="utf-8")
        return self._system_cache

    def ask(
        self,
        user_prompt: str,
        *,
        validate_output: bool = True,
        contract: str | None = None,
    ) -> dict:
        """Gọi model và trả về JSON theo contract.

        contract cho phép gọi vai trò khác: ví dụ QA đóng vai CRITIC khi
        phản biện thiết kế, dùng schema `critic` (concerns + severity)
        thay vì schema `qa` (verdict + defects). Mặc định là schema ứng
        với tên tác tử.

        Ngưỡng: một lượt gọi là VÀO token, mô tả việc cần làm, còn model
        tự sinh phần còn lại (thiết kế, quyết định, phản biện). Nhờ vậy
        `max_tokens` dành cho output, đủ dùng.
        """
        # Nhắc lại yêu cầu trong system prompt phía cuối: model đọc
        # system trước, nên phần "chỉ trả JSON" ở cuối file prompt có
        # hiệu lực mạnh hơn.
        system = self.system_prompt()
        try:
            return self.client.call_agent(
                agent=contract or self.name,
                system_prompt=system,
                user_prompt=user_prompt,
                validate_output=validate_output,
            )
        except SchemaError as exc:
            raise AgentError(
                f"Tác tử '{self.name}'"
                + (f" (contract '{contract}')" if contract else "")
                + f": {exc}"
            ) from exc

    # ── tiện ích cho lớp con ───────────────────────────────────────────────

    def render(self, template: str, **values: Any) -> str:
        """Điền template đơn giản dùng {tên}.

        Cố tình KHÔNG dùng str.format trực tiếp trên prompt file: prompt
        chứa cả ngoặc nhọn JSON ví dụ ({...}) sẽ làm format ném KeyError.
        """
        out = template
        for key, value in values.items():
            out = out.replace("{" + key + "}", str(value))
        return out


def build_agent(name: str, cfg, client: LlmClient | None = None) -> Agent:
    """Dựng tác tử từ agents.yaml — nguồn sự thật duy nhất cho cấu hình."""
    from agentic.config import ROOT

    spec = cfg.agents.get(name)
    if spec is None:
        raise AgentError(
            f"Không có cấu hình cho tác tử '{name}' trong agents.yaml.\n"
            f"Đang có: {', '.join(sorted(cfg.agents))}"
        )

    return Agent(
        name=name,
        client=client or LlmClient.from_config(cfg),
        prompt_dir=ROOT / "prompts",
        max_tokens=spec.get("max_tokens", 4000),
    )
