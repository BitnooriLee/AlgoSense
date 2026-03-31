"""Orchestrator: auto-decides the optimal review mode per (user, problem) pair.

Decision tree
─────────────
last_result == 'pass'  AND  skill_score >= 70  →  Follow-up   (deepen mastery)
skill_score >= 55      (pattern understood)    →  Big-O Drill  (complexity training)
otherwise                                       →  Pattern      (build recognition)

Thresholds are intentionally conservative so the user naturally progresses
Pattern → Big-O → Follow-up as their skill score rises.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypedDict

DB_PATH = Path("data/leetcode.db")

MODE_PATTERN = "Pattern"
MODE_BIG_O = "Big-O Drill"
MODE_FOLLOWUP = "Follow-up"

_SKILL_BIG_O_THRESHOLD = 55   # score needed to graduate from Pattern → Big-O
_SKILL_FOLLOWUP_THRESHOLD = 70 # score needed to graduate from Big-O  → Follow-up


class OrchestratorResult(TypedDict):
    mode: str           # decided mode
    skill_score: int    # current skill score for this pattern
    last_result: str    # 'pass' | 'fail' | 'new'
    reason: str         # human-readable explanation


def decide_mode(
    user_id: str,
    problem: dict,
    db_path: str | Path = DB_PATH,
) -> OrchestratorResult:
    """Return the best review mode for this user + problem.

    Reads skill_score from user_stats and last_result from review_logs.
    Pure DB logic — no LLM call.
    """
    problem_id = str(problem.get("id", ""))
    pattern = (problem.get("pattern") or "General").strip()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    skill_row = cur.execute(
        "SELECT skill_score FROM user_stats WHERE user_id = ? AND tag = ?",
        (user_id, pattern),
    ).fetchone()
    skill_score = int(skill_row["skill_score"]) if skill_row else 50

    log_row = cur.execute(
        "SELECT last_result FROM review_logs WHERE user_id = ? AND problem_id = ?",
        (user_id, problem_id),
    ).fetchone()
    last_result = (log_row["last_result"] or "new") if log_row else "new"

    conn.close()

    if last_result == "pass" and skill_score >= _SKILL_FOLLOWUP_THRESHOLD:
        return OrchestratorResult(
            mode=MODE_FOLLOWUP,
            skill_score=skill_score,
            last_result=last_result,
            reason=f"{pattern} score {skill_score} ≥ {_SKILL_FOLLOWUP_THRESHOLD} and last attempt passed → deepen with Follow-up",
        )

    if skill_score >= _SKILL_BIG_O_THRESHOLD:
        return OrchestratorResult(
            mode=MODE_BIG_O,
            skill_score=skill_score,
            last_result=last_result,
            reason=f"{pattern} score {skill_score} ≥ {_SKILL_BIG_O_THRESHOLD} → train complexity with Big-O Drill",
        )

    return OrchestratorResult(
        mode=MODE_PATTERN,
        skill_score=skill_score,
        last_result=last_result,
        reason=f"{pattern} score {skill_score} < {_SKILL_BIG_O_THRESHOLD} → reinforce pattern recognition",
    )
