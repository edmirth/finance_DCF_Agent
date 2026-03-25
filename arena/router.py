from __future__ import annotations
from arena.state import ThesisState
from arena.config import ARENA_CONFIG


def route_from_pm(state: ThesisState) -> str:
    """
    Called after every PM node execution.
    Returns the name of the next node to route to.

    Exit conditions (checked in priority order):
      1. round >= max_rounds  — safety valve, force exit after max rounds
      2. consensus_score >= threshold  — happy path, agents agree
      3. next_action == "finalise"  — PM explicitly decided to finalise
    Otherwise keeps debating.
    """
    max_rounds = ARENA_CONFIG["max_rounds"]
    threshold = ARENA_CONFIG["consensus_threshold"]

    # Priority 1: safety valve — force exit after max rounds
    if state.get("round", 0) >= max_rounds:
        return "output"

    # Priority 2: happy path — consensus reached
    if state.get("consensus_score", 0.0) >= threshold:
        return "output"

    # Priority 3: PM explicitly set finalise
    if state.get("next_action") == "finalise":
        return "output"

    # Keep debating
    return "agents"
