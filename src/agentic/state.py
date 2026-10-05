"""Trạng thái chia sẻ của hệ agentic.

★ QUY TẮC VÀNG của thiết kế này: TÁCH STATE KHỎI TRANSCRIPT.

State (thiết kế, sprint, defects) là thứ TÁC TỦ CẦN THẤY — nó được
đưa vào context mỗi lượt gọi.

Transcript (lịch sử tranh luận đầy đủ) là thứ CHỈ ĐỂ BẠN ĐỌC — nó
KHÔNG BAO GIỜ được đưa vào context.

Nếu vi phạm:
    4 tác tử × 3 vòng × 4.500 token × 3 lần lặp ≈ 160.000 token
    → vượt xa context 16K, OOM chắc chắn, hệ thống không chạy được.

Chỉ truyền state cô đọng:
    mỗi lượt ≈ 2.000-8.000 token → chạy được trên model 7B local.

Đây là lý do hệ thống khả thi với model nhỏ. Không phải tối ưu — mà là
điều kiện để tồn tại.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.managed import RemainingSteps


class TeamState(TypedDict, total=False):
    """State của toàn bộ hệ thống.

    total=False để node chỉ cần trả về phần mình thay đổi, không phải
    copy toàn bộ state ra — giảm rủi ro vô tình ghi đè nhầm khoá khác.
    """

    # ── Đầu vào của con người ───────────────────────────────────────────
    requirement: str
    """Yêu cầu gốc của bạn, không đổi trong suốt quá trình."""

    # ── State cô đọng — TÁC TỦ THẤY ────────────────────────────────────
    design: dict[str, Any]
    """Thiết kế hiện tại: {design, decisions[], tokens, round}.

    Đây là "bản chốt hiện tại", KHÔNG phải lịch sử. Mỗi tác tủ nhận đúng
    phần này để phản biện hoặc sửa.
    """

    stories: list[dict[str, Any]]
    """User story đã phân rã, kèm acceptance_criteria có thể kiểm thử."""

    sprint: dict[str, Any]
    """Sprint hiện tại: {story_id, acceptance_criteria[], retry, done}."""

    defects: list[dict[str, Any]]
    """Lỗi QA phát hiện, chưa xử lý. Developer đọc danh sách này."""

    lessons: list[str]
    """Bài học từ retrospective. Đọc TRƯỚC mỗi sprint để không lặp lỗi."""

    done_stories: list[str]
    """US đã hoàn thành. Nguồn sự thật cho việc còn US nào hay không."""

    # ── Sự thật từ MÁY — không phải lời LLM ────────────────────────────
    last_build_passed: bool
    """Kết quả ./gradlew assembleDebug. KHÔNG BAO GIỜ do agent tự đặt.

    Đây là điều phân biệt hệ thống này với hệ agent "tin LLM": khi build
    fail, mũi tên quay lại luôn dựa trên biến này, không phụ thuộc model
    có "nhận ra" hay không.
    """

    last_test_passed: bool
    """Kết quả ./gradlew testDebugUnitTest."""

    test_failed_before_fix: bool
    """Test phải FAIL trước khi PASS — chứng minh test có tác dụng.

    Nếu test xanh ngay khi vừa viết thì nó không kiểm tra gì cả. Đây là
    1 trong 5 điều kiện Definition of Done trong scrum.require.
    """

    # ── Bộ đếm — chống chạy vô hạn ─────────────────────────────────────
    debate_round: int
    """Vòng tranh luận hiện tại. Hết max_debate_rounds thì escalate hỏi bạn."""

    sprint_count: int
    """Số sprint đã chạy. Hết max_sprints thì dừng."""

    build_retries: int
    """Số lần đã thử sửa build trong sprint hiện tại."""

    # ── State nội bộ của vòng tranh luận ────────────────────────────────
    pending_critiques: list[dict[str, Any]]
    """Phản biện của VÒNG HIỌN TẠI, chờ Architect xử lý.

    Tách khỏi transcript vì đây là thứ tác tủ CẦN THẤY — nó được đưa vào
    prompt của Architect. Transcript chỉ để bạn đọc.
    """

    _route: str
    """Quyết định của converge_router, dùng để rẽ nhánh trong graph.

    Tên có gạch dưới để đánh dấu "nội bộ", không phải dữ liệu nghiệp vụ.
    """

    blocking_count: int
    """Số phản biện mức high/blocker ở vòng hiện tại — để bạn thấy vì sao
    hệ thống còn phải sửa thêm."""

    remaining_steps: RemainingSteps
    """Bộ đếm của LangGraph: số super-step còn lại trước khi chạm trần.

    Đặc biệt quan trọng khi có vòng lặp: nếu node sập (lỗi code, lỗi
    model) thì state KHÔNG được ghi, các bộ đếm không tăng, và LangGraph
    retry — dẫn tới lặp vô hạn. Đọc khoá này trước khi gọi model cho
    phép dừng có kiểm soát thay vì treo.
    """

    # ── Lịch sử — BẠN ĐỌC, TÁC TỦ KHÔNG THẤY ─────────────────────────
    transcript: Annotated[list[dict[str, Any]], operator.add]
    """Toàn bộ lượt gọi tác tử, để bạn đọc lại và đưa vào design.html.

    Ghi bằng reducer `operator.add` để mỗi node chỉ viết phần mình thêm,
    không phải đọc-ghi cả danh sách.

    ⛔ TUYỆT ĐỐI KHÔNG đưa trường này vào prompt của tác tủ. Nếu vi phạm,
       context nổ tung ngay lập tức. Prompt builder ở graph/ chịu trách
       nhiệm giữ ràng buộc này.
    """

    # ── Kết quả cuối ──────────────────────────────────────────────────
    artifacts: list[dict[str, Any]]
    """File sinh ra: APK, báo cáo, workflow CI."""

    gate1_result: dict[str, Any] | None
    """Quyết định của bạn ở GATE 1 (duyệt thiết kế)."""

    gate2_result: dict[str, Any] | None
    """Quyết định của bạn ở GATE 2 (duyệt phát hành)."""


# ── Trừu tượng hoá để tác tủ không đụng State ─────────────────────────────


class DoneChecks(dict):
    """Kết quả kiểm tra Definition of Done.

    Là dict để serialize được vào checkpoint và đưa vào JSON report,
    nhưng có phương thức đọc rõ ràng để node không phải nhớ key.
    """

    @property
    def passed(self) -> bool:
        return all(self.values()) if self else False

    @property
    def missing(self) -> list[str]:
        return [k for k, v in self.items() if not v]

    def explain(self) -> str:
        """Mô tả điều kiện nào chưa đạt, để bạn hiểu vì sao sprint bị kẹt."""
        miss = self.missing
        if not miss:
            return "Đủ cả 5 điều kiện."
        labels = {
            "build_passes": "build chưa xanh",
            "test_exists_and_passes": "thiếu test hoặc test chưa xanh",
            "test_failed_before": "test chưa từng fail (có thể test rỗng)",
            "acceptance_criteria": "còn tiêu chí nghiệm thu chưa có test",
            "commit_message": "commit message thiếu mã US-xxx",
        }
        lines = [f"  ✗ {labels.get(k, k)}" for k in miss]
        return "Chưa đạt:\n" + "\n".join(lines)
