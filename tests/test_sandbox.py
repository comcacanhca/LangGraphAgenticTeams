"""Kiểm tra lớp bảo mật sandbox — chặn agent ghi ra ngoài workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic.sandbox import Sandbox, SandboxError


@pytest.fixture
def root() -> Path:
    """Thư mục gốc sandbox (dùng workspace thật nhưng chỉ ĐỌC cấu hình)."""
    return Path(__file__).resolve().parent.parent / "workspace"


@pytest.fixture
def sandbox(root: Path) -> Sandbox:
    return Sandbox(
        root=root,
        writable_extra=[root.parent / ".runtime"],
        forbid_outside=True,
    )


class TestWriteInsideRoot:
    """Ghi trong sandbox phải được phép."""

    def test_allows_file_in_root(self, sandbox: Sandbox) -> None:
        assert sandbox.resolve_write_path("main.kt") == sandbox.root / "main.kt"

    def test_allows_nested_path(self, sandbox: Sandbox) -> None:
        target = sandbox.resolve_write_path("src/ui/theme/Color.kt")
        assert target == sandbox.root / "src" / "ui" / "theme" / "Color.kt"

    def test_allows_project_subdir(self, sandbox: Sandbox) -> None:
        target = sandbox.resolve_write_path("batubot/app/build.gradle.kts")
        assert target == sandbox.root / "batubot" / "app" / "build.gradle.kts"


class TestWriteOutsideRoot:
    """Ghi ra ngoài sandbox phải bị chặn."""

    def test_rejects_parent_traversal(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path("../hack.txt")

    def test_rejects_deep_traversal(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path("src/../../../../Windows/System32/x.txt")

    def test_rejects_absolute_path_outside(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path("C:\\Windows\\System32\\config.sys")

    def test_rejects_sibling_directory(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path("../RAG_BatTu/serve_prompt_api.py")

    def test_rejects_shared_prefix_sibling(self, sandbox: Sandbox) -> None:
        """workspace-backup KHÁC workspace. So chuỗi tiền tố sẽ bị lỗi."""
        sibling = sandbox.root.parent / "workspace-backup"
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path(str(sibling / "file.txt"))


class TestReadOnlyPaths:
    """Project tham khảo: đọc được, ghi thì không."""

    def test_can_read_reference_project(self, sandbox: Sandbox) -> None:
        ref = Path(r"C:\Users\admin\StudioProjects\Chatbot")
        assert sandbox.resolve_read_path(ref) == ref

    def test_cannot_write_reference_project(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path(
                r"C:\Users\admin\StudioProjects\Chatbot\app\build.gradle.kts"
            )

    def test_cannot_write_rag_service(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path(r"D:\RAG_BatTu\serve_prompt_api.py")


class TestForbidOutsideDisabled:
    """Chế độ dev: cho phép ghi ngoài để tiện debug."""

    def test_disabled_allows_write(self, root: Path) -> None:
        sb = Sandbox(root=root, writable_extra=[], forbid_outside=False)
        assert sb.resolve_write_path("../outside.txt").name == "outside.txt"


class TestWritableExtra:
    """Ngoài root còn được ghi vào .runtime (log, checkpoint)."""

    def test_allows_runtime_path(self, sandbox: Sandbox) -> None:
        target = sandbox.resolve_write_path(
            str(sandbox.root.parent / ".runtime" / "logs" / "run.log")
        )
        assert target.name == "run.log"

    def test_still_rejects_other_paths(self, sandbox: Sandbox) -> None:
        with pytest.raises(SandboxError):
            sandbox.resolve_write_path(str(sandbox.root.parent / "random.txt"))
