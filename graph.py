"""LangGraph workflow: selection -> validation -> analysis/followup."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.analyzer_agent import analyze_answer
from agents.interview_agent import generate_followup
from agents.selector_agent import select_problem
from state import AgentState
from tools.validator import check_answer


def selection_node(state: AgentState):
    """Selection node: fetch one problem using scheduler-backed selector."""
    problem = select_problem(state["user_id"], state["mode"])
    return {"current_problem": problem, "steps_completed": 1}


def validation_node(state: AgentState):
    """Validation node: fast static grading."""
    result = check_answer(state["current_problem"], state["user_response"])
    return {"is_correct": result, "steps_completed": 1}


def analysis_node(state: AgentState):
    """Analysis node: AI-style feedback and diagnosis."""
    feedback = analyze_answer(state)
    return {"feedback": feedback, "steps_completed": 1}


def followup_node(state: AgentState):
    """Follow-up node for chip-based mobile interaction."""
    q_and_chips = generate_followup(state["current_problem"])
    return {
        "feedback": q_and_chips["question"],
        "current_problem": q_and_chips,
        "steps_completed": 1,
    }


workflow = StateGraph(AgentState)
workflow.add_node("selection", selection_node)
workflow.add_node("validation", validation_node)
workflow.add_node("analysis", analysis_node)
workflow.add_node("followup", followup_node)
workflow.set_entry_point("selection")
workflow.add_edge("selection", "validation")


def route_after_validation(state: AgentState):
    if state["mode"] == "Follow-up" and state["is_correct"]:
        return "followup"
    return "analysis"


workflow.add_conditional_edges(
    "validation",
    route_after_validation,
    {"followup": "followup", "analysis": "analysis"},
)
workflow.add_edge("analysis", END)
workflow.add_edge("followup", END)

app = workflow.compile()
