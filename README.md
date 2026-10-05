# Hệ Agentic 6 Tác Tử — Sinh App Android

Hệ thống LangGraph gồm 6 tác tử thảo luận với nhau để sinh app Android,
chạy hoàn toàn trên máy local bằng Ollama.

```bash
agentic doctor                 # kiểm tra môi trường
agentic agents --list          # xem các tác tử
agentic benchmark              # đo độ tin cậy của model
pytest -m "not live"           # test nhanh (không gọi model)
pytest -m live                 # test đầy đủ với model thật
```

## Nguyên tắc thiết kế

**1. Cấu hình tập trung.** Mọi thứ — model, sandbox, quy trình Scrum,
version Android, CI/CD — nằm trong `agents.yaml`. Đổi model hay đổi
runner chỉ cần sửa file này, không đụng code.

**2. Máy là nguồn sự thật, không phải LLM.** Kết luận build pass/fail đến
từ `gradlew`. LLM chỉ được *đề xuất*, không được *tuyên bố*. Đây là điều
giữ cho hệ thống chạy được với model 7B yếu.

**3. Ràng buộc bằng code, không bằng lời dặn.** Agent không được ghi ra
ngoài workspace, không được commit keystore, không được tự kết luận thành
công — tất cả đều kiểm bằng code ở tầng tool, không phải trong prompt.
Vì LLM có thể bị prompt-injection, còn code thì không.

**4. Context có ngân sách.** Mỗi tác tử chỉ nhận trạng thái đã cô đọng,
không nhận toàn bộ lịch sử tranh luận. Không có quy tắc này thì hệ thống
tốn ~160K token mỗi sprint và không chạy nổi trên 12GB VRAM.

## Sáu tác tử

| Tác tử | Vai trò | Contract |
|---|---|---|
| **architect** | Phân rã yêu cầu, thiết kế, quyết định | `architect`, `backlog` |
| **designer** | Design token dạng JSON (màu hex) | `designer` |
| **developer** | Viết/sửa code, đọc log build | `developer` |
| **qa** | Test song song, review, phản biện | `qa`, `critic` |
| **devops** | Đóng gói, CI/CD, chặn secret | `devops`, `critic` |
| **reporter** | Xuất báo cáo HTML — **không dùng LLM** | không gọi model |

## Vì sao reporter không dùng LLM

Nếu để model sinh HTML trực tiếp: CSS hỏng, thiếu thẻ đóng, bảng vỡ
layout — rồi bạn phải tự sửa tay. Reporter là code thuần với template
cố định, nên HTML luôn đẹp và không bao giờ vỡ.

`config.py` chặn `use_llm: true` cho reporter ngay lúc khởi động.

## Cấu trúc

```
agents.yaml              ⭐ cấu hình duy nhất
prompts/                 7 file prompt (6 tác tử + critic)
src/agentic/
├─ config.py             đọc + validate cấu hình, fail sớm
├─ sandbox.py            chặn ghi ra ngoài workspace
├─ encoding.py           ép UTF-8 cho console Windows
├─ cli.py                doctor · config · benchmark · agents
├─ llm/
│  ├─ client.py          gọi Ollama, retry, serialize
│  ├─ schema.py          JSON contract + validator cho 7 contract
│  ├─ vram.py            đo VRAM, chặn OOM
│  └─ benchmark.py       đo độ tin cậy, so sánh model
├─ agents/               6 module tác tử
└─ (graph/, scrum/, cicd/, report/  — các giai đoạn sau)
workspace/               mọi project sinh ra, DUY NHẤT được ghi
.runtime/                checkpoint, log, Gradle cache (gitignored)
```

## Đổi model

```yaml
# agents.yaml
active_profile: test    # hoặc final
```

| Profile | Model | Context | Ghi chú |
|---|---|---|---|
| `test` | `qwen2.5-coder:7b` | 16K | Nhanh (~5s/lượt), đủ dùng khi test |
| `final` | `gemma4:12b` | 16K | Chậm hơn 5× (~28s/lượt), suy luận sâu hơn |

⚠ Gemma 4 hỗ trợ context 256K nhưng **RTX 3060 12GB không đủ VRAM** cho
`num_ctx` trên 16K — đã đo thực tế, model không nạp nổi.

Đổi model xong, chạy lại benchmark để so sánh bằng số liệu:

```bash
agentic benchmark --compare benchmark_qwen.json
```

## Yêu cầu môi trường

- Python 3.11+
- Ollama ≥ 0.35 đã cài và đang chạy
- JDK (Android Studio JBR 21)
- Android SDK với `platforms/android-35`
- NVIDIA GPU ~12GB

Chạy `agentic doctor` để kiểm tra đầy đủ.

## Giới hạn đã biết

| Giới hạn | Ảnh hưởng | Xử lý |
|---|---|---|
| Không có emulator | QA không chạy được test UI thật | Dùng JVM unit test + Robolectric |
| 1 model duy nhất | Các tác tử gọi **tuần tự** | Chấp nhận; đổi khi cần tốc độ |
| Máy không có `cmdline-tools` | Không tự cài thêm platform | Dùng bản compileSdk đã có |
| Ổ C: còn ~19GB | Gradle cache sẽ làm đầy ổ | `gradle_user_home` trỏ ổ D: |
