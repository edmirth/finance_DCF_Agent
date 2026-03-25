from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from arena.state import ThesisState
from arena.router import route_from_pm
from arena.pm import pm_node
from arena.agents import run_active_agents
from arena.output import output_node


def build_arena():
    """
    Constructs and compiles the finance agent arena graph.

    Graph structure:
      START → pm
      pm → agents        (when consensus low or no signals yet)
      pm → output        (when consensus reached or max rounds hit)
      agents → pm        (always — agents report back to PM)
      output → END
    """
    builder = StateGraph(ThesisState)

    builder.add_node("pm",     pm_node)
    builder.add_node("agents", run_active_agents)
    builder.add_node("output", output_node)

    builder.add_edge(START, "pm")

    builder.add_conditional_edges(
        "pm",
        route_from_pm,
        {
            "agents": "agents",
            "output": "output",
        }
    )

    builder.add_edge("agents", "pm")
    builder.add_edge("output", END)

    return builder.compile()
