from __future__ import annotations
from arena.config import ARENA_CONFIG
from arena.state import ThesisState, DebateEntry


def _is_in_conflict(agent_name: str, conflicts: list) -> bool:
    """Check whether this agent appears in any flagged conflict."""
    for c in conflicts:
        if agent_name in c.get("agents", []):
            return True
    return False


def _merge_signals(state: ThesisState, result: dict) -> dict:
    """
    LangGraph replaces dict fields on each node update (no automatic merge).
    This helper ensures agent_signals accumulates across sequential nodes the
    same way raw_outputs does inside each individual agent file.
    """
    accumulated = dict(state.get("agent_signals", {}))
    accumulated.update(result.get("agent_signals", {}))
    return {**result, "agent_signals": accumulated}


def fundamental_node(state: ThesisState) -> dict:
    from arena.fundamental_agent import run_fundamental_agent
    return _merge_signals(state, run_fundamental_agent(state))


def quant_node(state: ThesisState) -> dict:
    from arena.quant_agent import run_quant_agent
    return _merge_signals(state, run_quant_agent(state))


def macro_node(state: ThesisState) -> dict:
    from arena.macro_agent import run_macro_agent
    return _merge_signals(state, run_macro_agent(state))


def risk_node(state: ThesisState) -> dict:
    from arena.risk_agent import run_risk_agent
    return _merge_signals(state, run_risk_agent(state))


def sentiment_node(state: ThesisState) -> dict:
    from arena.sentiment_agent import run_sentiment_agent
    return _merge_signals(state, run_sentiment_agent(state))


STUB_REGISTRY = {
    "fundamental": fundamental_node,
    "quant":       quant_node,
    "macro":       macro_node,
    "risk":        risk_node,
    "sentiment":   sentiment_node,
}


def run_active_agents(state: ThesisState) -> dict:
    """
    The 'agents' LangGraph node.
    Calls only the active agent stubs, merges their signals,
    increments the round counter, and logs each write to debate_log.
    """
    active = state.get("active_agents", [])
    current_round = state.get("round", 0)

    merged_signals: dict = {}
    merged_raw: dict = dict(state.get("raw_outputs", {}))  # carry forward prior rounds
    log_entries: list[DebateEntry] = []

    for agent_name in active:
        stub_fn = STUB_REGISTRY.get(agent_name)
        if stub_fn is None:
            continue
        result = stub_fn(state)
        agent_signal = result.get("agent_signals", {}).get(agent_name, {})
        merged_signals[agent_name] = agent_signal
        merged_raw.update(result.get("raw_outputs", {}))
        log_entries.append({
            "round": current_round + 1,
            "agent": agent_name,
            "action": "signal_written",
            "content": (
                f"view={agent_signal.get('view')} "
                f"conf={agent_signal.get('confidence')} — "
                f"{agent_signal.get('reasoning', '')}"
            ),
        })

    new_round = current_round + 1

    return {
        "agent_signals": merged_signals,
        "signal_history": [merged_signals],
        "raw_outputs":    merged_raw,
        "round": new_round,
        "debate_log": log_entries,
    }


# ---------------------------------------------------------------------------
# Level 2 — sequential graph nodes
# ---------------------------------------------------------------------------

def sequence_start_node(state: ThesisState) -> dict:
    """
    Pass-through entry point for the sequential agent loop.
    No state changes — its purpose is to be the single convergence
    point (initial entry from PM and loop-back from sequence_advance)
    before the conditional router dispatches the next agent.
    """
    return {}


def route_from_sequence_start(state: ThesisState) -> str:
    """
    Conditional edge called after sequence_start_node.
    Returns active_agents[0] to dispatch the next agent, or
    'sequence_done' when the queue is exhausted.
    Agent names in active_agents equal their LangGraph node names.
    """
    active = state.get("active_agents", [])
    if not active:
        return "sequence_done"
    return active[0]


def sequence_advance_node(state: ThesisState) -> dict:
    """
    Runs after each individual agent node (in its own super-step).
    At this point the agent's output is already committed to state.

    Responsibilities:
      1. Pop active_agents[0] (the agent that just completed).
      2. Write a DebateEntry for that agent using its committed signal.
    """
    active = list(state.get("active_agents", []))
    if not active:
        return {"active_agents": [], "debate_log": []}

    completed = active.pop(0)
    signal = state.get("agent_signals", {}).get(completed, {})
    entry: DebateEntry = {
        "round":   state.get("round", 0) + 1,  # preview; sequence_done increments later
        "agent":   completed,
        "action":  "signal_written",
        "content": (
            f"view={signal.get('view')} "
            f"conf={signal.get('confidence')} — "
            f"{signal.get('reasoning', '')}"
        ),
    }
    return {"active_agents": active, "debate_log": [entry]}


def sequence_done_node(state: ThesisState) -> dict:
    """
    Runs once after all agents in the current round have completed.

    Responsibilities:
      1. Increment round counter.
      2. Snapshot agent_signals into signal_history (operator.add appends).
      3. Reset active_agents for round 2. For @mention queries
         (direct_agents= annotation present) we keep only those agents;
         otherwise we use the full query_mode sequence.
    """
    import re as _re
    query = state.get("query", "")
    direct_match = _re.search(r'direct_agents=([\w,]+)', query)
    if direct_match:
        valid = set(ARENA_CONFIG["query_modes"].get("full_ic", []))
        next_sequence = [a for a in direct_match.group(1).split(',') if a in valid]
    else:
        query_mode = state.get("query_mode", "full_ic")
        next_sequence = list(ARENA_CONFIG["query_modes"].get(
            query_mode, ARENA_CONFIG["query_modes"]["full_ic"]
        ))
    return {
        "round":          state.get("round", 0) + 1,
        "signal_history": [dict(state.get("agent_signals", {}))],
        "active_agents":  next_sequence,
    }
