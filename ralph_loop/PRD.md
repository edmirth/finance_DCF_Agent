# PRD: Finance Agent Arena

## Introduction

Build a LangGraph-based multi-agent investment committee arena under a new `finance_arena/` folder. A Portfolio Manager (PM) orchestrates 5 specialist agents (fundamental, quant, macro, risk, sentiment) in a cyclic debate loop — collecting signals, computing consensus, detecting conflicts, and deciding whether to loop or finalise. All agents are stubs with hardcoded signals so the arena runs end-to-end without any API keys. Real LLM agent logic is added later without touching the arena wiring.

## Goals

- Arena runs end-to-end with stub agents using `python -m finance_arena.main`
- PM correctly computes consensus score from agent signals each round
- Debate loop cycles until consensus ≥ 0.7, max rounds hit, or risk escalation triggered
- `signal_history` accumulates all rounds so PM can track signal drift
- All rule values (thresholds, max rounds, query modes) live in `ARENA_CONFIG` — never hardcoded
- Terminal output shows agent signals, conflicts, and final verdict using `rich`

## User Stories

### US-001: Create ARENA_CONFIG in config.py
**Description:** As a developer, I want all arena rules in one place so nothing is hardcoded in logic files.

**Acceptance Criteria:**
- [ ] Create `finance_arena/config.py` with `ARENA_CONFIG` dict containing: `consensus_threshold` (0.7), `max_rounds` (3), `query_modes` dict, `escalation_rules` dict (`unresolved_after_max_rounds: True`, `risk_escalation_threshold: 0.9`), `conflict_resolution` ("highest_confidence")
- [ ] `query_modes` has keys: `full_ic`, `quick_screen`, `risk_check`, `macro_view`
- [ ] `python -c "from finance_arena.config import ARENA_CONFIG; assert ARENA_CONFIG['consensus_threshold'] == 0.7"` passes

### US-002: Create ThesisState and nested TypedDicts in arena/state.py
**Description:** As a developer, I want a single source of truth for all state types so every agent reads from and writes to the same schema.

**Acceptance Criteria:**
- [ ] Create `finance_arena/arena/__init__.py` (empty)
- [ ] Create `finance_arena/arena/state.py` with `AgentSignal`, `Conflict`, `DebateEntry`, and `ThesisState` TypedDicts
- [ ] `AgentSignal` has fields: `view` (str), `reasoning` (str), `confidence` (float)
- [ ] `Conflict` has fields: `agents` (list[str]), `view_a` (str), `view_b` (str), `round` (int)
- [ ] `DebateEntry` has fields: `round` (int), `agent` (str), `action` (str), `content` (str)
- [ ] `ThesisState` has: `query`, `query_mode`, `thesis_summary`, `agent_signals` (plain dict — last-write-wins), `signal_history` (Annotated with operator.add), `conflicts` (Annotated with operator.add), `debate_log` (Annotated with operator.add), `consensus_score`, `next_action`, `round`, `active_agents`, `final_decision` (Optional), `conviction_level` (Optional)
- [ ] Uses `from __future__ import annotations` for Python 3.9 compatibility
- [ ] `python -c "from finance_arena.arena.state import ThesisState"` passes

### US-003: Create the five stub agent files
**Description:** As a developer, I want stub agents with hardcoded signals so the debate loop can run without any LLM calls.

**Acceptance Criteria:**
- [ ] Create `finance_arena/agents/__init__.py` (empty)
- [ ] Create `finance_arena/agents/fundamental.py` — `run(state)` returns bullish signal at confidence 0.82
- [ ] Create `finance_arena/agents/quant.py` — `run(state)` returns bullish signal at confidence 0.74
- [ ] Create `finance_arena/agents/macro.py` — `run(state)` returns neutral signal at confidence 0.61
- [ ] Create `finance_arena/agents/risk.py` — `run(state)` returns cautious signal at confidence 0.88
- [ ] Create `finance_arena/agents/sentiment.py` — `run(state)` returns bullish signal at confidence 0.77
- [ ] Each stub checks `state["conflicts"]` and appends a note to reasoning if the agent is involved in a conflict
- [ ] Each stub returns `{"agent_signals": {agent_name: AgentSignal}}` — no other keys
- [ ] No stub imports from any other agent module — only `ThesisState` from `arena.state`
- [ ] `python -c "from finance_arena.agents import fundamental, quant, macro, risk, sentiment"` passes

### US-004: Build compute_consensus and pm_node in agents/pm.py
**Description:** As the PM, I want to compute consensus from agent signals and drive the debate loop so the arena knows when to keep debating or finalise.

