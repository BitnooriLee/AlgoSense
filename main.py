"""Daily Review Mode Streamlit app."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agents.analyzer_agent import analyze_and_update_progress, get_or_create_complexity_explanation
from tools.scheduler import get_next_review_cards

load_dotenv()

st.set_page_config(page_title="AlgoSense Daily Review", layout="centered")

DEFAULT_USER_ID = "default_user"
SESSION_SIZE = 10
COMPLEXITY_OPTIONS = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(2^n)", "O(n!)"]


def _normalize_complexity(expr: str) -> str:
    return (expr or "").lower().replace(" ", "").replace("{", "").replace("}", "")


def load_user_stats(user_id: str) -> list[tuple[str, int]]:
    conn = sqlite3.connect("data/leetcode.db")
    rows = conn.cursor().execute(
        """
        SELECT tag, skill_score
        FROM user_stats
        WHERE user_id = ?
        ORDER BY skill_score ASC, tag ASC;
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def init_review_session(user_id: str) -> None:
    cards = get_next_review_cards(user_id=user_id, limit=SESSION_SIZE)
    st.session_state.cards = cards
    st.session_state.idx = 0
    st.session_state.feedback = ""
    st.session_state.submitted = False
    st.session_state.last_delta = 0
    st.session_state.last_pattern = ""


st.title("AlgoSense - Daily Review Mode")
user_id = st.text_input("User ID", value=DEFAULT_USER_ID)
mode = st.selectbox("Mode", ["Pattern", "Big-O Drill", "Follow-up"], index=0)
st.session_state.current_mode = mode

if "cards" not in st.session_state:
    init_review_session(user_id)

if st.button("Reload Today's 10 Cards"):
    init_review_session(user_id)

cards: list[dict] = st.session_state.cards
idx: int = st.session_state.idx

if not cards:
    st.warning("No review cards available. Try again after generating more review logs.")
    st.stop()

progress = min(idx, len(cards))
st.progress(progress / len(cards), text=f"{progress} of {len(cards)} problems reviewed today")

