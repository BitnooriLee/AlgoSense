"""LangGraph state definition for node-to-node context."""

from __future__ import annotations

from typing import Annotated, TypedDict
import operator


class AgentState(TypedDict):
    mode: str  # "Pattern", "Big-O", "Follow-up"
    user_id: str
    current_problem: dict  # Selected from DB
    user_response: str  # User's MCQ choice or Keyword
    is_correct: bool  # Result of validation
    feedback: str  # AI explanation
    steps_completed: Annotated[int, operator.add]  # Counter

