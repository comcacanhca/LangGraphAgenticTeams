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

import pytest

from agentic.llm.schema import (
    SchemaError,
    extract_json,
    parse_json,
    strip_fence,
    validate,
)


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


class TestUnknownAgent:
    def test_rejects_unknown_agent(self) -> None:
        with pytest.raises(SchemaError, match="contract"):
            validate("may_ton_tai", "{}")

        with pytest.raises(SchemaError, match="không rỗng"):
            validate("designer", '{"palette": {}, "typography": {}}')
