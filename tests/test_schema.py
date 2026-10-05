"""Kiểm tra JSON contract — lớp bảo vệ quan trọng nhất khi dùng model 7B.

Tham chiếu thực tế đã thấy:
  - Model hay bọc JSON trong ```json ... ```
  - Model hay thêm lời dẫn "Đây là kết quả:" trước JSON
  - Model hay dùng dấu nháy đơn kiểu Python
  - Model hay thêm dấu phẩy thừa trước dấu ngoặc đóng

Các trường hợp đó đều phải được xử lý, nếu không hệ thống sẽ hỏng ở
lượt gọi đầu tiên.
"""

from __future__ import annotations

import json

import pytest

from agentic.llm.schema import (
    SchemaError,
    extract_json,
    parse_json,
    strip_fence,
    validate,
)


@pytest.fixture(scope="module")
def cfg():
    """Cấu hình thật — nguyên lý của dự án: agents.yaml là nguồn duy nhất."""
    from agentic.config import get_config

    return get_config()


class TestJsonExtraction:
    """Bóc JSON ra khỏi văn bảu lẫn lộn — lỗi phổ biến nhất."""

    def test_parses_clean_json(self) -> None:
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_strips_markdown_fence(self) -> None:
        raw = '```json\n{"a": 1}\n```'
        assert parse_json(raw) == {"a": 1}

    def test_strips_fence_without_language(self) -> None:
        assert parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_extracts_from_preamble(self) -> None:
        """Model thường thêm câu dẫn trước JSON."""
        raw = 'Đây là kết quả:\n{"a": 1}\nHết.'
        assert parse_json(raw) == {"a": 1}

    def test_extracts_from_trailing_prose(self) -> None:
        raw = '{"a": 1}\n\nLưu ý: đã kiểm tra rồi.'
        assert parse_json(raw) == {"a": 1}

    def test_handles_single_quotes(self) -> None:
        """Dấu nháy đơn kiểu Python — model 7B rất hay dùng."""
        assert parse_json("{'a': 1}") == {"a": 1}

    def test_handles_trailing_comma(self) -> None:
        assert parse_json('{"a": 1,}') == {"a": 1}

    def test_strip_fence_leaves_plain_text(self) -> None:
        assert strip_fence('không có fence') == 'không có fence'

    def test_extract_returns_empty_when_no_json(self) -> None:
        assert extract_json("không có JSON ở đây") == "không có JSON ở đây"

    def test_raises_on_garbage(self) -> None:
        with pytest.raises(SchemaError):
            parse_json("đây chỉ là văn xuôi, không có gì cả")


class TestArchitectContract:
    def test_accepts_valid(self) -> None:
        raw = """{
            "design": "Ung dung doc truyen bat tu, giao dien don gian dung Compose Material3",
            "decisions": [{"decision": "Dung Jetpack Compose", "reason": "Nhanh va gon"}]
        }"""
        data = validate("architect", raw)
        assert len(data["decisions"]) == 1

    def test_rejects_missing_key(self) -> None:
        with pytest.raises(SchemaError, match="thiếu khoá"):
            validate("architect", '{"design": "mot thiet ke du lai day du"}')

    def test_rejects_decision_without_reason(self) -> None:
        """Quyết định không kèm lý do thì vô nghĩa khi bạn đọc design.html."""
        raw = """
        {"design": "Mot thiet ke du lai day du o day",
         "decisions": [{"decision": "Dung Compose"}]}
        """
        with pytest.raises(SchemaError, match="reason"):
            validate("architect", raw)

    def test_rejects_too_many_decisions(self) -> None:
        raw = (
            '{"design": "Mot thiet ke du lai day du o day", "decisions": ['
            + ",".join(['{"decision":"d","reason":"r"}'] * 11)
            + "]}"
        )
        with pytest.raises(SchemaError, match="tối đa 10"):
            validate("architect", raw)


class TestDesignerContract:
    """Validator quan trọng nhất về mặt thẩm mỹ."""

    def test_accepts_valid_hex(self) -> None:
        raw = """
        {"palette": {"primary": "#F8A5C2", "background": "#FFF9F5"},
         "typography": {"body_size": 16}}
        """
        data = validate("designer", raw)
        assert data["palette"]["primary"] == "#F8A5C2"

    def test_accepts_short_hex(self) -> None:
        raw = '{"palette": {"primary": "#FFF"}, "typography": {}}'
        assert validate("designer", raw)["palette"]["primary"] == "#FFF"

    def test_rejects_prose_colour(self) -> None:
        """Model hay trả "pastel pink" thay vì hex."""
        raw = '{"palette": {"primary": "pastel pink"}, "typography": {}}'
        with pytest.raises(SchemaError, match="hex"):
            validate("designer", raw)

    def test_rejects_missing_hash(self) -> None:
        raw = '{"palette": {"primary": "F8A5C2"}, "typography": {}}'
        with pytest.raises(SchemaError, match="hex"):
            validate("designer", raw)

    def test_rejects_empty_palette(self) -> None:
        with pytest.raises(SchemaError, match="không rỗng"):
            validate("designer", '{"palette": {}, "typography": {}}')


