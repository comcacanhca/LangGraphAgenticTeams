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
import time
from pathlib import Path

from agentic.config import ROOT, ConfigError, get_config
from agentic.encoding import force_utf8

# Ép UTF-8 trước khi in bất cứ thông báo tiếng Việt nào. config.py cũng
# tự làm việc này khi được import, nhưng gọi lại ở đây để chắc chắn khi
# chạy cli.py trực tiếp (python -m agentic.cli).
force_utf8()

OK = "[ OK ]"
BAD = "[FAIL]"
WARN = "[WARN]"


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
    """Model trong active_profile phải dùng được.

    Model CLOUD không xuất hiện trong `ollama list` (nó chạy trên server, máy
    không tải về), nên phải hỏi API `/api/show` thay vì đọc danh sách cục
    bộ. Nếu không tách hai trường hợp, mọi profile cloud đều bị báo FAIL
    dù chạy hoàn toàn bình thường.
    """
    name = cfg.model["name"]

    if name.endswith("-cloud"):
        check_cloud_model(cfg, name, r)
        return

    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        r.fail(f"Không kiểm tra được model '{name}' (Ollama chưa chạy)")
        return

    if name.split(":")[0].lower() in out.stdout.lower():
        r.ok(f"Model '{name}' đã cài (cục bộ)")
    else:
        r.fail(f"Model '{name}' chưa có. Cài bằng: ollama pull {name}")


