"""Vòng tranh luận thiết kế — subgraph LangGraph.

Sơ đồ một vòng:

    architect ─── đề xuất/sửa thiết kế ──┐
        │                                  │
        ├─ Send ─┬─ developer  (khả thi?)   │
        │         ├─ qa         (test được?)│
        │         └─ devops     (rủi ro?)   │
        │                     │
        │              converge_router ───┬── hội tụ ──► END (đi tiếp)
        │                                  └── chưa ────┐
        │                                               │
        └───────────────────────────────────────────────┘

Ba điều thiết kế quan trọng:

1. FAN-OUT KHÔNG THẬT SỰ SONG SONG. Dùng Send để 3 tác tử nhận cùng
   thiết kế, nhưng cả 3 dùng CHUNG một model Ollama nên chạy tuần tự
   (client đã có khoá). Khai báo song song là đúng về mô hình dữ liệu,
   serialize là đúng về tài nguyên.

2. HỘI TỤ KIỂM BẰNG MÁY, KHÔNG BẰNG CẢM TÍNH. Chỉ dừng khi hết phản
   biện nghiêm trọng HOẶC hết số vòng cho phép. Không có đường "cảm thấy
   ổn rồi thì dừng" — đó là chỗ hệ multi-agent tự trì dẫn vào vòng luẩn.

3. KHÔNG BAO GIỜ TRUYỀN TRANSCRIPT CHO TÁC TỦ. Chỉ truyền `design`
   hiện tại + phản biện mới. Xem state.py để hiểu vì sao.
"""

from __future__ import annotations

import re
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agentic.agents import architect, designer, developer, devops, qa
from agentic.agents.base import AgentError, build_agent
from agentic.state import TeamState

# Ngưỡng nghiêm trọng: phản biện nhẹ (low/medium) không chặn hội tụ.
# Nếu chặn cả phản biện nhẹ thì vòng tranh luận không bao giờ kết thúc.
BLOCKING_SEVERITIES = {"high", "blocker"}

# Số phản biện mong đợi từ mỗi tác tủ. Không ép quá nhiều — model 7B dễ
# bịa phản biện cho đủ số lượng thay vì phản biện có thật.
MIN_CONCERNS = 3


def _cfg_block(cfg) -> dict[str, Any]:
    """Thông tin môi trường cho prompt của DevOps.

    Truyền thật để DevOps không phải đoán: máy này không có emulator,
    CI chạy Windows, cache Gradle ở ổ D:.
    """
    return {
        "runner": cfg.cicd["runner"],
        "java_version": cfg.cicd["java_version"],
        "has_emulator": cfg.android.get("emulator_available", False),
        "gradle_cache_on_d": ":\\" in str(cfg.android["gradle_user_home"]),
        "compile_sdk": cfg.android["compile_sdk"],
        "test_task": cfg.android["tasks"]["test"],
        "build_task": cfg.android["tasks"]["build"],
    }


# ── Node: Architect ──────────────────────────────────────────────────────


