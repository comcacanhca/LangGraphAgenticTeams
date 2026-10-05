"""Báo cáo viên: sinh HTML. KHÔNG dùng mô hình ngôn ngữ.

Đây là quyết định thiết kế quan trọng nhất của hệ thống:

    Để model viết HTML → CSS hỏng, thiếu thẻ đóng, bảng vỡ layout,
                        rồi bạn phải tự sửa tay.
    Dùng Jinja2 với template cố định → HTML luôn đẹp, không bao giờ vỡ,
                                  bất kể model mạnh đến đâu.

Reporter chỉ điền DỮ LIỆU vào template. Nó không sinh nội dung, không
bịa số liệu, không gọi mạng. Số liệu trong báo cáo đến từ output thật
của Gradle, không phải lời tự nhận của agent.

config.py đã chặn use_llm=true cho reporter — xem _check_agents().

GĐ2 dùng f-string + html.escape để không phụ thuộc Jinja2. GĐ5 sẽ chuyển
sang template .j2 đầy đủ.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def _esc(value: Any) -> str:
    """Escape HTML.

    Không được bỏ: tên file, mô tả lỗi do model sinh ra có thể chứa
    ký tự < > và sẽ phá vỡ trang, thậm chí chèn script.
    """
    return html.escape(str(value if value is not None else ""))


# ── CSS dùng chung cho cả 2 báo cáo ───────────────────────────────────────
# Có dark mode theo hệ điều hành: report.theme.mode = auto trong
# agents.yaml, nên không cần người đọc bấm nút chuyển giao diện.
BASE_CSS = """\
  :root {{
    --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280;
    --line: #e5e7eb; --accent: #0F766E; --surface: #f9fafb;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#111827; --fg:#f3f4f6; --muted:#9ca3af;
             --line:#1f2937; --surface:#1f2937; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Inter, system-ui, -apple-system, sans-serif;
          margin:0; padding:2.5rem 1.5rem; background:var(--bg);
          color:var(--fg); line-height:1.65; }}
  main {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size:1.9rem; margin:0 0 .25rem; }}
  h2 {{ font-size:1.15rem; margin:2.5rem 0 1rem; padding-bottom:.5rem;
        border-bottom:1px solid var(--line); text-transform:uppercase;
        letter-spacing:.06em; color:var(--muted); }}
  .lede {{ color:var(--muted); margin:0 0 2rem; }}
  .panel {{ background:var(--surface); border:1px solid var(--line);
            border-radius:12px; padding:1.25rem 1.5rem; }}
  .muted {{ color:var(--muted); font-size:.85em; }}
  footer {{ margin-top:3rem; color:var(--muted); font-size:.82rem;
            border-top:1px solid var(--line); padding-top:1rem; }}
  code {{ font-family:ui-monospace,monospace; font-size:.9em;
          background:var(--surface); padding:.15rem .4rem;
          border-radius:4px; }}
"""

# ── CSS riêng cho design.html (swatch màu, bảng quyết định) ──────────────
# Lưu ý: mọi ngoặc nhọn trong CSS phải NHÂN ĐÔI. Dùng chuỗi thô (r"...")
# sẽ gặp xung đột với f-string nếu sau này cần chèn giá trị.
DESIGN_CSS = """\
  .swatches {{ display:flex; flex-wrap:wrap; gap:1rem; }}
  .swatch {{ text-align:center; width:104px; }}
  .chip {{ height:56px; border-radius:10px; border:1px solid var(--line); }}
  .swatch .name {{ display:block; font-size:.78rem; margin-top:.5rem; }}
  .swatch .hex {{ display:block; font-size:.72rem; color:var(--muted);
                  font-family:ui-monospace, monospace; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:.7rem .5rem;
            border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-size:.8rem; text-transform:uppercase; color:var(--muted);
        letter-spacing:.04em; }}
  .flag {{ background:#fef3c7; color:#92400e; padding:.6rem .9rem;
           border-radius:8px; font-size:.9rem; margin-top:1rem; }}
"""

# ── CSS riêng cho report.html (thẻ số liệu) ───────────────────────────────
REPORT_CSS = """\
  .stats {{ display:grid;
            grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
            gap:1rem; margin:1.5rem 0; }}
  .stat {{ background:var(--surface); border:1px solid var(--line);
           border-radius:12px; padding:1rem 1.2rem; }}
  .stat .n {{ font-size:1.6rem; font-weight:600; }}
  .stat .l {{ font-size:.8rem; color:var(--muted);
              text-transform:uppercase; letter-spacing:.04em; }}
  ul {{ padding-left:1.2rem; }}
  li {{ margin:.3rem 0; }}
