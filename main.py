"""Daily Review Mode Streamlit app."""

from __future__ import annotations

import concurrent.futures
import os
import sqlite3

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agents.analyzer_agent import analyze_and_update_progress, get_or_create_complexity_explanation
from agents.interview_agent import generate_followup_scenario
from agents.orchestrator_agent import decide_mode
from tools.scheduler import get_next_review_cards

load_dotenv()

st.set_page_config(
    page_title="AlgoSense — Daily Review",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="expanded",
)

DEFAULT_USER_ID = "default_user"
SESSION_SIZE = 10
COMPLEXITY_OPTIONS = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(2^n)", "O(n!)"]
MODE_AUTO = "Auto (AI decides)"
MODE_LABELS = {
    "Pattern": "🎯 Pattern",
    "Big-O Drill": "⏱ Big-O Drill",
    "Follow-up": "💬 Follow-up",
}
DB_PATH = "data/leetcode.db"


# ── Prerequisites check ───────────────────────────────────────────────────────

def _check_prerequisites() -> bool:
    """Validate API key and DB on startup. Returns True if all good."""
    ok = True

    if not os.getenv("OPENAI_API_KEY"):
        st.error(
            "**OpenAI API key not found.**\n\n"
            "Create a `.env` file in the project root with:\n"
            "```\nOPENAI_API_KEY=sk-...\n```",
            icon="🔑",
        )
        ok = False

    if not os.path.exists(DB_PATH):
        st.error(
            "**Database not found** at `data/leetcode.db`.\n\n"
            "Run `python3 tools/db_manager.py` to initialise the database first.",
            icon="🗄️",
        )
        ok = False
    else:
        try:
            conn = sqlite3.connect(DB_PATH)
            count = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
            conn.close()
            if count == 0:
                st.warning(
                    "Database is empty — no problems loaded yet.\n\n"
                    "Run `tools/data_loader.py` to populate problems.",
                    icon="⚠️",
                )
                ok = False
        except Exception as exc:
            st.error(f"**Database error:** {exc}", icon="🗄️")
            ok = False

    return ok


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🧠 AlgoSense")
        st.caption("LeetCode 인터뷰 준비 AI 코치")
        st.divider()

        st.markdown("### 사용 방법")
        st.markdown(
            "1. **User ID**를 입력하세요 (기록이 저장됩니다)\n"
            "2. **Mode**를 선택하거나 `Auto`로 두세요\n"
            "3. 문제를 읽고 Quiz 탭에서 답을 선택하세요\n"
            "4. Submit 후 AI 피드백을 확인하세요\n"
            "5. 10문제 완료 시 대시보드에서 성과를 확인하세요"
        )
        st.divider()

        st.markdown("### 모드 안내")
        st.markdown(
            "| 모드 | 설명 |\n"
            "|---|---|\n"
            "| 🤖 **Auto** | AI가 실력에 맞는 모드를 자동 선택 |\n"
            "| 🎯 **Pattern** | 4지선다 — 알고리즘 패턴 인식 |\n"
            "| ⏱ **Big-O Drill** | Time·Space 복잡도 직접 선택 |\n"
            "| 💬 **Follow-up** | AI 면접관 질문 + 키워드 칩 탭 |"
        )
        st.divider()

        st.markdown("### 점수 체계")
        st.markdown(
            "| 상황 | 점수 변화 |\n"
            "|---|---|\n"
            "| Easy 정답 | +4 ~ +9 |\n"
            "| Medium 정답 | +8 ~ +14 |\n"
            "| Hard 정답 | +12 ~ +20 |\n"
            "| Big-O 정답 | ×1.5 보너스 |\n"
            "| Follow-up 정답 | +20 고정 |\n"
            "| 오답 패널티 | Easy > Medium > Hard |"
        )
        st.divider()

        st.markdown("### AI 자동 모드 기준")
        st.markdown(
            "```\n"
            "score < 55       →  🎯 Pattern\n"
            "score ≥ 55       →  ⏱ Big-O Drill\n"
            "score ≥ 70 + 통과 →  💬 Follow-up\n"
            "```"
        )
        st.caption("패턴별 skill score 기준으로 카드마다 독립 판단합니다.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_complexity(expr: str) -> str:
    return (expr or "").lower().replace(" ", "").replace("{", "").replace("}", "")


def load_user_stats(user_id: str) -> list[tuple[str, int]]:
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute(
            "SELECT tag, skill_score FROM user_stats WHERE user_id = ? ORDER BY skill_score ASC, tag ASC;",
            (user_id,),
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def _scheduler_mode(selected_mode: str) -> str:
    return "Follow-up" if selected_mode == "Follow-up" else "Pattern"


def init_review_session(user_id: str, mode: str = "Pattern") -> None:
    try:
        cards = get_next_review_cards(user_id=user_id, limit=SESSION_SIZE, mode=_scheduler_mode(mode))
    except Exception as exc:
        st.error(f"카드를 불러오는 중 오류가 발생했습니다: {exc}", icon="🗄️")
        cards = []
    st.session_state.cards = cards
    st.session_state.idx = 0
    st.session_state.feedback = ""
    st.session_state.submitted = False
    st.session_state.last_delta = 0
    st.session_state.last_pattern = ""
    st.session_state.followup_scenario = None
    st.session_state.followup_selected_chip = None
    for key in list(st.session_state.keys()):
        if key.startswith("auto_mode_") or key.startswith("followup_future_"):
            del st.session_state[key]


def resolve_card_mode(card: dict, user_id: str, selected_mode: str) -> str:
    if selected_mode != MODE_AUTO:
        return selected_mode
    cache_key = f"auto_mode_{card.get('id')}"
    if cache_key not in st.session_state:
        try:
            result = decide_mode(user_id, card)
        except Exception:
            result = {"mode": "Pattern", "skill_score": 50, "last_result": "new", "reason": ""}
        st.session_state[cache_key] = result
    return st.session_state[cache_key]["mode"]


def _prefetch_followup(card: dict, effective_mode: str, idx: int) -> None:
    if effective_mode != "Follow-up":
        return
    if st.session_state.followup_scenario is not None:
        return
    future_key = f"followup_future_{idx}"
    future: concurrent.futures.Future | None = st.session_state.get(future_key)
    if future is not None and future.done():
        try:
            st.session_state.followup_scenario = future.result()
        except Exception:
            st.session_state.followup_scenario = None
        del st.session_state[future_key]
        return
    if future is None:
        if "executor" not in st.session_state:
            st.session_state.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        st.session_state[future_key] = st.session_state.executor.submit(
            generate_followup_scenario, card
        )


def _get_followup_scenario(card: dict, idx: int) -> dict:
    future_key = f"followup_future_{idx}"
    future: concurrent.futures.Future | None = st.session_state.get(future_key)
    if future is not None:
        if not future.done():
            with st.spinner("AI 면접관이 질문을 생성하는 중입니다..."):
                try:
                    result = future.result(timeout=20)
                except Exception:
                    result = None
        else:
            try:
                result = future.result()
            except Exception:
                result = None
        if future_key in st.session_state:
            del st.session_state[future_key]
        if result:
            return result
    with st.spinner("AI 면접관이 질문을 생성하는 중입니다..."):
        return generate_followup_scenario(card)


def _run_analyzer(
    user_id: str,
    card: dict,
    is_correct: bool,
    effective_mode: str,
    **kwargs,
) -> dict:
    """Call analyzer with spinner + error handling. Returns AnalyzeResult."""
    with st.spinner("AI 코치가 분석 중입니다..."):
        try:
            return analyze_and_update_progress(
                user_id=user_id,
                problem_id=str(card.get("id")),
                is_correct=is_correct,
                mode=effective_mode,
                **kwargs,
            )
        except Exception as exc:
            st.error(f"AI 피드백 생성 중 오류: {exc}\n\n점수는 기본값으로 처리됩니다.", icon="🤖")
            pattern = card.get("pattern", "General")
            return {
                "feedback": (
                    "AI 피드백을 가져올 수 없습니다. 네트워크 연결 또는 API 키를 확인해 주세요."
                ),
                "score_delta": 5 if is_correct else -5,
                "new_score": 50,
                "pattern": pattern,
            }


# ── App ───────────────────────────────────────────────────────────────────────

_render_sidebar()

st.title("🧠 AlgoSense — Daily Review")

if not _check_prerequisites():
    st.stop()

user_id = st.text_input(
    "User ID",
    value=DEFAULT_USER_ID,
    help="학습 기록이 이 ID에 저장됩니다. 여러 사람이 함께 사용할 경우 고유한 ID를 입력하세요.",
)
mode = st.selectbox(
    "Mode",
    [MODE_AUTO, "Pattern", "Big-O Drill", "Follow-up"],
    index=0,
    help=(
        "**Auto**: AI가 패턴별 skill score를 보고 카드마다 최적 모드를 자동 선택합니다.\n\n"
        "**Pattern**: 4지선다로 알고리즘 패턴을 빠르게 인식하는 훈련\n\n"
        "**Big-O Drill**: 코드를 보고 Time·Space 복잡도를 직접 선택\n\n"
        "**Follow-up**: AI 면접관의 심화 질문에 키워드 칩으로 응답"
    ),
)

if "cards" not in st.session_state:
    init_review_session(user_id, mode)

if st.button("🔄 오늘의 10문제 다시 불러오기"):
    init_review_session(user_id, mode)

cards: list[dict] = st.session_state.cards
idx: int = st.session_state.idx

if not cards:
    st.warning(
        "복습할 카드가 없습니다.\n\n"
        "**원인 & 해결책:**\n"
        "- DB에 문제가 없다면 `tools/data_loader.py`를 실행하세요.\n"
        "- Auto/Pattern 모드로 첫 세션을 완료하면 이후 모드에서 카드가 쌓입니다.",
        icon="📭",
    )
    st.stop()

progress = min(idx, len(cards))
st.progress(
    progress / len(cards),
    text=f"오늘 진행: {progress} / {len(cards)} 문제",
)

# ── Session complete ──────────────────────────────────────────────────────────
if idx >= len(cards):
    st.balloons()
    st.success("🎉 오늘 세션 완료! 꾸준함이 실력입니다.")
    st.subheader("📊 Skill Score 대시보드")
    stats = load_user_stats(user_id)
    if not stats:
        st.info("아직 기록이 없습니다. 몇 문제를 풀고 나면 여기에 통계가 표시됩니다.", icon="📈")
    else:
        df = pd.DataFrame(stats, columns=["pattern", "skill_score"])
        c1, c2, c3 = st.columns(3)
        c1.metric("🏆 Top Skill", df.loc[df["skill_score"].idxmax(), "pattern"])
        c2.metric("📊 Avg Score", f"{int(df['skill_score'].mean())}%")
        c3.metric("✅ Mastered (≥80)", int((df["skill_score"] >= 80).sum()))
        st.bar_chart(df.set_index("pattern"), height=320)
        st.dataframe(df, use_container_width=True, hide_index=True)
    if st.button("▶ 새 세션 시작"):
        init_review_session(user_id, mode)
        st.rerun()
    st.stop()

# ── Current card ──────────────────────────────────────────────────────────────
card = cards[idx]

effective_mode = resolve_card_mode(card, user_id, mode)
st.session_state.current_mode = effective_mode

_prefetch_followup(card, effective_mode, idx)

col_title, col_badge = st.columns([4, 1])
with col_title:
    difficulty = card.get("difficulty", "N/A")
    diff_color = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴"}.get(difficulty, "⚪")
    st.subheader(f"{card.get('id')}. {card.get('title')}")
    st.caption(f"Pattern: `{card.get('pattern', 'N/A')}` | {diff_color} {difficulty}")
with col_badge:
    label = MODE_LABELS.get(effective_mode, effective_mode)
    if mode == MODE_AUTO:
        orch_result = st.session_state.get(f"auto_mode_{card.get('id')}", {})
        st.markdown(f"**AI → {label}**")
        if orch_result.get("reason"):
            st.caption(orch_result["reason"])
    else:
        st.markdown(f"**{label}**")

tab_problem, tab_examples, tab_quiz = st.tabs(["📄 Problem", "📝 Examples / Constraints", "🎯 Quiz"])

with tab_problem:
    content = card.get("content", "")
    if content:
        st.markdown(content)
    else:
        st.info("문제 본문이 없습니다. Quiz 탭에서 바로 풀어보세요.", icon="ℹ️")

with tab_examples:
    examples = card.get("examples", "")
    constraints = card.get("constraints", "")
    if examples:
        st.markdown("### Examples")
        st.info(examples)
    if constraints:
        st.markdown("### Constraints")
        st.warning(constraints)
    if not examples and not constraints:
        st.info("예시 데이터가 없습니다.", icon="ℹ️")

# ── Quiz tab ──────────────────────────────────────────────────────────────────
with tab_quiz:

    if not st.session_state.get("submitted"):
        st.caption(
            {
                "Pattern": "💡 아래 4개 선택지 중 이 문제의 **핵심 접근법**을 고르세요.",
                "Big-O Drill": "💡 위 코드 스니펫을 분석해 **Time · Space 복잡도**를 선택하세요.",
                "Follow-up": "💡 AI 면접관의 질문에 답할 **핵심 키워드**를 탭하세요.",
            }.get(effective_mode, "")
        )

    # ── Big-O Drill ───────────────────────────────────────────────────────────
    if effective_mode == "Big-O Drill":
        snippet = card.get("snippet", "")
        if snippet:
            st.markdown("**Code Snippet**")
            st.code(snippet, language="python")
        else:
            st.warning("이 문제에는 코드 스니펫이 없습니다. Pattern 모드로 전환해 풀어보세요.", icon="⚠️")

        if not st.session_state.get("submitted"):
            c1, c2 = st.columns(2)
            with c1:
                selected_time = st.selectbox(
                    "⏱ Time Complexity", COMPLEXITY_OPTIONS,
                    index=None, key=f"time_{idx}", placeholder="Time 선택",
                )
            with c2:
                selected_space = st.selectbox(
                    "💾 Space Complexity", COMPLEXITY_OPTIONS,
                    index=None, key=f"space_{idx}", placeholder="Space 선택",
                )

            if st.button("✅ Submit", key=f"submit_big_o_{idx}", use_container_width=True):
                if selected_time is None or selected_space is None:
                    st.warning("Time과 Space 복잡도를 모두 선택해 주세요.", icon="⚠️")
                else:
                    expected_time = card.get("time_complexity", "")
                    expected_space = card.get("space_complexity", "")
                    is_correct = (
                        _normalize_complexity(selected_time) == _normalize_complexity(expected_time)
                        and _normalize_complexity(selected_space) == _normalize_complexity(expected_space)
                    )
                    result = _run_analyzer(
                        user_id, card, is_correct, "Big-O Drill",
                        selected_time=selected_time, selected_space=selected_space,
                    )
                    delta = int(result.get("score_delta", 0))
                    st.session_state.feedback = result.get("feedback", "")
                    st.session_state.last_delta = delta
                    st.session_state.last_pattern = result.get("pattern", "")
                    st.session_state.submitted = True
                    if is_correct:
                        st.success("정답입니다! 🎉")
                    else:
                        st.error(f"오답입니다. (정답: Time `{expected_time}` / Space `{expected_space}`)")
                    sign = "+" if delta >= 0 else ""
                    st.toast(f"{sign}{delta} Skill Points!")

    # ── Follow-up ─────────────────────────────────────────────────────────────
    elif effective_mode == "Follow-up":
        if st.session_state.followup_scenario is None:
            st.session_state.followup_scenario = _get_followup_scenario(card, idx)

        scenario: dict = st.session_state.followup_scenario or {}
        question: str = scenario.get("question", "")
        chips: list[str] = scenario.get("chips", [])
        correct_chip_idx: int = int(scenario.get("correct_chip_index", 0))

        with st.expander("💻 Solution Snippet 보기", expanded=False):
            snippet = card.get("snippet", "")
            if snippet:
                st.code(snippet, language="python")
            else:
                st.info("스니펫이 없습니다.")

        st.markdown("### 🎤 Interview Follow-up")
        if question:
            st.info(f"**{question}**")
        else:
            st.warning("질문을 생성할 수 없습니다. 카드를 다시 로드해 주세요.", icon="⚠️")

        if chips and not st.session_state.get("submitted"):
            cols = st.columns(2)
            for i, chip in enumerate(chips):
                if cols[i % 2].button(chip, key=f"chip_{idx}_{i}", use_container_width=True):
                    correct_chip = chips[correct_chip_idx] if chips else ""
                    is_correct = (i == correct_chip_idx)
                    result = _run_analyzer(
                        user_id, card, is_correct, "Follow-up",
                        followup_question=question,
                        correct_chip=correct_chip,
                        selected_chip=chip,
                    )
                    delta = int(result.get("score_delta", 0))
                    st.session_state.feedback = result.get("feedback", "")
                    st.session_state.last_delta = delta
                    st.session_state.last_pattern = result.get("pattern", "")
                    st.session_state.followup_selected_chip = chip
                    st.session_state.submitted = True
                    sign = "+" if delta >= 0 else ""
                    st.toast(f"{sign}{delta} Skill Points!")
                    st.rerun()
        elif not chips:
            st.warning("키워드 칩을 생성할 수 없습니다.", icon="⚠️")

    # ── Pattern (MCQ) ─────────────────────────────────────────────────────────
    else:
        options = card.get("mcq_options", [])
        if not options:
            st.warning(
                "이 문제에는 선택지가 없습니다.\n\n"
                "Big-O Drill 모드로 전환하거나 다음 카드로 이동해 주세요.",
                icon="⚠️",
            )
        else:
            if not st.session_state.get("submitted"):
                choice = st.radio(
                    "정답을 선택하세요",
                    options,
                    index=None,
                    key=f"choice_{idx}",
                )
                if st.button("✅ Submit", key=f"submit_{idx}", use_container_width=True):
                    if choice is None:
                        st.warning("선택지를 먼저 골라주세요.", icon="⚠️")
                    else:
                        is_correct = options.index(choice) == int(card.get("correct_idx", -1))
                        result = _run_analyzer(user_id, card, is_correct, effective_mode)
                        delta = int(result.get("score_delta", 0))
                        st.session_state.feedback = result.get("feedback", "")
                        st.session_state.last_delta = delta
                        st.session_state.last_pattern = result.get("pattern", "")
                        st.session_state.submitted = True
                        if is_correct:
                            st.success("정답입니다! 🎉")
                        else:
                            st.error("오답입니다.")
                        sign = "+" if delta >= 0 else ""
                        st.toast(f"{sign}{delta} Skill Points!")

    # ── Post-submit ───────────────────────────────────────────────────────────
    if st.session_state.get("submitted"):
        st.divider()
        st.markdown("### 🏋️ Coach Feedback")
        feedback = st.session_state.get("feedback", "")
        if feedback:
            st.write(feedback)
        delta = int(st.session_state.get("last_delta", 0))
        pattern = st.session_state.get("last_pattern", "")
        sign = "+" if delta >= 0 else ""
        if delta > 0:
            st.success(f"**{sign}{delta}** skill points on **{pattern}**", icon="📈")
        elif delta < 0:
            st.error(f"**{delta}** skill points on **{pattern}**", icon="📉")
        else:
            st.info(f"Score unchanged on **{pattern}**")

        col_ans, col_next = st.columns(2)
        with col_ans:
            if st.button("🔍 정답 보기", key=f"show_answer_{idx}", use_container_width=True):
                st.markdown("#### 정답")
                if effective_mode == "Big-O Drill":
                    exp_time = card.get("time_complexity", "N/A")
                    exp_space = card.get("space_complexity", "N/A")
                    st.info(f"Time: `{exp_time}` | Space: `{exp_space}`")
                    with st.spinner("설명을 불러오는 중..."):
                        try:
                            explanation = card.get("complexity_explanation")
                            if not explanation:
                                explanation = get_or_create_complexity_explanation(str(card.get("id")))
                                card["complexity_explanation"] = explanation
                                st.session_state.cards[idx] = card
                            if explanation:
                                st.write(explanation)
                        except Exception as exc:
                            st.warning(f"설명을 불러올 수 없습니다: {exc}", icon="⚠️")
                elif effective_mode == "Follow-up":
                    scenario = st.session_state.get("followup_scenario") or {}
                    chips = scenario.get("chips", [])
                    correct_chip_idx = int(scenario.get("correct_chip_index", 0))
                    correct_chip = chips[correct_chip_idx] if chips else "N/A"
                    selected_chip = st.session_state.get("followup_selected_chip", "")
                    st.info(f"핵심 개념: **{correct_chip}**")
                    if selected_chip and selected_chip != correct_chip:
                        st.caption(f"내가 선택한 답: {selected_chip}")
                else:
                    options = card.get("mcq_options", [])
                    correct_idx = int(card.get("correct_idx", -1))
                    if 0 <= correct_idx < len(options):
                        st.info(f"정답: **{options[correct_idx]}**")
                    else:
                        st.info("정답 데이터가 없습니다.")

        with col_next:
            if st.button("➡ 다음 카드", key=f"next_{idx}", use_container_width=True):
                st.session_state.idx += 1
                st.session_state.feedback = ""
                st.session_state.submitted = False
                st.session_state.last_delta = 0
                st.session_state.last_pattern = ""
                st.session_state.followup_scenario = None
                st.session_state.followup_selected_chip = None
                st.rerun()
