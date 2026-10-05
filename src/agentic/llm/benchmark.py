"""Sinh benchmark.json — đo độ tin cậy THẬT của model đang dùng.

Vì sao cần: câu hỏi "có nên đổi từ qwen2.5-coder:7b sang gemma4:12b
không?" không có câu trả lời nếu ta không đo. Cảm giác là không đủ.

File này ghi lại:
  - tỷ lệ JSON hợp lệ ngay lần đầu  (chất lượng thật của model)
  - số lần retry trung bình          (chi phí thời gian bị bù)
  - thời gian mỗi lượt gọi            (ước lượng cho một sprint)
  - VRAM rảnh sau khi chạy            (xác nhận không tràn)

Cách dùng: sau khi đổi active_profile trong agents.yaml, chạy lại
'agentic benchmark' rồi so hai file. Chỉ đổi model khi số liệu cải thiện.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic.config import ROOT, Config
from agentic.llm.client import LlmClient

# Bộ câu hỏi cố định. Phải NHẤT ĐỊNH, không random, để hai lần đo
# so sánh được với nhau.
CASES: list[tuple[str, str, str]] = [
    (
        "designer",
        "designer",
        "Thiết kế app xem truyện Bát Tự cho người Việt, giao diện "
        "đơn giản dễ thương, chủ đề hồng pastel.",
    ),
    (
        "designer",
        "designer",
        "Thiết kế app ghi chú tối giản, nền sáng, chữ đen, bo góc mềm.",
    ),
    (
        "architect",
        "architect",
        "Yêu cầu: app lấy lá số bát tự từ ngày sinh, xem 4 cung, chat "
        "hỏi đáp. Thiết kế kiến trúc tổng thể.",
    ),
    (
        "architect",
        "architect",
        "Yêu cầu: app đếm ngày, hiển thị lịch, ghi nhật ký. Cấu trúc "
        "dữ liệu và màn hình nên thế nào?",
    ),
    (
        "critic",
        "critic",
        "Dữ liệu lá số lưu trong bộ nhớ app, không cần database.",
    ),
    (
        "critic",
        "critic",
        "Giao diện đơn giản, dễ thương, phản hồi nhanh.",
    ),
    (
        "qa",
        "qa",
        "Tiêu chí nghiệm thu: AC1 lưu lá số qua app restart; "
        "AC2 xóa được 1 lá số. Viết kế hoạch test.",
    ),
    (
        "devops",
        "devops",
        "Dự dựng app Android Compose, cần CI chạy mỗi lần push và "
        "xuất APK. Đánh giá rủi ro triển khai.",
    ),
]


def _load_prompt(cfg: Config, name: str) -> str:
    path = ROOT / "prompts" / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Thiếu prompt: {path}")
    return path.read_text(encoding="utf-8")


def run(cfg: Config, out_path: Path | None = None) -> dict[str, Any]:
    """Chạy bộ test cố định, ghi kết quả ra JSON. Trả về dữ liệu."""
    client = LlmClient.from_config(cfg)
    out_path = out_path or (ROOT / "benchmark.json")

    results: list[dict[str, Any]] = []
    total = len(CASES)

    print(f"Đo độ tin cậy: {cfg.model['name']}  ({total} câu hỏi)")
    print("-" * 58)

    for i, (agent, prompt_name, question) in enumerate(CASES, start=1):
        before = len(client.stats)
        system = _load_prompt(cfg, prompt_name)

        try:
            client.call_agent(agent, system, question)
            ok = True
            error = ""
        except Exception as exc:  # noqa: BLE001 — cần ghi lại mọi lỗi
            ok = False
            error = f"{type(exc).__name__}: {exc}"[:300]

        stat = client.stats[-1] if len(client.stats) > before else None
        results.append(
            {
                "case": i,
                "agent": agent,
                "ok": ok,
                "attempts": stat.attempts if stat else 0,
                "seconds": stat.seconds if stat else 0.0,
                "error": error,
            }
        )

        mark = "OK  " if ok else "FAIL"
        secs = f"{stat.seconds:.1f}s" if stat else "-"
        tries = f"{stat.attempts}x" if stat else "-"
        print(f"  [{mark}] {agent:<10} {secs:>7}  retry={tries}")

    data = _summarise(cfg, results)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("-" * 58)
    print(f"  JSON hợp lệ lần đầu  : {data['first_try_rate']:.0%}")
    print(f"  Thành công cuối cùng : {data['success_rate']:.0%}")
    print(f"  Retry trung bình     : {data['avg_attempts']:.2f}")
    print(f"  Thời gian trung bình : {data['avg_seconds']:.1f}s")
    print(f"  Ước lượng 1 sprint   : {data['est_sprint_minutes']} phút (chưa kể Gradle)")
    print(f"\nĐã ghi: {out_path}")
    return data


def _summarise(cfg: Config, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Tính số liệu tổng hợp + ước lượng thời gian một sprint."""
    total = len(results) or 1
    succeeded = [r for r in results if r["ok"]]

    # first_try_rate là CHẤT LƯỢNG THẬT của model: đo được bao nhiêu câu
    # trả đúng JSON ngay lần đầu, không cần nhắc lại.
    first_try = sum(1 for r in results if r["attempts"] == 1)

    # Một sprint ước tính: planning + dev + qa + review + fix.
    avg_sec = (
        sum(r["seconds"] for r in succeeded) / len(succeeded)
        if succeeded
        else 0.0
    )
    # 6 lượt gọi model mỗi sprint, cộng thời gian chờ do build Gradle
    # (build thật mất 1-3 phút, không tính vào đây).
    calls_per_sprint = 6

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": cfg.model["name"],
        "profile": cfg.model["profile"],
        "params": {
            "num_ctx": cfg.model["num_ctx"],
            "temperature": cfg.model["temperature"],
            "max_retries": cfg.model["max_retries"],
        },
        "total_cases": len(results),
        "success_rate": round(len(succeeded) / total, 3),
        "first_try_rate": round(first_try / total, 3),
        "avg_attempts": round(
            sum(r["attempts"] for r in succeeded) / len(succeeded), 2
        ) if succeeded else 0.0,
        "avg_seconds": round(avg_sec, 1),
        "max_seconds": round(
            max((r["seconds"] for r in succeeded), default=0.0), 1
        ),
        "est_sprint_minutes": round(avg_sec * calls_per_sprint / 60, 1),
        "note": (
            "est_sprint_minutes KHÔNG gồm thời gian chạy Gradle "
            "(thực tế thêm 1-3 phút mỗi vòng build). Sử dụng để SO SÁNH "
            "hai model, không phải để dự báo tuyệt đối."
        ),
        "cases": results,
    }