"""


def _page(title: str, body: str, extra_css: str = "") -> str:
    """Bọc nội dung vào khung HTML hoàn chỉnh."""
    return (
        '<!DOCTYPE html>\n<html lang="vi">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f"<style>{BASE_CSS}{extra_css}</style>\n"
        f"</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )


def design_to_html(data: dict[str, Any], out_path: Path | None = None) -> str:
    """Dựng HTML cho bản thiết kế, để bạn xem ở GATE 1."""
    tokens = data.get("design_tokens") or {}
    palette = tokens.get("palette", data.get("palette", {}))

    swatches = "\n".join(
        f'      <div class="swatch">\n'
        f'        <div class="chip" style="background:{_esc(c)}"></div>\n'
        f'        <span class="name">{_esc(n)}</span>\n'
        f'        <span class="hex">{_esc(c)}</span>\n'
        f"      </div>"
        for n, c in palette.items()
    ) or '      <p class="muted">Chưa có design token.</p>'

    rows = "\n".join(
        f"      <tr><td>{_esc(d.get('decision'))}</td>"
        f"<td>{_esc(d.get('reason'))}</td></tr>"
        for d in data.get("decisions", [])
    ) or '      <tr><td colspan="2" class="muted">Chưa có quyết định.</td></tr>'

    flag = ""
    if data.get("fallback_used"):
        flag = (
            '  <div class="flag">Một số màu dùng palette dự phòng: '
            f'{_esc(", ".join(data["fallback_used"]))}</div>\n'
        )

    body = (
        f'  <h1>{_esc(data.get("project", "Bản thiết kế"))}</h1>\n'
        f'  <p class="lede">'
        f'{_esc(data.get("summary", "Tài liệu do các tác tử soạn."))}</p>\n\n'
        "  <h2>Nội dung thiết kế</h2>\n"
        f'  <div class="panel">'
        f'{_esc(data.get("design", "Chưa có nội dung."))}</div>\n\n'
        "  <h2>Design token</h2>\n"
        "  <div class=\"panel\">\n    <div class=\"swatches\">\n"
        f"{swatches}\n    </div>\n  </div>\n{flag}\n"
        "  <h2>Quyết định kiến trúc</h2>\n"
        "  <table>\n"
        "    <thead><tr><th>Quyết định</th><th>Lý do</th></tr></thead>\n"
        f"    <tbody>\n{rows}\n    </tbody>\n  </table>\n\n"
        "  <footer>Sinh bởi Reporter (không dùng LLM) · "
        f'{_esc(data.get("generated_at", ""))}</footer>'
    )

    title = data.get("project", "Bản thiết kế")
    return _write(_page(title, body, DESIGN_CSS), out_path)


def report_to_html(data: dict[str, Any], out_path: Path | None = None) -> str:
    """Dựng HTML cho báo cáo cuối dự án."""
    build = data.get("build", {})
    tests = data.get("tests", {})

    cards = "\n".join(
        f'    <div class="stat"><div class="n">{_esc(n)}</div>'
        f'      <div class="l">{_esc(label)}</div></div>'
        for n, label in [
            (build.get("result", "—"), "Build"),
            (tests.get("passed", "—"), "Test pass"),
            (data.get("sprints_done", "—"), "Sprint xong"),
            (data.get("open_defects", "—"), "Lỗi còn mở"),
        ]
    )

    items = "\n".join(
        f"      <li><code>{_esc(c.get('path'))}</code> "
        f'<span class="muted">{_esc(c.get("action"))}</span></li>'
        for c in data.get("changed_files", [])
    ) or '      <li class="muted">Chưa có thay đổi nào.</li>'

    body = (
        f'  <h1>Báo cáo dự án {_esc(data.get("project", ""))}</h1>\n'
        f'  <p class="lede">{_esc(data.get("summary", ""))}</p>\n\n'
        f'  <div class="stats">\n{cards}\n  </div>\n\n'
        "  <h2>File đã thay đổi</h2>\n"
        f'  <div class="panel">\n    <ul>\n{items}\n    </ul>\n  </div>\n\n'
        "  <h2>Ghi chú</h2>\n"
        '  <div class="panel">\n    <p class="muted">'
        "Số liệu lấy từ output thật của Gradle, không phải tự nhận "
        "của tác tử.</p>\n  </div>\n\n"
        "  <footer>Sinh bởi Reporter (không dùng LLM) · "
        f'{_esc(data.get("generated_at", ""))}</footer>'
    )

    return _write(_page(f"Báo cáo {data.get('project', '')}", body, REPORT_CSS), out_path)



def _write(text: str, out_path: Path | None) -> str:
    """Trả về HTML và ghi ra đĩa nếu có đường dẫn."""
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    return text
