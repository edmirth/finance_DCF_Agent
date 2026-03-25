from __future__ import annotations
from arena.state import ThesisState, Conflict, DebateEntry
from arena.config import ARENA_CONFIG


def compute_consensus(agent_signals: dict) -> float:
    """
    Computes a consensus score in [0, 1] from agent signals.

    Algorithm:
      1. Find the majority view (most common view string).
         Tie-break: pick the view with the highest average confidence.
      2. alignment_ratio = count(majority holders) / total agents
      3. avg_confidence   = mean confidence of majority holders
      4. consensus        = alignment_ratio * avg_confidence

    Returns 0.0 if no signals.
    """
    if not agent_signals:
        return 0.0

    # Bucket signals by view
    view_buckets: dict[str, list[float]] = {}
    for sig in agent_signals.values():
        view = sig.get("view", "neutral")
        conf = sig.get("confidence", 0.0)
        view_buckets.setdefault(view, []).append(conf)

    # Find majority view; tie-break by highest average confidence
    def _view_sort_key(item: tuple) -> tuple:
        view, confs = item
        return (len(confs), sum(confs) / len(confs))

    majority_view, majority_confs = max(view_buckets.items(), key=_view_sort_key)

    total = len(agent_signals)
    alignment_ratio = len(majority_confs) / total
    avg_confidence = sum(majority_confs) / len(majority_confs)

    return round(alignment_ratio * avg_confidence, 3)


def pm_node(state: ThesisState) -> dict:
    """
    Portfolio Manager node.

    First pass (empty agent_signals):
      - Reads query_mode, sets active_agents from config
      - Sets next_action = "debate"
      - Logs a dispatch entry

    Subsequent passes (signals present):
      - Computes consensus score
      - Detects conflicting agents
      - Rewrites thesis_summary  # TODO: replace with LLM call
      - Sets next_action and conviction_level
    """
    agent_signals = state.get("agent_signals", {})
    current_round = state.get("round", 0)
    max_rounds = ARENA_CONFIG["max_rounds"]
    threshold = ARENA_CONFIG["consensus_threshold"]

    # ── First pass: no signals yet ───────────────────────────────────────────
    if not agent_signals:
        query_mode = state.get("query_mode", "full_ic")
        active_agents = ARENA_CONFIG["query_modes"].get(query_mode, [])
        dispatch_entry: DebateEntry = {
            "round": 0,
            "agent": "pm",
            "action": "dispatch",
            "content": (
                f"Dispatching {len(active_agents)} agents for "
                f"query_mode={query_mode}: {', '.join(active_agents)}"
            ),
        }
        return {
            "active_agents": active_agents,
            "next_action": "debate",
            "debate_log": [dispatch_entry],
        }

    # ── Subsequent passes: signals available ─────────────────────────────────
    consensus_score = compute_consensus(agent_signals)

    # Find majority view for conflict detection
    view_buckets: dict[str, list[str]] = {}
    for agent_name, sig in agent_signals.items():
        view = sig.get("view", "neutral")
        view_buckets.setdefault(view, []).append(agent_name)

    majority_view = max(view_buckets, key=lambda v: len(view_buckets[v]))

    # Opposing view pairs (asymmetric — cautious conflicts with bullish, etc.)
    opposing: dict[str, set[str]] = {
        "bullish":  {"bearish", "cautious"},
        "bearish":  {"bullish"},
        "cautious": {"bullish"},
        "neutral":  set(),
    }

    new_conflicts: list[Conflict] = []
    conflict_log_entries: list[DebateEntry] = []

    minority_agents = [
        agent_name
        for agent_name, sig in agent_signals.items()
        if sig.get("view") in opposing.get(majority_view, set())
    ]

    if minority_agents:
        majority_agents = view_buckets[majority_view]
        conflict_desc = (
            f"{', '.join(majority_agents)} ({majority_view}) vs "
            f"{', '.join(minority_agents)} ({', '.join(agent_signals[a]['view'] for a in minority_agents)})"
        )
        conflict: Conflict = {
            "agents": majority_agents + minority_agents,
            "description": conflict_desc,
            "round": current_round,
        }
        new_conflicts.append(conflict)
        conflict_log_entries.append({
            "round": current_round,
            "agent": "pm",
            "action": "conflict_flagged",
            "content": f"Conflict: {conflict_desc}",
        })

    # Decide next action
    if current_round >= max_rounds or consensus_score >= threshold:
        next_action = "finalise"
    else:
        next_action = "debate"

    # Conviction level
    if consensus_score >= 0.80:
        conviction_level = "high"
    elif consensus_score >= 0.50:
        conviction_level = "medium"
    else:
        conviction_level = "low"

    # Views summary for thesis
    view_summary_parts = []
    for view, agents in sorted(view_buckets.items(), key=lambda x: -len(x[1])):
        view_summary_parts.append(f"{view} ({', '.join(agents)})")
    views_summary = "; ".join(view_summary_parts)

    conflict_note = ""
    if new_conflicts:
        conflict_note = f" Conflict flagged: {new_conflicts[0]['description']}."

    # TODO: replace with LLM call
    thesis_summary = (
        f"Round {current_round} synthesis: {views_summary}. "
        f"Consensus: {consensus_score:.3f}.{conflict_note}"
    )

    synthesis_entry: DebateEntry = {
        "round": current_round,
        "agent": "pm",
        "action": "synthesis",
        "content": (
            f"consensus={consensus_score:.3f} next_action={next_action} "
            f"conviction={conviction_level}"
        ),
    }

    return {
        "consensus_score": consensus_score,
        "thesis_summary": thesis_summary,
        "next_action": next_action,
        "conviction_level": conviction_level,
        "conflicts": new_conflicts,
        "debate_log": conflict_log_entries + [synthesis_entry],
    }
