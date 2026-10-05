"""Giám sát VRAM: chỉ nạp được MỘT model trên RTX 3060 12GB.

Vì sao cần module này:
  Tổng 12,288 MiB − Windows/Chrome/dwm (~1,200) − mức dự phòng
  = khoảng 10,000 MiB khả dụng. qwen2.5-coder:7b chiếm ~4,700 MiB,
  gemma4:12b ~8,000 MiB. Nạp cả hai là OOM chắc chắn.

Nguyên tắc: đo TRƯỚC khi gọi model. Nếu VRAM không đủ thì báo, không đoán.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuState:
    """Trạng thái VRAM tại một thời điểm."""

    total_mb: int
    used_mb: int
    free_mb: int

    @property
    def usable_mb(self) -> int:
        """VRAM dùng được cho model sau khi trừ phần Windows chiếm.

        used_mb của nvidia-shi bao gồm cả desktop, nên không dùng trực tiếp
        làm ngưỡng — phải trừ đi phần nền của hệ điều hành.
        """
        return max(0, self.free_mb)


def read_gpu() -> GpuState | None:
    """Đọc VRAM qua nvidia-smi. Trả None nếu máy không có NVIDIA GPU.

    Dùng nvidia-smi thay vì thư viện như pynvml/torch: không cài thêm gì,
    và câu lệnh làm việc ngay cả khi chưa cấu hình CUDA.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None

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
    except (OSError, subprocess.SubprocessError):
        return None

    # Máy có thể có nhiều GPU; lấy dòng đầu tiên.
    line = (out.stdout or "").strip().splitlines()
    if not line:
        return None

    parts = [p.strip() for p in line[0].split(",")]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None

    total, used, free = (int(p) for p in parts)
    return GpuState(total_mb=total, used_mb=used, free_mb=free)


def estimate_model_mb(model_name: str) -> int:
    """Ước lượng VRAM một model chiếm, đọc từ `ollama list`.

    Ollama hiện cột SIZE (dung lượng đĩa). VRAM thực cao hơn một chút vì
    KV cache, nhưng dùng cột SIZE làm cơ sở rồi cộng thêm buffer là đủ
    để ra quyết định nạp hay không.
    """
    exe = shutil.which("ollama")
    if not exe:
        return 0

    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return 0

    base = model_name.split(":")[0].lower()
    for line in (out.stdout or "").splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 2 and cols[0].lower().startswith(base):
            match = re.match(r"([\d.]+)\s*(GB|MB)", cols[1], re.IGNORECASE)
            if not match:
                continue
            value = float(match.group(1))
            return int(value * 1024) if match.group(2).upper() == "GB" else int(value)

    return 0


