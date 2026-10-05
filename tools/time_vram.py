"""Đo chi phí I/O của kiểm tra VRAM trước MỖI lượt gọi model.

can_load() chạy subprocess `ollama ps` và `nvidia-smi`. Nếu mỗi lần mất
vài giây, một vòng tranh luận 8 node sẽ mất hàng chục giây chỉ để HỎI
xem có cần nạp model không — trong khi model đã nằm sẵn trong VRAM từ
lượt đầu.

Cách dùng:
    python tools\\time_vram.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic.llm.vram import VramGovernor, read_gpu  # noqa: E402


def main() -> int:
    gov = VramGovernor(reserve_mb=512)

    t = time.perf_counter()
    gpu = read_gpu()
    read_s = time.perf_counter() - t
    print(f"read_gpu      {read_s:6.2f}s  {gpu}")

    t = time.perf_counter()
    names = gov._loaded_names()
    loaded_s = time.perf_counter() - t
    print(f"_loaded_names {loaded_s:6.2f}s  {names}")

    t = time.perf_counter()
    ok, reason = gov.can_load("qwen2.5-coder:7b", 16384)
    total_s = time.perf_counter() - t
    print(f"can_load      {total_s:6.2f}s  ok={ok}")
    print(f"  -> {reason}")

    # 8 node một vòng tranh luận → tổng thời gian chỉ để hỏi.
    print(f"\n8 node × can_load = {total_s * 8:.1f}s chi phi I/Os thuan")

    # Lần thứ hai có nhanh hơn không (cache trong tiến trình)?
    t = time.perf_counter()
    gov.can_load("qwen2.5-coder:7b", 16384)
    print(f"lan 2      {time.perf_counter() - t:6.2f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())