if idx >= len(cards):
    st.balloons()
    st.success("Session complete. Great consistency.")
    st.subheader("Summary Dashboard - Skill Scores by Pattern")
    stats = load_user_stats(user_id)
    if not stats:
        st.info("No user stats yet. Solve a few cards first.")
    else:
        df = pd.DataFrame(stats, columns=["pattern", "skill_score"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        c1, c2, c3 = st.columns(3)
        avg_v = int(df["skill_score"].mean())
        top_v = df.loc[df["skill_score"].idxmax(), "pattern"]
        c1.metric("Top Skill", top_v)
        c2.metric("Avg Score", f"{avg_v}%")
        c3.metric("Mastered", int((df["skill_score"] >= 80).sum()))
        st.bar_chart(df.set_index("pattern"), height=320)
    if st.button("Start New Session"):
        init_review_session(user_id)
        st.rerun()
    st.stop()

card = cards[idx]
st.subheader(f"{card.get('id')}. {card.get('title')}")
st.caption(f"Pattern: {card.get('pattern', 'N/A')} | Difficulty: {card.get('difficulty', 'N/A')}")

tab_problem, tab_examples, tab_quiz = st.tabs(["Problem", "Examples/Constraints", "Quiz"])

with tab_problem:
    st.markdown(card.get("content", "No problem statement."))

with tab_examples:
    st.markdown("### Examples")
    st.info(card.get("examples", "No examples."))
    st.markdown("### Constraints")
    st.warning(card.get("constraints", "No constraints."))

with tab_quiz:
    if st.session_state.current_mode == "Big-O Drill":
        st.markdown("### Analyze This Code")
        st.code(card.get("snippet", "No snippet available"), language="python")
        c1, c2 = st.columns(2)
        with c1:
            selected_time = st.selectbox(
                "Time Complexity",
                COMPLEXITY_OPTIONS,
                index=None,
                key=f"time_{idx}",
                placeholder="Select Time",
            )
        with c2:
            selected_space = st.selectbox(
                "Space Complexity",
                COMPLEXITY_OPTIONS,
                index=None,
                key=f"space_{idx}",
                placeholder="Select Space",
            )

        submit = st.button("Submit", key=f"submit_big_o_{idx}")
        if submit:
            if selected_time is None or selected_space is None:
                st.warning("Please select both Time and Space complexity first.")
            else:
                expected_time = card.get("time_complexity", "")
                expected_space = card.get("space_complexity", "")
                is_correct = (
                    _normalize_complexity(selected_time) == _normalize_complexity(expected_time)
                    and _normalize_complexity(selected_space) == _normalize_complexity(expected_space)
                )
                result = analyze_and_update_progress(
                    user_id=user_id,
                    problem_id=str(card.get("id")),
                    is_correct=is_correct,
                    mode="Big-O Drill",
                    selected_time=selected_time,
                    selected_space=selected_space,
                )
                delta = int(result.get("score_delta", 0))
                st.session_state.feedback = result.get("feedback", "")
                st.session_state.last_delta = delta
                st.session_state.last_pattern = result.get("pattern", "")
                st.session_state.submitted = True
                st.success("Correct answer." if is_correct else "Wrong answer.")
                sign = "+" if delta >= 0 else ""
                st.toast(f"{sign}{delta} Skill Points!")
    else:
        options = card.get("mcq_options", [])
        if not options:
            st.error("This card has no MCQ options.")
        else:
            choice = st.radio("Choose one answer", options, index=None, key=f"choice_{idx}")
            submit = st.button("Submit", key=f"submit_{idx}")
            if submit:
                if choice is None:
                    st.warning("Select an option first.")
                else:
                    is_correct = options.index(choice) == int(card.get("correct_idx", -1))
                    result = analyze_and_update_progress(
                        user_id=user_id,
                        problem_id=str(card.get("id")),
                        is_correct=is_correct,
                        mode=st.session_state.current_mode,
                    )
                    delta = int(result.get("score_delta", 0))
                    st.session_state.feedback = result.get("feedback", "")
                    st.session_state.last_delta = delta
                    st.session_state.last_pattern = result.get("pattern", "")
                    st.session_state.submitted = True
                    st.success("Correct answer." if is_correct else "Wrong answer.")
                    sign = "+" if delta >= 0 else ""
                    st.toast(f"{sign}{delta} Skill Points!")
    if st.session_state.get("submitted"):
        st.markdown("### Coach Feedback")
        st.write(st.session_state.get("feedback", ""))
        delta = int(st.session_state.get("last_delta", 0))
        pattern = st.session_state.get("last_pattern", "")
        sign = "+" if delta >= 0 else ""
        st.caption(f"Score update: {sign}{delta} on {pattern}")

        show_answer = st.button("Show Answer", key=f"show_answer_{idx}")
        if show_answer:
            st.markdown("### Answer")
            if st.session_state.current_mode == "Big-O Drill":
                exp_time = card.get("time_complexity", "N/A")
                exp_space = card.get("space_complexity", "N/A")
                st.info(f"Time: `{exp_time}` | Space: `{exp_space}`")
                explanation = card.get("complexity_explanation")
                if not explanation:
                    explanation = get_or_create_complexity_explanation(str(card.get("id")))
                    card["complexity_explanation"] = explanation
                    st.session_state.cards[idx] = card
                st.write(explanation)
            else:
                options = card.get("mcq_options", [])
                correct_idx = int(card.get("correct_idx", -1))
                if 0 <= correct_idx < len(options):
                    st.info(f"Correct Answer: **{options[correct_idx]}**")
                else:
                    st.info("No correct answer data.")
                st.write(
                    "Explanation: The optimal approach should satisfy the core pattern and constraints of the problem."
                )

        if st.button("Next Card", key=f"next_{idx}"):
            st.session_state.idx += 1
            st.session_state.feedback = ""
            st.session_state.submitted = False
            st.session_state.last_delta = 0
            st.session_state.last_pattern = ""
            st.rerun()
