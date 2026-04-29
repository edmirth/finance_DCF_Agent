"""
Shared validation helpers for scheduled-agent style configurations.
"""
from __future__ import annotations

from typing import Iterable


VALID_AGENT_TEMPLATES = frozenset(
    {
        "earnings_watcher",
        "market_pulse",
        "thesis_guardian",
        "portfolio_heartbeat",
        "arena_analyst",
        "firm_pipeline",
    }
)

TEMPLATES_REQUIRING_TICKERS = frozenset(
    {
        "earnings_watcher",
        "thesis_guardian",
        "portfolio_heartbeat",
        "arena_analyst",
        "firm_pipeline",
    }
)


def normalize_tickers(tickers: Iterable[str] | None) -> list[str]:
    """Uppercase, trim, and dedupe ticker inputs while preserving order."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tickers or []:
        ticker = str(raw or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        cleaned.append(ticker)
    return cleaned


def validate_template(template: str) -> str:
    normalized = (template or "").strip()
    if normalized not in VALID_AGENT_TEMPLATES:
        raise ValueError(
            f"Invalid template. Must be one of: {sorted(VALID_AGENT_TEMPLATES)}"
        )
    return normalized


def validate_ticker_requirement(template: str, tickers: Iterable[str] | None) -> None:
    cleaned = normalize_tickers(tickers)
    if template in TEMPLATES_REQUIRING_TICKERS and not cleaned:
        raise ValueError(f"Template '{template}' requires at least one ticker")