**Acceptance Criteria:**
- [ ] Create `finance_arena/agents/pm.py`
- [ ] `compute_consensus(signals)` finds the majority view, computes `fraction * avg_confidence` for majority holders, returns float rounded to 3 decimal places
- [ ] `compute_consensus` with default stub signals (3 bullish, 1 neutral, 1 cautious) returns a value between 0.4 and 0.5
- [ ] `pm_node(state)` on first pass (empty `agent_signals`): sets `active_agents` from `ARENA_CONFIG["query_modes"][query_mode]`, sets `next_action="debate"`, appends dispatch entry to `debate_log`
- [ ] `pm_node(state)` on subsequent passes: calls `compute_consensus`, detects conflicts (bullish↔bearish and bullish↔cautious are opposing pairs), rewrites `thesis_summary` as a programmatic string (comment: `# TODO: replace with LLM call`), sets `next_action` (finalise/escalate_to_human/debate), sets `conviction_level` (≥0.8→high, ≥0.5→medium, else→low)
- [ ] `pm_node` returns only new `debate_log` entries (not the full accumulated list)
- [ ] All threshold values read from `ARENA_CONFIG` — none hardcoded
- [ ] `python -c "from finance_arena.agents.pm import pm_node, compute_consensus"` passes

### US-005: Build route_from_pm in arena/router.py
**Description:** As the arena, I want a conditional router that decides whether to keep debating or exit so the loop has a clear termination contract.

**Acceptance Criteria:**
- [ ] Create `finance_arena/arena/router.py` with `route_from_pm(state) -> str`
- [ ] Returns `"output"` if risk agent confidence ≥ `risk_escalation_threshold` (priority 1)
- [ ] Returns `"output"` if `round >= max_rounds` (priority 2)
- [ ] Returns `"output"` if `consensus_score >= consensus_threshold` (priority 3)
- [ ] Returns `"agents"` otherwise
- [ ] On first call (empty `agent_signals`, round=0, score=0.0) correctly returns `"agents"`
- [ ] All threshold values read from `ARENA_CONFIG`
- [ ] `python -c "from finance_arena.arena.router import route_from_pm"` passes

### US-006: Wire the StateGraph in arena/graph.py
**Description:** As a developer, I want the arena graph compiled and ready to invoke so I can run the full debate loop end-to-end.

**Acceptance Criteria:**
- [ ] Create `finance_arena/arena/graph.py` with `build_arena()` and `agents_node(state)`
- [ ] `agents_node` reads `state["active_agents"]`, calls each active agent's `run(state)` sequentially, merges returned `agent_signals` dicts, increments `round` by 1, returns `{"agent_signals": merged, "signal_history": [merged], "round": new_round, "debate_log": [entries]}`
- [ ] `build_arena()` creates `StateGraph(ThesisState)`, adds nodes `"pm"`, `"agents"`, `"output"`, sets entry point to `"pm"`, adds conditional edge on `"pm"` using `route_from_pm` with mapping `{"agents": "agents", "output": "output"}`, adds fixed edge `"agents" → "pm"` (the loop), adds fixed edge `"output" → END`, returns `workflow.compile()`
- [ ] `output_node` sets `final_decision` to uppercase majority view or `"ESCALATE_TO_HUMAN"` based on `next_action`
- [ ] `python -c "from finance_arena.arena.graph import build_arena; build_arena()"` passes without error

### US-007: Create main.py entry point with rich terminal output
**Description:** As a developer, I want to run the arena from the command line and see a clear formatted output of agent signals, conflicts, and the final verdict.

**Acceptance Criteria:**
- [ ] Create `finance_arena/main.py` with `run_arena(query, query_mode)` function
- [ ] Initialises `ThesisState` with all fields set (Annotated lists initialised to `[]`)
- [ ] Invokes compiled arena graph and prints results using `rich`
- [ ] Terminal output includes: agent signals table (agent, view, confidence, reasoning), conflicts list with round numbers, debate log entry count and round count, final verdict panel (decision, conviction, consensus score, rounds run)
- [ ] `__main__` block calls `run_arena("Should we open a long position on AAPL this quarter?", "full_ic")`
- [ ] Create `finance_arena/requirements.txt` with: `langgraph>=0.2.0`, `langchain-core>=0.3.0`, `rich>=13.0.0`
- [ ] `python -m finance_arena.main` runs to completion and prints `ESCALATE_TO_HUMAN` verdict (consensus 0.466 never reaches 0.7, max rounds hit)
- [ ] `python finance_arena/main.py` also works (script-style invocation)

## Non-Goals

- No real LLM calls in any agent — stubs only for now
- No integration with existing codebase agents or tools
- No FastAPI endpoint or web UI for the arena
- No persistence — arena state is in-memory only
- No authentication or multi-user support
- No async execution — agents_node calls stubs sequentially

## Technical Considerations

- LangGraph 0.6.11 and langchain-core 0.3.27 are already installed in the project venv
- `rich` is already in `requirements.txt` at the project root
- Use `from __future__ import annotations` on all files for Python 3.9 compatibility (same pattern used in `backend/database.py`)
- Pattern reference for StateGraph build: `agents/equity_analyst_graph.py` and `agents/earnings_agent.py`
- Pattern reference for `Annotated[List[...], operator.add]`: `agents/earnings_agent.py` lines 40-76
- `finance_arena/` is a standalone package — run as `python -m finance_arena.main` from project root
