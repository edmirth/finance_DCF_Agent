from __future__ import annotations
from arena.graph import build_arena
from arena.state import ThesisState


def run_arena(
    query: str,
    ticker: str,
    query_mode: str = "full_ic"
) -> dict:
    """
    Builds the arena and runs it for a given investment query.
    Returns the final ThesisState dict.

    Args:
        query:      Natural language question e.g. "Should we long AAPL?"
        ticker:     Stock ticker symbol e.g. "AAPL"
        query_mode: Which agents to activate — see ARENA_CONFIG["query_modes"]

    Returns:
        Final state dict with thesis_summary, final_decision,
        conviction_level, investment_memo, debate_log, and all agent_signals.
    """
    arena = build_arena()

    initial_state: ThesisState = {
        "query":           query,
        "ticker":          ticker.upper(),
        "query_mode":      query_mode,
        "thesis_summary":  "",
        "agent_signals":   {},
        "signal_history":  [],
        "conflicts":       [],
        "debate_log":      [],
        "raw_outputs":     {},
        "agent_questions": {},
        "agent_answers":   {},
        "consensus_score": 0.0,
        "next_action":     "",
        "round":           0,
        "active_agents":   [],
        "final_decision":  None,
        "conviction_level": None,
        "investment_memo": None,
    }

    # Default LangGraph recursion limit (25) is too low for 2 rounds × 5 agents.
    # Each agent traverses 3 nodes (sequence_start → agent → sequence_advance),
    # plus PM and memo nodes, totalling ~40 steps for a full IC run.
    return arena.invoke(initial_state, config={"recursion_limit": 100})