def compare(old_path: Path, new_path: Path) -> str:
    """So sánh hai file benchmark, trả về bảng đọc được."""
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))

    # (nhãn, khoá, định dạng, hướng tốt) — "hướng tốt" cho biết tăng hay
    # giảm mới là cải thiện, để gắn mũi tên ▲/▼ đúng nghĩa.
    metrics = [
        ("JSON hợp lệ lần đầu", "first_try_rate", "{:.0%}", 1),
        ("Thành công cuối cùng", "success_rate", "{:.0%}", 1),
        ("Retry trung bình", "avg_attempts", "{:.2f}", -1),
        ("Thời gian/câu (giây)", "avg_seconds", "{:.1f}", -1),
    ]

    lines = [
        "",
        "SO SÁNH ĐỘ TIN CẬY",
        "=" * 62,
        f"  cũ: {old['model']} ({old['measured_at']})",
        f"  mới: {new['model']} ({new['measured_at']})",
        "-" * 62,
    ]

    for label, key, fmt, good_dir in metrics:
        before = old.get(key, 0)
        after = new.get(key, 0)

        # "{:.0%}" của str.format ĐÃ tự nhân 100, nên không được nhân thêm.
        # Trước đây nhân 2 lần nên 1.0 hiện thành "10000%".
        old_txt = fmt.format(before)
        new_txt = fmt.format(after)

        delta = ""
        if isinstance(before, (int, float)) and before != after:
            diff = after - before
            arrow = "▲" if diff > 0 else "▼"
            improved = (diff > 0) if good_dir > 0 else (diff < 0)
            verdict = "tốt hơn" if improved else "kém hơn"
            delta = f"   {arrow} {verdict}"

        lines.append(f"  {label:<26} {old_txt:>9} → {new_txt:>9}{delta}")

    lines.append("=" * 62)
    return "\n".join(lines)