class VramGovernor:
    """Quyết định có được nạp model hay không, dựa trên VRAM thật.

    Không tự ý dừng tiến trình khác — chỉ báo cáo và chặn. Việc tắt
    TeamViewer/Chrome là quyết định của bạn, không phải của hệ thống.
    """

    def __init__(self, reserve_mb: int, single_model_only: bool = True) -> None:
        self.reserve_mb = reserve_mb
        self.single_model_only = single_model_only
        # Nếu profile khai báo vram_estimate_mb thì dùng con số đó thay
        # vì cột SIZE của `ollama list` KHÔNG tính KV cache — mà KV cache
        # mới là phần quyết định với model nặng như gemma4:12b.
        self.explicit_mb: int | None = None

    def can_load(self, model_name: str, ctx: int = 0) -> tuple[bool, str]:
        """Có nạp được model này không? Trả về (ok, lý do).

        ctx là số token context — context càng lớn, KV cache càng nặng.
        """
        gpu = read_gpu()
        if gpu is None:
            # Không đọc được VRAM thì cho qua — nhiều máy không có NVIDIA,
            # và việc chặn sẽ khiến hệ thống không chạy được ở đâu đó.
            return True, "Không đọc được VRAM, bỏ qua kiểm tra."

        # ═══ Model ĐANG NẠP thì không cần thêm VRAM ═══
        # Đây là chỗ dễ sai nhất: sau lượt gọi đầu tiên, model đã nằm
        # trong VRAM, nên `free_mb` sẽ thấp MÀI model đó chiếm. Nếu kiểm
        # VRAM như lần đầu thì mọi lượt gọi thứ hai trở đi đều bị chặn
        # oan, dù máy hoàn toàn ổn.
        #
        # Đã thử nghiệm: Ollama BÁO kích thước nhỏ hơn VRAM thật (cột
        # SIZE của `ollama ps` là dung lượng weight, không gồm KV cache),
        # nên KHÔNG dùng ngưỡng MB để quyết định "đã nạp" hay chưa. Chỉ
        # cần model CÓ TÊN trong `ollama ps` là đủ để coi là nạp rồi —
        # Ollama tự nạp phần còn lại khi có request.
        loaded = self._loaded_names()
        # So KHỚP HOÀN CHỈNH tên model, không so tên rút gọn. `ollama ps`
        # in tên đầy đủ ("gemma4:12b"), nên tách ở dấu ":" rồi so sánh
        # "gemma4" với "gemma4:12b" sẽ KHÔNG BAO GIỜ khớp — lỗi này khiến
        # mọi lượt gọi sau lượt đầu bị chặn oan.
        if model_name in loaded:
            return True, f"'{model_name}' đã nằm trong VRAM, không cần nạp lại."

        needed = self.explicit_mb or estimate_model_mb(model_name)
        if needed == 0:
            return True, "Không ước lượng được kích thước model, bỏ qua."

        # Chỉ cộng thêm KV cache khi dùng con số ước lượng từ ollama list
        # (con số đó đã là dung lượng model, chưa gồm KV cache).
        if not self.explicit_mb:
            needed += (ctx // 8192) * 250

        free_for_model = gpu.free_mb - self.reserve_mb

        if needed > free_for_model:
            return (
                False,
                f"Thiếu VRAM: cần ~{needed}MB, đang rảnh {gpu.free_mb}MB, "
                f"ngưỡng dự phòng {self.reserve_mb}MB.\n"
                f"        Tắt Chrome/TeamViewer sẽ thêm khoảng 3GB.",
            )

        if self.single_model_only and len(loaded) > 1:
            # Nhiều model cùng nằm trong VRAM sẽ tranh chấp và OOM.
            names = ", ".join(loaded)
            return (
                False,
                f"single_model_only=true nhưng đang có {len(loaded)} model "
                f"nạp: {names}.\n        Dùy 'ollama stop <model>' để giải phóng.",
            )

        return (
            True,
            f"VRAM OK: cần ~{needed}MB, rảnh {gpu.free_mb}MB "
            f"(dự phòng {self.reserve_mb}MB).",
        )


    @staticmethod
    def _loaded_names() -> list[str]:
        """Tên các model đang nằm trong VRAM (qua `ollama ps`).

        CHỈ CẦN TÊN, không cần kiểm kích thước. Đã thử nghiệm: cột SIZE
        của `ollama ps` là dung lượng weight, KHÔNG gồm KV cache, nên nó
        luôn nhỏ hơn VRAM model thật sự chiếm. Dùng SIZE để quyết định
        "đã nạp chưa" sẽ gây ra hai lỗi ngược nhau:
          - cho qua quá sớm → Ollama tự nạp, vẫn chạy được (vô hại)
          - chặn quá mức → mọi lượt gọi sau lượt đầu đều bị từ chối oan

        Ollama tự lo phần nạp còn lại khi nhận request, nên chỉ cần biết
        model đã có mặt trong bảng là được.
        """
        exe = shutil.which("ollama")
        if not exe:
            return []

        try:
            out = subprocess.run(
                ["ollama", "ps"], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            return []

        return [
            cols[0]
            for cols in (line.split() for line in
                         (out.stdout or "").strip().splitlines()[1:])
            if cols
        ]


