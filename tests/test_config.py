"""Kiểm tra agents.yaml và các validator của config.

GĐ0 chỉ xanh khi các validator này BẮT ĐƯỢC lỗi. Một validator không bắt
lỗi thì tệ hơn không có validator — nó tạo cảm giác an toàn giả.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from agentic.config import CONFIG_FILE, Config, ConfigError


@pytest.fixture
def raw() -> dict:
    """Cấu hình gốc, mỗi test một bản riêng để sửa không ảnh hưởng nhau."""
    with CONFIG_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class TestValidConfig:
    """Cấu hình hiện tại phải hợp lệ — nếu không thì mọi test khác vô nghĩa."""

    def test_loads_without_error(self, raw: dict) -> None:
        cfg = Config(copy.deepcopy(raw))
        assert cfg.project["name"] == "batubot"

    def test_resolves_active_profile(self, raw: dict) -> None:
        """model phải lấy từ active_profile, không đọc trực tiếp profiles."""
        cfg = Config(copy.deepcopy(raw))
        assert cfg.model["name"] == "qwen2.5-coder:7b"
        assert cfg.model["profile"] == raw["active_profile"]

    def test_has_all_six_agents(self, raw: dict) -> None:
        cfg = Config(copy.deepcopy(raw))
        assert set(cfg.agents) == {
            "architect", "developer", "qa", "devops", "designer", "reporter",
        }

    def test_reporter_does_not_use_llm(self, raw: dict) -> None:
        """Reporter là Jinja2 thuần — LLM sinh HTML sẽ hỏng."""
        cfg = Config(copy.deepcopy(raw))
        assert cfg.agents["reporter"]["use_llm"] is False


class TestProfileValidation:
    def test_rejects_unknown_active_profile(self, raw: dict) -> None:
        raw["active_profile"] = "khong_ton_tai"
        with pytest.raises(ConfigError, match="không có trong profiles"):
            Config(raw)

    def test_rejects_profile_missing_field(self, raw: dict) -> None:
        del raw["profiles"]["test"]["temperature"]
        with pytest.raises(ConfigError, match="thiếu khoá"):
            Config(raw)


class TestScrumValidation:
    """5 điều kiện Definition of Done — xương sống chống 'quên nhiệm vụ'."""

    @pytest.mark.parametrize(
        "condition",
        [
            "build_passes",
            "test_exists_and_passes",
            "test_failed_before",
            "acceptance_criteria",
            "commit_message",
        ],
    )
    def test_rejects_disabled_done_condition(
        self, raw: dict, condition: str
    ) -> None:
        raw["scrum"]["require"][condition] = False
        with pytest.raises(ConfigError, match=condition):
            Config(raw)


class TestAndroidValidation:
    def test_rejects_missing_java(self, raw: dict) -> None:
        raw["android"]["java_home"] = "C:\\Khong\\Ton\\Tai"
        with pytest.raises(ConfigError, match="java.exe"):
            Config(raw)

    def test_rejects_missing_sdk(self, raw: dict) -> None:
        raw["android"]["sdk_dir"] = "C:\\Khong\\Ton\\Tai"
        with pytest.raises(ConfigError, match="Android SDK"):
            Config(raw)

    def test_rejects_incompatible_agp_gradle(self, raw: dict) -> None:
        """AGP 8.5 không chạy được với Gradle 8.4."""
        raw["android"]["agp"] = "8.5.2"
        raw["android"]["gradle"] = "8.4"
        with pytest.raises(ConfigError, match="không tương thích"):
            Config(raw)

    def test_accepts_agp_85_with_gradle_89(self, raw: dict) -> None:
        """AGP 8.5.2 + Gradle 8.9 là tổ hợp hợp lệ."""
        raw["android"]["agp"] = "8.5.2"
        raw["android"]["gradle"] = "8.9"
        assert Config(raw).android["agp"] == "8.5.2"


class TestAgentValidation:
    def test_rejects_missing_agent(self, raw: dict) -> None:
        del raw["agents"]["designer"]
        with pytest.raises(ConfigError, match="Thiếu tác tử"):
            Config(raw)

    def test_rejects_reporter_with_llm(self, raw: dict) -> None:
        """Bật LLM cho reporter là sai — HTML do model sinh sẽ vỡ."""
        raw["agents"]["reporter"]["use_llm"] = True
        with pytest.raises(ConfigError, match="use_llm"):
            Config(raw)


class TestSandboxValidation:
    def test_rejects_missing_sandbox_root(self, raw: dict) -> None:
        raw["sandbox"]["root"] = "D:\\Khong\\Ton\\Tai"
        with pytest.raises(ConfigError, match="sandbox.root"):
            Config(raw)

    def test_rejects_sandbox_outside_system(self, raw: dict, tmp_path) -> None:
        """Sandbox trỏ ra ngoài hệ thống là vi phạm ràng buộc ghi."""
        raw["sandbox"]["root"] = str(tmp_path)
        with pytest.raises(ConfigError, match="phải nằm trong"):
            Config(raw)


class TestRequiredKeys:
    def test_rejects_missing_section(self, raw: dict) -> None:
        del raw["cicd"]
        with pytest.raises(ConfigError, match="Thiếu khoá bắt buộc"):
            Config(raw)

    def test_rejects_missing_file(self) -> None:
        with pytest.raises(ConfigError, match="Không thấy file cấu hình"):
            Config.load(Path("khong-ton-tai.yaml"))
