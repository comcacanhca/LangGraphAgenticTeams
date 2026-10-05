"""JSON contract cho 6 tác tử + validator.

Vì sao cần: model 7B hay trả về JSON sai — thiếu khoá, thừa văn xuôi
quanh, hoặc nhầm kiểu. Nếu tin nó, lỗi lan xuống các phase sau và hệ
thống tạo ra project hỏng một cách âm thầm.

Nguyên tắc: không có JSON hợp lệ ⇒ coi như lượt gọi đó THẤT BẠI, thử lại
hoặc escalate. Không bao giờ "sửa tay cho qua".

Lỗi định dạng JSON thường tới từ 3 chỗ:
  1. Model bọc trong ```json ... ``` → tay sạch bằng strip_fence().
  2. Model thêm lời dẫn trước/sau JSON → cắt ra đoạn ngoặc.
  3. Model viết dấu nháy đơn kiểu Python → thử sửa.
"""

from __future__ import annotations

import json
import re
from typing import Any

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class SchemaError(ValueError):
    """Agent trả về JSON không khớp contract."""


def strip_fence(raw: str) -> str:
    """Bóc ```json ... ``` nếu model có bọc. Trả nguyên bản nếu không."""
    match = _FENCE.search(raw)
    return match.group(1) if match else raw


def extract_json(raw: str) -> str:
    """Cắt ra đoạn JSON từ câu trả lời có lẫn văn xuôi.

    Dùng CÂN BẰNG NGOẶC chứ không phải rfind("}"). Lý do: văn xuôi phía
    sau thường chứa ngoặc (ví dụ "...xong {xem lại}"), rfind sẽ khớp vào
    đó và cắt quá dài → json.loads báo "Extra data".
    """
    text = strip_fence(raw).strip()

    # Thử cân bằng ngoặc TRƯỚC. Dù đã bắt đầu bằng "{" thì vẫn phải
    # cắt chính xác, vì model có thể viết JSON rồi ghi chú thêm sau đó.
    block = _balanced_block(text, "{", "}")
    if block:
        return block

    block = _balanced_block(text, "[", "]")
    if block:
        return block

    return text


def _balanced_block(text: str, open_ch: str, close_ch: str) -> str | None:
    """Trả về khối đầy đủ từ open_ch tới close_ch tương ứng, hoặc None.

    Bỏ qua ngoặc nằm trong chuỗi — JSON chứa dấu ngoặc trong giá trị
    (ví dụ mô tả UI) rất phổ biến, đếm cả chúng sẽ ra sai số.
    """
    start = text.find(open_ch)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]

        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    # Không đóng ngoặc — trả None để thử chiến lược khác hoặc báo lỗi.
    return None


