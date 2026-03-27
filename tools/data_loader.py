"""Batch metadata loader for LeetCode problems."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from langchain_core.tools import tool

from tools.db_manager import DEFAULT_DB_PATH, get_connection

SYSTEM_PROMPT_TEMPLATE = """You are a LeetCode Expert. I will provide a list of {N} LeetCode problems (Title + Description + Solution Code).
Your task is to generate learning metadata for EACH problem in a STRICT JSON LIST format.

For each problem, return:
1. "id": Problem ID
2. "primary_pattern": Most common interview tag (e.g., "Two Pointers")
3. "all_patterns": List of all valid patterns (e.g., ["DFS", "Recursion"])
4. "mcq_options": 4 choices (A, B, C, D) focusing on the optimal approach or Big-O.
5. "correct_idx": 0-3
6. "followup_keywords": 3 interview-focused keywords for deeper discussion.

CRITICAL RULES:
- Output MUST be a valid JSON List: [{"id": "..."}, {"id": "..."}]
- No conversational text, only JSON.
- If a problem is too complex, prioritize the "Optimal" interview solution for MCQ.
- Language: English only.
"""


def build_batch_prompt(batch: list[dict[str, Any]]) -> str:
    """Create one compact prompt text from a list of problems."""
    payload = "\n---\n".join(
        [
            (
                f"ID: {p.get('id', '')}\n"
                f"Title: {p.get('title', '')}\n"
                f"Content: {str(p.get('content', ''))[:700]}\n"
                f"Code: {str(p.get('solution', ''))[:400]}"
            )
            for p in batch
        ]
    )
    return f"{SYSTEM_PROMPT_TEMPLATE.format(N=len(batch))}\n\n{payload}"


def apply_metadata_to_db(metadata_items: list[dict[str, Any]], db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Upsert generated metadata into `problems` table."""
    with get_connection(db_path) as conn:
        for item in metadata_items:
            problem_id = str(item["id"])
            primary_pattern = str(item.get("primary_pattern", "General"))
            mcq_options = json.dumps(item.get("mcq_options", []))
            correct_idx = int(item.get("correct_idx", 0))
            followup_keywords = json.dumps(item.get("followup_keywords", []))

            conn.execute(
                """
                UPDATE problems
                SET pattern = ?, mcq_options = ?, correct_idx = ?, followup_keywords = ?
                WHERE id = ?;
                """,
                (primary_pattern, mcq_options, correct_idx, followup_keywords, problem_id),
            )
        conn.commit()


def process_in_batches(
    problems_list: list[dict[str, Any]],
    llm_infer: Callable[[str], str],
    batch_size: int = 20,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """
    Generate metadata in batches, parse JSON list output, and write to DB.

    - `llm_infer(prompt)` must return JSON list text.
    """
    final_data: list[dict[str, Any]] = []
    for i in range(0, len(problems_list), batch_size):
        batch = problems_list[i : i + batch_size]
        prompt = build_batch_prompt(batch)
        raw_output = llm_infer(prompt)
        result_json = json.loads(raw_output)
        if not isinstance(result_json, list):
            raise ValueError("LLM output must be a JSON list.")
        apply_metadata_to_db(result_json, db_path=db_path)
        final_data.extend(result_json)
    return final_data


@tool
def build_prompt_tool(problems_list: list[dict[str, Any]], batch_size: int = 20) -> list[str]:
    """
    Build prompts only (no API call) for debugging or manual generation.
    """
    prompts: list[str] = []
    for i in range(0, len(problems_list), batch_size):
        batch = problems_list[i : i + batch_size]
        prompts.append(build_batch_prompt(batch))
    return prompts