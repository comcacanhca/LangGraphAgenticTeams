"""Ràng buộc sandbox: agent KHÔNG được ghi ra ngoài workspace.

Đây là lớp bảo mật quan trọng nhất của hệ thống. Ràng buộc được kiểm bằng
CODE chứ không phải bằng lời dặn trong prompt — vì LLM có thể bị
prompt-injection bảo ghi file tùy ý, và một lời dặn không đủ để chặn.

Mọi tool ghi file phải đi qua resolve_write_path() trước khi thực hiện.
"""

from __future__ import annotations

from pathlib import Path


class SandboxError(PermissionError):
    """Agent cố ghi ra ngoài vùng được phép."""


class Sandbox:
    """Giới hạn vùng ghi của agent.

    So sánh đường dẫn bằng path component (qua relative_to), KHÔNG dùng
    str.startswith(). Lý do: "workspace-backup" bắt đầu bằng chuỗi
    "workspace" nên so chuỗi sẽ cho rò vào thư mục bên cạnh.
    """

    def __init__(
        self,
        root: Path,
        writable_extra: list[Path] | None = None,
        forbid_outside: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        self.writable_extra = [Path(p).resolve() for p in (writable_extra or [])]
        self.forbid_outside = forbid_outside

    # ── kiểm tra ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_inside(candidate: Path, parent: Path) -> bool:
        """candidate nằm trong parent (bao gồm chính nó)?"""
        # relative_to() ném ValueError nếu không phải con — đây là cách
        # so sánh đúng theo path component, an toàn hơn startswith().
        try:
            candidate.relative_to(parent)
        except ValueError:
            return False
        return True

    def _is_allowed(self, resolved: Path) -> bool:
        if self._is_inside(resolved, self.root):
            return True
        return any(self._is_inside(resolved, p) for p in self.writable_extra)

    # ── ghi ───────────────────────────────────────────────────────────────

    def resolve_write_path(self, raw: str | Path) -> Path:
        """Đường dẫn tuyệt đối để ghi. Ném SandboxError nếu ra ngoài vùng.

        Luôn resolve() trước khi kiểm tra, để ".." và symlink bị chuẩn hoá.
        Nếu không, kiểm tra sẽ bị đánh lừa.
        """
        candidate = Path(raw)

        # Đường dẫn tương đối: nối vào root trước khi resolve.
        if not candidate.is_absolute():
            candidate = self.root / candidate

        resolved = candidate.resolve()

        if self._is_allowed(resolved):
            return resolved

        if not self.forbid_outside:
            # Chế độ dev: cho ghi để tiện debug, nhưng nói rõ là ngoài sandbox.
            print(f"[CẢNH BÁO] Ghi ngoài sandbox: {resolved}")
            return resolved

        allowed = ", ".join(str(p) for p in [self.root, *self.writable_extra])
        raise SandboxError(
            "Agent không được ghi ra ngoài sandbox.\n"
            f"  Đường dẫn: {resolved}\n"
            f"  Được ghi : {allowed}"
        )

    def write_file(self, raw: str | Path, content: str) -> Path:
        """Ghi file an toàn: kiểm tra trước, tạo thư mục cha sau."""
        target = self.resolve_write_path(raw)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    # ── đọc ───────────────────────────────────────────────────────────────

    def resolve_read_path(self, raw: str | Path) -> Path:
        """Chuẩn hoá đường dẫn để đọc. Không giới hạn — đọc là vô hại."""
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve()

    def read_file(self, raw: str | Path) -> str:
        """Đọc file. Cho phép đọc ngoài sandbox để tham khảo conventions."""
        return self.resolve_read_path(raw).read_text(encoding="utf-8")

    def list_files(self, raw: str | Path = ".") -> list[Path]:
        """Liệt kê file trong sandbox, bỏ qua thư mục build cho gọn."""
        base = self.resolve_read_path(raw)
        if not base.is_dir():
            return []

        skip = {".git", ".gradle", "build", "__pycache__", ".idea"}
        return [
            p for p in sorted(base.rglob("*"))
            if p.is_file() and not (skip & set(p.parts))
        ]
