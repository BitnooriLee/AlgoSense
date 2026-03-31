"""LangGraph workflow: selection → orchestrator → validation → analysis/followup."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.analyzer_agent import analyze_and_update_progress
from agents.interview_agent import generate_followup
from agents.orchestrator_agent import decide_mode
from agents.selector_agent import select_problem
from state import AgentState
from tools.validator import check_answer


def selection_node(state: AgentState):
    """Fetch one problem using scheduler-backed selector."""
    problem = select_problem(state["user_id"], state.get("mode", "Pattern"))
    return {"current_problem": problem, "steps_completed": 1}


def orchestrator_node(state: AgentState):
    """Auto-decide the optimal review mode for this (user, problem) pair.

    Reads skill_score and last_result from DB — no LLM call.
    Overrides mode only when auto_mode is True (i.e. caller did not
    manually specify a mode).
    """
    if not state.get("auto_mode", False):
        # Manual mode selected by user — respect it.
        return {"steps_completed": 1}

    result = decide_mode(state["user_id"], state["current_problem"])
    return {
        "mode": result["mode"],
        "steps_completed": 1,
    }


def validation_node(state: AgentState):
    """Fast static grading — no LLM."""
    result = check_answer(state["current_problem"], state["user_response"])
    return {"is_correct": result, "steps_completed": 1}


def analysis_node(state: AgentState):
    """AI feedback and skill diagnosis."""
    problem = state.get("current_problem") or {}
    result = analyze_and_update_progress(
        user_id=state["user_id"],
        problem_id=str(problem.get("id", "")),
        is_correct=state.get("is_correct", False),
        mode=state.get("mode", "Pattern"),
    )
    return {"feedback": result["feedback"], "steps_completed": 1}


def followup_node(state: AgentState):
    """Follow-up question + keyword chips for chip-based mobile interaction."""
    q_and_chips = generate_followup(state["current_problem"])
    return {
        "feedback": q_and_chips["question"],
        "current_problem": q_and_chips,
        "steps_completed": 1,
    }


def route_after_validation(state: AgentState) -> str:
    if state.get("mode") == "Follow-up" and state.get("is_correct"):
        return "followup"
    return "analysis"


# ── Graph assembly ─────────────────────────────────────────────────────────────
workflow = StateGraph(AgentState)

workflow.add_node("selection", selection_node)
workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("validation", validation_node)
workflow.add_node("analysis", analysis_node)
workflow.add_node("followup", followup_node)

workflow.set_entry_point("selection")
workflow.add_edge("selection", "orchestrator")
workflow.add_edge("orchestrator", "validation")
workflow.add_conditional_edges(
    "validation",
    route_after_validation,
    {"followup": "followup", "analysis": "analysis"},
)
workflow.add_edge("analysis", END)
workflow.add_edge("followup", END)

app = workflow.compile()
