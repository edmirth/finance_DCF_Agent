"""Firm mandate and routine catalog API routes."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.heartbeat_service import ensure_agent_heartbeat_routine
from backend.mandate import get_mandate
from backend.models import InvestmentMandate, ScheduledAgent
from backend.scheduled_agent_config import normalize_tickers, validate_ticker_requirement
from backend.scheduler import next_run_time, register_agent_job

logger = logging.getLogger(__name__)

router = APIRouter()


class MandateUpdate(BaseModel):
    firm_name: Optional[str] = None
    mandate_text: Optional[str] = None
    benchmark: Optional[str] = None
    target_return_pct: Optional[float] = None
    max_position_pct: Optional[float] = None
    max_sector_pct: Optional[float] = None
    max_portfolio_beta: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    strategy_style: Optional[str] = None
    investment_horizon: Optional[str] = None
    restricted_tickers: Optional[List[str]] = None


FIRM_ROUTINE_CATALOG = [
    {
        "id": "pre_market_brief",
        "name": "Pre-Market Brief",
        "icon": "🌅",
        "description": (
            "Every weekday at 6:30am. Runs the full investment pipeline on your "
            "watchlist tickers so you wake up to fresh BUY/HOLD/SELL signals."
        ),
        "schedule_label": "pre_market_brief",
        "schedule_human": "Weekdays 6:30am",
        "template": "firm_pipeline",
        "default_instruction": (
            "Pre-market brief: re-run the full pipeline on watchlist names. "
            "Highlight any thesis changes since yesterday."
        ),
    },
    {
        "id": "earnings_radar",
        "name": "Earnings Radar",
        "icon": "📰",
        "description": (
            "Every weekday at 6am. Catches any overnight earnings releases on your "
            "watchlist and triggers a fresh earnings analysis task."
        ),
        "schedule_label": "pre_market",
        "schedule_human": "Weekdays 6am",
        "template": "earnings_watcher",
        "default_instruction": (
            "Check watchlist tickers for overnight earnings releases. "
            "Flag any beats / misses / guidance changes."
        ),
    },
    {
        "id": "market_open_pulse",
        "name": "Market Open Pulse",
        "icon": "🔔",
        "description": (
            "Weekdays at 9:30am. Snapshots macro conditions and sector rotation "
            "so you start the trading session with the macro Macro Agent's read."
        ),
        "schedule_label": "market_open",
        "schedule_human": "Weekdays 9:30am",
        "template": "market_pulse",
        "default_instruction": (
            "Market open snapshot: macro regime, sector winners/losers, "
            "any breaking news affecting the watchlist."
        ),
    },
    {
        "id": "market_close_review",
        "name": "Market Close Review",
        "icon": "📊",
        "description": (
            "Weekdays at 4pm. End-of-day portfolio heartbeat — flags positions "
            "that moved against your thesis or breached risk limits."
        ),
        "schedule_label": "market_close",
        "schedule_human": "Weekdays 4pm",
        "template": "portfolio_heartbeat",
        "default_instruction": (
            "End-of-day portfolio review: surface any drawdown, big moves, "
            "or breaches of mandate limits."
        ),
    },
    {
        "id": "weekly_ic",
        "name": "Weekly Investment Committee",
        "icon": "📋",
        "description": (
            "Every Friday at 4pm. CIO-style end-of-week brief covering the full "
            "watchlist with pipeline-driven recommendations for the next week."
        ),
        "schedule_label": "weekly_friday_close",
        "schedule_human": "Friday 4pm",
        "template": "firm_pipeline",
        "default_instruction": (
            "Weekly IC summary: full pipeline rerun on the watchlist. "
            "Identify the top 3 names to act on next week with rationale."
        ),
    },
    {
        "id": "monthly_attribution",
        "name": "Monthly Attribution",
        "icon": "📈",
        "description": (
            "1st of every month. Full re-rating of every name in your watchlist — "
            "DCF refresh, factor scores, thesis review."
        ),
        "schedule_label": "monthly_first",
        "schedule_human": "1st of month, 8am",
        "template": "firm_pipeline",
        "default_instruction": (
            "Monthly portfolio review: re-run the full pipeline on every covered name. "
            "Flag any thesis that has materially changed."
        ),
    },
    {
        "id": "quarterly_research",
        "name": "Quarterly Research Refresh",
        "icon": "🧮",
        "description": (
            "1st of January, April, July, October. Deep refresh of all "
            "fundamental theses with the latest financials and SEC filings."
        ),
        "schedule_label": "quarterly",
        "schedule_human": "1st of Jan/Apr/Jul/Oct, 8am",
        "template": "firm_pipeline",
        "default_instruction": (
            "Quarterly deep refresh: rebuild theses from latest 10-Q/10-K filings. "
            "Update price targets, re-score conviction."
        ),
    },
]


class InstallRoutineBody(BaseModel):
    catalog_id: str
    tickers: List[str] = []
    instruction: Optional[str] = None
    delivery_email: Optional[str] = None


@router.get("/firm/mandate")
async def get_firm_mandate(db: AsyncSession = Depends(get_db)):
    """Return the current investment mandate."""
    return await get_mandate(db)


@router.put("/firm/mandate")
async def update_firm_mandate(body: MandateUpdate, db: AsyncSession = Depends(get_db)):
    """Upsert the investment mandate. Only supplied fields are updated."""
    result = await db.execute(
        select(InvestmentMandate).where(InvestmentMandate.id == "default")
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = InvestmentMandate(id="default")
        db.add(row)

    if body.firm_name is not None:
        row.firm_name = body.firm_name
    if body.mandate_text is not None:
        row.mandate_text = body.mandate_text
    if body.benchmark is not None:
        row.benchmark = body.benchmark
    if body.target_return_pct is not None:
        row.target_return_pct = body.target_return_pct
    if body.max_position_pct is not None:
        row.max_position_pct = body.max_position_pct
    if body.max_sector_pct is not None:
        row.max_sector_pct = body.max_sector_pct
    if body.max_portfolio_beta is not None:
        row.max_portfolio_beta = body.max_portfolio_beta
    if body.max_drawdown_pct is not None:
        row.max_drawdown_pct = body.max_drawdown_pct
    if body.strategy_style is not None:
        row.strategy_style = body.strategy_style
    if body.investment_horizon is not None:
        row.investment_horizon = body.investment_horizon
    if body.restricted_tickers is not None:
        row.restricted_tickers = json.dumps([t.upper() for t in body.restricted_tickers])

    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)

    return await get_mandate(db)


@router.get("/firm/routines/catalog")
async def get_firm_routines_catalog():
    """Return the catalog of pre-built firm routines."""
    return {"routines": FIRM_ROUTINE_CATALOG}


@router.post("/firm/routines/install", status_code=201)
async def install_firm_routine(body: InstallRoutineBody, db: AsyncSession = Depends(get_db)):
    """Install one of the catalog routines as a scheduled agent."""
    catalog = next((r for r in FIRM_ROUTINE_CATALOG if r["id"] == body.catalog_id), None)
    if not catalog:
        raise HTTPException(status_code=404, detail=f"Unknown routine: {body.catalog_id}")

    cleaned_tickers = normalize_tickers(body.tickers)
    try:
        validate_ticker_requirement(catalog["template"], cleaned_tickers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    agent = ScheduledAgent(
        name=catalog["name"],
        description=catalog["description"],
        template=catalog["template"],
        tickers=json.dumps(cleaned_tickers),
        topics=json.dumps([]),
        instruction=body.instruction or catalog["default_instruction"],
        schedule_label=catalog["schedule_label"],
        delivery_email=body.delivery_email,
        delivery_inapp=True,
        is_active=True,
        next_run_at=next_run_time(catalog["schedule_label"]),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    await ensure_agent_heartbeat_routine(db, agent)
    await db.commit()

    try:
        register_agent_job(agent.id, agent.name, agent.schedule_label)
    except Exception as exc:
        logger.warning("Could not register routine job immediately: %s", exc)

    return {
        "id": agent.id,
        "name": agent.name,
        "template": agent.template,
        "schedule_label": agent.schedule_label,
        "schedule_human": catalog["schedule_human"],
        "tickers": cleaned_tickers,
        "next_run_at": agent.next_run_at.isoformat() if agent.next_run_at else None,
        "is_active": agent.is_active,
    }
