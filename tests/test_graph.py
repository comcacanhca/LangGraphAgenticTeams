"""Kiểm tra vòng tranh luận thiết kế — phần QUYẾT ĐỊNH hệ thống có chạy
vô hạn hay không.

converge_router là node quan trọng nhất của cả hệ agentic. Nếu nó quyết
định sai, toàn bộ vòng tranh luận trở nên vô nghĩa: hoặc chạy mãi không
dừng, hoặc dừng quá sớm.

Các test ở đây dùng state giả, KHÔNG gọi model — vì logic router thuần
tuý, không cần LLM để kiểm chứng.
"""

from __future__ import annotations

import pytest

from agentic.config import get_config
from agentic.graph.design_council import (
    BLOCKING_SEVERITIES,
    _severity_of,
    collect_critique,
    converge_router,
    designer_node,
    route_after_converge,
)
from agentic.state import TeamState


@pytest.fixture(scope="module")
def cfg():
    return get_config()


def crit(severity: str, issue: str = "vấn đề") -> dict:
    """Tạo phản biện đúng định dạng mà _flatten sinh ra."""
    return {"text": f"- [{severity}] {issue}", "agent": "qa"}


class TestSeverityExtraction:
    def test_reads_severity_from_text(self) -> None:
        assert _severity_of(crit("blocker")) == "blocker"

    def test_defaults_to_low_when_missing(self) -> None:
        """Không đọc được thì giả định nhẹ — không tự chặn vô ích."""
        assert _severity_of({"text": "không có nhãn"}) == "low"

    def test_takes_highest_of_many(self) -> None:
        text = "- [low] a\n- [blocker] b\n- [medium] c"
        assert _severity_of({"text": text}) == "blocker"

    def test_handles_empty(self) -> None:
        assert _severity_of({}) == "low"


class TestConvergeRouter:
    """★ Nguyên tắc: dừng khi hết vòng HOẶC hết phản biện nghiêm trọng."""

    def test_converges_when_no_critiques(self, cfg) -> None:
        """Không ai phản biện → hội tụ ngay, đừng lãng phí vòng."""
        out = converge_router(
            {"debate_round": 0, "pending_critiques": []}, cfg
        )
        assert out["_route"] == "converged"

    def test_converges_when_only_minor_critiques(self, cfg) -> None:
        """Phản biện nhẹ không chặn — nếu chặn thì không bao giờ hội tụ."""
        state = {
            "debate_round": 0,
            "pending_critiques": [crit("low"), crit("medium")],
        }
        assert converge_router(state, cfg)["_route"] == "converged"

    def test_loops_back_when_blocking_critique(self, cfg) -> None:
        """Còn vấn đề nghiêm trọng → Architect phải sửa."""
        state = {
            "debate_round": 0,
            "pending_critiques": [crit("high", "không build được")],
        }
        out = converge_router(state, cfg)
        assert out["_route"] == "architect"
        assert out["blocking_count"] == 1

    def test_escalates_after_max_rounds(self, cfg) -> None:
        """★ Chống chạy vô hạn.

        Dù còn phản biện nghiêm trọng, hết số vòng cho phép thì phải DỪNG
        và hỏi bạn. Đây là nguyên nhân phổ biến nhất khiến hệ multi-agent
        trở nên vô dụng.
        """
        max_rounds = cfg.scrum["max_debate_rounds"]
        state = {
            "debate_round": max_rounds,
            "pending_critiques": [crit("blocker")],
        }
        assert converge_router(state, cfg)["_route"] == "escalate"

    def test_counts_all_blocking(self, cfg) -> None:
        state = {
            "debate_round": 0,
            "pending_critiques": [crit("high"), crit("blocker"), crit("low")],
        }
        assert converge_router(state, cfg)["blocking_count"] == 2

    def test_blocking_set_excludes_minor(self) -> None:
        """Ngưỡng chặn không được nuốt cả phản biện nhẹ."""
        assert "low" not in BLOCKING_SEVERITIES
        assert "medium" not in BLOCKING_SEVERITIES
        assert "high" in BLOCKING_SEVERITIES
        assert "blocker" in BLOCKING_SEVERITIES


class TestRouteAfterConverge:
    def test_reads_stored_route(self) -> None:
        assert route_after_converge({"_route": "architect"}) == "architect"

    def test_defaults_to_converged(self) -> None:
        """Không có quyết định thì coi như hội tụ — an toàn hơn kẹt vòng."""
        assert route_after_converge({}) == "converged"


class TestCollectCritique:
    """Chỉ lấy phản biện của VÒNG HIỆN TẠI."""

    def test_collects_current_round_only(self) -> None:
        """Lấy cả lịch sử sẽ khiến Architect sửa đi sửa lại vấn đề cũ."""
        state: TeamState = {
            "debate_round": 1,
            "transcript": [
                {"round": 0, "agent": "qa", "text": "- [high] vấn đề cũ"},
                {"round": 1, "agent": "qa", "text": "- [high] vấn đề mới"},
            ],
        }
        out = collect_critique(state)
        assert len(out["pending_critiques"]) == 1
        assert "vấn đề mới" in out["pending_critiques"][0]["text"]

    def test_ignores_architect_entries(self) -> None:
        """Chỉ gom từ 3 tác tủ phản biện, không gom từ Architect/Designer."""
        state: TeamState = {
            "debate_round": 0,
            "transcript": [
                {"round": 0, "agent": "architect", "text": "thiết kế"},
                {"round": 0, "agent": "designer", "text": "màu"},
                {"round": 0, "agent": "qa", "text": "- [low] góp ý"},
            ],
        }
        out = collect_critique(state)
        assert len(out["pending_critiques"]) == 1

    def test_skips_empty_text(self) -> None:
        """Tác tủ nói không có vấn đề → text rỗng, không tính."""
        state: TeamState = {
            "debate_round": 0,
            "transcript": [{"round": 0, "agent": "qa", "text": ""}],
        }
        assert collect_critique(state)["pending_critiques"] == []
