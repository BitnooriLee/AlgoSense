# AlgoSense AI

AlgoSense is a LangGraph-based LeetCode interview practice agent.

## 1) Agent Concept

| Item | Description |
|---|---|
| Name | AlgoSense AI |
| Role | LeetCode interview preparation coach |
| Input | `AgentState` + selected mode (`Pattern`, `Big-O`, `Follow-up`) + user response |
| Output | Problem selection, static answer validation, feedback generation, and optional follow-up question/chips |

## 2) Graph (Current Implementation)

```text
[START]
   |
   v
[Problem Curation Node]
[Selection Node]
   |
   v
[Validation Node]
   |
   +-----------------------------+
   | if mode == Follow-up        |
   | and is_correct == true      |
   v                             v
[Follow-up Node]             [Analysis Node]
   |                             |
   +-------------+---------------+
                 |
                 v
                [END]
```

## 3) Runtime Entry

- Main module: `main.py`
  - Loads `.env` via `python-dotenv`
  - Compiles a minimal `classification_agent` graph
- Practice workflow module: `graph.py`
  - Exposes compiled workflow as `app`
  - Run with `from graph import app` then `app.invoke(state)`

## 4) Implementation Notes

- `selection` uses `agents/selector_agent.py`, which calls `tools/scheduler.py`.
- `validation` uses `tools/validator.py` (`check_answer`) for low-latency grading.
- `analysis` uses `agents/analyzer_agent.py` (`analyze_answer`) for feedback.
- `followup` uses `agents/interview_agent.py` (`generate_followup`) for question + chips.
- DB and SRS are managed by:
  - `tools/db_manager.py` (`problems`, `user_stats`, `review_logs`)
  - `tools/scheduler.py` (due-first + weakest-tag + new-card fallback, SM-2 update)

## 5) Project Structure

```text
.
├── main.py
├── state.py
├── graph.py
├── agents/
│   ├── classification_agent.py
│   ├── selector_agent.py
│   ├── analyzer_agent.py
│   └── interview_agent.py
└── tools/
    ├── db_manager.py
    ├── complexity_backfill.py
    ├── scheduler.py
    └── validator.py
```
