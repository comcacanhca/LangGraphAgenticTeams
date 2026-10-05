"""Đọc và kiểm tra agents.yaml — file cấu hình duy nhất của hệ thống.

Nguyên tắc: cấu hình sai phải FAIL LÚC BOOT, không phải lúc chạy.
Một hệ agent sai cấu hình mà chạy được thì tệ hơn hệ không chạy — nó tạo
ra project hỏng một cách âm thầm.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from agentic.encoding import force_utf8

# Ép UTF-8 ngay khi import: config.py in cảnh báo tiếng Việt, và nếu
# console là cp1252 thì việc in sẽ ném UnicodeEncodeError.
force_utf8()

# Thư mục gốc của hệ thống (nơi chứa agents.yaml)
ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = ROOT / "agents.yaml"


class ConfigError(RuntimeError):
    """Cấu hình sai. Ném lỗi này thay vì để hệ chạy tiếp với giá trị bừa."""


class Config:
    """Bọc agents.yaml, có kiểm tra tính nhất quán."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._raw = data
        self._validate()
        self.root = Path(self.project["workspace"])

    # ── load ──────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Đọc YAML từ đĩa. Không tự tạo file — thiếu là lỗi, im lặng mới đáng sợ."""
        cfg_path = path or CONFIG_FILE
        if not cfg_path.exists():
            raise ConfigError(f"Không thấy file cấu hình: {cfg_path}")

        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise ConfigError(f"{cfg_path.name} phải là YAML dạng mapping.")
        return cls(data)

    # ── validate ──────────────────────────────────────────────────────────
    def _validate(self) -> None:
        """Chạy tất cả kiểm tra trước khi hệ thống bắt đầu chạy."""
        required = [
            "project", "sandbox", "profiles", "active_profile", "model",
            "gpu", "scrum", "android", "cicd", "agents", "limits",
        ]
        missing = [k for k in required if k not in self._raw]
        if missing:
            raise ConfigError(f"Thiếu khoá bắt buộc: {', '.join(missing)}")

        self._check_profile()
        self._check_sandbox()
        self._check_scrum()
        self._check_android()
        self._check_agents()

    def _check_profile(self) -> None:
        """active_profile phải tồn tại — đây là chỗ hay sai nhất khi đổi model."""
        name = self._raw["active_profile"]
        profiles = self._raw["profiles"]
        if name not in profiles:
            raise ConfigError(
                f"active_profile='{name}' không có trong profiles. "
                f"Đang có: {', '.join(profiles)}"
            )
        p = profiles[name]
        for key in ("name", "num_ctx", "temperature"):
            if key not in p:
                raise ConfigError(f"profile '{name}' thiếu khoá '{key}'")

        # Cảnh báo sớm nếu profile cuối được bật mà Ollama chưa đủ mới.
        #
        # CHỈ áp dụng cho model CỤC BỘ. Model cloud chạy trên server của
        # Ollama nên phiên bản Ollama trên máy không liên quan — cảnh báo
        # "quá cũ cho Gemma 4" khi dùng gemma4:31b-cloud là sai hoàn toàn.
        if p["name"].startswith("gemma4") and not p["name"].endswith("-cloud"):
            self._warn_gemma4()

    @staticmethod
    def _warn_gemma4() -> None:
        """Gemma 4 cần Ollama >= 0.40. Bản cũ báo 'unknown model architecture'."""
        try:
            out = subprocess.run(
                ["ollama", "--version"], capture_output=True, text=True, timeout=10
            )
            ver = (out.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            print("[CẢNH BÁO] Không chạy được 'ollama --version'.")
            return

        try:
            minor = int(ver.split(".")[1])
        except (ValueError, IndexError):
            print(f"[CẢNH BÁO] Không đọc được phiên bản Ollama: {ver}")
            return

        if minor < 40:
            print(
                f"[CẢNH BÁO] Ollama {ver} quá cũ cho Gemma 4 (cần >= 0.40.0).\n"
                "           Chạy 'agentic doctor' để xem chi tiết."
            )

    def _check_sandbox(self) -> None:
        """Sandbox phải tồn tại và nằm trong hệ thống."""
        sb = self._raw["sandbox"]
        root = Path(sb["root"])
        if not root.exists():
            raise ConfigError(
                f"sandbox.root không tồn tại: {root}. Chạy 'agentic init' để tạo."
            )
        # Ràng buộc mạng: sandbox phải nằm trong hệ thống, tránh cấu hình
        # trỏ nhầm sang ổ khác rồi agent ghi bừa.
        if ROOT not in root.resolve().parents:
            raise ConfigError(
                f"sandbox.root phải nằm trong {ROOT}, đang là {root}"
            )

    def _check_scrum(self) -> None:
        """5 điều kiện Definition of Done là xương sống chống 'quên nhiệm vụ'."""
        require = self._raw["scrum"].get("require", {})
        conditions = [
            "build_passes",
            "test_exists_and_passes",
            "test_failed_before",
            "acceptance_criteria",
            "commit_message",
        ]
        for cond in conditions:
            if not require.get(cond):
                raise ConfigError(
                    f"scrum.require.{cond} phải bật. Đây là điều kiện "
                    "chống agent đóng sprint khi chưa xong việc."
                )

    def _check_android(self) -> None:
        """Kiểm tra toolchain có thực sự tồn tại trên máy."""
        android = self._raw["android"]
        java_home = Path(android["java_home"])
        if not (java_home / "bin" / "java.exe").exists():
            raise ConfigError(
                f"Không thấy java.exe tại {java_home}. "
                "Sửa android.java_home trong agents.yaml."
            )
        sdk = Path(android["sdk_dir"])
        if not sdk.exists():
            raise ConfigError(f"Không thấy Android SDK: {sdk}")

        # AGP và Gradle phải tương thích, nếu không sẽ fail lúc build.
        self._check_agp_gradle(android["agp"], android["gradle"])

    @staticmethod
    def _check_agp_gradle(agp: str, gradle: str) -> None:
        """AGP 8.5 cần Gradle >= 8.7; bộ đã chọn là 8.7.3 + 8.9."""
        try:
            agp_parts = tuple(int(x) for x in agp.split(".")[:2])
            gradle_parts = tuple(int(x) for x in gradle.split(".")[:2])
        except ValueError as exc:
            raise ConfigError(f"Không đọc được version: {exc}") from exc

        if agp_parts < (8, 5):
            raise ConfigError(f"AGP {agp} quá cũ, cần >= 8.5")
        if agp_parts[:2] == (8, 5) and gradle_parts < (8, 7):
            raise ConfigError(
                f"AGP {agp} không tương thích Gradle {gradle}. Cần Gradle >= 8.7."
            )

    def _check_agents(self) -> None:
        """Đủ 6 tác tử, và reporter phải tắt LLM."""
        agents = self._raw["agents"]
        expected = {"architect", "developer", "qa", "devops", "designer", "reporter"}
        missing = expected - set(agents)
        if missing:
            raise ConfigError(f"Thiếu tác tử: {', '.join(sorted(missing))}")

        # Reporter sinh HTML bằng Jinja2. Bật LLM thì model 7B ra HTML hỏng.
        if agents["reporter"].get("use_llm", True):
            raise ConfigError(
                "agents.reporter.use_llm phải là false. "
                "Reporter là code thuần Jinja2 để HTML luôn đẹp."
            )

    # ── truy cập thuộc tính ───────────────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    @property
    def project(self) -> dict[str, Any]:
        return self._raw["project"]

    @property
    def sandbox(self) -> dict[str, Any]:
        return self._raw["sandbox"]

    @property
    def scrum(self) -> dict[str, Any]:
        return self._raw["scrum"]

    @property
    def android(self) -> dict[str, Any]:
        return self._raw["android"]

    @property
    def cicd(self) -> dict[str, Any]:
        return self._raw["cicd"]

    @property
    def agents(self) -> dict[str, Any]:
        return self._raw["agents"]

    @property
    def limits(self) -> dict[str, Any]:
        return self._raw["limits"]

    @property
    def gpu(self) -> dict[str, Any]:
        return self._raw["gpu"]

    @property
    def llm(self) -> dict[str, Any]:
        return self._raw.get("llm", {})

    @property
    def memory(self) -> dict[str, Any]:
        return self._raw.get("memory", {})

    @property
    def report(self) -> dict[str, Any]:
        return self._raw.get("report", {})

    @property
    def model(self) -> dict[str, Any]:
        """Cấu hình model đã resolve theo active_profile."""
        profile_name = self._raw["active_profile"]
        base = dict(self._raw["model"])
        base.update(self._raw["profiles"][profile_name])
        base["profile"] = profile_name
        return base

    @property
    def thread_id(self) -> str:
        """thread_id cho checkpointer. Giữ nguyên để tiếp tục được phiên cũ."""
        return self.project["name"]

    def project_dir(self) -> Path:
        """Thư mục làm việc của project hiện tại."""
        return self.root / self.project["name"]


def get_config() -> Config:
    """Điểm vào duy nhất để lấy cấu hình."""
    return Config.load()

