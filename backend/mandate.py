"""
Investment Mandate helpers.

Provides two public functions used across the backend:

  get_mandate(db)          — async: load the singleton row from DB
  build_mandate_context()  — sync: turn a mandate dict into a prompt string
                             that any agent can prepend to its system prompt

The mandate is a singleton (id='default'). If the row doesn't exist yet
(fresh install before first save) sensible defaults are returned so agents
always receive a valid context string.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default values (mirrors DB column defaults)
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "id": "default",
    "firm_name": "My Investment Firm",
    "mandate_text": "",
    "benchmark": "S&P 500",
    "target_return_pct": 12.0,
    "max_position_pct": 5.0,
    "max_sector_pct": 25.0,
    "max_portfolio_beta": 1.3,
    "max_drawdown_pct": 15.0,
    "strategy_style": "blend",
    "investment_horizon": "12 months",
    "restricted_tickers": [],
}


# ---------------------------------------------------------------------------
# DB loader (async)
# ---------------------------------------------------------------------------

async def get_mandate(db, raise_on_error: bool = False) -> dict:
    """
    Load the investment mandate from the database.
    Returns a plain dict (never raises). Falls back to defaults on any error.
    """
    try:
        from sqlalchemy import select
        from backend.models import InvestmentMandate

        result = await db.execute(
            select(InvestmentMandate).where(InvestmentMandate.id == "default")
        )
        row = result.scalar_one_or_none()
        if row is None:
            return dict(_DEFAULTS)

        restricted = []
        try:
            restricted = json.loads(row.restricted_tickers or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "id": row.id,
            "firm_name": row.firm_name,
            "mandate_text": row.mandate_text,
            "benchmark": row.benchmark,
            "target_return_pct": row.target_return_pct,
            "max_position_pct": row.max_position_pct,
            "max_sector_pct": row.max_sector_pct,
            "max_portfolio_beta": row.max_portfolio_beta,
            "max_drawdown_pct": row.max_drawdown_pct,
            "strategy_style": row.strategy_style,
            "investment_horizon": row.investment_horizon,
            "restricted_tickers": restricted,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    except Exception as e:
        logger.warning(f"[mandate] Failed to load from DB, using defaults: {e}")
        if raise_on_error:
            raise
        return dict(_DEFAULTS)


def get_mandate_sync(db_session, raise_on_error: bool = False) -> dict:
    """
    Synchronous version for use in threadpool-based agent runners.
    Uses the sync SQLAlchemy session (SyncSessionLocal).
    """
    try:
        from sqlalchemy import select as sync_select
        from backend.models import InvestmentMandate

        row = db_session.execute(
            sync_select(InvestmentMandate).where(InvestmentMandate.id == "default")
        ).scalar_one_or_none()

        if row is None:
            return dict(_DEFAULTS)

        restricted = []
        try:
            restricted = json.loads(row.restricted_tickers or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "firm_name": row.firm_name,
            "mandate_text": row.mandate_text,
            "benchmark": row.benchmark,
            "target_return_pct": row.target_return_pct,
            "max_position_pct": row.max_position_pct,
            "max_sector_pct": row.max_sector_pct,
            "max_portfolio_beta": row.max_portfolio_beta,
            "max_drawdown_pct": row.max_drawdown_pct,
            "strategy_style": row.strategy_style,
            "investment_horizon": row.investment_horizon,
            "restricted_tickers": restricted,
        }
    except Exception as e:
        logger.warning(f"[mandate] Sync load failed, using defaults: {e}")
        if raise_on_error:
            raise
        return dict(_DEFAULTS)


# ---------------------------------------------------------------------------
# Prompt injection builder (sync, no DB needed)
# ---------------------------------------------------------------------------

def build_mandate_context(mandate: dict) -> str:
    """
    Convert a mandate dict into a concise context block for agent system prompts.

    Example output:
        === FIRM INVESTMENT MANDATE ===
        Firm: Apex Capital
        Mandate: Long-only, quality-growth equity portfolio targeting 15% annual return.
        Benchmark: S&P 500 | Style: Growth | Horizon: 12 months
        Risk limits: max position 5.0%, max sector 25.0%, max beta 1.3, max drawdown 15.0%
        Restricted tickers: NONE
        ================================
    """
    firm = mandate.get("firm_name") or "Investment Firm"
    mandate_text = (mandate.get("mandate_text") or "").strip()
    benchmark = mandate.get("benchmark") or "S&P 500"
    style = mandate.get("strategy_style") or "blend"
    horizon = mandate.get("investment_horizon") or "12 months"
    target = mandate.get("target_return_pct", 12.0)
    max_pos = mandate.get("max_position_pct", 5.0)
    max_sec = mandate.get("max_sector_pct", 25.0)
    max_beta = mandate.get("max_portfolio_beta", 1.3)
    max_dd = mandate.get("max_drawdown_pct", 15.0)

    restricted = mandate.get("restricted_tickers") or []
    if isinstance(restricted, str):
        try:
            restricted = json.loads(restricted)
        except (json.JSONDecodeError, TypeError):
            restricted = []
    restricted_str = ", ".join(str(t).upper() for t in restricted) if restricted else "NONE"

    mandate_line = f"\nMandate: {mandate_text}" if mandate_text else ""
    target_line = f"Target return: {target:.1f}% p.a. | " if target else ""

    return (
        f"\n=== FIRM INVESTMENT MANDATE ===\n"
        f"Firm: {firm}{mandate_line}\n"
        f"Benchmark: {benchmark} | Style: {style.capitalize()} | Horizon: {horizon}\n"
        f"{target_line}"
        f"Risk limits: max position {max_pos:.1f}%, max sector {max_sec:.1f}%, "
        f"max beta {max_beta:.2f}×, max drawdown {max_dd:.1f}%\n"
        f"Restricted tickers: {restricted_str}\n"
        f"================================\n"
    )
