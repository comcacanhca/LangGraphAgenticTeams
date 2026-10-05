"""Kiểm tra State — đặc biệt là ranh giới transcript.

★ Ranh giới quan trọng nhất của hệ này: transcript KHÔNG BAO GIỜ được đưa
vào context của tác tủ. Nếu vi phạm, mỗi lượt gọi sẽ mang theo toàn bộ
lịch sử tranh luận và hệ thống OOM ngay.

Có test riêng cho ranh giới này vì đó là thứ dễ phá nhất khi sửa code.
"""

from __future__ import annotations

from typing import get_type_hints

from agentic.state import DoneChecks, TeamState


class TestStateSeparation:
    def test_transcript_uses_appending_reducer(self) -> None:
        """Transcript phải có reducer operator.add.

        Nếu không có, mỗi node ghi sẽ GHI ĐÈ danh sách cũ và bạn mất
        toàn bộ lịch sử sau node thứ hai.
        """
        # File có `from __future__ import annotations` nên __annotations__
        # chỉ chứa ForwardRef — phải resolve mới thấy metadata của
        # Annotated. Đọc thẳng __annotations__ sẽ cho kết quả sai.
        hints = get_type_hints(TeamState, include_extras=True)
        assert getattr(hints["transcript"], "__metadata__", []), (
            "transcript phải dùng Annotated[..., operator.add]"
        )

    def test_state_fields_are_all_optional(self) -> None:
        """total=False để node chỉ trả phần mình đổi, không ghi đè khoá khác."""
        assert TeamState.__total__ is False

    def test_keeps_ground_truth_fields(self) -> None:
        """Các khoá sự thật từ máy phải tồn tại trong state.

        Đây là thứ phân biệt hệ này với hệ agent "tin LLM": biến build/test
        đến từ gradlew, không phải từ lời model.
        """
        for field in (
            "last_build_passed",
            "last_test_passed",
            "test_failed_before_fix",
        ):
            assert field in TeamState.__annotations__

    def test_has_convergence_counters(self) -> None:
        """Bộ đếm chống chạy vô hạn phải có trong state."""
        for field in ("debate_round", "sprint_count", "build_retries"):
            assert field in TeamState.__annotations__


class TestDoneChecks:
    """5 điều kiện Definition of Done — xương sống chống 'quên nhiệm vụ'."""

    def test_passes_when_all_true(self) -> None:
        checks = DoneChecks({
            "build_passes": True,
            "test_exists_and_passes": True,
            "test_failed_before": True,
            "acceptance_criteria": True,
            "commit_message": True,
        })
        assert checks.passed
        assert checks.missing == []

    def test_fails_when_any_missing(self) -> None:
        checks = DoneChecks({"build_passes": True, "acceptance_criteria": False})
        assert not checks.passed
        assert checks.missing == ["acceptance_criteria"]

    def test_empty_is_not_passed(self) -> None:
        """Rỗng KHÔNG phải đạt — tránh bug "chưa kiểm gì thì coi như xong"."""
        assert not DoneChecks().passed

    def test_explain_names_the_gap(self) -> None:
        """Thông báo phải nói rõ thiếu gì, không chỉ "chưa đạt"."""
        checks = DoneChecks({"build_passes": False, "commit_message": False})
        text = checks.explain()
        assert "build chưa xanh" in text
        assert "US-xxx" in text

    def test_explain_when_all_good(self) -> None:
        assert "Đủ" in DoneChecks({"build_passes": True}).explain()
