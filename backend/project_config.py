"""Helpers for normalizing and validating project configuration."""

from __future__ import annotations

from typing import Optional

ALLOWED_PROJECT_PREFERRED_AGENTS = {"dcf", "analyst", "earnings", "market", "research"}


def normalize_project_config(
    config: Optional[dict],
    *,
    existing: Optional[dict] = None,
) -> dict:
    """Normalize project config while preserving unspecified existing keys."""
    normalized = dict(existing or {})
    incoming = dict(config or {})

    raw_tickers = incoming.pop("tickers", normalized.get("tickers", []))
    tickers: list[str] = []
    seen_tickers: set[str] = set()
    for raw in raw_tickers or []:
        ticker = str(raw).strip().upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        tickers.append(ticker)
    normalized["tickers"] = tickers

    raw_agents = incoming.pop("preferred_agents", normalized.get("preferred_agents", []))
    preferred_agents: list[str] = []
    seen_agents: set[str] = set()
    for raw in raw_agents or []:
        agent = str(raw).strip().lower()
        if agent not in ALLOWED_PROJECT_PREFERRED_AGENTS or agent in seen_agents:
            continue
        seen_agents.add(agent)
        preferred_agents.append(agent)
    normalized["preferred_agents"] = preferred_agents

    normalized.update(incoming)
    return normalized
