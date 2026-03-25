from __future__ import annotations
from arena.state import ThesisState


def output_node(state: ThesisState) -> dict:
    """
    Reads the final agent signals and consensus score.
    Writes final_decision, conviction_level, and investment_memo.
    """
    signals = state.get("agent_signals", {})
    consensus = state.get("consensus_score", 0.0)
    ticker = state.get("ticker", "UNKNOWN")
    rounds_run = state.get("round", 0)

    # Determine final view from majority
    if signals:
        views = [s["view"] for s in signals.values()]
        final_view = max(set(views), key=views.count)
    else:
        final_view = "neutral"

    # Conviction from consensus score
    if consensus >= 0.80:
        conviction = "high"
    elif consensus >= 0.60:
        conviction = "medium"
    else:
        conviction = "low"

    # Map view to decision language
    decision_map = {
        "bullish":  f"LONG {ticker}",
        "bearish":  f"AVOID / SHORT {ticker}",
        "neutral":  f"HOLD {ticker} — MONITOR",
        "cautious": f"UNDERWEIGHT {ticker}",
    }
    final_decision = (
        f"{decision_map.get(final_view, f'HOLD {ticker}')} — {conviction} conviction"
    )

    # Build investment memo
    signal_lines = "\n".join(
        f"  {name.upper():15} {sig['view'].upper():8} "
        f"conf:{sig['confidence']:.0%}  {sig['reasoning']}"
        for name, sig in signals.items()
    )

    memo = (
        f"INVESTMENT COMMITTEE MEMO — {ticker}\n"
        f"{'='*52}\n"
        f"DECISION: {final_decision}\n"
        f"CONSENSUS: {consensus:.0%} after {rounds_run} round(s)\n\n"
        f"ANALYST SIGNALS:\n{signal_lines}\n\n"
        f"THESIS:\n{state.get('thesis_summary', 'No summary available.')}\n"
    )

    if state.get("conflicts"):
        conflict_lines = "\n".join(
            f"  Round {c['round']}: {c['description']}"
            for c in state["conflicts"]
        )
        memo += f"\nCONFLICTS IDENTIFIED:\n{conflict_lines}\n"

    return {
        "final_decision": final_decision,
        "conviction_level": conviction,
        "investment_memo": memo,
    }
