from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from arena.state import ThesisState
from arena.router import route_from_pm
from arena.pm import pm_node
from arena.output import output_node
from arena.agents import (
    fundamental_node,
    quant_node,
    macro_node,
    risk_node,
    sentiment_node,
    sequence_start_node,
    sequence_advance_node,
    sequence_done_node,
    route_from_sequence_start,
)

# All possible agent node names — must match ARENA_CONFIG query_modes values
_AGENT_NODES = ["fundamental", "risk", "quant", "macro", "sentiment"]


def build_arena():
    """
    Constructs and compiles the finance agent arena graph.

    Graph structure (Level 2 — sequential handoff version):

      START → pm
      pm → sequence_start     (route_from_pm returns "agents", remapped here)
      pm → output              (route_from_pm returns "output")

      sequence_start → <agent_node>   (one of the five agent nodes)
      sequence_start → sequence_done  (when active_agents is exhausted)

      <each agent_node> → sequence_advance

      sequence_advance → sequence_start  (loop — next super-step has committed state)

      sequence_done → pm   (round complete; round incremented, signals snapshotted)

      output → END

    Sequential guarantee:
      Each agent runs in its own LangGraph super-step. When agent N+1 starts,
      LangGraph has fully applied agent N's state update (including raw_outputs
      and agent_signals). Agent N+1 therefore sees agent N's findings via
      state["raw_outputs"], enabling true sequential peer-context reasoning.

    Dynamic routing:
      ARENA_CONFIG["query_modes"] controls which agents run and in what order
      per query_mode. PM sets active_agents on its first pass; sequence_advance
      pops agents off the front as they complete.
    """
    builder = StateGraph(ThesisState)

    # ── Core nodes ────────────────────────────────────────────────────────────
    builder.add_node("pm",     pm_node)
    builder.add_node("output", output_node)

    # ── Sequential loop nodes ─────────────────────────────────────────────────
    builder.add_node("sequence_start",   sequence_start_node)
    builder.add_node("sequence_advance", sequence_advance_node)
    builder.add_node("sequence_done",    sequence_done_node)

    # ── Individual agent nodes (each runs in its own super-step) ─────────────
    for name, fn in [
        ("fundamental", fundamental_node),
        ("risk",        risk_node),
        ("quant",       quant_node),
        ("macro",       macro_node),
        ("sentiment",   sentiment_node),
    ]:
        builder.add_node(name, fn)

    # ── Entry edge ────────────────────────────────────────────────────────────
    builder.add_edge(START, "pm")

    # ── PM routing ────────────────────────────────────────────────────────────
    # route_from_pm is untouched — returns "agents" or "output".
    # Remap "agents" → "sequence_start" (the only coupling change vs Level 1).
    builder.add_conditional_edges(
        "pm",
        route_from_pm,
        {
            "agents": "sequence_start",
            "output": "output",
        }
    )

    # ── Sequence router ───────────────────────────────────────────────────────
    # route_from_sequence_start reads active_agents[0] and returns the agent
    # name (== node name), or "sequence_done" when the queue is empty.
    _path_map = {name: name for name in _AGENT_NODES}
    _path_map["sequence_done"] = "sequence_done"
    builder.add_conditional_edges(
        "sequence_start",
        route_from_sequence_start,
        _path_map,
    )

    # ── Agent → advance → loop ────────────────────────────────────────────────
    for name in _AGENT_NODES:
        builder.add_edge(name, "sequence_advance")
    builder.add_edge("sequence_advance", "sequence_start")

    # ── Round completion → PM ─────────────────────────────────────────────────
    builder.add_edge("sequence_done", "pm")

    # ── Terminal ──────────────────────────────────────────────────────────────
    builder.add_edge("output", END)

    return builder.compile()
