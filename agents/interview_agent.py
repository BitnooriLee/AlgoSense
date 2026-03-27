"""Follow-up question and keyword chip generator."""

from __future__ import annotations

from state import AgentState


def build_follow_up(state: AgentState) -> tuple[str, list[str]]:
    """Return one follow-up question and 3-4 mobile tap chips."""
    problem = state.get("current_problem") or {}
    pattern = problem.get("pattern", "알고리즘")
    question = f"{pattern}에서 이 문제를 더 빨리 푸는 핵심 패턴은 무엇인가요?"
    chips = problem.get("followup_keywords") or ["핵심 아이디어", "시간복잡도", "경계 케이스", "대안 풀이"]
    return question, chips


def generate_followup(current_problem: dict) -> dict:
    """Generate follow-up question + keyword chips payload."""
    pattern = current_problem.get("pattern", "알고리즘")
    chips = current_problem.get("followup_keywords") or ["핵심 아이디어", "시간복잡도", "경계 케이스", "대안 풀이"]
    question = f"{pattern} 문제를 다시 볼 때 어떤 단서부터 확인할까요?"
    return {"question": question, "chips": chips}
