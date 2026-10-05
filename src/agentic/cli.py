"""CLI của hệ agentic.

GĐ0 chỉ có `doctor` — kiểm tra môi trường trước khi làm bất cứ việc gì.
Sau này thêm: run, resume, approve, gate, init.

Điểm mấu chốt: doctor phải BÁO CẢ lỗi chứ không sụp. Một lệnh chẩn đoán
vấp ngã thì bạn không biết chính hệ thống hỏng hay môi trường hỏng.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from agentic.config import ROOT, ConfigError, get_config

OK = "[ OK ]"
BAD = "[FAIL]"
WARN = "[WARN]"


def _force_utf8() -> None:
    """Ép stdout/stderr dùng UTF-8.

    Console Windows mặc định dùng cp1252, không có ký tự tiếng Việt có
    dấu. Không ép thì mọi thông báo tiếng Việt đều ném UnicodeEncodeError
    và CLI sập trước khi kịp kiểm tra gì.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Console cũ không hỗ trợ — bỏ qua, in ASCII phần nào được.
            pass


_force_utf8()


class Report:
    """Gom kết quả kiểm tra, in ra cuối cùng."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures = 0
        self.warnings = 0

    def ok(self, msg: str) -> None:
        self.lines.append(f"{OK} {msg}")

    def fail(self, msg: str) -> None:
        self.lines.append(f"{BAD} {msg}")
        self.failures += 1

    def warn(self, msg: str) -> None:
        self.lines.append(f"{WARN} {msg}")
        self.warnings += 1

    def print(self) -> None:
        print()
        print("\n".join(self.lines))
        if self.failures or self.warnings:
            print(f"\n{self.failures} lỗi, {self.warnings} cảnh báo.")
        else:
            print("\nTất cả đều ổn.")


def check_python(r: Report) -> None:
    v = sys.version_info
    if v >= (3, 11):
        r.ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        r.fail(f"Cần Python >= 3.11, đang có {v.major}.{v.minor}")


def check_disk(r: Report) -> None:
    """Ổ C: chỉ còn ~19GB nên cần biết trước khi Gradle làm đầy ổ."""
    try:
        free_gb = shutil.disk_usage(ROOT).free / 1e9
        if free_gb < 10:
            r.fail(f"Ổ đĩa chỉ còn {free_gb:.1f}GB — Gradle sẽ hỏng")
        elif free_gb < 30:
            r.warn(f"Ổ đĩa còn {free_gb:.1f}GB")
        else:
            r.ok(f"Ổ đĩa còn {free_gb:.1f}GB")
    except OSError as exc:
        r.warn(f"Không đọc được dung lượng ổ đĩa: {exc}")


def check_ollama(r: Report) -> None:
    """Ollama phải CÀI và SERVER phải CHẠY. Hai chuyện khác nhau."""
    exe = shutil.which("ollama")
    if not exe:
        r.fail("Không tìm thấy 'ollama'. Cài tại https://ollama.com")
        return

    try:
        out = subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, timeout=10
        )
        r.ok(out.stdout.strip() or "Ollama đã cài")
    except (OSError, subprocess.SubprocessError) as exc:
        r.fail(f"Không chạy được 'ollama --version': {exc}")
        return

    # Server có chạy không? Kiểm tra bằng cách liệt kê model.
    try:
        subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=15, check=True
        )
    except subprocess.CalledProcessError:
        r.fail("Ollama server chưa chạy. Mở app Ollama hoặc chạy: ollama serve")
        return
    except (OSError, subprocess.SubprocessError) as exc:
        r.fail(f"Không gọi được Ollama server: {exc}")
        return
    r.ok("Ollama server đang chạy")


def check_model(cfg, r: Report) -> None:
    """Model trong active_profile phải có sẵn trên máy."""
    name = cfg.model["name"]
    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        r.fail(f"Không kiểm tra được model '{name}' (Ollama chưa chạy)")
        return

    if name.split(":")[0].lower() in out.stdout.lower():
        r.ok(f"Model '{name}' đã cài")
    else:
        r.fail(f"Model '{name}' chưa có. Cài bằng: ollama pull {name}")


def check_java(cfg, r: Report) -> None:
    java = Path(cfg.android["java_home"]) / "bin" / "java.exe"
    if not java.exists():
        r.fail(f"Không thấy java.exe tại {java}")
        return
    try:
        out = subprocess.run(
            [str(java), "-version"], capture_output=True, text=True, timeout=20
        )
        ver = (out.stderr or out.stdout).splitlines()[0].strip()
        r.ok(f"JDK: {ver}")
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        r.fail(f"Không chạy được java: {exc}")


def check_sdk(cfg, r: Report) -> None:
    """compileSdk phải có sẵn — máy không có cmdline-tools nên không
    tự cài thêm được."""
    sdk = Path(cfg.android["sdk_dir"])
    if not sdk.exists():
        r.fail(f"Không thấy Android SDK: {sdk}")
        return

    platforms = sdk / "platforms"
    if not platforms.is_dir():
        r.fail(f"Thiếu thư mục platforms trong {sdk}")
        return

    want = f"android-{cfg.android['compile_sdk']}"
    found = [p.name for p in platforms.iterdir() if p.is_dir()]
    if want in found:
        r.ok(f"{want} có sẵn (compileSdk)")
    else:
        r.fail(
            f"Thiếu {want}. Máy có: {', '.join(sorted(found)) or 'không có gì'}.\n"
            "         Không có cmdline-tools nên không cài tự động được."
        )


def check_gradle_cache(cfg, r: Report) -> None:
    """Gradle user home phải nằm ở ổ D: — ổ C: chỉ còn ~19GB."""
    guh = Path(cfg.android["gradle_user_home"])

    if guh.drive.upper() == "C:":
        r.fail(
            f"Gradle cache đang ở ổ C: ({guh}). Ổ C: chỉ còn ~19GB.\n"
            "         Sửa android.gradle_user_home trong agents.yaml sang ổ D:."
        )
    elif guh.exists():
        r.ok(f"Gradle cache ở ổ {guh.drive.upper()} (đúng — tránh đầy ổ C:)")
    else:
        r.warn(f"Gradle cache {guh} chưa tồn tại, sẽ tạo khi build")


def check_gpu(cfg, r: Report) -> None:
    """Đo VRAM rảnh bằng nvidia-smi — không cần cài thêm thư viện."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        r.warn("Không tìm thấy nvidia-smi, bỏ qua kiểm tra VRAM")
        return

    try:
        out = subprocess.run(
            [
                exe,
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        total, _used, free = (int(x) for x in out.stdout.strip().split(","))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        r.warn(f"Không đọc được VRAM: {exc}")
        return

    reserve = cfg.gpu["reserve_mb"]

    # Nếu TeamViewer/Chrome đang chiếm, free sẽ thấp hơn thật — đó là
    # lý do ta chừa reserve lớn hơn mức Windows nền.
    if free > 7000:
        r.ok(f"VRAM rảnh {free}MB / {total}MB")
    elif free > reserve:
        r.warn(
            f"VRAM rảnh {free}MB — hơi chật. Tắt Chrome/TeamViewer thêm ~3GB."
        )
    else:
        r.fail(
            f"VRAM rảnh chỉ {free}MB, dưới ngưỡng {reserve}MB.\n"
            "         Tắt Chrome/TeamViewer rồi chạy lại."
        )

    if cfg.gpu.get("single_model_only"):
        r.ok("Chế độ single_model_only: không nạp 2 model cùng lúc")


def check_emulator(cfg, r: Report) -> None:
    """Máy không có system-images → không tạo được AVD."""
    if cfg.android.get("emulator_available"):
        r.ok("Emulator khả dụng")
    else:
        r.warn(
            "Không có emulator. QA sẽ dùng JVM unit test + Robolectric.\n"
            "         Đây là giới hạn đã biết, không phải lỗi."
        )


def cmd_doctor(args: argparse.Namespace) -> int:
    """Chẩn đoán môi trường. Trả về 0 nếu không có lỗi chặn."""
    print("=" * 64)
    print("  CHẨN ĐOÁN HỆ AGENTIC")
    print(f"  {ROOT}")
    print("=" * 64)

    r = Report()

    # Cấu hình lỗi thì dừng — không có config thì các kiểm tra sau vô nghĩa.
    try:
        cfg = get_config()
    except ConfigError as exc:
        r.fail(f"Cấu hình lỗi: {exc}")
        r.print()
        return 1

    r.ok(f"agents.yaml hợp lệ  (project={cfg.project['name']})")
    r.ok(
        f"model={cfg.model['name']}  profile={cfg.model['profile']}  "
        f"thread={cfg.thread_id}"
    )
    check_python(r)
    check_disk(r)
    check_ollama(r)
    check_model(cfg, r)
    check_gpu(cfg, r)
    check_java(cfg, r)
    check_sdk(cfg, r)
    check_gradle_cache(cfg, r)
    check_emulator(cfg, r)

    r.print()

    if r.failures:
        print("\n→ Chưa thể chạy. Sửa các [FAIL] rồi chạy lại.")
        return 1

    print("\n→ Môi trường sẵn sàng cho GĐ1.")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """In cấu hình đã resolve, bỏ qua phần bí mật nếu có."""
    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"LỖI: {exc}")
        return 1
    print(json.dumps(cfg._raw, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentic",
        description="Hệ 6 tác tử sinh app Android — cấu hình trong agents.yaml",
    )
    sub = parser.add_subparsers(dest="command")

    p_doctor = sub.add_parser(
        "doctor", help="Kiểm tra môi trường (model, GPU, JDK, SDK, disk)"
    )
    p_doctor.set_defaults(func=cmd_doctor)

    p_config = sub.add_parser("config", help="In cấu hình đang resolve")
    p_config.set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
