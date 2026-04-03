"""
ArenaAgent — thin wrapper that exposes the Finance Agent Arena as a
drop-in agent compatible with the existing api_server.py infrastructure.

api_server.py sets:
    agent._progress_queue = queue
    agent._progress_loop  = loop
before calling agent.analyze(message), exactly as it does for EarningsAgent
and EquityAnalystGraph.
"""
from __future__ import annotations

import re
from typing import Optional

from arena.run import run_arena
from arena.progress import set_arena_queue, clear_arena_queue
from arena.config import ARENA_CONFIG


_AGENT_MENTION_MAP: dict[str, str] = {
    "fundamental": "fundamental", "fund": "fundamental", "fundamentals": "fundamental",
    "risk":        "risk",
    "quant":       "quant",  "quantitative": "quant",
    "macro":       "macro",
    "sentiment":   "sentiment", "sent": "sentiment",
}

_TICKER_BLACKLIST = {
    "THE", "FOR", "ARE", "AND", "BUT", "NOT", "YOU", "ALL", "CAN", "HAS",
    "ITS", "FROM", "HE", "HIS", "SHE", "THEY", "WILL", "WAS", "ONE",
    "HAVE", "WITH", "WHAT", "THIS", "THAT", "AT", "BY", "AS", "AN",
    "IC", "DO", "AI", "OR", "IF", "ON", "IN", "IT", "IS", "BE", "US",
    "OUR", "WE", "TO", "A", "OF", "MY", "ANY", "NO", "NEW",
}


def _extract_ticker(query: str) -> str:
    """
    Best-effort ticker extraction from a free-text query.
    Precedence:
      1. $TICKER format
      2. All-caps 2-5 char word not in blacklist
    Returns empty string if no ticker found — agents treat this as a
    broad market / thematic query rather than a single-stock analysis.
    """
    dollar_match = re.search(r'\$([A-Z]{2,5})\b', query)
    if dollar_match:
        return dollar_match.group(1)

    for match in re.finditer(r'\b([A-Z]{2,5})\b', query):
        candidate = match.group(1)
        if candidate not in _TICKER_BLACKLIST:
            return candidate

    return ""


def _extract_mentions(query: str) -> list:
    """Return list of agent keys found via @mention in the query."""
    agents = []
    for match in re.finditer(r'@(\w+)', query, re.IGNORECASE):
        key = _AGENT_MENTION_MAP.get(match.group(1).lower())
        if key and key not in agents:
            agents.append(key)
    return agents


def _infer_query_mode(query: str) -> str:
    """Map natural language cues to ARENA_CONFIG query_modes keys.

    An explicit ``query_mode=<mode>`` annotation (appended by the frontend when
    the user has manually selected a mode) takes highest priority so the UI
    selection is always honoured over keyword inference.
    """
    explicit = re.search(r'query_mode=(\w+)', query)
    if explicit:
        mode = explicit.group(1)
        valid = {"full_ic", "quick_screen", "risk_check", "valuation", "macro_view"}
        if mode in valid:
            return mode

    q = query.lower()
    if any(w in q for w in ("risk", "leverage", "debt", "downside")):
        return "risk_check"
    if any(w in q for w in ("valuation", "dcf", "intrinsic", "cheap", "expensive", "overvalued", "undervalued")):
        return "valuation"
    if any(w in q for w in ("macro", "fed", "rates", "inflation", "sentiment", "news")):
        return "macro_view"
    if any(w in q for w in ("quick", "screen", "fast", "brief")):
        return "quick_screen"
    return "full_ic"


class ArenaAgent:
    """
    Wraps run_arena() so it can be used by api_server.py's
    run_agent_with_callbacks() path (fallback method = "analyze").
    """

    def __init__(self) -> None:
        self._progress_queue = None
        self._progress_loop = None

    def analyze(self, query: str) -> str:
        ticker = _extract_ticker(query)
        query_mode = _infer_query_mode(query)

        # If the user @mentioned specific agents, inject a direct_agents annotation
        # so pm_node activates only those agents instead of the full query_mode set.
        mentions = _extract_mentions(query)
        if mentions:
            query = query + f" direct_agents={','.join(mentions)}"

        set_arena_queue(self._progress_queue, self._progress_loop)
        try:
            final_state = run_arena(query=query, ticker=ticker, query_mode=query_mode)
        finally:
            clear_arena_queue()

        return final_state.get("investment_memo") or "Arena analysis complete — no memo generated."
