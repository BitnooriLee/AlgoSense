"""Backfill complexity fields from Solution.py with deterministic rules.

Usage:
  python3 tools/complexity_backfill.py
  python3 tools/complexity_backfill.py --start-id 1 --end-id 50
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path


DB_PATH = Path("data/leetcode.db")
SOLUTION_ROOT = Path("leetcode/solution")


def bucket(problem_id: int) -> str:
    start = (problem_id // 100) * 100
    return f"{start:04d}-{start + 99:04d}"


def find_problem_dir(problem_id: int) -> Path | None:
    base = SOLUTION_ROOT / bucket(problem_id)
    if not base.exists():
        return None
    prefix = f"{problem_id:04d}."
    for entry in base.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix):
            return entry
    return None


def infer_from_solution(code: str) -> tuple[str, str, str]:
    """Return (time, space, reason)."""
    s = (code or "").lower()

    # Specific numeric-loop pattern first (Reverse Integer style).
    if "% 10" in s or "// 10" in s:
        return "O(log10(|x|))", "O(1)", "digit-by-digit processing loop"

    if re.search(r"\[\[.*for .* in range\(", s, flags=re.S):
        loops = len(re.findall(r"\bfor\b|\bwhile\b", s))
        if loops >= 2:
            return "O(n^2)", "O(n^2)", "2D DP table with nested iteration"
        return "O(n^2)", "O(n^2)", "2D table allocation"

    if "heapq" in s:
        return "O(nlogn)", "O(n)", "heap operations across input"

    if ".sort(" in s:
        return "O(nlogn)", "O(1)", "in-place sort"
    if "sorted(" in s:
        return "O(nlogn)", "O(n)", "sorted() allocates copied list"

    if ("dict(" in s or "{}" in s or "defaultdict" in s or "counter" in s or "set(" in s) and (
        re.search(r"\bfor\b|\bwhile\b", s)
    ):
        return "O(n)", "O(n)", "hash structure with linear traversal"

    recursive = bool(re.search(r"def\s+(\w+)\(.*\):[\s\S]*?\1\(", s))
    loops = len(re.findall(r"\bfor\b|\bwhile\b", s))

    if recursive and loops >= 1:
        return "O(n^2)", "O(n)", "recursion plus loop traversal"
    if recursive:
        return "O(n)", "O(n)", "recursive traversal stack depth"

    if loops >= 2:
        return "O(n^2)", "O(1)", "nested loops"
    if loops == 1:
        return "O(n)", "O(1)", "single loop"

    return "O(1)", "O(1)", "constant-size operations only"


def backfill(start_id: int | None, end_id: int | None) -> tuple[int, int]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if start_id is None or end_id is None:
        ids = [int(r["id"]) for r in cur.execute("SELECT id FROM problems WHERE id GLOB '[0-9]*'").fetchall()]
        target_ids = sorted(set(ids))
    else:
        target_ids = list(range(start_id, end_id + 1))

    updated = 0
    missing_source = 0
    rows_to_update: list[tuple[str, str, str]] = []

    for pid in target_ids:
        problem_dir = find_problem_dir(pid)
        if not problem_dir:
            missing_source += 1
            continue
        solution_path = problem_dir / "Solution.py"
        code = solution_path.read_text(encoding="utf-8", errors="ignore") if solution_path.exists() else ""

        time_c, space_c, _ = infer_from_solution(code)
        rows_to_update.append((time_c, space_c, str(pid)))
        updated += 1

    if rows_to_update:
        cur.execute("BEGIN")
        cur.executemany(
            "UPDATE problems SET time_complexity = ?, space_complexity = ? WHERE id = ?",
            rows_to_update,
        )
        conn.commit()
    conn.close()
    return updated, missing_source


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill complexity columns from Solution.py")
    parser.add_argument("--start-id", type=int, default=None, help="Start problem id (inclusive)")
    parser.add_argument("--end-id", type=int, default=None, help="End problem id (inclusive)")
    args = parser.parse_args()

    if (args.start_id is None) != (args.end_id is None):
        raise SystemExit("Provide both --start-id and --end-id together, or neither.")
    if args.start_id is not None and args.start_id > args.end_id:
        raise SystemExit("--start-id must be <= --end-id")

    updated, missing_source = backfill(args.start_id, args.end_id)
    print(f"updated={updated} missing_source={missing_source}")


if __name__ == "__main__":
    main()
