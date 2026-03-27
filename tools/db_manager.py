"""SQLite schema and helpers for AlgoSense smart memory."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB_PATH = Path("data/leetcode.db")
MAX_PROBLEMS = 500


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create a SQLite connection with dictionary-like row access."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH, *, reset: bool = False) -> Path:
    """Initialize problems, user_stats, and review_logs tables."""
    with get_connection(db_path) as conn:
        if reset:
            conn.executescript(
                """
                DROP TABLE IF EXISTS review_logs;
                DROP TABLE IF EXISTS user_stats;
                DROP TABLE IF EXISTS problems;
                """
            )
        create_tables(conn)
    return Path(db_path)


def create_tables(conn: sqlite3.Connection) -> None:
    """Create DB schema requested for SRS workflow."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS problems (
            id TEXT PRIMARY KEY,
            title TEXT,
            pattern TEXT,
            difficulty TEXT,
            content TEXT,
            examples TEXT,
            constraints TEXT,
            time_complexity TEXT,
            space_complexity TEXT,
            complexity_explanation TEXT,
            mcq_options TEXT,
            correct_idx INTEGER,
            snippet TEXT,
            followup_keywords TEXT
        );

        CREATE TABLE IF NOT EXISTS user_stats (
            user_id TEXT,
            tag TEXT,
            skill_score INTEGER DEFAULT 50,
            PRIMARY KEY (user_id, tag)
        );

        CREATE TABLE IF NOT EXISTS review_logs (
            user_id TEXT,
            problem_id TEXT,
            last_reviewed TIMESTAMP,
            next_review_date TIMESTAMP,
            interval_days INTEGER DEFAULT 1,
            ease_factor REAL DEFAULT 2.5,
            PRIMARY KEY (user_id, problem_id)
        );

        CREATE INDEX IF NOT EXISTS idx_problems_pattern ON problems(pattern);
        CREATE INDEX IF NOT EXISTS idx_review_logs_due ON review_logs(user_id, next_review_date);
        CREATE INDEX IF NOT EXISTS idx_user_stats_skill ON user_stats(user_id, skill_score);
        """
    )
    _migrate_problem_columns(conn)
    conn.commit()


def _migrate_problem_columns(conn: sqlite3.Connection) -> None:
    """Ensure text columns exist when DB was created with old schema."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(problems);").fetchall()}
    for col in (
        "content",
        "examples",
        "constraints",
        "time_complexity",
        "space_complexity",
        "complexity_explanation",
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE problems ADD COLUMN {col} TEXT;")


def seed_problem_placeholders(conn: sqlite3.Connection, total: int = MAX_PROBLEMS) -> int:
    """
    Ensure placeholder rows exist up to `total` problems.

    Returns number of newly inserted rows.
    """
    if total <= 0:
        return 0

    existing = conn.execute("SELECT COUNT(*) AS cnt FROM problems;").fetchone()["cnt"]
    if existing >= total:
        return 0

    rows: list[tuple[Any, ...]] = []
    for problem_id in range(existing + 1, total + 1):
        rows.append(
            (
                str(problem_id),
                f"Placeholder Problem {problem_id}",
                "DFS",
                "easy",
                "",
                "",
                "",
                "",
                "",
                "",
                json.dumps(["Option A", "Option B", "Option C", "Option D"]),
                0,
                "def solve(): pass",
                json.dumps(["핵심 아이디어", "시간복잡도", "경계 케이스"]),
            )
        )

    conn.executemany(
        """
        INSERT INTO problems
        (id, title, pattern, difficulty, content, examples, constraints, time_complexity, space_complexity, complexity_explanation, mcq_options, correct_idx, snippet, followup_keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_user_skill(conn: sqlite3.Connection, user_id: str, tag: str, skill_score: int) -> None:
    """Upsert user skill score per tag (0~100)."""
    conn.execute(
        """
        INSERT INTO user_stats (user_id, tag, skill_score)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, tag)
        DO UPDATE SET
            skill_score = excluded.skill_score;
        """,
        (user_id, tag, int(skill_score)),
    )
    conn.commit()


def bulk_insert_problems(conn: sqlite3.Connection, rows: Iterable[tuple[Any, ...]]) -> None:
    """Bulk upsert problems. Tuple: id,title,pattern,difficulty,content,examples,constraints,time_complexity,space_complexity,complexity_explanation,mcq_options,correct_idx,snippet,followup_keywords."""
    conn.executemany(
        """
        INSERT INTO problems
        (id, title, pattern, difficulty, content, examples, constraints, time_complexity, space_complexity, complexity_explanation, mcq_options, correct_idx, snippet, followup_keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            pattern = excluded.pattern,
            difficulty = excluded.difficulty,
            content = excluded.content,
            examples = excluded.examples,
            constraints = excluded.constraints,
            time_complexity = excluded.time_complexity,
            space_complexity = excluded.space_complexity,
            complexity_explanation = excluded.complexity_explanation,
            mcq_options = excluded.mcq_options,
            correct_idx = excluded.correct_idx,
            snippet = excluded.snippet,
            followup_keywords = excluded.followup_keywords;
        """,
        list(rows),
    )
    conn.commit()


def initialize_database(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    create_placeholders: bool = True,
    placeholder_total: int = MAX_PROBLEMS,
    reset: bool = False,
) -> Path:
    """Initialize DB schema and optionally pre-seed up to 500 placeholders."""
    with get_connection(db_path) as conn:
        if reset:
            conn.executescript(
                """
                DROP TABLE IF EXISTS review_logs;
                DROP TABLE IF EXISTS user_stats;
                DROP TABLE IF EXISTS problems;
                """
            )
        create_tables(conn)
        if create_placeholders:
            seed_problem_placeholders(conn, total=placeholder_total)
    return Path(db_path)

def add_indexes(db_path="data/leetcode.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_problems_pattern ON problems(pattern);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_date ON review_logs(user_id, next_review_date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_user_score ON user_stats(user_id, skill_score);")
    conn.commit()
    conn.close()