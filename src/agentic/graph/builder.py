"""Lắp graph chính và chạy thử vòng tranh luận thiết kế.

GĐ3 chỉ lắp tới phase thiết kế. Các phase Scrum, CI/CD, release sẽ nối
tiếp ở GĐ4-5.

Luồng hiện tại:

    START → design_council (subgraph) → render_design → GATE 1 → END

GATE 1 dùng interrupt() của LangGraph: hệ thống DỪNG, lưu toàn bộ state
vào SQLite, chờ bạn duyệt. Bạn chạy `agentic approve` để tiếp tục.
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agentic.agents import reporter
from agentic.graph.design_council import build_design_council
from agentic.memory.checkpointer import build_checkpointer, thread_config
from agentic.state import TeamState


# ── Node: sinh design.html ───────────────────────────────────────────────


def render_design_node(state: TeamState, cfg) -> dict:
    """Đưa thiết kế ra file HTML để bạn đọc trước khi duyệt.

    Node này CỐ Ý nằm TRƯỚC gate1. Nguyên tắc của LangGraph: side-effect
    phải hoàn tất TRƯỚC khi gọi interrupt(), vì khi resume node sẽ chạy
    lại từ đầu và side-effect sẽ lặp lần nữa.
    """
    payload = {
        "project": cfg.project["name"],
        "summary": _summarise(state),
        "design": state.get("design", {}).get("design", "Chưa có nội dung."),
        "decisions": state.get("design", {}).get("decisions", []),
        "design_tokens": state.get("design", {}).get("tokens", {}),
        "fallback_used": state.get("design", {}).get("fallback_used"),
        "rounds": state.get("debate_round", 0),
        # Blueprint là nguồn cho sơ đồ Mermaid, mockup UI, bảng rủi ro.
        "blueprint": state.get("blueprint", {}),
        "stories": state.get("stories", []),
        # Transcript đưa vào HTML để bạn thấy quá trình tranh luận,
        # không chỉ kết quả cuối.
        "debate": _debate_rows(state),
        "generated_at": _now(),
    }

    out = cfg.project_dir() / cfg.report.get("output", {}).get(
        "design", "design.html"
    )
    reporter.design_to_html(payload, out_path=out)

    return {
        "artifacts": [{"path": str(out), "type": "design_html"}],
        "transcript": [
            {
                "round": state.get("debate_round", 0),
                "agent": "reporter",
                "action": f"sinh {out.name}",
            }
        ],
    }


def _summarise(state: TeamState) -> str:
    """Một dòng tóm tắt cho tiêu đề báo cáo."""
    design = state.get("design", {})
    bp = state.get("blueprint", {})
    tokens = design.get("tokens") or {}
    palette = tokens.get("palette", {})
    screens = bp.get("screens", [])
    return (
        f"Sau {state.get('debate_round', 0)} vòng tranh luận · "
        f"{len(design.get('decisions', []))} quyết định · "
        f"{len(palette)} màu design token · "
        f"{len(screens)} màn hình · "
        f"{len(bp.get('risks', []))} rủi ro"
    )


def _debate_rows(state: TeamState) -> list[dict]:
    """Rút gọn transcript thành các dòng cho HTML.

    Chỉ lấy phần người đọc cần: ai nói gì, ở vòng nào. Không đưa toàn
    bộ JSON kỹ thuật vào báo cáo.
    """
    rows = []
    for entry in state.get("transcript", []):
        agent = entry.get("agent")
        if agent == "architect":
            detail = entry.get("design", "")
        elif entry.get("concerns") is not None:
            detail = "; ".join(
                f"[{c.get('severity')}] {c.get('issue')}"
                for c in entry.get("concerns", [])
            )
        else:
            detail = entry.get("action", "")

        rows.append({
            "round": entry.get("round", 0),
            "agent": agent,
            "action": entry.get("action", ""),
            "detail": detail,
        })
    return rows


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── Node: GATE 1 ─────────────────────────────────────────────────────────


def gate1_node(state: TeamState, cfg) -> dict:
    """Chặn chờ bạn duyệt bản thiết kế.

    Dùng interrupt() — hàm dừng của LangGraph. Khi gọi:
      1. Toàn bộ state được ghi vào SQLite
      2. Hàm trả về giá trị bạn truyền khi resume
    Khi bạn chạy `agentic approve --yes`, giá trị đó là {"approved": True}.

    Sau khi duyệt: graph.invoke(None, config) — truyền None nghĩa là
    "tiếp tục từ checkpoint", không phải "chạy lại từ đầu".
    """
    art = (state.get("artifacts") or [{}])[-1].get("path", "design.html")

    decision = interrupt({
        "type": "design_approval",
        "message": "Mở file design.html và duyệt bản thiết kế.",
        "file": str(art),
        "summary": _summarise(state),
        "rounds": state.get("debate_round", 0),
    })

    approved = bool((decision or {}).get("approved"))
    return {"gate1_result": {**(decision or {}), "approved": approved}}


def after_gate1(state: TeamState) -> Literal[END]:
    """Sau GATE 1: GĐ3 dừng ở đây.

    Khi bạn từ chối, cũng dừng — chứ không tự quay lại tranh luận, vì
    việc quay lại cần quyết định của bạn về việc sửa gì (GĐ4 mới làm).
    """
    return END


# ── Lắp graph ────────────────────────────────────────────────────────────


def build_graph(cfg):
    """Dựng toàn bộ graph và compile với checkpointer."""
    import functools as ft

    b = StateGraph(TeamState)

    council = build_design_council(cfg).compile()
    b.add_node("design_council", council)
    b.add_node("render_design", ft.partial(render_design_node, cfg=cfg))
    b.add_node("gate1", ft.partial(gate1_node, cfg=cfg))

    b.add_edge(START, "design_council")
    b.add_edge("design_council", "render_design")
    b.add_edge("render_design", "gate1")
    b.add_conditional_edges("gate1", after_gate1, {END: END})

    return b.compile(checkpointer=build_checkpointer(cfg))


def run_design_phase(cfg, requirement: str, mood: str = "đơn giản, dễ thương",
                     on_progress=None):
    """Chạy phase thiết kế từ yêu cầu đến GATE 1.

    Trả về (graph, config) để bạn có thể resume sau khi duyệt.

    Dùng stream thay vì invoke vì một lần chạy gồm 8-10 lượt gọi model,
    tổng cỡ 1-2 phút. invoke() im lặng suốt, nên lỡ gặp lỗi thì không
    biết đang kẹt ở node nào — đã gặp tình huống này. stream() cho ta
    thấy tiến triển từng bước mà vẫn trả về kết quả cuối.

    on_progress(node) được gọi sau mỗi node; mặc định là im lặng.
    """
    graph = build_graph(cfg)
    cfg.project_dir().mkdir(parents=True, exist_ok=True)

    payload = {"requirement": requirement, "mood": mood, "debate_round": 0}
    config = thread_config(cfg)

    # subgraphs=True là BẮT BUỘC: vòng tranh luận là một subgraph được
    # compile riêng rồi nhúng vào graph cha. Không có tham số này,
    # stream() chỉ yield khi CẢ subgraph xong — tức là im lặng suốt 1-2
    # phút rồi mới in ra một dòng, không hữu ích khi cần biết đang ở đâu.
    for chunk in graph.stream(
        payload, config=config, subgraphs=True, stream_mode="updates"
    ):
        # chunk là {(node, namespace): state_update}. Gọi callback để CLI
        # in tiến triển; không in ở đây để thư viện không phụ thuộc console.
        if on_progress:
            for key, update in chunk.items():
                node = key[0] if isinstance(key, tuple) else key
                on_progress(node, update)

    return graph, config
