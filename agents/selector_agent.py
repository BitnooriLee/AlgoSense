"""Problem selector that delegates to scheduler tool."""

from __future__ import annotations

from tools.scheduler import get_next_problems


def select_problem(user_id: str, mode: str) -> dict:
    """Return one problem chosen by SRS-aware scheduler."""
    problems = get_next_problems(user_id=user_id, mode=mode, limit=1)
    return problems[0] if problems else {}