class TestDeveloperContract:
    def test_accepts_valid(self) -> None:
        raw = """
        {"changed_files": [{"path": "app/Main.kt", "action": "create"}],
         "summary": "Tao file MainActivity co ban"}
        """
        assert len(validate("developer", raw)["changed_files"]) == 1

    def test_rejects_bad_action(self) -> None:
        raw = """
        {"changed_files": [{"path": "a.kt", "action": "rewrite"}],
         "summary": "s"}
        """
        with pytest.raises(SchemaError, match="action"):
            validate("developer", raw)

    def test_rejects_empty_summary(self) -> None:
        raw = '{"changed_files": [], "summary": "   "}'
        with pytest.raises(SchemaError, match="summary"):
            validate("developer", raw)


class TestQaContract:
    def test_accepts_pass(self) -> None:
        raw = '{"verdict": "PASS", "tests": ["testSave"], "defects": []}'
        assert validate("qa", raw)["verdict"] == "PASS"

    def test_rejects_invalid_verdict(self) -> None:
        raw = '{"verdict": "MAYBE", "tests": [], "defects": []}'
        with pytest.raises(SchemaError, match="verdict"):
            validate("qa", raw)

    def test_rejects_fail_without_defects(self) -> None:
        """FAIL mà không nêu lý do thì mâu thuẫn — hoặc bịa, hoặc quên."""
        raw = '{"verdict": "FAIL", "tests": [], "defects": []}'
        with pytest.raises(SchemaError, match="defects"):
            validate("qa", raw)

    def test_accepts_fail_with_defect(self) -> None:
        raw = """
        {"verdict": "FAIL", "tests": [],
         "defects": [{"file": "Main.kt", "why": "Sai kieu du lieu"}]}
        """
        assert validate("qa", raw)["verdict"] == "FAIL"


class TestCriticContract:
    def test_accepts_valid(self) -> None:
        raw = """
        {"concerns": [{"issue": "Compose state bi vo khi xoay man hinh",
                       "severity": "high"}]}
        """
        assert len(validate("critic", raw)["concerns"]) == 1

    def test_rejects_bad_severity(self) -> None:
        raw = '{"concerns": [{"issue": "x", "severity": "nghiem_trong"}]}'
        with pytest.raises(SchemaError, match="severity"):
            validate("critic", raw)

    def test_empty_concerns_gets_warning(self) -> None:
        """Không phản biện gì thì gắn cờ — với model 7B đây là dấu hiệu
        nó không thật sự đọc thiết kế."""
        data = validate("critic", '{"concerns": []}')
        assert "warning" in data

    def test_rejects_non_list(self) -> None:
        with pytest.raises(SchemaError, match="concerns"):
            validate("critic", '{"concerns": "khong co gi"}')


