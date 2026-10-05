"""Gọi thật một model cloud qua local Ollama và in kết quả đúng encoding.

Dùng để chứng minh `gemma4:31b-cloud` dùng được trên máy này. Kiểm tra
cả ba điều: model có tồn tại, Ollama tự chuyển tiếp sang cloud, và nội dung
trả về đúng UTF-8 (PowerShell hay in ra ký tự hỏng nên phải kiểm bằng Python).

Cách dùng:
    python tools\\probe_cloud.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

BASE = "http://localhost:11434"


def post(path: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def show(model: str) -> bool:
    """Kiểm tra model có tồn tại không."""
    print("=" * 62)
    print(f"MODEL: {model}")
    print("=" * 62)
    try:
        info = post("/api/show", {"model": model}, timeout=20)
        det = info.get("details", {})
        print(f"  ton tai      : co")
        print(f"  ho so        : {det.get('family')}")
        print(f"  so tham so   : {det.get('parameter_size')}")
        print(f"  dinh luong   : {det.get('quantization_level')}")
    except urllib.error.HTTPError as exc:
        print(f"  ton tai      : KHONG ({exc.code})")
        return False
    return True


def chat(model: str, prompt: str, num_predict: int = 40) -> None:
    """Gọi chat và in nội dung, đo thời gian."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {
            "num_ctx": 16384,
            "temperature": 0.3,
            "num_predict": num_predict,
        },
    }

    print(f"\n  dang goi (num_predict={num_predict})...", flush=True)
    t0 = time.perf_counter()
    try:
        out = post("/api/chat", payload)
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - t0
        body = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"  LOI HTTP {exc.code} sau {elapsed:.1f}s")
        print(f"  {body}")
        return
    elapsed = time.perf_counter() - t0

    content = out.get("message", {}).get("content", "")
    print(f"  OK {elapsed:.1f}s — {len(content)} ky tu")
    print(f"  noi dung: {content[:300]}")

    # Token usage để biết model cloud có báo chi phí hay không.
    if out.get("eval_count"):
        print(
            f"  tokens: prompt={out.get('prompt_eval_count')} "
            f"eval={out.get('eval_count')} "
            f"({out.get('eval_count', 0) / elapsed:.1f} tok/s)"
        )
    if out.get("total_duration"):
        print(f"  server: {out['total_duration'] / 1e9:.1f}s")


def main() -> int:
    models = [
        "gemma4:31b-cloud",
        "gpt-oss:120b-cloud",
        "qwen3-coder:480b-cloud",
    ]

    print("Kiem tra model cloud co ton tai tren may nay\n")
    found = [m for m in models if show(m)]

    print(f"\nTim thay {len(found)}/{len(models)}: {found}")
    if found:
        print("\n--- goi that voi model dau tien ---")
        chat(found[0], "Tra ve JSON hop le: {\"status\": \"ok\"}")
    return 0


if __name__ == "__main__":
    sys.exit(main())