def architect_node(state: TeamState, cfg) -> dict:
    """Architect đề xuất (vòng 0) hoặc sửa (các vòng sau).

    Ghi transcript để bạn đọc lại, nhưng KHÔNG đưa vào context tác tủ.
    """
    rnd = state.get("debate_round", 0)

    # ★ Chặn vòng lặp vô hạn TRƯỚC KHI gọi model.
    #
    # Lý do cần: nếu node sập vì lỗi (NameError, KeyError…) thì LangGraph
    # retry. Node sập không ghi state, nên debate_round không tăng, nên lần
    # sau vẫn rơi vào cùng nhánh → lặp vô hạn, mỗi lần gọi model mất
    # hàng phút. Đã xảy ra thật: một lỗi gọi nhầm tên hàm làm treo 8
    # phút và tạo 192 checkpoint trước khi phát hiện.
    #
    # remaining_steps là bộ đếm của LangGraph; khi còn ít thì biết chắc
    # sắp chạm trần. Dừng lại và báo bạn tốt hơn là treo.
    remaining = state.get("remaining_steps", 99)
    if isinstance(remaining, int) and remaining <= 2:
        return _error(
            state,
            f"Architect: sắp chạm giới hạn bước (còn {remaining}). "
            "Có thể vòng tranh luận không hội tụ — xem transcript.",
        )

    agent = build_agent("architect", cfg)

    try:
        if rnd == 0:
            result = architect.propose(agent, state["requirement"])
            action = "đề xuất thiết kế"
        else:
            critiques = [c["text"] for c in state.get("pending_critiques", [])]
            result = architect.revise(
                agent, state["design"]["design"], critiques
            )
            action = f"sửa thiết kế sau vòng {rnd}"
    except (AgentError, ValueError) as exc:
        # _error, KHÔNG phải _escalate — hàm đó không tồn tại. Gọi sai tên
        # làm NameError, mà NameError KHÔNG thuộc except ở trên nên nó
        # nổi lên và làm node sập → retry vô hạn.
        return _error(state, f"Architect: {exc}")

    return {
        "design": {**state.get("design", {}), **result, "round": rnd},
        "pending_critiques": [],
        "transcript": [
            {
                "round": rnd,
                "agent": "architect",
                "action": action,
                "design": result["design"],
                "decisions": result.get("decisions", []),
            }
        ],
    }



# ── Node: 3 tác tủ phản biện ─────────────────────────────────────────────
#
# Cả 3 dùng chung một hàm vì logic giống hệt nhau; chỉ khác lăng kính soi.
# Viết 3 hàm riêng sẽ lặp code mà không thêm giá trị.


class _DeveloperCritic:
    """Adapter để Developer dùng chung hàm phản biện của QA/DevOps.

    Developer không có hàm critique_design riêng vì vai trò của nó trong
    vòng tranh luận là phản biện KHẢ THI KỸ THUẬT — cùng dạng với hai
    tác tủ kia, chỉ khác lăng kính.
    """

    @staticmethod
    def critique_design(agent, design: str) -> dict:
        prompt = f"""THIẾT KẾ CẦN ĐÁNH GIÁ:
{design}

Hãy phản biện với vai trò kỹ sư phần mềm senior. Tập trung vào:

1. Cấu trúc dữ liệu này có hợp lý không? Có chỗ nào khó mở rộng?
2. Có phần nào trong thiết kế này KHÔNG build được với Compose?
3. Rủi ro hiệu năng: có chỗ nào chậm khi dữ liệu lớn lên?
4. Thiết kế này có dễ sửa khi yêu cầu thay đổi không?

Nếu không có vấn đề nghiêm trọng, để concerns rỗng.

Trả về JSON dạng:
{{"concerns": [{{"issue": "mô tả vấn đề", "severity": "low|medium|high|blocker"}}]}}"""

        return agent.ask(prompt, contract="critic")

def _flatten(concerns: list[dict]) -> str:
    """Gộp phản biện thành chuỗi cho prompt của Architect.

    Ghi kèm [severity] để converge_router đọc được mức nghiêm trọng mà
    không cần thêm trường riêng vào transcript.
    """
    return "\n".join(
        f"- [{c.get('severity')}] {c.get('issue')}" for c in concerns
    )




def _critic_node(
    state: TeamState, cfg, name: str, module, note: str
) -> dict:
    """Chạy một tác tủ phản biện, ghi kết quả vào transcript."""
    agent = build_agent(name, cfg)
    try:
        result = module.critique_design(agent, state["design"]["design"])
    except AgentError as exc:
        return _error(state, f"{name}: {exc}")

    concerns = result.get("concerns", [])

    return {
        "transcript": [
            {
                "round": state.get("debate_round", 0),
                "agent": name,
                "action": note,
                "concerns": concerns,
                # text ghi kèm [severity] để converge_router đọc được.
                "text": _flatten(concerns),
            }
        ]
    }


def developer_critic(state: TeamState, cfg) -> dict:
    return _critic_node(
        state, cfg, "developer", _DeveloperCritic(), "phản biện khả thi kỹ thuật"
    )


def qa_critic(state: TeamState, cfg) -> dict:
    return _critic_node(state, cfg, "qa", qa, "phản biện khả thi kiểm thử")


