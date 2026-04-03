from __future__ import annotations
import json
from anthropic import Anthropic
from arena.state import ThesisState, Conflict, DebateEntry
from arena.config import ARENA_CONFIG

HAIKU_MODEL  = "claude-haiku-4-5-20251001"


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


def _synthesize_thesis(
    state: ThesisState,
    consensus_score: float,
    views_summary: str,
    new_conflicts: list,
    current_round: int,
    has_open_questions: bool,
) -> str:
    """
    Uses Haiku to write a concise 3-4 sentence investment thesis synthesis.
    This feeds back into agents' context for the next debate round.
    Falls back to the formula string if the LLM call fails.
    """
    ticker     = state.get("ticker", "UNKNOWN")
    signals    = state.get("agent_signals", {})
    raw_outputs = state.get("raw_outputs", {})
    agent_answers = state.get("agent_answers", {})
    agent_questions = state.get("agent_questions", {})

    # Build concise signal lines
    signal_lines = "\n".join(
        f"  {name}: {sig['view']} ({sig['confidence']:.0%}) — {sig['reasoning'][:120]}"
        for name, sig in signals.items()
    )

    # Truncate raw outputs to keep the prompt lean
    raw_lines = "\n".join(
        f"  [{name.upper()}]\n{text[:400]}"
        for name, text in raw_outputs.items()
    )

    # Summarise Q&A if any
    qa_lines = ""
    if agent_answers:
        parts = []
        for answering, askers in agent_answers.items():
            for asker, answer in askers.items():
                q = agent_questions.get(asker, {}).get(answering, "")
                if q:
                    parts.append(f"  {asker} asked {answering}: {q[:80]}\n  Answer: {answer[:120]}")
        qa_lines = "\n".join(parts)

    conflict_text = (
        "; ".join(c["description"] for c in new_conflicts)
        if new_conflicts else "none"
    )

    prompt = f"""You are the Portfolio Manager synthesizing a round-{current_round} investment committee debate on {ticker}.

Analyst signals:
{signal_lines}

Key findings from analysts:
{raw_lines}

Conflicts: {conflict_text}
Q&A exchanges this round:
{qa_lines if qa_lines else "none"}

Consensus score: {consensus_score:.1%}

Write a structured synthesis using exactly this markdown format:

**[ticker] — Round [N] Synthesis**

[One sentence on the dominant thesis with the single most important number behind it.]

**Key tension**
[One sentence on the core unresolved risk or disagreement holding back conviction.]

**What remains open**
[One sentence on what Q&A clarified, or what critical unknown still needs resolving.]

**Conviction shift**
[One sentence: the specific condition or data point that would materially change the view.]

Be direct and precise. Use actual ticker-specific numbers. No extra sections. No preamble."""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[PM] _synthesize_thesis LLM call failed: {e}")
        # Fallback to formula
        view_parts = []
        for view, agents in sorted(
            {sig["view"]: [] for sig in signals.values()}.items()
        ):
            holders = [n for n, s in signals.items() if s["view"] == view]
            view_parts.append(f"{view} ({', '.join(holders)})")
        views_summary_fb = "; ".join(view_parts)
        conflict_note = (
            f" Conflict flagged: {new_conflicts[0]['description']}." if new_conflicts else ""
        )
        return (
            f"Round {current_round} synthesis: {views_summary_fb}. "
            f"Consensus: {consensus_score:.3f}.{conflict_note}"
        )


def _has_unanswered_questions(state: ThesisState) -> bool:
    """Returns True if any agent has asked a question that the target agent has not yet answered."""
    questions = state.get("agent_questions", {})
    answers = state.get("agent_answers", {})
    for asking_agent, targets in questions.items():
        for target_agent in targets:
            if asking_agent not in answers.get(target_agent, {}):
                return True
    return False


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
        query = state.get("query", "")

        # @mention override: user explicitly named agents → run only those
        import re as _re
        direct_match = _re.search(r'direct_agents=([\w,]+)', query)
        if direct_match:
            valid = set(ARENA_CONFIG["query_modes"].get("full_ic", []))
            active_agents = [a for a in direct_match.group(1).split(',') if a in valid]
        else:
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
        from arena.progress import emit_arena_event
        emit_arena_event({
            "type": "arena_dispatch",
            "round": 1,
            "agents": active_agents,
            "query_mode": query_mode,
        })
        return {
            "active_agents": active_agents,
            "next_action": "debate",
            "debate_log": [dispatch_entry],
        }

    # ── Subsequent passes: signals available ─────────────────────────────────
    # For @mention / direct-agent queries: skip debate rounds, go straight to memo.
    query = state.get("query", "")
    import re as _re
    if _re.search(r'direct_agents=', query):
        consensus_score = compute_consensus(agent_signals)
        views_summary = ", ".join(
            f"{n}: {s['view']}" for n, s in agent_signals.items()
        )
        thesis_summary = _synthesize_thesis(
            state, consensus_score, views_summary, [], current_round, False
        )
        return {
            "next_action":     "finalise",
            "consensus_score": consensus_score,
            "conviction_level": "medium",
            "thesis_summary":  thesis_summary,
            "debate_log":      [],
        }

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
    has_open_questions = _has_unanswered_questions(state)

    if current_round >= max_rounds:
        next_action = "finalise"                                    # safety valve — always wins
    elif consensus_score >= threshold and not has_open_questions:
        next_action = "finalise"
    else:
        next_action = "debate"                                      # low consensus OR open questions

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

    # Build open questions note if any are unresolved (used in fallback only)
    open_q_note = ""
    if has_open_questions:
        open_items = []
        for asker, targets in state.get("agent_questions", {}).items():
            for target, q_text in targets.items():
                if asker not in state.get("agent_answers", {}).get(target, {}):
                    open_items.append(f"{asker}→{target}: {q_text[:60]}")
        if open_items:
            open_q_note = f" Open questions: {'; '.join(open_items)}."

    thesis_summary = _synthesize_thesis(
        state, consensus_score, views_summary, new_conflicts, current_round, has_open_questions
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

    from arena.progress import emit_arena_event
    if new_conflicts:
        emit_arena_event({
            "type": "arena_conflict",
            "round": current_round,
            "description": new_conflicts[0]["description"],
        })
    emit_arena_event({
        "type": "arena_synthesis",
        "round": current_round,
        "consensus_score": consensus_score,
        "conviction_level": conviction_level,
        "next_action": next_action,
        "thesis_summary": thesis_summary,
    })

    return {
        "consensus_score": consensus_score,
        "thesis_summary": thesis_summary,
        "next_action": next_action,
        "conviction_level": conviction_level,
        "conflicts": new_conflicts,
        "debate_log": conflict_log_entries + [synthesis_entry],
    }