def parse_json(raw: str) -> Any:
    """Ép chuỗi thành JSON, thử lại vài cách trước khi bỏ cuộc."""
    text = extract_json(raw)
    if not text:
        raise SchemaError("Model không trả về nội dung JSON nào.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        first_error = exc

    # Sửa dấu nháy đơn kiểu Python: 'key': value  →  "key": value.
    # Chỉ thay dấu nháy đứng trước/sau một chuỗi rồi tới dấu hai chấm.
    try:
        return json.loads(re.sub(r"'([^'\"]*)'(\s*:)", r'"\1"\2', text))
    except json.JSONDecodeError:
        pass

    # Bỏ dấu phẩy thừa trước } hoặc ] — model hay thêm "cho chắc".
    try:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", text))
    except json.JSONDecodeError:
        pass

    pos = first_error.pos
    raise SchemaError(
        f"Không parse được JSON tại vị trí {pos}: {first_error.msg}\n"
        f"      Trích đoạn: {text[max(0, pos - 60):pos + 60]}"
    )


# ── contract từng tác tử ───────────────────────────────────────────────────


def validate_architect(payload: Any) -> dict:
    """Architect: thiết kế + quyết định đã kèm lý do."""
    data = _require_dict(payload)
    _require_keys(data, ["design", "decisions"], "architect")

    if not isinstance(data["design"], str) or len(data["design"].strip()) < 20:
        raise SchemaError("architect.design phải là mô tả ≥20 ký tự.")

    decisions = data["decisions"]
    if not isinstance(decisions, list) or not decisions:
        raise SchemaError("architect.decisions phải là danh sách không rỗng.")
    if len(decisions) > 10:
        raise SchemaError(
            f"architect.decisions có {len(decisions)} mục, tối đa 10. "
            "Quá nhiều quyết định = thiết kế không có trọng tâm."
        )

    # Mỗi quyết định phải kèm lý do — quyết định không có lý do thì vô nghĩa
    # khi bạn đọc lại design.html.
    for i, dec in enumerate(decisions):
        if not isinstance(dec, dict):
            raise SchemaError(f"decisions[{i}] phải là object.")
        _require_keys(dec, ["decision", "reason"], f"decisions[{i}]")

    return data


def validate_designer(payload: Any) -> dict:
    """Designer: design token. Màu phải là hex hợp lệ.

    Validator quan trọng nhất về mặt thẩm mỹ: model 7B rất dễ trả
    "pastel pink" hoặc "#FFF" sai định dạng. Thiếu kiểm tra này thì code
    Compose sinh ra sẽ không compile, vì Color() nhận Long chứ không
    phải chuỗi.
    """
    data = _require_dict(payload)
    _require_keys(data, ["palette", "typography"], "designer")

    palette = data["palette"]
    if not isinstance(palette, dict) or not palette:
        raise SchemaError("designer.palette phải là object không rỗng.")

    for name, value in palette.items():
        if not isinstance(value, str) or not _HEX.match(value.strip()):
            raise SchemaError(
                f"palette.{name} = {value!r} không phải mã hex hợp lệ. "
                'Cần dạng "#RRGGBB" hoặc "#RGB".'
            )

    return data


def validate_developer(payload: Any) -> dict:
    """Developer: danh sách file đã sửa + mô tả."""
    data = _require_dict(payload)
    _require_keys(data, ["changed_files", "summary"], "developer")

    files = data["changed_files"]
    if not isinstance(files, list):
        raise SchemaError("developer.changed_files phải là danh sách.")

    for i, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise SchemaError(f"changed_files[{i}] phải là object.")
        _require_keys(entry, ["path", "action"], f"changed_files[{i}]")
        if entry["action"] not in {"create", "modify", "delete"}:
            raise SchemaError(
                f"changed_files[{i}].action = {entry['action']!r} không hợp lệ. "
                "Chỉ nhận create / modify / delete."
            )

    if not isinstance(data["summary"], str) or not data["summary"].strip():
        raise SchemaError("developer.summary không được rỗng.")

    return data


def validate_qa(payload: Any) -> dict:
    """QA: kết luận PASS/FAIL.

    QA KHÔNG được tự tuyên PASS khi chưa chạy test. Validator ở đây chỉ
    kiểm hình dạng; việc chạy gradlew thuộc done_validator ở tầng scrum,
    và đó mới là nguồn sự thật.
    """
    data = _require_dict(payload)
    _require_keys(data, ["verdict", "tests", "defects"], "qa")

    if data["verdict"] not in {"PASS", "FAIL"}:
        raise SchemaError(
            f"qa.verdict = {data['verdict']!r} không hợp lệ. "
            "Chỉ nhận 'PASS' hoặc 'FAIL'."
        )

    if not isinstance(data["tests"], list):
        raise SchemaError("qa.tests phải là danh sách.")
    if not isinstance(data["defects"], list):
        raise SchemaError("qa.defects phải là danh sách.")

    # FAIL mà không có defect thì mâu thuẫn: hoặc model bịa, hoặc quên
    # ghi lý do.
    if data["verdict"] == "FAIL" and not data["defects"]:
        raise SchemaError(
            "qa.verdict='FAIL' nhưng defects rỗng. "
            "Phải nêu lý do cụ thể nào fail."
        )

    return data


def validate_devops(payload: Any) -> dict:
    """DevOps: artifact + trạng thái."""
    data = _require_dict(payload)
    _require_keys(data, ["artifacts", "status"], "devops")

    if not isinstance(data["artifacts"], list):
        raise SchemaError("devops.artifacts phải là danh sách.")
    if data["status"] not in {"OK", "WARN", "FAIL"}:
        raise SchemaError(
            f"devops.status = {data['status']!r} không hợp lệ. "
            "Chỉ nhận OK / WARN / FAIL."
        )
    return data


def validate_critic(payload: Any) -> dict:
    """Phản biện trong vòng tranh luận thiết kế."""
    data = _require_dict(payload)
    _require_keys(data, ["concerns"], "critic")

    concerns = data["concerns"]
    if not isinstance(concerns, list):
        raise SchemaError("critic.concerns phải là danh sách.")

    if not concerns:
        return {**data, "warning": "Không có phản biện nào."}

    for i, c in enumerate(concerns):
        if not isinstance(c, dict):
            raise SchemaError(f"concerns[{i}] phải là object.")
        _require_keys(c, ["issue", "severity"], f"concerns[{i}]")
        if c["severity"] not in {"low", "medium", "high", "blocker"}:
            raise SchemaError(
                f"concerns[{i}].severity = {c['severity']!r} không hợp lệ. "
                "Chỉ nhận low / medium / high / blocker."
            )
    return data


VALIDATORS = {
    "architect": validate_architect,
    "designer": validate_designer,
    "developer": validate_developer,
    "qa": validate_qa,
    "devops": validate_devops,
    "critic": validate_critic,
}


def validate(agent: str, raw: str) -> dict:
    """Parse + kiểm tra theo contract của agent. Ném SchemaError nếu sai."""
    fn = VALIDATORS.get(agent)
    if fn is None:
        raise SchemaError(
            f"Không có contract cho agent '{agent}'. "
            f"Đã có: {', '.join(sorted(VALIDATORS))}"
        )
    return fn(parse_json(raw))


# ── tiện ích ──────────────────────────────────────────────────────────────


def _require_dict(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise SchemaError(f"Cần JSON object, nhận {type(payload).__name__}.")
    return payload


def _require_keys(data: dict, keys: list[str], where: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise SchemaError(f"{where}: thiếu khoá {', '.join(missing)}.")
