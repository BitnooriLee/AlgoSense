"""Follow-up question and keyword chip generator (GPT-4o powered)."""

from __future__ import annotations

import json

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from state import AgentState

load_dotenv()

llm = init_chat_model("openai:gpt-4o")

_SYSTEM_PROMPT = """\
You are a senior software engineer conducting a mock coding interview.
Given a LeetCode-style problem and its solution snippet, generate ONE follow-up question
and EXACTLY 4 keyword chips (short phrases, max 4 words each).

Rules:
- The follow-up question must challenge the candidate to think deeper (e.g. memory constraints,
  scale, edge cases, alternative approaches).
- Exactly ONE chip must be the correct key concept that answers the follow-up.
- The other 3 chips must be plausible but incorrect for this specific follow-up.
- Vary the position of the correct chip randomly (0–3).

Return ONLY valid JSON with this exact shape:
{
  "question": "<follow-up question>",
  "chips": ["<chip0>", "<chip1>", "<chip2>", "<chip3>"],
  "correct_chip_index": <0|1|2|3>
}
"""


def generate_followup_scenario(problem: dict) -> dict:
    """Call GPT-4o to produce a follow-up question + 4 keyword chips.

    Returns a dict with keys: question, chips (list[str]), correct_chip_index (int).
    Falls back to template-based generation on any error.
    """
    title = problem.get("title", "Unknown Problem")
    pattern = problem.get("pattern", "Algorithm")
    content = (problem.get("content") or "")[:800]
    snippet = (problem.get("snippet") or "")[:800]

    user_msg = (
        f"Problem: {title}\n"
        f"Pattern: {pattern}\n"
        f"Description:\n{content}\n\n"
        f"Solution snippet:\n{snippet}\n"
    )

    try:
        raw = llm.invoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]).content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        question = str(parsed["question"]).strip()
        chips = [str(c).strip() for c in parsed["chips"]]
        correct_idx = int(parsed["correct_chip_index"])

        if len(chips) != 4 or not (0 <= correct_idx <= 3) or not question:
            raise ValueError("Malformed response")

        return {"question": question, "chips": chips, "correct_chip_index": correct_idx}

    except Exception:
        return _fallback_followup(problem)


def _fallback_followup(problem: dict) -> dict:
    """Template-based fallback when LLM call fails."""
    pattern = problem.get("pattern", "Algorithm")
    followup_kws: list[str] = problem.get("followup_keywords") or []

    question = (
        f"What if the input size grew to 10^9? "
        f"How would you modify your {pattern} approach to handle memory constraints?"
    )
    if len(followup_kws) >= 4:
        chips = followup_kws[:4]
        correct_idx = 0
    else:
        chips = ["In-place swap", "External sort", "Bitmask trick", "Streaming window"]
        correct_idx = 0

    return {"question": question, "chips": chips, "correct_chip_index": correct_idx}


# ── LangGraph node compat wrapper ─────────────────────────────────────────────

def build_follow_up(state: AgentState) -> tuple[str, list[str]]:
    """Return (question, chips) for LangGraph node usage."""
    result = generate_followup_scenario(state.get("current_problem") or {})
    return result["question"], result["chips"]


def generate_followup(current_problem: dict) -> dict:
    """graph.py node wrapper — returns question + chips payload."""
    return generate_followup_scenario(current_problem)
