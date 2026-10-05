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
  /* ── Thẻ số liệu ── */
  .stats { display:grid;
           grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
           gap:.8rem; margin:1.5rem 0; }
  .stat { background:var(--surface); border:1px solid var(--line);
          border-radius:12px; padding:.9rem 1.1rem; }
  .stat .n { font-size:1.5rem; font-weight:600; line-height:1.2; }
  .stat .l { font-size:.74rem; color:var(--muted);
             text-transform:uppercase; letter-spacing:.05em; }

  /* ── Swatch màu ── */
  .swatches { display:flex; flex-wrap:wrap; gap:1rem; }
  .swatch { text-align:center; width:104px; }
  .chip { height:56px; border-radius:10px; border:1px solid var(--line); }
  .swatch .name { display:block; font-size:.78rem; margin-top:.5rem; }
  .swatch .hex { display:block; font-size:.72rem; color:var(--muted);
                 font-family:ui-monospace, monospace; }

  /* ── Bảng ── */
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:.7rem .5rem;
           border-bottom:1px solid var(--line); vertical-align:top; }
  th { font-size:.78rem; text-transform:uppercase; color:var(--muted);
       letter-spacing:.04em; }
  .flag { background:#fef3c7; color:#92400e; padding:.6rem .9rem;
          border-radius:8px; font-size:.9rem; margin-top:1rem; }

  /* ── Sơ đồ Mermaid ── */
  .diagram { background:var(--surface); border:1px solid var(--line);
             border-radius:12px; padding:1.5rem; margin:.5rem 0;
             overflow-x:auto; text-align:center; }
  .diagram.error { color:#b91c1c; font-family:ui-monospace,monospace;
                   font-size:.82rem; text-align:left; white-space:pre-wrap; }
  .mermaid { display:none; }
  .diagram .loading { color:var(--muted); font-size:.85rem; }

  /* ── Mockup màn hình điện thoại ── */
  .phones { display:flex; flex-wrap:wrap; gap:1.5rem; }
  .phone { width:270px; border:1px solid var(--line);
           border-radius:26px; overflow:hidden;
           background:var(--phone-bg, #fff);
           box-shadow:0 6px 20px rgba(0,0,0,.09); }
  .phone .screen { padding:14px 14px 18px; min-height:330px;
                   display:flex; flex-direction:column; gap:9px; }
  .phone .bar { display:flex; align-items:center; gap:6px;
                font-size:.7rem; color:var(--phone-muted, #888);
                padding-bottom:6px; }
  .phone .el { font-size:.78rem; line-height:1.45;
               color:var(--phone-text, #222); }
  .ph-title { font-size:.95rem; font-weight:700;
              color:var(--phone-text, #222); }
  .ph-box { border:1px solid var(--phone-line, #e6e6e6);
            border-radius:12px; padding:.7rem .8rem; }
  .ph-btn { border-radius:999px; padding:.6rem 1rem; text-align:center;
            font-size:.8rem; font-weight:600; color:#fff; }
  .ph-input { border:1px dashed var(--phone-line, #ccc);
              border-radius:10px; padding:.55rem .7rem;
              font-size:.75rem; color:var(--phone-muted, #999); }
  .ph-row { display:flex; gap:6px; flex-wrap:wrap; }
  .phone .cap { font-size:.72rem; color:var(--muted); text-align:center;
                padding:8px 4px 4px; border-top:1px solid var(--line); }
  .purpose { font-size:.78rem; color:var(--muted); font-style:italic; }

  /* ── Rủi ro ── */
  .risk { display:inline-block; padding:.1rem .5rem; border-radius:5px;
          font-size:.7rem; font-weight:600; white-space:nowrap; }
  .risk-cao { background:#fee2e2; color:#991b1b; }
  .risk-tb { background:#fef3c7; color:#92400e; }
  .risk-thap { background:#dcfce7; color:#166534; }

  /* ── Vòng tranh luận ── */
  .round { display:inline-block; min-width:2rem; text-align:center;
           background:var(--accent); color:#fff; border-radius:999px;
           padding:.1rem .5rem; font-size:.72rem; font-weight:600; }
  .who { font-weight:600; white-space:nowrap; }
  .detail { color:var(--fg); opacity:.9; font-size:.94rem; }
  .empty { color:var(--muted); font-style:italic; }
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


def _page(
    title: str, body: str, extra_css: str = "", mermaid: bool = False
) -> str:
    """Bọc nội dung vào khung HTML hoàn chỉnh.

    mermaid=True nhúng mermaid.js đã bundle sẵn trong thư mục vendor, nên
    sơ đồ vẽ được khi MÁY KHÔNG CÓ MẠNG. Đây là điểm quan trọng: báo
    cáo phải mở được trên máy offline, không phụ thuộc CDN.
    """
    script = ""
    if mermaid:
        js = _read_mermaid()
        if js:
            script = (
                f"<script>{js}</script>\n"
                "<script>\n"
                "  mermaid.initialize({startOnLoad:true, theme:'default',\n"
                "    securityLevel:'loose', flowchart:{htmlLabels:true}});\n"
                "</script>\n"
            )
        else:
            # Không có file mermaid.js → vẫn trả HTML, chỉ mất sơ đồ.
            # Báo rõ thay vì im lặng để bạn không tưởng sơ đồ bị lỗi cú pháp.
            script = (
                "<style>.diagram .loading:after{content:' (thiếu mermaid.js)'}"
                "</style>\n"
            )

    return (
        '<!DOCTYPE html>\n<html lang="vi">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f"<style>{BASE_CSS}{extra_css}</style>\n"
        f"{script}"
        "</head>\n<body>\n<main>\n"
        f"{body}\n"
        "</main>\n</body>\n</html>\n"
    )


_MERMAID_CACHE: str | None = None


def _read_mermaid() -> str:
    """Đọc mermaid.min.js từ thư mục vendor, nhúng thẳng vào HTML.

    Nhúng inline thay vì thẻ <script src="..."> vì file:// của trình duyệt
    chặn tải script ngoài — nhúng inline thì luôn chạy.
    """
    global _MERMAID_CACHE
    if _MERMAID_CACHE is not None:
        return _MERMAID_CACHE

    path = Path(__file__).parent.parent / "report" / "vendor" / "mermaid.min.js"
    try:
        _MERMAID_CACHE = path.read_text(encoding="utf-8")
    except OSError:
        _MERMAID_CACHE = ""
    return _MERMAID_CACHE


def _mockup_html(screens: list[dict], tokens: dict) -> str:
    """Dựng mockup màn hình điện thoại bằng HTML/CSS thuần.

    Dùng đúng màu Designer chọn, nên bạn thấy giao diện thật mà chưa cần
    dựng project Android. Không dùng ảnh vì bản vẽ bằng HTML luôn sắc
    nét, đổi màu được ngay, và không cần model tạo ảnh.

    Phân loại phần tử theo từ khoá trong tên để chọn kiểu hiển thị: tiêu
    đề, nút, ô nhập, thẻ, hay khối nội dung.
    """
    if not screens:
        return '      <p class="empty">Thiết kế chưa mô tả màn hình nào.</p>\n'

    palette = (tokens or {}).get("palette", {})
    p_bg = palette.get("background", "#FFF9F5")
    p_surface = palette.get("surface", "#FFFFFF")
    p_text = palette.get("text", "#3D3A45")
    p_primary = palette.get("primary", "#F8A5C2")
    p_secondary = palette.get("secondary", "#B8E0D2")
    p_accent = palette.get("accent", "#FFD166")

    # Nội suy biến CSS để mockup đổi màu theo design token.
    css = (
        f"--phone-bg:{p_bg};--phone-text:{p_text};"
        f"--phone-line:{p_secondary};"
        f"--phone-muted:{_mix(p_text, p_bg, 0.45)};"
    )

    out = [f'      <div class="phones" style="{css}">']
    for screen in screens:
        out.append(
            _one_phone(
                screen, p_text, p_primary, p_secondary, p_accent, p_surface
            )
        )
    out.append("      </div>")
    return "\n".join(out) + "\n"


def _one_phone(
    screen: dict, text: str, primary: str, secondary: str, accent: str,
    surface: str,
) -> str:
    """Dựng một khung điện thoại với các phần tử bên trong."""
    parts = [
        '        <div class="phone">',
        '          <div class="screen">',
        '            <div class="bar">'
        '<span>9:41</span><span style="margin-left:auto">● ● ▮</span></div>',
        f'            <div class="el ph-title">{_esc(screen.get("name"))}</div>',
    ]

    for element in screen.get("elements", [])[:7]:
        parts.append(
            "            "
            + _render_element(
                element, text, primary, secondary, accent, surface
            )
        )

    parts.append("          </div>")
    parts.append(
        f'          <div class="cap">{_esc(screen.get("purpose", ""))}</div>'
    )
    parts.append("        </div>")
    return "\n".join(parts)


def _render_element(
    element: str, text: str, primary: str, secondary: str, accent: str,
    surface: str,
) -> str:
    """Chọn kiểu hiển thị cho một phần tử, dựa trên từ khoá trong tên."""
    low = element.lower()

    if any(k in low for k in ("tiêu đề", "tieu de", "title", "heading")):
        return f'<div class="el ph-title">{_esc(element)}</div>'

    if any(k in low for k in ("nút", "nut ", "button", "btn")):
        return (
            f'<div class="el ph-btn" style="background:{primary}">'
            f"{_esc(element)}</div>"
        )

    if any(k in low for k in ("nhập", "input", "textfield", "search", "ô ")):
        return f'<div class="el ph-input">{_esc(element)}</div>'

    if any(k in low for k in ("danh sách", "list", "lịch", "lich", "card")):
        # Vẽ vài dòng giả lập để thấy độ dài danh sách.
        return (
            f'<div class="el ph-box" style="background:{surface}">'
            f'{_esc(element)}<br>· · ·<br>· · ·</div>'
        )

    if any(k in low for k in ("ảnh", "anh", "image", "icon", "avatar")):
        return (
            f'<div class="el ph-box" style="background:{accent};'
            f'text-align:center">◻ {_esc(element)}</div>'
        )

    return (
        f'<div class="el ph-box" style="background:{secondary}">'
        f"{_esc(element)}</div>"
    )


def _mix(c1: str, c2: str, ratio: float) -> str:
    """Trộn hai mã hex — dùng cho màu chữ phụ trong mockup."""
    try:
        a = [int(c1.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
        b = [int(c2.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
        return "#" + "".join(
            f"{round(x + (y - x) * ratio):02x}" for x, y in zip(a, b)
        )
    except (ValueError, IndexError):
        # Màu không phải hex → trả về màu phụ an toàn.
        return "#888888"


def _diagram_html(source: str, title: str) -> str:
    """Bọc mã Mermaid vào khung chờ render.

    Mermaid chạy ở trình duyệt. Nội dung <pre class="mermaid"> bị ẩn cho tới
    khi mermaid.js biến nó thành SVG. Nếu JS lỗi hoặc không tải được, khung
    sẽ hiện thông báo thay vì trống trơn — bạn luôn biết chuyện gì xảy ra.
    """
    if not source:
        return ""
    return (
        f'  <h3 class="sub">{_esc(title)}</h3>\n'
        '  <div class="diagram">\n'
        '    <p class="loading">Đang vẽ sơ đồ…</p>\n'
        f'    <pre class="mermaid">{_esc(source)}</pre>\n'
        "  </div>\n"
    )



def design_to_html(data: dict[str, Any], out_path: Path | None = None) -> str:
    """Dựng bản thiết kế đầy đủ để bạn duyệt ở GATE 1.

    11 mục, từ số liệu tổng quan tới mockup UI và sơ đồ Mermaid.
    """
    tokens = data.get("design_tokens") or {}
    palette = tokens.get("palette", data.get("palette", {}))
    bp = data.get("blueprint") or {}

    parts: list[str] = []

    # ── 1. Tiêu đề + thẻ số liệu ──
    cards = [
        (data.get("rounds", 0), "vòng tranh luận"),
        (len(data.get("decisions", [])), "quyết định kiến trúc"),
        (len(palette), "màu design token"),
        (len(bp.get("screens", [])), "màn hình"),
        (len(bp.get("risks", [])), "rủi ro đã nhận diện"),
    ]
    stat_html = "\n".join(
        f'    <div class="stat"><div class="n">{_esc(n)}</div>'
        f'      <div class="l">{_esc(label)}</div></div>'
        for n, label in cards
    )
    parts.append(f'  <h1>{_esc(data.get("project", "Bản thiết kế"))}</h1>')
    parts.append(
        f'  <p class="lede">{_esc(data.get("summary", ""))}</p>'
    )
    parts.append(f'  <div class="stats">\n{stat_html}\n  </div>')

    # ── 2. Tổng quan ──
    overview = bp.get("overview") or data.get("design", "")
    parts.append("  <h2>Tổng quan thiết kế</h2>")
    parts.append(f'  <div class="panel">{_esc(overview)}</div>')

    # ── 3. Sơ đồ kiến trúc (Mermaid) ──
    parts.append("  <h2>Sơ đồ kiến trúc</h2>")
    parts.append(
        _diagram_html(bp.get("architecture_diagram", ""), "Các tầng")
    )

    # ── 4. Mô hình dữ liệu (Mermaid) ──
    parts.append("  <h2>Mô hình dữ liệu</h2>")
    parts.append(_diagram_html(bp.get("data_model", ""), "Các bảng"))

    # ── 5. Mockup màn hình ──
    parts.append("  <h2>Mockup màn hình</h2>")
    parts.append(
        '  <p class="lede">Dựng từ design token — màu sắc chính là màu '
        'sẽ dùng trong app.</p>'
    )
    parts.append(_mockup_html(bp.get("screens", []), tokens))

    # ── 6. Design token ──
    swatches = "\n".join(
        f'      <div class="swatch">\n'
        f'        <div class="chip" style="background:{_esc(c)}"></div>\n'
        f'        <span class="name">{_esc(n)}</span>\n'
        f'        <span class="hex">{_esc(c)}</span>\n'
        f"      </div>"
        for n, c in palette.items()
    ) or '      <p class="empty">Chưa có design token.</p>'

    parts.append("  <h2>Design token</h2>")
    parts.append(f'  <div class="panel swatches">\n{swatches}\n  </div>')
    if data.get("fallback_used"):
        parts.append(
            '  <div class="flag">Một số màu dùng palette dự phòng: '
            f'{_esc(", ".join(data["fallback_used"]))}</div>'
        )

    # ── 7. Quyết định kiến trúc ──
    rows = "\n".join(
        f"      <tr><td>{_esc(d.get('decision'))}</td>"
        f"<td>{_esc(d.get('reason'))}</td></tr>"
        for d in data.get("decisions", [])
    ) or '      <tr><td colspan="2" class="empty">Chưa có quyết định.</td></tr>'

    parts.append("  <h2>Quyết định kiến trúc</h2>")
    parts.append(
        "  <table>\n"
        "    <thead><tr><th>Quyết định</th><th>Lý do</th></tr></thead>\n"
        f"    <tbody>\n{rows}\n    </tbody>\n  </table>"
    )

    # ── 8. Rủi ro ──
    risk_rows = "\n".join(
        f"      <tr><td>{_esc(r.get('risk'))}</td>"
        f'<td><span class="risk {_risk_class(r.get("impact"))}">'
        f'{_esc(r.get("impact"))}</span></td>'
        f"<td>{_esc(r.get('mitigation'))}</td></tr>"
        for r in bp.get("risks", [])
    )
    if risk_rows:
        parts.append("  <h2>Rủi ro đã nhận diện</h2>")
        parts.append(
            "  <table>\n"
            "    <thead><tr><th>Rủi ro</th><th>Mức độ</th>"
            "<th>Cách xử lý</th></tr></thead>\n"
            f"    <tbody>\n{risk_rows}\n    </tbody>\n  </table>"
        )

    # ── 9. Kế hoạch sprint ──
    if data.get("stories"):
        story_rows = "\n".join(
            f"      <tr><td><code>{_esc(s.get('id'))}</code></td>"
            f"<td>{_esc(s.get('title'))}</td>"
            f'<td class="detail">{_esc("; ".join(s.get("acceptance_criteria", [])))}</td></tr>'
            for s in data["stories"]
        )
        parts.append("  <h2>Kế hoạch phát triển</h2>")
        parts.append(
            "  <table>\n"
            "    <thead><tr><th>ID</th><th>User story</th>"
            "<th>Tiêu chí nghiệm thu</th></tr></thead>\n"
            f"    <tbody>\n{story_rows}\n    </tbody>\n  </table>"
        )

    # ── 10. Quá trình tranh luận ──
    debate = "\n".join(
        "      <tr>"
        f'<td><span class="round">{_esc(e.get("round", 0))}</span></td>'
        f'<td class="who">{_esc(e.get("agent"))}</td>'
        f'<td class="detail">{_esc(e.get("detail", ""))}</td>'
        "</tr>"
        for e in data.get("debate", [])
    )
    parts.append("  <h2>Quá trình tranh luận</h2>")
    if debate:
        parts.append(
            "  <table>\n"
            "    <thead><tr><th>Vòng</th><th>Tác tử</th>"
            "<th>Nội dung</th></tr></thead>\n"
            f"    <tbody>\n{debate}\n    </tbody>\n  </table>"
        )
    else:
        parts.append(
            '  <div class="panel"><p class="empty">Chưa có lượt tranh luận.</p></div>'
        )

    # ── 11. Chân trang ──
    parts.append(
        "  <footer>Sinh bởi Reporter (không dùng LLM) · "
        f'{_esc(data.get("generated_at", ""))}</footer>'
    )

    body = "\n".join(parts)
    title = data.get("project", "Bản thiết kế")
    return _write(_page(title, body, DESIGN_CSS, mermaid=True), out_path)


def _risk_class(impact: str) -> str:
    """Ánh xạ mức độ rủi ro sang class CSS."""
    low = (impact or "").lower()
    if "cao" in low or "high" in low:
        return "risk-cao"
    if "thấp" in low or "low" in low:
        return "risk-thap"
    return "risk-tb"


# ── CSS riêng cho report.html (thẻ số liệu) ───────────────────────────────
REPORT_CSS = """\
  .stats { display:grid;
           grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
           gap:1rem; margin:1.5rem 0; }
  .stat { background:var(--surface); border:1px solid var(--line);
          border-radius:12px; padding:1rem 1.2rem; }
  .stat .n { font-size:1.6rem; font-weight:600; }
  .stat .l { font-size:.8rem; color:var(--muted);
             text-transform:uppercase; letter-spacing:.04em; }
  ul { padding-left:1.2rem; }
  li { margin:.3rem 0; }
  code { font-family:ui-monospace,monospace; font-size:.9em;
         background:var(--surface); padding:.15rem .4rem;
         border-radius:4px; }
"""


def report_to_html(data: dict[str, Any], out_path: Path | None = None) -> str:
    """Dựng báo cáo cuối dự án."""
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

    return _write(_page(f"Báo cáo {data.get('project', '')}", body, REPORT_CSS),
                  out_path)


def _write(text: str, out_path: Path | None) -> str:
    """Trả về HTML và ghi ra đĩa nếu có đường dẫn."""
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    return text