def devops_critic(state: TeamState, cfg) -> dict:
    return _critic_node(
        state, cfg, "devops", devops, "phản biện rủi ro triển khai"
    )


# ── Node: Designer ───────────────────────────────────────────────────────


def designer_node(state: TeamState, cfg) -> dict:
    """Designer xuất design token từ thiết kế đã hội tụ.

    Chạy SAU khi hội tụ, không chen vào vòng tranh luận. Màu sắc chỉ quyết
    định sau khi luồng chức năng đã ổn, và đổi màu không làm thay đổi kiến
    trúc nên không cần phản biện lại.
    """
    agent = build_agent("designer", cfg)
    try:
        tokens = designer.design_tokens(
            agent,
            app_purpose=state["design"]["design"],
            mood=state.get("mood", "đơn giản, dễ thương"),
        )
    except AgentError as exc:
        return _error(state, f"Designer: {exc}")

    return {
        "design": {**state["design"], "tokens": tokens},
        "transcript": [
            {
                "round": state.get("debate_round", 0),
                "agent": "designer",
                "action": "xuất design token",
                "palette": tokens.get("palette", {}),
                "fallback_used": tokens.get("fallback_used"),
            }
        ],
    }


# ── Router: hội tụ ───────────────────────────────────────────────────────


def collect_critique(state: TeamState) -> dict:
    """Gom phản biện của 3 tác tủ thành danh sách cho Architect.

    Chỉ lấy phản biện của VÒNG HIỆN TẠI. Lấy cả lịch sử sẽ khiến
    Architect sửa đi sửa lại vấn đề đã giải quyết xong.
    """
    round_now = state.get("debate_round", 0)
    critiques = [
        {"text": e["text"], "agent": e["agent"]}
        for e in state.get("transcript", [])
        if e.get("round") == round_now
        and e.get("agent") in {"developer", "qa", "devops"}
        and e.get("text")
    ]
    return {"pending_critiques": critiques}


def converge_router(state: TeamState, cfg) -> dict:
    """Quyết định hội tụ và LƯU KẾT QUẢ vào state.

    Đây là node QUAN TRỌNG NHẤT của vòng tranh luận. Quyết định dựa trên
    máy và số đếm, không dựa vào cảm giác của model.

    Tách khỏi route_after_converge là có chủ đích: nếu dùng cùng một hàm
    cho cả tính toán lẫn rẽ nhánh, LangGraph sẽ chạy nó hai lần — tốn thêm
    một lượt gọi model vô ích giữa mỗi vòng.
    """
    rnd = state.get("debate_round", 0)
    critiques = state.get("pending_critiques", [])

    blocking = [
        c for c in critiques if _severity_of(c) in BLOCKING_SEVERITIES
    ]

    # 1. Hết số vòng cho phép → dừng, hỏi bạn.
    if rnd >= cfg.scrum.get("max_debate_rounds", 3):
        route = "escalate"
    # 2. Không còn phản biện nghiêm trọng → hội tụ.
    elif not blocking:
        route = "converged"
    # 3. Còn phản biện nghiêm trọng → Architect sửa.
    else:
        route = "architect"

    return {
        "_route": route,
        "blocking_count": len(blocking),
    }


def route_after_converge(state: TeamState) -> str:
    """Đọc quyết định mà converge_router đã lưu, trả về tên nhánh."""
    return state.get("_route", "converged")


def _severity_of(critique: dict) -> str:
    """Trích mức nghiêm trọng cao nhất từ một phản biện."""
    found = re.findall(
        r"\[(low|medium|high|blocker)\]", critique.get("text", "")
    )
    if not found:
        return "low"
    order = ["low", "medium", "high", "blocker"]
    return max(found, key=order.index)


def finalize_node(state: TeamState) -> dict:
    """Đánh dấu hội tụ xong, tăng vòng, chuẩn bị sang Designer."""
    return {
        "design": {**state["design"], "converged": True},
        "debate_round": state.get("debate_round", 0) + 1,
        "transcript": [
            {
                "round": state.get("debate_round", 0),
                "agent": "system",
                "action": "hội tụ — chuyển sang thiết kế giao diện",
            }
        ],
    }


