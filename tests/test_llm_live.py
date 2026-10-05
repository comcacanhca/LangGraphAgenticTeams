"""Kiểm tra tầng LLM với model THẬT, không mock.

Vì sao cần test thật: mock thì không phát hiện được những lỗi model 7B
thực sự gây ra — trả JSON sai định dạng, quá thời gian, hoặc OOM.
GĐ1 chỉ xanh khi đo được độ tin cậy THẬT của model.

Các test này gọi Ollama nên chậm. Chạy: pytest tests/test_llm_live.py -v
Bỏ qua nếu Ollama không chạy: pytest -k "not live"
"""

from __future__ import annotations

import time

import pytest

from agentic.config import get_config
from agentic.llm.client import LlmClient, LlmError


@pytest.fixture(scope="module")
def client() -> LlmClient:
    cfg = get_config()
    return LlmClient.from_config(cfg)


@pytest.fixture(scope="module")
def prompt():
    """Nạp prompt file theo đường dẫn khai trong agents.yaml."""
    from pathlib import Path

    from agentic.config import ROOT

    def load(name: str) -> str:
        return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")

    return load


@pytest.fixture(scope="module")
def skip_without_ollama() -> None:
    """Bỏ qua thay vì fail nếu Ollama server chưa chạy."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5):
            return
    except OSError as exc:
        pytest.skip(f"Ollama server chưa chạy: {exc}")


@pytest.mark.live
class TestDesignerLive:
    """Designer là tác tử quan trọng nhất về mặt thẩm mỹ — màu sai
    hex thì code không biên dịch được."""

    def test_returns_valid_hex_palette(
        self, client: LlmClient, prompt, skip_without_ollama
    ) -> None:
        result = client.call_agent(
            "designer",
            prompt("designer"),
            "Thiết kế app xem truyện Bát Tự cho người Việt, "
            "giao diện đơn giản dễ thương, chủ đề màu hồng pastel.",
        )
        # validate() đã kiểm hex; kiểm lại lần nữa cho chắc.
        assert len(result["palette"]) >= 6
        for name, value in result["palette"].items():
            assert value.startswith("#"), f"{name}={value} thiếu dấu #"

    def test_palette_has_required_colors(
        self, client: LlmClient, prompt, skip_without_ollama
    ) -> None:
        result = client.call_agent(
            "designer",
            prompt("designer"),
            "Thiết kế app ghi chú đơn giản, nền sáng.",
        )
        for key in ("primary", "background", "text"):
            assert key in result["palette"], f"thiếu màu {key}"


@pytest.mark.live
class TestCriticLive:
    """Phản biện — nếu model luôn trả danh sách rỗng thì vòng tranh luận
    chỉ là hình thức."""

    def test_returns_critique(
        self, client: LlmClient, prompt, skip_without_ollama
    ) -> None:
        result = client.call_agent(
            "critic",
            prompt("critic").replace("{ROLE}", "Kỹ sư DevOps"),
            'Thiết kế: "Dữ liệu lá số lưu trong bộ nhớ của app, không cần '
            'database, không cần Internet."',
        )
        assert "concerns" in result

    def test_valid_severity_values(
        self, client: LlmClient, prompt, skip_without_ollama
    ) -> None:
        result = client.call_agent(
            "critic",
            prompt("critic").replace("{ROLE}", "Kỹ sư QA"),
            'Thiết kế: "Giao diện đơn giản, dễ thương, phản hồi nhanh."',
        )
        allowed = {"low", "medium", "high", "blocker"}
        for c in result["concerns"]:
            assert c["severity"] in allowed


@pytest.mark.live
class TestRetryBehaviour:
    """Retry là cơ chế bù cho việc model 7B hay trả JSON sai."""

    def test_connection_error_is_not_retried(self) -> None:
        """Lỗi kết nối thì thử lại cũng vô ích — phải ném ngay.

        Đây là hành vi quan trọng: nếu Ollama chết, hệ thống phải báo
        ngay thay vì mất 3 lần gọi × 300s timeout rồi mới báo.
        """
        cfg = get_config()
        bad = LlmClient.from_config(cfg)
        bad.base_url = "http://localhost:59999"  # cổng không có gì
        started = time.perf_counter()
        with pytest.raises(LlmError, match="Ollama"):
            bad.call_agent("qa", "prompt", "test")
        # Phải ném gần như tức thì, không phải sau khi hết retry.
        assert time.perf_counter() - started < 20

    def test_schema_error_raises_after_retries(
        self, client: LlmClient, skip_without_ollama
    ) -> None:
        """Hỏi architect một câu mà contract bắt buộc design ≥20 ký tự.

        Model có thể trả design quá ngắn — khi đó phải retry rồi ném
        SchemaError, không phải trả về kết quả sai cho các phase sau.
        """
        from agentic.llm.schema import SchemaError

        short_question = (
            'Trả về JSON với khoá "design" là chuỗi rỗng "" và '
            '"decisions" là mảng [{"decision": "a", "reason": "b"}].'
        )
        with pytest.raises(SchemaError, match="architect"):
            client.call_agent("architect", "Trả về JSON.", short_question)

    def test_raw_mode_skips_validation(
        self, client: LlmClient, skip_without_ollama
    ) -> None:
        """validate_output=False thì không kiểm contract, trả raw."""
        result = client.call_agent(
            "architect", "Trả JSON.", "Một mô tả dài...", validate_output=False
        )
        assert "raw" in result



@pytest.mark.live
class TestClientWiring:
    """Kiểm client dựng đúng từ agents.yaml."""

    def test_resolves_from_config(self, client: LlmClient) -> None:
        cfg = get_config()
        assert client.model == cfg.model["name"]
        assert client.num_ctx == cfg.model["num_ctx"]

    def test_serialize_enabled_by_default(self, client: LlmClient) -> None:
        """1 model trên 12GB thì bắt buộc serialize."""
        assert client.serialize is True

    def test_has_lock(self, client: LlmClient) -> None:
        assert hasattr(client, "_lock")