def check_cloud_model(cfg, name: str, r: Report) -> None:
    """Kiểm tra model cloud có tồn tại và máy đã đăng nhập chưa.

    Điều kiện duy nhất cho model cloud là đã `ollama signin` một lần — không
    cần API key, không cần `ollama pull`. Không kiểm tra điều này thì lỗi
    hiện ra giữa chừng dưới dạng HTTP 401 khó hiểu.
    """
    import json
    import urllib.request

    base = cfg.model.get("base_url", "http://localhost:11434")

    try:
        req = urllib.request.Request(
            f"{base}/api/show",
            data=json.dumps({"model": name}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            r.fail(
                f"Model cloud '{name}' bị từ chối truy cập.\n"
                f"        Chạy: ollama signin"
            )
        else:
            r.fail(
                f"Model cloud '{name}' không tồn tại (HTTP {exc.code}).\n"
                f"        Kiểm tra danh sách: https://ollama.com/search?c=cloud"
            )
        return
    except (OSError, urllib.error.URLError) as exc:
        r.fail(f"Không gọi được Ollama tại {base}: {exc}")
        return

    details = info.get("details", {})
    params = details.get("parameter_size", "?")
    r.ok(
        f"Model cloud '{name}' sẵn sàng "
        f"({params} tham số, {details.get('quantization_level', '?')}, "
        f"không tốn VRAM máy)"
    )


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

    print("\n→ Môi trường sẵn sàng cho bước tiếp theo.")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Đo độ tin cậy thật của model đang active.

    Dùng để trả lời câu hỏi "có nên đổi model không" bằng số liệu thay
    vì cảm giác.
    """
    from pathlib import Path

    from agentic.llm import benchmark as bench

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"LỖI: {exc}")
        return 1

    out = Path(args.out) if args.out else cfg_root() / "benchmark.json"

    if args.compare:
        old = Path(args.compare)
        if not old.exists():
            print(f"LỖI: không thấy file so sánh {old}")
            return 1
        print(bench.compare(old, out))
        return 0

    try:
        data = bench.run(cfg, out)
    except FileNotFoundError as exc:
        print(f"LỖI: {exc}")
        return 1

    # Độ tin cậy thấp thì cảnh báo sớm, trước khi GĐ2 gặp vấn đề.
    if data["success_rate"] < 1.0:
        print(
            "\n⚠ Một số câu không đạt. Xem trường 'error' trong benchmark.json."
        )
    if data["first_try_rate"] < 0.5:
        print(
            "⚠ Tỷ lệ đúng lần đầu thấp — hệ thống sẽ retry nhiều, "
            "mỗi sprint sẽ chậm."
        )
    return 0


def cfg_root() -> Path:
    """Thư mục gốc hệ thống (nơi chứa agents.yaml)."""
    return ROOT


def cmd_design(args: argparse.Namespace) -> int:
    """Chạy phase thiết kế: các tác tử tranh luận rồi dừng ở GATE 1.

    Gọi lại sau khi đã có checkpoint sẽ tiếp tục, không chạy lại từ đầu.
    """
    from agentic.graph.builder import run_design_phase
    from agentic.memory.checkpointer import thread_config

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"LỖI: {exc}")
        return 1

    requirement = " ".join(args.requirement)
    if not requirement:
        print(
            'Cần yêu cầu. Ví dụ:\n'
            '  agentic design "App đếm ngày sinh nhật, ghi nhật ký"'
        )
        return 1

    print(f"→ Chạy tranh luận thiết kế với {cfg.model['name']}")
    print(f"  Yêu cầu: {requirement}\n")
    print("  Mỗi vòng: architect → developer → qa → devops → hội tụ")
    print("  Dừng khi hết phản biện nghiêm trọng hoặc hết số vòng cho phép.\n")

    started = time.perf_counter()

    def show(node: str, update: dict) -> None:
        """In tiến triển từng node.

        Mỗi node gọi model mất 5-15 giây, cả vòng cỡ 1-2 phút. Không in
        gì trong lúc đó thì không phân biệt được "đang chạy" với "treo" —
        và lần này đã phải mất nhiều phút chẩn đoán vì thiếu thông tin này.
        """
        elapsed = time.perf_counter() - started
        detail = ""

        # Rút thông tin đáng quan tâm ra, đừng in cả state.
        for entry in (update or {}).get("transcript", []):
            detail = entry.get("action") or ""
            if detail:
                break

        bp = (update or {}).get("blueprint") or {}
        if bp:
            detail = (
                f"{len(bp.get('screens', []))} màn hình, "
                f"{len(bp.get('risks', []))} rủi ro"
            )

        suffix = f"  — {detail}" if detail else ""
        print(f"  [{elapsed:5.1f}s] {node}{suffix}", flush=True)

    try:
        graph, config = run_design_phase(
            cfg, requirement, args.mood, on_progress=show
        )
    except Exception as exc:  # noqa: BLE001 — cần báo rõ cho người dùng
        print(f"LỖI: {type(exc).__name__}: {exc}")
        return 1

    # interrupt() chặn ở GATE 1 — graph.invoke trả về với __interrupt__.
    state = graph.get_state(config)
    out = cfg.project_dir() / "design.html"

    print()
    print("=" * 64)
    if out.exists():
        print(f"  Bản thiết kế: {out}")
        print(f"  Mở file đó bằng trình duyệt để đọc.")
    print()
    print("  Trạng thái:")
    for key in ("debate_round", "blocking_count"):
        print(f"    {key}: {state.values.get(key)}")

    design = state.values.get("design", {})
    if design:
        print(f"    quyết định kiến trúc: {len(design.get('decisions', []))}")
        tokens = design.get("tokens") or {}
        print(f"    màu design token: {len(tokens.get('palette', {}))}")

    gate = state.values.get("gate1_result")
    if gate and not gate.get("approved"):
        print(f"\n  ⚠ {gate.get('reason') or gate.get('error')}")

    print("\n" + "=" * 64)
    print("\n  Hệ thống đang DỪNG ở GATE 1 chờ bạn.")
    print("  Duyệt:  agentic approve --yes")
    print("  Từ chối: agentic approve --no \"<lý do>\"")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Trả lời GATE: tiếp tục hoặc dừng.

    Resume bằng cách gọi lại graph với input None — đó là cách LangGraph
    tiếp tục từ checkpoint, không phải chạy lại từ đầu.
    """
    from langgraph.types import Command

    from agentic.graph.builder import build_graph
    from agentic.memory.checkpointer import thread_config

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"LỖI: {exc}")
        return 1

    graph = build_graph(cfg)
    config = thread_config(cfg)

    state = graph.get_state(config)
    if not state.interrupts:
        print("Không có GATE nào đang chờ. Chạy 'agentic design' trước.")
        return 1

    decision = {
        "approved": bool(args.yes),
        "feedback": " ".join(args.feedback) if args.feedback else "",
    }

    print(f"→ Trả lời GATE 1: {'DUYỆT' if args.yes else 'TỪ CHỐI'}")
    try:
        graph.invoke(Command(resume=decision), config=config)
    except Exception as exc:  # noqa: BLE001
        print(f"LỖI: {type(exc).__name__}: {exc}")
        return 1

    if args.yes:
        print("\n✓ Đã duyệt. Tiếp theo là phase Scrum (sẽ có ở GĐ4).")
    else:
        reason = decision["feedback"] or "không nêu lý do"
        print(f"\n✗ Đã từ chối: {reason}")
        print("  Sửa agents.yaml hoặc chạy lại 'agentic design' với yêu cầu khác.")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Xem tiến trình đã đi được đâu."""
    from agentic.memory.checkpointer import thread_config

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"LỖI: {exc}")
        return 1

    from agentic.graph.builder import build_graph

    graph = build_graph(cfg)
    state = graph.get_state(thread_config(cfg))

    print(f"Project : {cfg.project['name']}")
    print(f"Model   : {cfg.model['name']}  (profile {cfg.model['profile']})")
    print(f"Thread  : {cfg.thread_id}")

    if not state.values:
        print("\nChưa chạy gì. Bắt đầu bằng: agentic design \"<yêu cầu>\"")
        return 0

    v = state.values
    print(f"\nTiến trình:")
    print(f"  vòng tranh luận : {v.get('debate_round', 0)}")
    print(f"  phản biện chặn  : {v.get('blocking_count', 0)}")

    design = v.get("design", {})
    if design.get("design"):
        print(f"  thiết kế        : {len(design['design'])} ký tự")
    if design.get("decisions"):
        print(f"  quyết định      : {len(design['decisions'])}")
    if design.get("tokens"):
        print(f"  màu token       : {len(design['tokens'].get('palette', {}))}")

    print(f"  lượt tranh luận  : {len(v.get('transcript', []))}")

    gate = v.get("gate1_result")
    if state.interrupts:
        print("\n  ⏸ ĐANG CHỜ bạn duyệt GATE 1")
        print("    agentic approve --yes")
    elif gate:
        status = "duyệt" if gate.get("approved") else "từ chối"
        print(f"\n  GATE 1: {status}")

    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    """Thử tác tử từ dòng lệnh — nhanh hơn web UI để kiểm tra.

    Có hai chế độ:
      agentic agents --list          → xem các tác tử có sẵn
      agentic agents designer "..."  → gọi một tác tử, in JSON kết quả
    """
    from agentic.agents import architect, designer, developer, devops, qa
    from agentic.agents.base import build_agent

    registry = {
        "architect": architect,
        "designer": designer,
        "developer": developer,
        "qa": qa,
        "devops": devops,
    }

    if args.list or not args.who:
        # Load cấu hình MỘT lần. Gọi get_config() trong vòng lặp sẽ in cảnh
        # báo Ollama lặp lại 5 lần — rất nhiễu khi xem danh sách.
        try:
            cfg = get_config()
            roles = {
                n: " ".join(cfg.agents[n]["role"].split())[:58]
                for n in registry
                if n in cfg.agents
            }
        except (ConfigError, KeyError):
            roles = {}

        print("Các tác tử có thể thử:\n")
        for name in sorted(registry):
            print(f"  {name:<10} {roles.get(name, '')}")
        print(
            "\nDùng:  agentic agents <tên-tác-tử> \"<câu hỏi>\"\n"
            "Ví dụ: agentic agents designer \"App ghi chú, màu pastel\""
        )
        return 0

    if args.who not in registry:
        print(f"Không có tác tử '{args.who}'. Có: {', '.join(sorted(registry))}")
        return 1

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"LỖI: {exc}")
        return 1

    module = registry[args.who]
    agent = build_agent(args.who, cfg)

    question = " ".join(args.question) if args.question else ""
    if not question:
        print("Cần câu hỏi. Ví dụ: agentic agents designer \"App ghi chú\"")
        return 1

    print(f"→ Gọi '{args.who}' với model {cfg.model['name']}...\n")
    try:
        if args.who == "designer":
            result = designer.design_tokens(agent, question)
        elif args.who == "architect":
            result = architect.propose(agent, question)
        else:
            result = agent.ask(question)
    except Exception as exc:  # noqa: BLE001 — cần báo lỗi cho người dùng
        print(f"LỖI: {type(exc).__name__}: {exc}")
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n({agent.client.stats[-1].seconds:.1f}s)")
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

    p_bench = sub.add_parser(
        "benchmark",
        help="Đo độ tin cậy thật của model, ghi ra benchmark.json",
    )
    p_bench.add_argument("--out", help="Đường dẫn file kết quả")
    p_bench.add_argument(
        "--compare",
        help="Đường dẫn benchmark cũ để so sánh (sau khi đổi model)",
    )
    p_bench.set_defaults(func=cmd_benchmark)

    p_agents = sub.add_parser(
        "agents", help="Thử tác tử từ dòng lệnh (gọi model thật)"
    )
    p_agents.add_argument("who", nargs="?", help="Tên tác tử")
    p_agents.add_argument("question", nargs="*", help="Câu hỏi cho tác tử")
    p_agents.add_argument(
        "--list", action="store_true", help="Chỉ liệt kê các tác tử"
    )
    p_agents.set_defaults(func=cmd_agents)

    p_design = sub.add_parser(
        "design",
        help="Chạy tranh luận thiết kế, dừng ở GATE 1 chờ bạn duyệt",
    )
    p_design.add_argument("requirement", nargs="*", help="Yêu cầu xây app")
    p_design.add_argument(
        "--mood",
        default="đơn giản, dễ thương",
        help="Phong cách giao diện mong muốn",
    )
    p_design.set_defaults(func=cmd_design)

    p_approve = sub.add_parser(
        "approve", help="Trả lời GATE 1 (duyệt hoặc từ chối)"
    )
    p_approve.add_argument(
        "--yes", action="store_true", help="Duyệt bản thiết kế"
    )
    p_approve.add_argument(
        "--no", dest="yes", action="store_false",
        help="Từ chối bản thiết kế",
    )
    p_approve.set_defaults(func=cmd_approve, yes=True)
    p_approve.add_argument(
        "feedback", nargs="*", help="Lý do nếu từ chối, hoặc góp ý chỉnh sửa"
    )

    p_status = sub.add_parser(
        "status", help="Xem tiến trình hiện tại"
    )
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
