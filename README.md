# AlgoSense AI

LangGraph-based LeetCode interview preparation coach.  
Pattern recognition · Big-O analysis · Interview follow-up simulation — optimized for one-handed mobile review.

---

## 1) Agent Concept

| Item | Description |
|---|---|
| Name | AlgoSense AI |
| Role | Adaptive LeetCode interview coach |
| Input | `AgentState` + selected mode (`Pattern`, `Big-O Drill`, `Follow-up`) + user response |
| Output | Curated problem card, static answer validation, GPT-4o feedback, optional follow-up question + keyword chips |
| LLM | OpenAI GPT-4o (feedback, follow-up generation, Big-O explanation, complexity caching) |
| DB | SQLite — 500 problems, user skill scores, spaced repetition logs |

---

## 2) Interaction Flow (Streamlit App)

```text
[Session Start]
      |
      v
[Scheduler] ──── mode=Follow-up ──▶ [Pass-first bucket]
      |                                      |
      | (Pattern / Big-O)                    |
      v                                      v
[Problem Card Display]            [Passed-problem Card Display]
      |                                      |
      v                                      v
[Pattern: MCQ 4-choice]      [Follow-up: AI question + 4 keyword chips]
[Big-O Drill: Time/Space select]            |
      |                                      |
      +──────────────────────────────────────+
                          |
                          v
              [Validator — zero-LLM grading]
                          |
                          v
              [Analyzer Agent (GPT-4o)]
              · Adaptive score delta (difficulty × mode)
              · 1-sentence tough-love feedback
              · SM-2 schedule update
                          |
                          v
              [Show Answer / Next Card]
                          |
                          v
              [Session Summary Dashboard]
```

---

## 3) LangGraph Workflow (graph.py)

```text
[START]
   |
   v
[selection]   ── selector_agent → scheduler (4-bucket priority)
   |
   v
[orchestrator] ── decide_mode() → reads user_stats + review_logs (no LLM)
                  · auto_mode=True  → writes mode to state
                  · auto_mode=False → passes through (manual mode respected)
   |
   v
[validation]  ── validator.py (zero-LLM, instant grading)
   |
   +─────────────────────────────+
   | mode==Follow-up             |
   | AND is_correct==True        |
   v                             v
[followup]                  [analysis]
(interview_agent GPT-4o)    (analyzer_agent GPT-4o)
   |                             |
   +──────────────+──────────────+
                  |
                  v
               [END]
```

---

## 4) Runtime Entry

| Entry | Purpose |
|---|---|
| `streamlit run main.py` | Daily Review Mode — full Streamlit app (primary) |
| `from graph import app; app.invoke(state)` | LangGraph workflow prototype |

---

## 5) Mode Details

### Pattern Mode
- Presents a problem description with MCQ 4-choice answers.
- Validates instantly via `tools/validator.py` (no LLM).
- GPT-4o generates 1-sentence feedback after submission.
- Score delta: difficulty-adjusted (+4 ~ +20 correct / -18 ~ -4 wrong).

### Big-O Drill Mode
- Displays a code snippet; user selects Time and Space complexity from dropdowns.
- Correct answers receive a 1.5× score multiplier.
- "Show Answer" triggers a cached GPT-4o explanation stored in `problems.complexity_explanation`.
- Explanation is generated once and persisted — no repeated LLM calls.

### Follow-up Mode (Interview Simulation)
- Scheduler prioritizes problems the user has already passed (`last_result = 'pass'`).
- GPT-4o generates one follow-up question and exactly 4 keyword chips per card.
- One chip is the correct key concept; three are plausible distractors.
- User taps a chip (no typing) — result is graded and feedback is delivered immediately.
- Score delta: fixed +20 correct / -8 wrong (advanced concept reward, no difficulty clamping).
- Interviewer-tone feedback: "Exactly! …" or "Not quite — …"

---

## 6) Implementation Notes

