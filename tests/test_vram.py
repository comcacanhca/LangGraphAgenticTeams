"""Kiểm tra VRAM governor — lớp chặn lỗi trước khi OOM.

Lỗi đã gặp thực tế (và nguy hiểm): sau lượt gọi đầu tiên, model đã nằm
trong VRAM nên free_mb thấp đúng bằng phần model chiếm. Nếu governor
đo kiểu "cần bao nhiêu để NẠP" mà không xét "model đã nạp chưa", thì mọi
lượt gọi thứ hai trở đi bị chặn oan. Benchmark lúc đó báo 12% thành công
dù máy hoàn toàn ổn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic.llm.vram import VramGovernor, estimate_model_mb, read_gpu


def _gpu(free_mb: int):
    """Giả lập GpuState — gọn hơn việc dựng class trong từng test."""
    return type(
        "G", (), {"total_mb": 12288, "used_mb": 12288 - free_mb, "free_mb": free_mb}
    )()


class TestGpuReading:
    def test_reads_gpu_or_none(self) -> None:
        """Máy không có NVIDIA thì trả None, không ném lỗi."""
        state = read_gpu()
        if state is None:
            pytest.skip("Máy không có NVIDIA GPU")
        assert state.total_mb > 0
        assert state.free_mb <= state.total_mb

    def test_estimate_known_model(self) -> None:
        """qwen2.5-coder đã cài nên phải đọc được kích thước."""
        mb = estimate_model_mb("qwen2.5-coder:7b")
        if mb == 0:
            pytest.skip("Ollama chưa chạy hoặc model chưa cài")
        assert 1000 < mb < 20000


class TestAlreadyLoaded:
    """★ Bài học từ 3 lỗi thật liên tiếp.

    Bản đầu kiểm "đã nạp" bằng dung lượng VRAM trống → chặn oan từ
    lượt gọi thứ hai. Bản sau dùng ngưỡng MB trên cột SIZE của
    `ollama ps` → vẫn chặn oan vì SIZE không gồm KV cache.
    Bản đúng: chỉ cần model CÓ TÊN trong bảng là coi như đã nạp.
    """

    def test_allows_already_loaded_model(self, monkeypatch) -> None:
        gov = VramGovernor(reserve_mb=1200)
        gov.explicit_mb = 9500
        # Model đã có trong `ollama ps`, VRAM còn rất ít — vẫn phải cho qua.
        monkeypatch.setattr(VramGovernor, "_loaded_names", staticmethod(
            lambda: ["gemma4:12b"]
        ))
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: _gpu(1484))

        ok, reason = gov.can_load("gemma4:12b", ctx=16384)
        assert ok, f"Phải cho phép vì model đã nạp. Lý do: {reason}"
        assert "đã nằm trong VRAM" in reason

    def test_ignores_reported_size(self, monkeypatch) -> None:
        """Cột SIZE nhỏ (chưa gồm KV cache) không được dùng để chặn."""
        gov = VramGovernor(reserve_mb=1200)
        gov.explicit_mb = 9500
        monkeypatch.setattr(VramGovernor, "_loaded_names", staticmethod(
            lambda: ["gemma4:12b"]
        ))
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: _gpu(1484))

        ok, reason = gov.can_load("gemma4:12b", ctx=16384)
        assert ok, reason
        assert "đã nằm trong VRAM" in reason

    def test_still_blocks_when_other_models_loaded(self, monkeypatch) -> None:
        """Model khác đang chiếm VRAM thì phải chặn model mới.

        Tình huống: qwen2.5-coder:7b đang nạp (chiếm ~5.6GB), giờ muốn
        gọi gemma4:12b (cần ~9.5GB) — tổng vượt 12GB nên phải chặn.
        """
        gov = VramGovernor(reserve_mb=1200)
        gov.explicit_mb = 9500
        monkeypatch.setattr(VramGovernor, "_loaded_names", staticmethod(
            lambda: ["qwen2.5-coder:7b"]
        ))
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: type(
            "G", (), {"total_mb": 12288, "used_mb": 6800, "free_mb": 5488}
        )())

        ok, reason = gov.can_load("gemma4:12b", ctx=16384)
        assert not ok
        assert "Thiếu VRAM" in reason


class TestLoadedNames:
    def test_parses_ollama_ps_output(self, monkeypatch) -> None:
        """Phải đọc đúng tên từ bảng `ollama ps`."""
        fake = (
            "NAME           ID       SIZE    PROCESSOR  CONTEXT  UNTIL\n"
            "gemma4:12b     61145    8.0GB   100% GPU   16384    30 minutes\n"
            "qwen2.5-coder  dae16    4.7GB   100% GPU   16384    30 minutes\n"
        )
        monkeypatch.setattr("agentic.llm.vram.subprocess.run", lambda *a, **k: type(
            "R", (), {"stdout": fake, "returncode": 0}
        )())
        monkeypatch.setattr("agentic.llm.vram.shutil.which", lambda _: "ollama")

        names = VramGovernor._loaded_names()
        assert names == ["gemma4:12b", "qwen2.5-coder"]

    def test_handles_empty_table(self, monkeypatch) -> None:
        monkeypatch.setattr("agentic.llm.vram.subprocess.run", lambda *a, **k: type(
            "R", (), {"stdout": "NAME  ID  SIZE\n", "returncode": 0}
        )())
        monkeypatch.setattr("agentic.llm.vram.shutil.which", lambda _: "ollama")

        assert VramGovernor._loaded_names() == []



class TestVramThresholds:
    def test_blocks_when_insufficient(self, monkeypatch) -> None:
        gov = VramGovernor(reserve_mb=1200)
        gov.explicit_mb = 9500
        monkeypatch.setattr(VramGovernor, "_loaded_names", staticmethod(list))
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: type(
            "G", (), {"total_mb": 12288, "used_mb": 3000, "free_mb": 9288}
        )())

        ok, reason = gov.can_load("gemma4:12b", ctx=16384)
        assert not ok
        assert "Thiếu VRAM" in reason

    def test_allows_when_enough(self, monkeypatch) -> None:
        gov = VramGovernor(reserve_mb=1200)
        gov.explicit_mb = 9000
        monkeypatch.setattr(VramGovernor, "_loaded_names", staticmethod(list))
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: type(
            "G", (), {"total_mb": 12288, "used_mb": 1000, "free_mb": 11288}
        )())

        ok, _ = gov.can_load("gemma4:12b", ctx=16384)
        assert ok

    def test_explicit_mb_skips_kv_cache_addition(self, monkeypatch) -> None:
        """Con số khai trong profile đã gồm KV cache thì không cộng thêm."""
        gov = VramGovernor(reserve_mb=1200)
        gov.explicit_mb = 9500
        monkeypatch.setattr(VramGovernor, "_loaded_names", staticmethod(list))
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: type(
            "G", (), {"total_mb": 12288, "used_mb": 1000, "free_mb": 12000}
        )())

        ok, reason = gov.can_load("gemma4:12b", ctx=16384)
        # Nếu cộng thêm KV cache thì needed > 12000 và sẽ bị chặn.
        assert ok, reason
        assert "~9500MB" in reason


class TestNoGpu:
    def test_allows_when_gpu_unreadable(self, monkeypatch) -> None:
        """Không có GPU không phải lý do để chặn — máy chạy CPU vẫn được."""
        gov = VramGovernor(reserve_mb=1200)
        monkeypatch.setattr("agentic.llm.vram.read_gpu", lambda: None)

        ok, reason = gov.can_load("qwen2.5-coder:7b")
        assert ok
        assert "bỏ qua" in reason
