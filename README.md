# AlgoSense AI

> **An adaptive LeetCode interview coach powered by LangGraph, GPT-4o, and spaced repetition.**  
> Built for engineers who want to stay sharp — one-handed, mobile-first, 10 cards a day.

<br/>

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.1+-1C3C3C?style=flat-square)
![LangChain](https://img.shields.io/badge/LangChain-0.3+-1C3C3C?style=flat-square&logo=chainlink&logoColor=white)
![OpenAI](https://img.shields.io/badge/GPT--4o-OpenAI-412991?style=flat-square&logo=openai&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.44+-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-500%20Problems-003B57?style=flat-square&logo=sqlite&logoColor=white)

---

## What Is This?

AlgoSense is a **multi-agent interview prep system** that adapts to your skill level in real time.

Instead of mindlessly grinding problems, AlgoSense:

- **Knows where you're weak** — tracks per-pattern skill scores across 500 LeetCode problems
- **Decides what to study** — Orchestrator agent picks the right mode (Pattern / Big-O / Interview) based on your history, with zero LLM cost
- **Teaches, not just tests** — GPT-4o delivers concise, tough-love feedback after every answer
- **Remembers your schedule** — SM-2 spaced repetition ensures you review at exactly the right time
- **Runs in 10 minutes** — 10-card daily sessions, tap-based UI, no typing required

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Streamlit UI (main.py)                  │
│   User ID → Mode → 10-Card Session → Answer → Feedback → Score  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
            ┌───────────────▼───────────────┐
            │       LangGraph Workflow       │
            │                               │
            │  [selection]                  │  selector_agent → 4-bucket scheduler
            │      │                        │
            │  [orchestrator]               │  decide_mode() — pure DB, no LLM
            │      │                        │  skill < 55  → Pattern
            │      │                        │  skill ≥ 55  → Big-O Drill
            │      │                        │  skill ≥ 70 + passed → Follow-up
            │      │                        │
            │  [validation]                 │  zero-LLM instant grading
            │      │                        │
            │   ┌──┴──────────────┐         │
            │   │                 │         │
            │ [followup]      [analysis]    │  GPT-4o agents (parallel prefetch)
            │   │                 │         │
            └───┴─────────────────┴─────────┘
                          │
              ┌───────────▼────────────┐
              │     SQLite Database     │
              │  500 problems           │
              │  user_stats (scores)    │
              │  review_logs (SM-2)     │
              └────────────────────────┘
```

---

## Three Study Modes

### Pattern Recognition
The foundation. Given a problem description, choose the correct algorithmic approach from 4 options.

- Instant grading via `validator.py` — no LLM latency
- GPT-4o delivers one-sentence feedback after submission
- Score delta scaled by difficulty: Easy (+4~+8) → Hard (+12~+20)

### Big-O Drill
Code snippet is shown. You select Time and Space complexity from dropdowns.

- String-normalized matching (e.g., `O(n log n)` vs `O(N log N)`)
- Correct answers earn a **1.5× score multiplier**
- "Show Answer" triggers a GPT-4o complexity explanation — generated once, cached forever in DB

### Follow-up Interview Simulation
For problems you've already passed. GPT-4o acts as a FAANG-style interviewer.

- Generates a follow-up question + 4 keyword chips (1 correct, 3 plausible distractors)
- User taps a chip — no typing, optimized for one-handed mobile review
- Score delta: fixed ±20 / -8 (advanced concept, bypasses difficulty clamping)
- Prefetched via `ThreadPoolExecutor` the moment a card loads — zero wait time

---

## Scheduler: Four-Bucket Priority

Rather than random or sequential ordering, the scheduler ensures the highest-impact cards surface first:

| Priority | Condition | Reason |
|----------|-----------|--------|
| 1st | `last_result = 'fail'`, most recent | Fix failures before they compound |
| 2nd | Not reviewed in 7+ days | SM-2 due date enforcement |
| 3rd | Lowest 3 `skill_score` patterns | Target your weakest areas |
| 4th | Blind 75 / NeetCode 150 list | Curated fallback for new users |

Follow-up mode uses a separate path: problems with `last_result = 'pass'`, most recently reviewed first.

---

## Agent Design

| Agent | Role | LLM? |
|-------|------|-------|
| `orchestrator_agent` | Reads `user_stats` + `review_logs`, decides study mode | No |
| `selector_agent` | Wraps scheduler for LangGraph node compatibility | No |
| `analyzer_agent` | Feedback, score delta, SM-2 update, Big-O explanation cache | GPT-4o |
| `interview_agent` | Generates follow-up question + 4 chips as structured JSON | GPT-4o |
| `validator` | MCQ index / keyword matching grader | No |

**Design principle:** Only call the LLM when human-quality language is actually needed. Orchestration, scheduling, and grading all run locally at zero cost.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.13+ |
| Agent Orchestration | LangGraph `StateGraph` |
| LLM | LangChain + LangChain-OpenAI → GPT-4o |
| UI | Streamlit (mobile-first, one-handed layout) |
| Database | SQLite — 500 problems, user stats, review logs |
| Scheduling Algorithm | SM-2 (SuperMemo 2) spaced repetition |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` (follow-up prefetch) |
| Packaging | `pyproject.toml` + `uv` |

---

## Project Structure

```
AlgoSense/
├── main.py                        # Streamlit Daily Review app (primary entry)
├── state.py                       # LangGraph AgentState TypedDict
├── graph.py                       # LangGraph pipeline: selection → validation → analysis/followup
├── agents/
│   ├── orchestrator_agent.py      # Auto mode-selection (DB only, no LLM)
│   ├── selector_agent.py          # Scheduler wrapper for graph node
│   ├── analyzer_agent.py          # GPT-4o: feedback + score delta + SM-2 + Big-O cache
│   ├── interview_agent.py         # GPT-4o: follow-up question + 4 keyword chips
│   └── classification_agent.py   # Routing stub (extensible)
├── tools/
│   ├── db_manager.py              # SQLite schema init + bulk insert helpers
│   ├── scheduler.py               # 4-bucket card selector + SM-2 schedule updater
│   ├── validator.py               # Zero-LLM MCQ and keyword grader
│   ├── data_loader.py             # LeetCode ETL pipeline (parse → metadata → DB)
│   └── complexity_backfill.py     # Batch Big-O inference from README / Solution.py
└── data/
    └── leetcode.db                # 500 problems + user stats + review logs
```

---

## Database Schema

```sql
problems    (id, title, pattern, difficulty, content, examples, constraints,
             mcq_options, correct_idx, snippet, followup_keywords,
             time_complexity, space_complexity, complexity_explanation)

user_stats  (user_id, tag, skill_score)

review_logs (user_id, problem_id, last_reviewed, next_review_date,
             interval_days, ease_factor, last_result)
```

The `complexity_explanation` column acts as a **persistent LLM cache** — generated once on first "Show Answer" and never re-fetched.

---

## Setup

```bash
# 1. Install dependencies
pip install -e .

# 2. Add your OpenAI API key
echo "OPENAI_API_KEY=sk-..." > .env

# 3. Initialize the database (first time only)
python3 tools/db_manager.py

# 4. Launch the app
streamlit run main.py
```

The app validates the API key and DB connection on startup and surfaces clear error messages if either is missing.

---

## Key Design Decisions

**Why LangGraph?**  
The study flow is fundamentally a stateful, conditional pipeline — not a chat loop. LangGraph's `StateGraph` makes the branching logic (`followup` vs. `analysis`) explicit and inspectable, rather than buried in `if/else` chains.

**Why SQLite instead of a vector store?**  
The knowledge base is structured and finite (500 problems). Pattern-matching and skill scoring are relational operations. SQLite gives sub-millisecond query latency with zero infrastructure.

**Why zero-LLM grading?**  
MCQ index comparison and string-normalized Big-O matching are deterministic and instant. Calling GPT-4o to grade a multiple-choice answer would add 1–2 seconds of latency per card with no accuracy benefit. LLM calls are reserved exclusively for generative tasks.

**Why SM-2?**  
The SM-2 algorithm is well-proven, simple to implement, and maps cleanly onto a SQL schema (`interval_days`, `ease_factor`). It ensures problems resurface at the moment forgetting is most likely — maximizing retention per review minute.

---

## AgentState

```python
class AgentState(TypedDict):
    mode: str                    # 'Pattern' | 'Big-O Drill' | 'Follow-up'
    user_id: str
    current_problem: dict
    user_response: str
    is_correct: bool
    feedback: str
    auto_mode: bool              # True → orchestrator decides mode
    steps_completed: Annotated[int, operator.add]
```

---

*Built as part of an AI Agents course assignment. Designed to be a real tool, not just a demo.*
