"""Gọi model Ollama với retry, timeout và khoá tuần tự.

Ba quyết định thiết kế quan trọng:

1. SERIALIZE (khoá toàn cục): cả 6 tác tử dùng CHUNG một model. Nếu cho
   nhiều request chạy song song, chúng tranh nhau VRAM và OOM. Khoá
   buộc mọi lượt gọi đi tuần tự. Đánh đổi là mất tính song song, nhưng
   với 1 model trên 12GB thì đó là lựa chọn đúng.

2. format="json": Ollama ép model trả JSON hợp lệ ngay từ tầng server.
   Giảm tỉ lệ lỗi định dạng nhiều hơn cả mọi hack ở tầng Python.

3. keep_alive: giữ model nóng trong VRAM. Không có nó thì mỗi lượt gọi
   phải nạp lại 4.7GB từ đĩa — chậm và giật.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from agentic.llm.schema import SchemaError, validate
from agentic.llm.vram import VramGovernor, read_gpu


class LlmError(RuntimeError):
    """Không gọi được model, hoặc model trả về thứ không dùng được."""


@dataclass
class CallStat:
    """Thống kê một lần gọi — dùng để dựng benchmark.json."""

    agent: str
    seconds: float
    ok: bool
    attempts: int
    error: str = ""
    free_vram_mb: int = 0


@dataclass
class LlmClient:
    """Client Ollama cho toàn bộ hệ thống."""

    base_url: str
    model: str
    num_ctx: int
    temperature: float
    top_p: float
    keep_alive: str
    timeout_sec: int
    max_retries: int
    serialize: bool = True

    # Trần mặc định khi tác tử không khai báo max_tokens (hoặc khai 0).
    # Luôn hữu hạn: không có trần thì model sinh tới khi đầy context.
    default_max_tokens: int = 4000

    governor: VramGovernor | None = None

    # Model cloud do Ollama chuyển tiếp lên server, không nằm trong VRAM máy.
    # Nhận biết theo hậu tố `-cloud` trong tên, theo quy ước của Ollama —
    # không cần khai thêm cờ trong config, tránh cấu hình mâu thuẫn.
    @property
    def is_cloud(self) -> bool:
        return self.model.endswith("-cloud")
    stats: list[CallStat] = field(default_factory=list)

    # Khoá toàn cục: mọi lượt gọi model phải đi qua đây một lần.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_config(cls, cfg) -> "LlmClient":
        """Dựng client từ agents.yaml (đã resolve qua Config.model)."""
        model_cfg = cfg.model
        llm_cfg = cfg.llm

        # Model cloud qua mạng cần chờ lâu hơn nhiều: 31B tham số ở server
        # có thể mất 30-60 giây cho một lượt dài, trong khi 7B local chỉ 10s.
        # Cho phép profile ghi đè bằng `timeout_sec`.
        timeout = model_cfg.get("timeout_sec") or llm_cfg.get("timeout_sec", 300)

        client = cls(
            base_url=model_cfg.get("base_url", "http://localhost:11434"),
            model=model_cfg["name"],
            num_ctx=model_cfg["num_ctx"],
            temperature=model_cfg["temperature"],
            top_p=model_cfg.get("top_p", 0.9),
            keep_alive=model_cfg.get("keep_alive", "30m"),
            timeout_sec=timeout,
            max_retries=model_cfg.get("max_retries", 3),
            serialize=llm_cfg.get("serialize_calls", True),
            governor=VramGovernor(
                reserve_mb=cfg.gpu["reserve_mb"],
                single_model_only=cfg.gpu.get("single_model_only", True),
            ),
        )
        # Profile có thể ghi đè ngưỡng dự phòng: model nặng (gemma4:12b)
        # cần dự phòng nhỏ hơn vì máy không còn nhiều dung lượng.
        override = model_cfg.get("vram_estimate_mb")
        if override and client.governor is not None:
            client.governor.explicit_mb = int(override)
        return client

    # ── gọi thô ───────────────────────────────────────────────────────────

    def _post(self, payload: dict) -> dict:
        """POST /api/chat. Dùng urllib để không cài thêm thư viện HTTP."""
        url = f"{self.base_url}/api/chat"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise LlmError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise LlmError(
                f"Không gọi được Ollama tại {self.base_url}: {exc.reason}\n"
                "        Kiểm tra server đã chạy chưa (agentic doctor)."
            ) from exc
        except TimeoutError as exc:
            raise LlmError(
                f"Timeout sau {self.timeout_sec}s. Model có thể đang nạp lần đầu."
            ) from exc


    # ── gọi có contract ───────────────────────────────────────────────────

    def call_agent(
        self,
        agent: str,
        system_prompt: str,
        user_prompt: str,
        validate_output: bool = True,
        max_tokens: int | None = None,
    ) -> dict:
        """Gọi model và ép trả về đúng JSON theo contract của tác tử.

        Đây là hàm các node LangGraph sẽ gọi. Nó tự retry khi model trả
        sai định dạng — model 7B chuyển JSON sai khá thường xuyên, và
        thất bại ở lượt đầu không có nghĩa là thất bại vĩnh viễn.

        validate_output=False dùng cho prompt trung gian (ví dụ phản biện
        đọc thiết kế) nơi ta chỉ cần text, không cần JSON chặt.

        max_tokens truyền xuống thành `num_predict` của llama.cpp. Không có
        thì model sinh đến khi đầy context — một node phản biện có thể mất
        5 phút thay vì 10 giây. Đây là tham số BẮT BUỘC, không phải tuỳ chọn.
        """
        payload = {
            "model": self.model,
            "stream": False,
            # Ép JSON ngay từ server — hiệu quả hơn mọi cách sửa ở Python.
            "format": "json",
            # keep_alive chỉ có nghĩa với model CỤC BỘ (giữ trong VRAM).
            # Gửi cho model cloud là vô nghĩa, nên bỏ hẳn để payload sạch.
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
                "top_p": self.top_p,
                # Không có num_predict thì model sinh tới khi đầy context.
                # Một node phản biện đơn giản có thể mất 5 phút, cả vòng
                # tranh luận mất 15 phút — và ta không hề biết vì sao.
                # max_tokens=0 nghĩa là "không giới hạn", nên phải chặn.
                "num_predict": self._num_predict(max_tokens),
            },
        }
        if not self.is_cloud:
            payload["keep_alive"] = self.keep_alive

        started = time.perf_counter()
        last_error = ""
        attempts = 0

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                raw = self._invoke(payload)
                result = validate(agent, raw) if validate_output else {"raw": raw}
                self._record(agent, started, ok=True, attempts=attempt)
                return result
            except (LlmError, SchemaError) as exc:
                last_error = str(exc)
                # Lỗi kết nối không phải lỗi model — thử lại cũng vô ích.
                if isinstance(exc, LlmError):
                    self._record(agent, started, ok=False, attempts=attempt,
                                 error=last_error)
                    raise
                # Lỗi schema: thử lại, nhắc nghiêm ngặt hơn.
                payload["messages"][1]["content"] = (
                    f"{user_prompt}\n\n"
                    "LƯU Ý: lần trước JSON sai định dạng. "
                    "Chỉ trả về JSON hợp lệ, không thêm chữ nào khác."
                )
                if attempt < self.max_retries:
                    time.sleep(1.5)  # chờ chút, tránh spam model đang bận

        self._record(agent, started, ok=False, attempts=attempts, error=last_error)
        raise SchemaError(
            f"Tác tử '{agent}' không trả JSON hợp lệ sau {attempts} lần thử.\n"
            f"      Lỗi cuối: {last_error}"
        )

    def _num_predict(self, max_tokens: int | None) -> int:
        """Chốt trần số token model được sinh.

        Reporter có max_tokens=0 trong agents.yaml vì nó không gọi LLM, nhưng
        nếu ai đó vô tình bật LLM cho nó thì 0 sẽ thành "sinh vô hạn". Vì vậy
        luôn dùng một trần hữu hạn, kể cả khi cấu hình là 0.
        """
        if not max_tokens or max_tokens <= 0:
            return self.default_max_tokens
        # Không để trần vượt quá context: phần còn lại dành cho prompt.
        return min(max_tokens, self.num_ctx // 2)

    def _invoke(self, payload: dict) -> str:
        """Bọc _post bằng khoá tuần tự và kiểm tra VRAM trước.

        Model CLOUD bỏ qua kiểm tra VRAM: nó chạy trên server của Ollama,
        không chiếm VRAM máy này. Nếu vẫn kiểm tra, ước lượng 31B tham số
        (~62GB) sẽ vượt xa 12GB của máy và mọi lượt gọi bị chặn oan.
        """
        if self.governor is not None and not self.is_cloud:
            ok, reason = self.governor.can_load(self.model, self.num_ctx)
            if not ok:
                raise LlmError(f"VRAM không đủ để chạy model.\n        {reason}")

        if not self.serialize:
            return self._extract_content(self._post(payload))

        # Khoá toàn cục: chỉ một request chạm model mỗi lúc.
        with self._lock:
            return self._extract_content(self._post(payload))

    @staticmethod
    def _extract_content(resp: dict) -> str:
        """Lấy phần text từ response của Ollama."""
        try:
            return resp["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LlmError(f"Response thiếu message.content: {resp}") from exc

    def _record(
        self,
        agent: str,
        started: float,
        ok: bool,
        attempts: int,
        error: str = "",
    ) -> None:
        gpu = read_gpu()
        self.stats.append(
            CallStat(
                agent=agent,
                seconds=round(time.perf_counter() - started, 2),
                ok=ok,
                attempts=attempts,
                error=error,
                free_vram_mb=gpu.free_mb if gpu else 0,
            )
        )