class TestNumPredict:
    """★ Không giới hạn token sinh ra là nguyên nhân chạy chậm khó đoán nhất.

    Đã gặp thật: không truyền num_predict thì model sinh tới khi đầy context,
    một node phản biện mất 5 phút, cả lần chạy 15 phút — mà không có lỗi nào
    được báo. Test ở đây để lỗi đó không quay lại.
    """

    def _client(self, num_ctx: int = 16384):
        from agentic.llm.client import LlmClient

        return LlmClient(
            base_url="http://x", model="m", num_ctx=num_ctx,
            temperature=0.3, top_p=0.9, keep_alive="30m",
            timeout_sec=300, max_retries=1,
        )

    def test_uses_agent_max_tokens(self) -> None:
        assert self._client()._num_predict(6000) == 6000

    def test_zero_falls_back_to_default(self) -> None:
        """reporter có max_tokens=0; 0 nghĩa là sinh vô hạn — phải chặn."""
        c = self._client()
        assert c._num_predict(0) == c.default_max_tokens

    def test_none_falls_back_to_default(self) -> None:
        c = self._client()
        assert c._num_predict(None) == c.default_max_tokens

    def test_caps_at_half_context(self) -> None:
        """Trần vượt context sẽ khiến prompt bị cắt cụt."""
        c = self._client(num_ctx=8192)
        assert c._num_predict(999999) == 4096

    def test_payload_contains_num_predict(self) -> None:
        """★ Kiểm tra ở MỨC PAYLOAD, không chỉ hàm trợ giúp.

        Hàm trợ giúp đúng mà payload không gọi tới thì vẫn hỏng — đó chính là
        trạng thái trước khi sửa.
        """
        client = self._client()
        captured: dict = {}
        client._invoke = lambda p: captured.update(p) or "ban bat ky"

        # validate_output=False vì chỉ quan tâm payload, không quan tâm
        # nội dung JSON — dùng contract nào cũng được.
        client.call_agent(
            agent="designer",
            system_prompt="s",
            user_prompt="u",
            validate_output=False,
            max_tokens=2500,
        )

        assert captured["options"]["num_predict"] == 2500

    def test_ask_passes_agent_max_tokens(self, cfg, monkeypatch) -> None:
        """★ max_tokens trong agents.yaml phải tới được payload."""
        from agentic.agents import architect
        from agentic.agents.base import build_agent

        agent = build_agent("architect", cfg)
        seen: dict = {}
        agent.client.call_agent = lambda **kw: seen.update(kw) or {}

        architect.propose(agent, "yeu cau", "mo ta")
        assert seen["max_tokens"] == cfg.agents["architect"]["max_tokens"]
    def test_rejects_unknown_agent(self) -> None:
        with pytest.raises(SchemaError, match="contract"):
            validate("may_ton_tai", "{}")

        with pytest.raises(SchemaError, match="không rỗng"):
            validate("designer", '{"palette": {}, "typography": {}}')


# ── Blueprint: hợp đồng cho sơ đồ Mermaid ───────────────────────────────


class TestBlueprintContract:
    """Sơ đồ Mermaid sai cú pháp thì trình duyệt hiện khối đỏ, không phải sơ đồ.

    Nên validator phải chặn lỗi rõ ràng TRƯỚC khi ghi ra file — kiểm lúc
    render thì bạn đã mở file rồi và không biết vì sao hỏng.
    """

    GOOD = {
        "overview": "A" * 150,
        "architecture_diagram": "graph TD\n  A[UI] --> B[VM]",
        "data_model": "erDiagram\n  NhatKy {\n    string id PK\n  }",
        "screens": [{"name": "Chính", "purpose": "p", "elements": ["nút"]}],
        "risks": [{"risk": "r", "impact": "cao", "mitigation": "m"}],
    }

    def test_accepts_valid(self) -> None:
        assert validate("blueprint", json.dumps(self.GOOD))

    def test_rejects_short_overview(self) -> None:
        """★ Chính là lỗi đã gặp: thiết kế 279 ký tự quá sơ sài.

        Validator phải chặn để bạn không duyệt nhầm một bản thiết kế rỗng.
        """
        bp = dict(self.GOOD, overview="Ngắn quá")
        with pytest.raises(SchemaError, match="100"):
            validate("blueprint", json.dumps(bp))

    def test_rejects_wrong_diagram_type(self) -> None:
        bp = dict(self.GOOD, architecture_diagram="sequenceDiagram\n  A->>B: x")
        with pytest.raises(SchemaError, match="graph TD"):
            validate("blueprint", json.dumps(bp))

    def test_rejects_empty_diagram(self) -> None:
        bp = dict(self.GOOD, data_model="")
        with pytest.raises(SchemaError, match="data_model"):
            validate("blueprint", json.dumps(bp))

    def test_rejects_screen_without_elements(self) -> None:
        """Thiếu `elements` thì mockup dựng được rỗng — vô nghĩa."""
        bp = dict(self.GOOD, screens=[{"name": "A", "purpose": "p", "elements": []}])
        with pytest.raises(SchemaError, match="elements"):
            validate("blueprint", json.dumps(bp))

    def test_rejects_screen_missing_key(self) -> None:
        """Báo thiếu khoá, không phải lỗi kiểu dữ liệu.

        Lỗi phải nói rõ thiếu khoá nào, vì model cần đọc thông báo này để
        tự sửa ở lượt thử lại.
        """
        bp = dict(self.GOOD, screens=[{"name": "A", "purpose": "p"}])
        with pytest.raises(SchemaError, match="screens\\[0\\]"):
            validate("blueprint", json.dumps(bp))

    def test_rejects_risk_missing_mitigation(self) -> None:
        """Rủi ro không có cách xử lý thì chỉ là than phiền, không phải thiết kế."""
        bp = dict(self.GOOD, risks=[{"risk": "r", "impact": "cao"}])
        with pytest.raises(SchemaError, match="mitigation"):
            validate("blueprint", json.dumps(bp))

    def test_screens_and_rrisks_optional(self) -> None:
        """Model không vẽ được màn hình thì vẫn dùng phần còn lại được."""
        bp = {k: v for k, v in self.GOOD.items() if k not in ("screens", "risks")}
        assert validate("blueprint", json.dumps(bp))

    def test_requires_core_three(self) -> None:
        bp = {"overview": "A" * 150}
        with pytest.raises(SchemaError):
            validate("blueprint", json.dumps(bp))


