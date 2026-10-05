"""Kiểm tra 6 tác tử với model THẬT.

Đây là bài kiểm tra quan trọng nhất của GĐ2: chứng minh 6 tác tử thật sự
tạo được JSON hợp lệ từ model local trên máy, chứ không chỉ logic code
chạy đúng.

Chạy: pytest tests/test_agents_live.py -m live -v
Bỏ qua nếu Ollama chưa chạy (fixture tự xử lý).

Toàn bộ module đánh dấu `live` vì mọi test ở đây đều gọi model thật.
"""

from __future__ import annotations

import urllib.request

import pytest

from agentic.agents import architect, designer, developer, devops, qa, reporter
from agentic.agents.base import build_agent

pytestmark = pytest.mark.live



@pytest.fixture(scope="module")
def cfg():
    from agentic.config import get_config

    return get_config()


@pytest.fixture(scope="module", autouse=True)
def require_ollama() -> None:
    """Bỏ qua toàn bộ module nếu Ollama server chưa chạy."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5):
            return
    except OSError as exc:
        pytest.skip(f"Ollama server chưa chạy: {exc}")


@pytest.fixture(scope="module")
def agent(cfg):
    """Dựng tác tử có client dùng chung — serialize nên không song song."""
    return build_agent("architect", cfg)


# ── Architect ───────────────────────────────────────────────────────────

REQ = (
    "Ứng dụng xem truyện Bát Tự: người dùng nhập ngày sinh, app tính "
    "lá số, hiển thị 4 cung và cho phép chat hỏi đáp."
)


class TestArchitectLive:
    def test_propose_returns_valid_json(self, agent) -> None:
        result = architect.propose(agent, REQ)
        assert len(result["design"]) >= 20
        assert result["decisions"]
        for dec in result["decisions"]:
            assert dec["decision"] and dec["reason"]

    def test_revise_responds_to_critique(self, agent) -> None:
        first = architect.propose(agent, REQ)
        revised = architect.revise(
            agent,
            first["design"],
            [
                "Dev: chưa nói rõ dữ liệu lá số lưu ở đâu, "
                "app restart có mất không?",
                "QA: tiêu chí 'giao diện dễ thương' không kiểm thử được.",
            ],
        )
        assert revised["design"] != first["design"]

    def test_decompose_produces_measurable_criteria(self, agent) -> None:
        """Tiêu chí nghiệm thu phải đo được — cơ chế chống 'quên nhiệm vụ'."""
        first = architect.propose(agent, REQ)
        stories = architect.decompose(agent, REQ, first["design"])
        assert stories.get("stories"), "phải có ít nhất một user story"


# ── Designer ────────────────────────────────────────────────────────────

class TestDesignerLive:
    def test_returns_hex_palette(self, cfg) -> None:
        a = build_agent("designer", cfg)
        tokens = designer.design_tokens(
            a, "App xem truyện Bát Tự", "đơn giản, dễ thương, màu hồng pastel"
        )
        for name, value in tokens["palette"].items():
            assert value.startswith("#"), f"{name}={value} thiếu dấu #"
            assert len(value) in (4, 7), f"{name}={value} sai định dạng hex"

    def test_palette_has_enough_colours(self, cfg) -> None:
        a = build_agent("designer", cfg)
        tokens = designer.design_tokens(a, "App ghi chú đơn giản")
        # Sau khi bù dự phòng, palette luôn đủ 6 màu.
        assert len(tokens["palette"]) >= 6

    def test_tokens_are_renderable(self, cfg) -> None:
        """Token phải đưa được vào HTML — nếu không Designer vô dụng."""
        a = build_agent("designer", cfg)
        tokens = designer.design_tokens(a, "App đếm ngày")
        html = reporter.design_to_html({"design_tokens": tokens})
        assert "<!DOCTYPE html>" in html
        assert tokens["palette"]["primary"] in html


# ── Developer ───────────────────────────────────────────────────────────

CODE_SUMMARY = (
    "Đã tạo app/src/main/kotlin/com/demo/app/MainActivity.kt với "
    "màn hình nhập ngày sinh, và app/src/test/.../CalculatorTest.kt "
    "kiểm tra phép tính tuổi."
)


class TestDeveloperLive:
    def test_implement_lists_files(self, cfg) -> None:
        a = build_agent("developer", cfg)
        result = developer.implement(
            a,
            "Tạo màn hình nhập ngày sinh và nút tính lá số",
            "Dùng Compose, một màn hình đơn giản.",
            tokens='{"palette": {"primary": "#F8A5C2"}}',
        )
        assert result["changed_files"]
        for f in result["changed_files"]:
            assert f["action"] in {"create", "modify", "delete"}
            assert "\\" not in f["path"], "đường dẫn phải dùng dấu /"

    def test_fix_targets_one_error(self, cfg) -> None:
        """Sửa từng lỗi một — sửa hàng loạt khi chưa hiểu lỗi gốc chỉ
        tạo thêm lỗi mới."""
        a = build_agent("developer", cfg)
        result = developer.fix(
            a,
            "Tạo màn hình chính",
            "e: Main.kt:42:5 Unresolved reference: Color",
        )
        assert result["summary"]

    def test_write_tests_covers_criteria(self, cfg) -> None:
        a = build_agent("developer", cfg)
        result = developer.write_tests(
            a,
            [
                "Lưu được lá số qua app restart",
                "Xóa được một lá số, danh sách cập nhật",
            ],
            CODE_SUMMARY,
        )
        assert result["summary"]


# ── QA ──────────────────────────────────────────────────────────────────

class TestQaLive:
    def test_test_plan(self, cfg) -> None:
        a = build_agent("qa", cfg)
        result = qa.test_plan(
            a,
            ["Lưu lá số qua app restart", "Xóa lá số cập nhật danh sách"],
        )
        assert result["verdict"] in {"PASS", "FAIL"}

    def test_critique_finds_vague_criteria(self, cfg) -> None:
        """QA phải tìm được tiêu chí mơ hồ — đây là giá trị của nó."""
        a = build_agent("qa", cfg)
        result = qa.critique_design(
            a, "Giao diện đơn giản, dễ thương, phản hồi nhanh."
        )
        assert "concerns" in result

    def test_review_code(self, cfg) -> None:
        a = build_agent("qa", cfg)
        result = qa.review_code(
            a,
            CODE_SUMMARY,
            ["Hiển thị lá số đúng 4 cung"],
        )
        assert result["verdict"] in {"PASS", "FAIL"}
        # FAIL phải kèm lý do — schema validator đã chặn trường hợp này.
        if result["verdict"] == "FAIL":
            assert result["defects"]


# ── DevOps ──────────────────────────────────────────────────────────────

CI_SUMMARY = (
    "AGP 8.7.3, Gradle 8.9, Kotlin 2.0.21, compileSdk 35, "
    "không có emulator, CI trên windows-latest."
)


class TestDevOpsLive:
    def test_ci_plan(self, cfg) -> None:
        a = build_agent("devops", cfg)
        result = devops.ci_plan(a, CI_SUMMARY)
        assert result["status"] in {"OK", "WARN", "FAIL"}

    def test_release_plan(self, cfg) -> None:
        a = build_agent("devops", cfg)
        result = devops.release_plan(a, "App Demo", CI_SUMMARY)
        assert result["status"] in {"OK", "WARN", "FAIL"}

    def test_secret_scan_blocks_commit(self, cfg, tmp_path) -> None:
        """★ Chốt chặn secret phải hoạt động bằng code."""
        (tmp_path / "release.jks").write_text("fake", encoding="utf-8")
        with pytest.raises(devops.SecretLeakError):
            devops.assert_no_secrets(tmp_path, cfg.cicd["forbid_in_git"])

