"""Performance analyzer and adaptive progress updater (GPT-4o coach)."""

from __future__ import annotations

import json
import sqlite3
from typing import TypedDict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()

DB_PATH = "data/leetcode.db"
llm = init_chat_model("openai:gpt-4o")


class AnalyzeResult(TypedDict):
    feedback: str
    score_delta: int
    new_score: int
    pattern: str


def get_or_create_complexity_explanation(problem_id: str) -> str:
    """
    Return cached complexity explanation if present; otherwise generate once and persist.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    row = cur.execute(
        """
        SELECT id, title, snippet, time_complexity, space_complexity, complexity_explanation
        FROM problems
        WHERE id = ?;
        """,
        (str(problem_id),),
    ).fetchone()
    if row is None:
        conn.close()
        return "복잡도 설명을 생성할 수 없습니다: 문제를 찾지 못했습니다."

    cached = (row["complexity_explanation"] or "").strip()
    if cached:
        conn.close()
        return cached

    prompt = (
        "You are a concise algorithm coach. Return exactly one sentence in Korean.\n"
        "Explain why the given code has the stated time and space complexity.\n"
        f"Title: {row['title']}\n"
        f"Expected Time: {row['time_complexity']}\n"
        f"Expected Space: {row['space_complexity']}\n"
        f"Code:\n{(row['snippet'] or '')[:1400]}\n"
    )
    try:
        explanation = llm.invoke(prompt).content.strip()
        if not explanation:
            raise ValueError("empty explanation")
    except Exception:
        explanation = (
            f"이 코드는 핵심 반복/자료구조 사용 패턴 때문에 시간 {row['time_complexity']} 및 공간 "
            f"{row['space_complexity']}로 수렴합니다."
        )

    cur.execute(
        "UPDATE problems SET complexity_explanation = ? WHERE id = ?;",
        (explanation, str(problem_id)),
    )
    conn.commit()
    conn.close()
    return explanation


def _ensure_review_log_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(review_logs)").fetchall()}
    if "last_result" not in cols:
        conn.execute("ALTER TABLE review_logs ADD COLUMN last_result TEXT;")
    conn.commit()


def _clamp_delta_by_difficulty(difficulty: str, is_correct: bool, delta: int) -> int:
    diff = (difficulty or "medium").lower()
    if is_correct:
        # Hard success gets largest upside.
        ranges = {"easy": (4, 9), "medium": (8, 14), "hard": (12, 20)}
    else:
        # Easy failure penalized more; hard failure penalized less.
        ranges = {"easy": (-18, -10), "medium": (-12, -7), "hard": (-8, -4)}
    lo, hi = ranges.get(diff, ranges["medium"])
    return max(lo, min(hi, int(delta)))


def _get_llm_feedback_and_delta(
    title: str,
    pattern: str,
    difficulty: str,
    is_correct: bool,
    mode: str,
    snippet: str = "",
    expected_time: str = "",
    expected_space: str = "",
    selected_time: str = "",
    selected_space: str = "",
) -> tuple[str, int]:
    result_text = "correct" if is_correct else "incorrect"
    prompt = (
        "You are a strict interview coach. Return JSON only.\n"
        'Format: {"score_delta": <int>, "feedback": "<one sentence>"}\n'
        "Rules:\n"
        "- Hard success should grant more points.\n"
        "- Hard failure should penalize less.\n"
        "- Easy failure should penalize more.\n"
        "- feedback must be one sentence, tough-love, actionable.\n"
        f"Mode: {mode}\n"
        f"Problem: {title}\n"
        f"Pattern: {pattern}\n"
        f"Difficulty: {difficulty}\n"
        f"Result: {result_text}\n"
    )
    if mode == "Big-O Drill":
        prompt += (
            "Big-O context:\n"
            f"- Expected Time: {expected_time}\n"
            f"- Expected Space: {expected_space}\n"
            f"- User Time: {selected_time}\n"
            f"- User Space: {selected_space}\n"
            f"- Code Snippet (analyze why complexity):\n{snippet[:1200]}\n"
            "If incorrect, explicitly mention why the code shape implies the expected complexity."
        )
    default_delta = 10 if is_correct else -9
    try:
        raw = llm.invoke(prompt).content.strip()
        parsed = json.loads(raw)
        feedback = str(parsed.get("feedback", "")).strip()
        delta = int(parsed.get("score_delta", default_delta))
        if not feedback:
            raise ValueError("empty feedback")
        return feedback, delta
    except Exception:
        if is_correct:
            return f"Good job on {pattern}, but speed and consistency still need work.", default_delta
        return f"You slipped on {pattern}; write the invariant first and stop guessing.", default_delta


def analyze_and_update_progress(
    user_id: str,
    problem_id: str,
    is_correct: bool,
    mode: str = "Pattern",
    selected_time: str = "",
    selected_space: str = "",
) -> AnalyzeResult:
    """Update skill/review schedule and return feedback + dynamic score delta."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_review_log_columns(conn)
    cur = conn.cursor()

    problem = cur.execute(
        """
        SELECT id, title, pattern, difficulty, snippet, time_complexity, space_complexity
        FROM problems
        WHERE id = ?;
        """,
        (str(problem_id),),
    ).fetchone()
    if problem is None:
        conn.close()
        return {
            "feedback": "Problem not found. Sync your database first.",
            "score_delta": 0,
            "new_score": 0,
            "pattern": "General",
        }

    pattern = problem["pattern"] or "General"
    title = problem["title"] or f"Problem {problem_id}"
    difficulty = (problem["difficulty"] or "medium").lower()
    snippet = problem["snippet"] or ""
    expected_time = problem["time_complexity"] or ""
    expected_space = problem["space_complexity"] or ""

    current = cur.execute(
        "SELECT skill_score FROM user_stats WHERE user_id = ? AND tag = ?;",
        (user_id, pattern),
    ).fetchone()
    current_score = int(current["skill_score"]) if current else 50

    feedback, raw_delta = _get_llm_feedback_and_delta(
        title=title,
        pattern=pattern,
        difficulty=difficulty,
        is_correct=is_correct,
        mode=mode,
        snippet=snippet,
        expected_time=expected_time,
        expected_space=expected_space,
        selected_time=selected_time,
        selected_space=selected_space,
    )
    delta = _clamp_delta_by_difficulty(difficulty, is_correct, raw_delta)
    if mode == "Big-O Drill" and is_correct:
        # Weight Big-O correctness higher than normal drill.
        delta = min(25, max(delta, int(round(delta * 1.5))))
    new_score = max(0, min(100, current_score + delta))

    cur.execute(
        """
        INSERT INTO user_stats (user_id, tag, skill_score)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, tag) DO UPDATE SET
            skill_score = excluded.skill_score;
        """,
        (user_id, pattern, new_score),
    )

    prev_review = cur.execute(
        """
        SELECT interval_days, ease_factor
        FROM review_logs
        WHERE user_id = ? AND problem_id = ?;
        """,
        (user_id, str(problem_id)),
    ).fetchone()
    interval = int(prev_review["interval_days"]) if prev_review else 1
    ease = float(prev_review["ease_factor"]) if prev_review else 2.5

    if is_correct:
        next_interval = min(30, max(2, int(interval * max(ease, 1.5))))
        next_date_expr = f"+{next_interval} days"
    else:
        next_interval = 1
        next_date_expr = "+1 day"
        ease = max(1.3, ease - 0.2)

    cur.execute(
        """
        INSERT INTO review_logs (
            user_id, problem_id, last_reviewed, next_review_date, interval_days, ease_factor, last_result
        )
        VALUES (?, ?, datetime('now'), datetime('now', ?), ?, ?, ?)
        ON CONFLICT(user_id, problem_id) DO UPDATE SET
            last_reviewed = datetime('now'),
            next_review_date = datetime('now', ?),
            interval_days = excluded.interval_days,
            ease_factor = excluded.ease_factor,
            last_result = excluded.last_result;
        """,
        (
            user_id,
            str(problem_id),
            next_date_expr,
            next_interval,
            ease if is_correct else max(1.3, ease),
            "pass" if is_correct else "fail",
            next_date_expr,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "feedback": feedback,
        "score_delta": delta,
        "new_score": new_score,
        "pattern": pattern,
    }