### Scheduler (`tools/scheduler.py`)
Four-bucket priority for Pattern / Big-O modes:
1. **Failures** — `last_result = 'fail'`, most recent first
2. **Stale** — not reviewed in 7+ days
3. **Weak patterns** — lowest 3 `skill_score` tags, unsolved cards only
4. **Fallback** — Blind 75 / NeetCode 150 priority list, unsolved first

Follow-up mode uses a separate path: `last_result = 'pass'` → most recently reviewed first.

### Analyzer (`agents/analyzer_agent.py`)
- `analyze_and_update_progress()` handles all 3 modes.
- `_clamp_delta_by_difficulty()` bounds score changes per difficulty tier.
- Follow-up mode bypasses difficulty clamping (fixed ±delta from LLM).
- SM-2 algorithm updates `interval_days` and `ease_factor` in `review_logs`.

### Big-O Cache (`agents/analyzer_agent.py → get_or_create_complexity_explanation`)
- Checks `problems.complexity_explanation` before calling LLM.
- Generates a one-sentence Korean explanation and persists it on first access.

### Orchestrator (`agents/orchestrator_agent.py`)
- `decide_mode(user_id, problem)` — pure DB logic, zero LLM cost.
- Decision tree: `skill_score < 55` → Pattern · `≥ 55` → Big-O Drill · `≥ 70 + last=pass` → Follow-up.
- Returns `OrchestratorResult` with `mode`, `skill_score`, `last_result`, `reason`.
- In `graph.py`: only fires when `auto_mode=True`; manual mode selections are respected.
- In `main.py`: result cached per card in `session_state`; reason displayed as badge caption.
- Enables parallel pre-fetch: `ThreadPoolExecutor` starts Follow-up generation the moment a card loads.

### Interview Agent (`agents/interview_agent.py`)
- `generate_followup_scenario()` calls GPT-4o with problem title, pattern, content, and snippet.
- Returns `{question, chips[4], correct_chip_index}`.
- Falls back to template on any parse/API error.

### Complexity Backfill (`tools/complexity_backfill.py`)
- Standalone script to infer and write `time_complexity` / `space_complexity` from `Solution.py`.
- Priority: regex extraction from `README_EN.md` → code analysis fallback.

### DB Schema (`tools/db_manager.py`)
```sql
problems      (id, title, pattern, difficulty, content, examples, constraints,
               mcq_options, correct_idx, snippet, followup_keywords,
               time_complexity, space_complexity, complexity_explanation)
user_stats    (user_id, tag, skill_score)
review_logs   (user_id, problem_id, last_reviewed, next_review_date,
               interval_days, ease_factor, last_result)
```

---

## 7) Project Structure

```text
.
├── main.py                        # Streamlit Daily Review app (primary entry)
├── state.py                       # LangGraph AgentState TypedDict
├── graph.py                       # LangGraph workflow (selection→validation→analysis/followup)
├── agents/
│   ├── orchestrator_agent.py      # Auto mode-decision (skill_score + review_logs, no LLM)
│   ├── selector_agent.py          # Scheduler wrapper for graph node
│   ├── analyzer_agent.py          # GPT-4o coach: feedback, score delta, SM-2 update
│   ├── interview_agent.py         # GPT-4o follow-up: question + 4 keyword chips
│   └── classification_agent.py    # Initial routing stub
├── tools/
│   ├── db_manager.py              # SQLite schema init + bulk insert helpers
│   ├── scheduler.py               # 4-bucket card selector + SM-2 schedule update
│   ├── validator.py               # Zero-LLM MCQ / keyword grader
│   ├── data_loader.py             # LeetCode ETL pipeline (parse → metadata → DB)
│   └── complexity_backfill.py     # Batch Big-O inference from README / Solution.py
└── data/
    └── leetcode.db                # 500 problems + user stats + review logs
```

---

## 8) Setup

```bash
# Install dependencies
pip install -e .

# Set OpenAI key
echo "OPENAI_API_KEY=sk-..." > .env

# (First time) Initialise DB and populate 500 problems
python3 tools/db_manager.py

# Run app
streamlit run main.py
```

> The app validates the API key and DB on startup and shows clear error messages if either is missing.
