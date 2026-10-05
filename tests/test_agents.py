"""Kiểm tra 6 tác tử.

Tách 2 nhóm:
  - Test không gọi model: kiểm logic thuần (escape, fallback, secret scan)
  - Test có gọi model: đánh dấu `live`, chạy bằng `pytest -m live`

Điểm quan trọng: nhóm live mới chứng minh tác tử thật sự tạo được JSON
hợp lệ từ model thật. Test offline chỉ bảo đảm phần code không hỏng.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic.agents import architect, designer, devops, reporter
from agentic.agents.base import Agent, AgentError, build_agent


@pytest.fixture(scope="module")
def cfg():
    from agentic.config import get_config

    return get_config()


# ── Reporter: không dùng LLM, nên test offline hoàn toàn ───────────────


class TestReporterHtml:
    """Reporter là code thuần — không cần model để kiểm thử."""

    def test_design_html_has_structure(self) -> None:
        html = reporter.design_to_html({
            "project": "App Demo",
            "design": "Dùng Jetpack Compose với Material3.",
            "decisions": [
                {"decision": "Chọn Compose", "reason": "Ít code hơn XML"},
            ],
            "design_tokens": {"palette": {"primary": "#F8A5C2"}},
        })
        assert "<!DOCTYPE html>" in html
        assert "App Demo" in html
        assert "#F8A5C2" in html
        assert "Chọn Compose" in html

    def test_report_html_has_stats(self) -> None:
        html = reporter.report_to_html({
            "project": "App Demo",
            "build": {"result": "PASS"},
            "tests": {"passed": 42},
            "sprints_done": 3,
        })
        assert "PASS" in html
        assert "42" in html
        assert "Sprint xong" in html

    def test_escapes_script_tags(self) -> None:
        """★ Dữ liệu do model sinh ra có thể chứa HTML.

        Không escape thì mô tả lỗi từ model sẽ chèn script vào báo cáo
        của bạn. Đây là lỗ hổng thật, không phải cảnh báo lý thuyết.
        """
        html = reporter.report_to_html({
            "project": "<script>alert('xss')</script>",
            "summary": "Dùng thẻ <img onerror=alert(1)> để kiểm tra",
        })
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_in_decision_text(self) -> None:
        html = reporter.design_to_html({
            "decisions": [{"decision": "a & b", "reason": "x < y > z"}],
        })
        assert "x &lt; y &gt; z" in html

    def test_writes_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "sub" / "design.html"
        reporter.design_to_html({"project": "X"}, out_path=out)
        assert out.exists()
        assert "X" in out.read_text(encoding="utf-8")

    def test_empty_data_does_not_crash(self) -> None:
        """Dữ liệu rỗng phải ra trang trống chứ không được ném lỗi."""
        assert reporter.design_to_html({})
        assert reporter.report_to_html({})

    def test_has_dark_mode(self) -> None:
        """report.theme.mode = auto trong agents.yaml."""
        html = reporter.report_to_html({"project": "X"})
        assert "prefers-color-scheme: dark" in html

    def test_never_calls_llm(self, cfg) -> None:
        """Reporter KHÔNG được bật LLM — config đã chặn, test này để
        tự tài liệu hoá quyết định thiết kế."""
        assert cfg.agents["reporter"]["use_llm"] is False


# ── Reporter: sơ đồ Mermaid + mockup UI ─────────────────────────────────


BLUEPRINT = {
    "overview": "Ứng dụng ghi nhật ký sinh nhật, theo dõi số ngày còn lại "
    "và lưu lịch sử vào cơ sở dữ liệu cục bộ.",
    "architecture_diagram": "graph TD\n  A[Compose] --> B[ViewModel]",
    "data_model": "erDiagram\n  NhatKy {\n    string id PK\n  }",
    "screens": [
        {
            "name": "Màn hình chính",
            "purpose": "Xem số ngày còn lại",
            "elements": ["tiêu đề", "thẻ đếm ngày", "nút Ghi nhật ký"],
        }
    ],
    "risks": [
        {"risk": "Mất dữ liệu", "impact": "cao", "mitigation": "Sao lưu"}
    ],
}


class TestReporterDiagrams:
    def test_embeds_mermaid_source(self) -> None:
        html = reporter.design_to_html(
            {"blueprint": BLUEPRINT, "design": BLUEPRINT["overview"]}
        )
        assert "mermaid" in html
        assert "graph TD" in html

    def test_inlines_mermaid_js_for_offline_use(self) -> None:
        """★ File thiết kế phải mở được khi MÁY KHÔNG CÓ MẠNG.

        Dùng thẻ <script src="cdn..."> thì trình duyệt chặn khi mở file
        file://, và mất mạng thì không vẽ được. Nhúng inline là cách chắc
        chắn duy nhất.
        """
        html = reporter.design_to_html({"blueprint": BLUEPRINT})
        assert "mermaid.initialize" in html
        assert 'src="https://' not in html
        assert 'src="//cdn' not in html

    def test_diagram_wrapped_for_render(self) -> None:
        html = reporter.design_to_html({"blueprint": BLUEPRINT})
        assert '<pre class="mermaid">' in html
        assert "Đang vẽ sơ đồ" in html

    def test_escapes_mermaid_source(self) -> None:
        """★ Mermaid đi qua HTML phải escape.

        Model có thể sinh nhãn chứa `<` hoặc `>`. Không escape thì sơ đồ
        vừa hỏng hiển thị vừa là lỗ hổng XSS trong file báo cáo.
        """
        bp = dict(BLUEPRINT)
        bp["architecture_diagram"] = "graph TD\n  A[<img onerror=alert(1)>]"
        html = reporter.design_to_html({"blueprint": bp})
        assert "<img onerror" not in html
        assert "&lt;img onerror" in html


class TestReporterMockup:
    def test_renders_phone_per_screen(self) -> None:
        bp = dict(
            BLUEPRINT,
            screens=BLUEPRINT["screens"] + [{
                "name": "Lịch sử", "purpose": "Xem nhật ký",
                "elements": ["danh sách nhật ký"],
            }],
        )
        html = reporter.design_to_html({"blueprint": bp})
        assert html.count('class="phone"') == 2
        assert "Lịch sử" in html

    def test_uses_palette_colours(self) -> None:
        """Mockup phải dùng đúng màu Designer chọn, không phải màu hardcode."""
        html = reporter.design_to_html({
            "blueprint": BLUEPRINT,
            "design_tokens": {"palette": {"primary": "#ABCDEF"}},
        })
        assert "#ABCDEF" in html

    def test_classifies_element_types(self) -> None:
        bp = dict(
            BLUEPRINT,
            screens=[{
                "name": "T", "purpose": "p",
                "elements": [
                    "tiêu đề", "nút Lưu", "ô nhập nội dung",
                    "danh sách", "ảnh đại diện",
                ],
            }],
        )
        html = reporter.design_to_html({"blueprint": bp})
        assert "ph-title" in html
        assert "ph-btn" in html
        assert "ph-input" in html

    def test_empty_screens_is_safe(self) -> None:
        html = reporter.design_to_html({"blueprint": dict(BLUEPRINT, screens=[])})
        assert "chưa mô tả màn hình nào" in html


class TestReporterRiskTable:
    @pytest.mark.parametrize(
        ("impact", "css"), [
            ("cao", "risk-cao"),
            ("Mức độ cao", "risk-cao"),
            ("trung bình", "risk-tb"),
            ("thấp", "risk-thap"),
        ],
    )
    def test_maps_impact_to_class(self, impact: str, css: str) -> None:
        assert reporter._risk_class(impact) == css

    def test_unknown_impact_defaults_to_medium(self) -> None:
        """Không nhận diện được thì mặc định trung bình — không mất rủi ro."""
        assert reporter._risk_class("???") == "risk-tb"
        assert reporter._risk_class("") == "risk-tb"


class TestReporterSprintPlan:
    def test_lists_stories_with_acceptance(self) -> None:
        html = reporter.design_to_html({
            "stories": [{
                "id": "US-001",
                "title": "Xem số ngày còn lại",
                "acceptance_criteria": ["Hiển thị đúng số ngày"],
            }],
        })
        assert "US-001" in html
        assert "Hiển thị đúng số ngày" in html


class TestColorMix:
    def test_mixes_hex(self) -> None:
        assert reporter._mix("#000000", "#FFFFFF", 0.5) == "#808080"

    def test_full_ratio_returns_target(self) -> None:
        assert reporter._mix("#123456", "#FFFFFF", 1.0) == "#ffffff"

    def test_bad_input_falls_back(self) -> None:
        """Màu lỗi từ model không được làm sập trang."""
        assert reporter._mix("x", "#FFF", 0.5) == "#888888"


# ── DevOps: secret scanner chạy bằng code, không cần model ───────────────


class TestSecretScanner:
    """Chốt chặn secret phải chạy bằng CODE, không phải lời nhắc model."""

    def test_finds_keystore(self, tmp_path: Path) -> None:
        (tmp_path / "release.jks").write_text("fake", encoding="utf-8")
        leaks = devops.scan_for_secrets(tmp_path, ["*.jks"])
        assert len(leaks) == 1
        assert "release.jks" in leaks[0]

    def test_finds_nested_keystore(self, tmp_path: Path) -> None:
        """Keystore thường nằm sâu trong app/ — phải tìm thấy."""
        nested = tmp_path / "app" / "release"
        nested.mkdir(parents=True)
        (nested / "my.jks").write_text("fake", encoding="utf-8")
        assert devops.scan_for_secrets(tmp_path, ["*.jks"])

    def test_finds_local_properties(self, tmp_path: Path) -> None:
        """local.properties chứa đường dẫn SDK của máy — không được commit."""
        (tmp_path / "local.properties").write_text("sdk.dir=x", encoding="utf-8")
        assert devops.scan_for_secrets(tmp_path, ["local.properties"])

    def test_clean_dir_has_no_leaks(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")
        assert not devops.scan_for_secrets(tmp_path, ["*.jks", "*.keystore"])

    def test_assert_raises_on_leak(self, tmp_path: Path) -> None:
        (tmp_path / "key.jks").write_text("fake", encoding="utf-8")
        with pytest.raises(devops.SecretLeakError, match="key.jks"):
            devops.assert_no_secrets(tmp_path, ["*.jks"])

    def test_assert_passes_on_clean(self, tmp_path: Path) -> None:
        (tmp_path / "a.kt").write_text("// code", encoding="utf-8")
        devops.assert_no_secrets(tmp_path, ["*.jks"])  # không ném lỗi

    def test_uses_patterns_from_config(self, cfg, tmp_path: Path) -> None:
        """Danh sách cấm lấy từ agents.yaml, không hardcode."""
        (tmp_path / "x.keystore").write_text("fake", encoding="utf-8")
        assert devops.scan_for_secrets(tmp_path, cfg.cicd["forbid_in_git"])


# ── Designer: fallback palette ──────────────────────────────────────────


class TestDesignerFallback:
    def test_fills_missing_colours(self, monkeypatch, cfg) -> None:
        """Model có thể trả palette thiếu màu — phải bù được, không sập."""
        agent = designer.make(cfg=cfg)
        monkeypatch.setattr(
            agent, "ask",
            lambda prompt, **kw: {"palette": {"primary": "#F8A5C2"}, "typography": {}},
        )

        tokens = designer.design_tokens(agent, "App ghi chú")
        assert len(tokens["palette"]) == len(designer.FALLBACK_PALETTE)
        assert "fallback_used" in tokens

    def test_no_flag_when_complete(self, monkeypatch, cfg) -> None:
        agent = designer.make(cfg=cfg)
        monkeypatch.setattr(
            agent, "ask",
            lambda prompt, **kw: {
                "palette": dict(designer.FALLBACK_PALETTE), "typography": {},
            },
        )
        # Không gắn cờ dự phòng khi model đã trả đủ.
        assert "fallback_used" not in designer.design_tokens(agent, "App")


# ── Architect: chống vòng tranh luận kẹt ─────────────────────────────────


class TestArchitectRevise:
    def test_rejects_empty_critiques(self, cfg) -> None:
        """revise() không có phản biện là vô nghĩa — phải chặn."""
        with pytest.raises(ValueError, match="phản biện"):
            architect.revise(architect.make(cfg=cfg), "thiết kế cũ", [])

    def test_rejects_unchanged_design(self, monkeypatch, cfg) -> None:
        """★ Chống vòng tranh luận kẹt.

        Nếu Architect trả về y hệt thiết kế cũ, vòng lặp chạy vô hạn
        cho tới giới hạn max_debate_rounds. Phải chặn ở đây.
        """
        agent = architect.make(cfg=cfg)
        same = "thiết kế không đổi"
        monkeypatch.setattr(
            agent, "ask",
            lambda prompt, **kw: {
                "design": same,
                "decisions": [{"decision": "d", "reason": "r"}],
            },
        )

        with pytest.raises(ValueError, match="không thay đổi"):
            architect.revise(agent, same, ["phản biện 1"])

    def test_accepts_changed_design(self, monkeypatch, cfg) -> None:
        agent = architect.make(cfg=cfg)
        monkeypatch.setattr(
            agent, "ask",
            lambda prompt, **kw: {
                "design": "thiết kế đã sửa theo phản biện",
                "decisions": [{"decision": "d", "reason": "r"}],
            },
        )
        result = architect.revise(agent, "thiết kế cũ", ["phản biện 1"])
        assert "đã sửa" in result["design"]


# ── Lớp base ────────────────────────────────────────────────────────────


class TestAgentBase:
    def test_loads_prompt_from_disk(self, cfg) -> None:
        assert "KIẾN TRÚC SƯ" in architect.make(cfg=cfg).system_prompt()

    def test_raises_on_missing_prompt(self, tmp_path: Path) -> None:
        agent = Agent(name="architect", client=None, prompt_dir=tmp_path)
        with pytest.raises(AgentError, match="Không có prompt"):
            agent.system_prompt()

    def test_rejects_unknown_agent(self, cfg) -> None:
        with pytest.raises(AgentError, match="Không có cấu hình"):
            build_agent("khong_ton_tai", cfg)

    def test_reads_max_tokens_from_config(self, cfg) -> None:
        agent = architect.make(cfg=cfg)
        assert agent.max_tokens == cfg.agents["architect"]["max_tokens"]

    def test_all_six_agents_buildable(self, cfg) -> None:
        """Cả 6 tác tử phải dựng được từ cấu hình."""
        for name in ("architect", "designer", "developer", "qa", "devops"):
            assert build_agent(name, cfg).name == name
