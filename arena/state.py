from __future__ import annotations
import operator
from typing import TypedDict, Optional, Annotated, List


class AgentSignal(TypedDict):
    """One agent's finding written onto the shared thesis bus."""
    view: str           # exactly "bullish" | "bearish" | "neutral" | "cautious"
    reasoning: str
    confidence: float


class Conflict(TypedDict):
    """A disagreement between agents flagged by the PM."""
    agents: List[str]
    description: str
    round: int


class DebateEntry(TypedDict):
    """One entry in the full debate history."""
    round: int
    agent: str
    action: str         # "dispatch" | "signal_written" | "conflict_flagged" | "synthesis"
    content: str


class ThesisState(TypedDict):
    """
    The complete shared state of the finance agent arena.
    This is the whiteboard that every node reads from and writes to.
    LangGraph passes this between every node automatically.
    """

    # Input
    query: str
    ticker: str
    query_mode: str

    # Thesis bus
    thesis_summary: str
    agent_signals: dict                                    # plain dict — last-write-wins per key
    signal_history: Annotated[List[dict], operator.add]   # accumulates every round's snapshot
    conflicts: Annotated[List[Conflict], operator.add]
    debate_log: Annotated[List[DebateEntry], operator.add]

    # Control
    consensus_score: float
    next_action: str    # "debate" | "finalise" | "escalate_to_human"
    round: int
    active_agents: List[str]

    # Output
    final_decision: Optional[str]
    conviction_level: Optional[str]
    investment_memo: Optional[str]
