"""No-LLM, low-latency answer validator."""

from __future__ import annotations


def grade_choice(selected_index: int | None, answer_index: int | None) -> bool:
    """Return True if selected answer index matches expected answer index."""
    if selected_index is None or answer_index is None:
        return False
    return int(selected_index) == int(answer_index)


def check_answer(current_problem: dict, user_response: str) -> bool:
    """
    Validate answer without LLM.
    `user_response` accepts numeric string (e.g. "2") or integer-like text.
    """
    if not current_problem:
        return False
    correct_idx = current_problem.get("answer_index")
    if correct_idx is None:
        return False
    try:
        selected_idx = int(user_response.strip())
    except (TypeError, ValueError, AttributeError):
        return False
    return grade_choice(selected_idx, int(correct_idx))
