"""Review card scheduler with failure/stale/weak-priority buckets."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/leetcode.db")

# Blind 75 + NeetCode-style fallback ids (subset used as unsolved fallback queue).
PRIORITY_FALLBACK_IDS = [
    "1", "2", "3", "11", "15", "19", "20", "21", "23", "33", "34", "39", "49",
    "53", "55", "56", "57", "62", "70", "76", "79", "84", "98", "100", "102",
    "104", "105", "121", "124", "125", "128", "133", "139", "141", "143", "146",
    "152", "153", "198", "200", "206", "207", "208", "210", "211", "212", "213",
    "217", "226", "230", "235", "236", "238", "242", "271", "295", "297", "300",
    "322", "347", "417", "424", "543", "572", "621", "647", "684", "695", "703",
    "721", "733", "739", "875", "973", "981", "994",
]


def _ensure_review_log_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(review_logs)").fetchall()}
    if "last_result" not in cols:
        conn.execute("ALTER TABLE review_logs ADD COLUMN last_result TEXT;")
    conn.commit()


def _rows_to_cards(rows: list[sqlite3.Row]) -> list[dict]:
    cards: list[dict] = []
    for row in rows:
        cards.append(
            {
                "id": row["id"],
                "title": row["title"],
                "pattern": row["pattern"],
                "difficulty": row["difficulty"],
                "content": row["content"],
                "examples": row["examples"],
                "constraints": row["constraints"],
                "time_complexity": row["time_complexity"],
                "space_complexity": row["space_complexity"],
                "complexity_explanation": row["complexity_explanation"],
                "mcq_options": json.loads(row["mcq_options"] or "[]"),
                "correct_idx": row["correct_idx"],
                "snippet": row["snippet"],
                "followup_keywords": json.loads(row["followup_keywords"] or "[]"),
            }
        )
    return cards


def get_next_review_cards(user_id: str, limit: int = 10, mode: str = "Pattern") -> list[dict]:
    """Return next review cards by bucket priority.

    Follow-up mode prioritises problems the user has already passed in Pattern/Big-O
    mode (last_result = 'pass') so they have a solution context to discuss.
    All other modes use the standard failure > stale > weak > fallback order.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_review_log_columns(conn)
    cursor = conn.cursor()

    selected_ids: set[str] = set()
    cards: list[dict] = []

    def extend(rows: list[sqlite3.Row]) -> None:
        for row in rows:
            pid = str(row["id"])
            if pid in selected_ids:
                continue
            cards.append(dict(row))
            selected_ids.add(pid)
            if len(cards) >= limit:
                return

    if mode == "Follow-up":
        # Priority: problems already passed (last_result='pass'), ordered by most recently reviewed.
        passed_rows = cursor.execute(
            """
            SELECT p.*
            FROM review_logs rl
            JOIN problems p ON p.id = rl.problem_id
            WHERE rl.user_id = ? AND rl.last_result = 'pass'
            ORDER BY datetime(COALESCE(rl.last_reviewed, '1970-01-01')) DESC
            LIMIT ?;
            """,
            (user_id, limit),
        ).fetchall()
        extend(passed_rows)

        # Fallback: any unsolved priority problems when not enough passed cards.
        if len(cards) < limit:
            placeholders = ", ".join(["?"] * len(PRIORITY_FALLBACK_IDS))
            fallback_rows = cursor.execute(
                f"""
                SELECT p.*
                FROM problems p
                LEFT JOIN review_logs rl
                  ON rl.problem_id = p.id AND rl.user_id = ?
                WHERE p.id IN ({placeholders})
                ORDER BY CAST(p.id AS INTEGER) ASC
                LIMIT ?;
                """,
                (user_id, *PRIORITY_FALLBACK_IDS, limit),
            ).fetchall()
            extend(fallback_rows)

        conn.close()
        return _rows_to_cards(cards[:limit])

    # ── Standard mode: failures > stale > weak > fallback ─────────────────────

    # Bucket 1: failures
    failed_rows = cursor.execute(
        """
        SELECT p.*
        FROM review_logs rl
        JOIN problems p ON p.id = rl.problem_id
        WHERE rl.user_id = ? AND rl.last_result = 'fail'
        ORDER BY datetime(COALESCE(rl.last_reviewed, '1970-01-01')) DESC
        LIMIT ?;
        """,
        (user_id, limit),
    ).fetchall()
    extend(failed_rows)

    # Bucket 2: stale (> 7 days not reviewed)
    if len(cards) < limit:
        stale_rows = cursor.execute(
            """
            SELECT p.*
            FROM review_logs rl
            JOIN problems p ON p.id = rl.problem_id
            WHERE rl.user_id = ?
              AND datetime(COALESCE(rl.last_reviewed, '1970-01-01')) < datetime('now', '-7 days')
            ORDER BY datetime(COALESCE(rl.last_reviewed, '1970-01-01')) ASC
            LIMIT ?;
            """,
            (user_id, limit),
        ).fetchall()
        extend(stale_rows)

    # Bucket 3: weak patterns from lowest 3 skill tags, unsolved/new cards
    if len(cards) < limit:
        weak_tags = [
            row["tag"]
            for row in cursor.execute(
                """
                SELECT tag
                FROM user_stats
                WHERE user_id = ?
                ORDER BY skill_score ASC
                LIMIT 3;
                """,
                (user_id,),
            ).fetchall()
        ]
        if weak_tags:
            placeholders = ", ".join(["?"] * len(weak_tags))
            weak_rows = cursor.execute(
                f"""
                SELECT p.*
                FROM problems p
                LEFT JOIN review_logs rl
                  ON rl.problem_id = p.id
                  AND rl.user_id = ?
                WHERE p.pattern IN ({placeholders})
                  AND rl.problem_id IS NULL
                LIMIT ?;
                """,
                (user_id, *weak_tags, limit),
            ).fetchall()
            extend(weak_rows)

    # Fallback: unsolved problems from Blind75/NeetCode-like priority list.
    if len(cards) < limit:
        placeholders = ", ".join(["?"] * len(PRIORITY_FALLBACK_IDS))
        fallback_rows = cursor.execute(
            f"""
            SELECT p.*
            FROM problems p
            LEFT JOIN review_logs rl
              ON rl.problem_id = p.id
              AND rl.user_id = ?
            WHERE p.id IN ({placeholders})
              AND rl.problem_id IS NULL
            ORDER BY CAST(p.id AS INTEGER) ASC
            LIMIT ?;
            """,
            (user_id, *PRIORITY_FALLBACK_IDS, limit),
        ).fetchall()
        extend(fallback_rows)

    conn.close()
    return _rows_to_cards(cards[:limit])
