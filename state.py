"""LangGraph state definition for node-to-node context."""

from __future__ import annotations

from typing import Annotated, TypedDict
import operator


class AgentState(TypedDict):
    mode: str                  # "Pattern", "Big-O Drill", "Follow-up" — set by orchestrator
    user_id: str
    current_problem: dict      # Selected from DB
    user_response: str         # User's MCQ choice or Keyword
    is_correct: bool           # Result of validation
    feedback: str              # AI explanation
    auto_mode: bool            # True when mode was decided by orchestrator (not manually)
    steps_completed: Annotated[int, operator.add]  # Counter