def escalate_node(state: TeamState) -> dict:
    """Hết số vòng mà vẫn còn phản biện nghiêm trọng → dừng hỏi bạn.

    KHÔNG tự tăng max_debate_rounds rồi chạy tiếp. Hệ agent chạy vô hạn khi
    không hội tụ là nguyên nhân khiến nó trở nên vô dụng.
    """
    return {
        "gate1_result": {"approved": False, "reason": "hết số vòng tranh luận"},
        "transcript": [
            {
                "round": state.get("debate_round", 0),
                "agent": "system",
                "action": "DỪNG — hết số vòng, cần bạn quyết định",
                "open_critiques": state.get("pending_critiques", []),
            }
        ],
    }


def _error(state: TeamState, reason: str) -> dict:
    """Tác tủ lỗi → ghi vào transcript và đánh dấu cần bạn xử lý.

    Không ném lỗi ra ngoài: một tác tủ lỗi mà graph chết thì bạn mất toàn
    bộ tiến trình. Ghi lại rồi dừng ở GATE an toàn hơn.
    """
    return {
        "gate1_result": {"approved": False, "reason": reason},
        "transcript": [
            {
                "round": state.get("debate_round", 0),
                "agent": "system",
                "action": f"LỖI: {reason}",
            }
        ],
    }


# ── Lắp graph ────────────────────────────────────────────────────────────


def build_design_council(cfg):
    """Dựng subgraph vòng tranh luận thiết kế.

    Bind cfg vào từng node bằng functools.partial — LangGraph gọi node với
    đúng một tham số `state`, nên phải gắn cfg từ trước.
    """
    import functools as ft

    b = StateGraph(TeamState)

    b.add_node("architect", ft.partial(architect_node, cfg=cfg))
    b.add_node("developer", ft.partial(developer_critic, cfg=cfg))
    b.add_node("qa", ft.partial(qa_critic, cfg=cfg))
    b.add_node("devops", ft.partial(devops_critic, cfg=cfg))
    b.add_node("collect", collect_critique)
    b.add_node("designer", ft.partial(designer_node, cfg=cfg))
    b.add_node("converge", ft.partial(converge_router, cfg=cfg))
    b.add_node("finalize", finalize_node)
    b.add_node("escalate", escalate_node)

    # ── Luồng ──
    b.add_edge(START, "architect")

    # 3 tác tủ phản biện nối tiếp nhau, không phải song song.
    #
    # Về mô hình dữ liệu, Send có thể fan-out cả 3 cùng lúc. Nhưng cả 3
    # dùng CHUNG một model Ollama nên client đã có khoá toàn cục và chạy
    # tuần tự dù khai báo song song — khai báo song song chỉ gây khó hiểu
    # mà không đổi gì. Nối tiếp rõ ràng hơn và dễ đọc log.
    #
    # Mỗi node phản biện trả về `transcript` (có reducer operator.add)
    # nên ba node chạy liên tiếp vẫn CỘNG DỒN, không ghi đè lẫn nhau.
    b.add_edge("architect", "developer")
    b.add_edge("developer", "qa")
    b.add_edge("qa", "devops")
    b.add_edge("devops", "collect")

    # converge_router vừa quyết định vừa ghi kết quả vào state, nên nó
    # hoạt động như một node bình thường rồi mới rẽ nhánh. Rẽ nhánh bằng
    # chính hàm đó sẽ chạy nó HAI LẦN — lần hai gọi lại model là lãng phí
    # hơn 5 phút với gemma4. Vì vậy: node converge chỉ tính toán và lưu
    # kết quả, node route đọc kết quả đó để chọn nhánh.
    b.add_edge("collect", "converge")

    b.add_conditional_edges(
        "converge",
        route_after_converge,
        {
            "converged": "finalize",
            "architect": "architect",
            "escalate": "escalate",
        },
    )

    b.add_edge("finalize", "designer")
    b.add_edge("designer", END)
    b.add_edge("escalate", END)

    return b
