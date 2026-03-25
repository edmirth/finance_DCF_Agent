from __future__ import annotations
from arena.state import ThesisState, AgentSignal, DebateEntry


def _is_in_conflict(agent_name: str, conflicts: list) -> bool:
    """Check whether this agent appears in any flagged conflict."""
    for c in conflicts:
        if agent_name in c.get("agents", []):
            return True
    return False


def fundamental_node(state: ThesisState) -> dict:
    base_reasoning = "P/E 15% below sector peers, strong FCF growth"
    if _is_in_conflict("fundamental", state.get("conflicts", [])):
        base_reasoning += "; revising after conflict"
    signal: AgentSignal = {
        "view": "bullish",
        "reasoning": base_reasoning,
        "confidence": 0.82,
    }
    return {"agent_signals": {"fundamental": signal}}


def quant_node(state: ThesisState) -> dict:
    base_reasoning = "Momentum factor positive, low beta vs index"
    if _is_in_conflict("quant", state.get("conflicts", [])):
        base_reasoning += "; revising after conflict"
    signal: AgentSignal = {
        "view": "bullish",
        "reasoning": base_reasoning,
        "confidence": 0.74,
    }
    return {"agent_signals": {"quant": signal}}


def macro_node(state: ThesisState) -> dict:
    base_reasoning = "Rate environment uncertain, tech rotation risk"
    if _is_in_conflict("macro", state.get("conflicts", [])):
        base_reasoning += "; revising after conflict"
    signal: AgentSignal = {
        "view": "neutral",
        "reasoning": base_reasoning,
        "confidence": 0.61,
    }
    return {"agent_signals": {"macro": signal}}


def risk_node(state: ThesisState) -> dict:
    base_reasoning = "High leverage on balance sheet, concentration risk"
    if _is_in_conflict("risk", state.get("conflicts", [])):
        base_reasoning += "; revising after conflict"
    signal: AgentSignal = {
        "view": "cautious",
        "reasoning": base_reasoning,
        "confidence": 0.88,
    }
    return {"agent_signals": {"risk": signal}}


def sentiment_node(state: ThesisState) -> dict:
    base_reasoning = "Positive earnings call tone, analyst upgrades"
    if _is_in_conflict("sentiment", state.get("conflicts", [])):
        base_reasoning += "; revising after conflict"
    signal: AgentSignal = {
        "view": "bullish",
        "reasoning": base_reasoning,
        "confidence": 0.77,
    }
    return {"agent_signals": {"sentiment": signal}}


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
    log_entries: list[DebateEntry] = []

    for agent_name in active:
        stub_fn = STUB_REGISTRY.get(agent_name)
        if stub_fn is None:
            continue
        result = stub_fn(state)
        agent_signal = result.get("agent_signals", {}).get(agent_name, {})
        merged_signals[agent_name] = agent_signal
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
        "round": new_round,
        "debate_log": log_entries,
    }