class TestCloudModel:
    """★ Model cloud chạy trên server nên khác model cục bộ ở vài điểm.

    Những khác biệt này không kiểm thử thì sẽ hỏng lúc chạy thật: kiểm tra
    VRAM sẽ chặn oan model 31B, và `ollama list` không thấy model cloud nên
    doctor báo FAIL dù mọi thứ vẫn chạy tốt.
    """

    def _client(self, model: str):
        from agentic.llm.client import LlmClient

        return LlmClient(
            base_url="http://x", model=model, num_ctx=16384,
            temperature=0.3, top_p=0.9, keep_alive="30m",
            timeout_sec=300, max_retries=1,
        )

    def test_detects_cloud_by_suffix(self) -> None:
        assert self._client("gemma4:31b-cloud").is_cloud is True

    def test_local_model_is_not_cloud(self) -> None:
        assert self._client("qwen2.5-coder:7b").is_cloud is False

    def test_cloud_skips_vram_check(self) -> None:
        """★ Điều quan trọng nhất.

        Model 31B ước lượng ~62GB, vượt xa 12GB của máy. Nếu vẫn kiểm tra
        VRAM thì mọi lượt gọi cloud đều bị chặn, dù máy hoàn toàn rảnh.
        """
        client = self._client("gemma4:31b-cloud")

        class Governor:
            @staticmethod
            def can_load(*_args, **_kwargs):
                raise AssertionError("khong duoc goi can_load cho model cloud")

        client.governor = Governor()
        # Chặn _post để không gọi mạng — mục tiêu là chứng minh _invoke
        # KHÔNG gọi can_load cho model cloud.
        client._post = lambda _payload: {"message": {"content": "x"}}

        assert client._invoke({"model": "gemma4:31b-cloud"}) == "x"

    def test_cloud_payload_omits_keep_alive(self) -> None:
        """keep_alive chỉ dành cho model giữ trong VRAM; cloud thì vô nghĩa."""
        client = self._client("gemma4:31b-cloud")
        seen: dict = {}
        client._invoke = lambda p: seen.update(p) or ""

        client.call_agent(
            agent="designer", system_prompt="s", user_prompt="u",
            validate_output=False, max_tokens=100,
        )
        assert "keep_alive" not in seen

    def test_local_payload_keeps_keep_alive(self) -> None:
        client = self._client("qwen2.5-coder:7b")
        seen: dict = {}
        client._invoke = lambda p: seen.update(p) or ""

        client.call_agent(
            agent="designer", system_prompt="s", user_prompt="u",
            validate_output=False, max_tokens=100,
        )
        assert seen["keep_alive"] == "30m"

    def test_cloud_profile_can_override_timeout(self, cfg) -> None:
        """Model lớn qua mạng cần chờ lâu hơn model 7B cục bộ."""
        import copy

        from agentic.config import Config
        from agentic.llm.client import LlmClient

        # Dựng Config riêng thay vì sửa cfg dùng chung: cfg là fixture
        # scope="module", sửa nó sẽ rò sang test khác.
        raw = copy.deepcopy(cfg._raw)
        raw["active_profile"] = "cloud"
        raw["profiles"]["cloud"]["timeout_sec"] = 900

        client = LlmClient.from_config(Config(raw))
        assert client.timeout_sec == 900
        assert client.is_cloud is True

    def test_cloud_profile_exists_in_config(self, cfg) -> None:
        """agents.yaml phải có sẵn profile cloud dùng được."""
        assert "cloud" in cfg._raw["profiles"]
        assert cfg._raw["profiles"]["cloud"]["name"].endswith("-cloud")

    def test_cloud_profile_needs_no_vram_estimate(self, cfg) -> None:
        """Khai vram_estimate_mb cho cloud là gây hiểu nhầm — không nên có."""
        assert "vram_estimate_mb" not in cfg._raw["profiles"]["cloud"]


class TestUnknownAgent:
    def test_rejects_unknown_agent(self) -> None:
        with pytest.raises(SchemaError, match="contract"):
            validate("may_ton_tai", "{}")

        with pytest.raises(SchemaError, match="không rỗng"):
            validate("designer", '{"palette": {}, "typography": {}}')
