"""
Heartbeat Scheduler

Manages APScheduler jobs for all active ScheduledAgent configs.
Each agent fires on its cron schedule, runs via AgentRunnerService,
persists an AgentRun record, and optionally sends an email.

Lifecycle:
  start_scheduler()  — call once on FastAPI lifespan startup
  stop_scheduler()   — call once on lifespan shutdown
  sync_jobs()        — reload all active agents from DB (call after CRUD)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Cron expressions for each schedule label
_CRON_MAP: dict[str, dict] = {
    "daily_morning": {"hour": 7, "minute": 0},
    "pre_market":    {"hour": 6, "minute": 30, "day_of_week": "mon-fri"},
    "weekly_monday": {"hour": 7, "minute": 0,  "day_of_week": "mon"},
    "weekly_friday": {"hour": 16, "minute": 0, "day_of_week": "fri"},
    "monthly":       {"hour": 7, "minute": 0,  "day": 1},
}

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def start_scheduler() -> None:
    """Start the scheduler and load all active agents from DB."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Heartbeat scheduler started")
    await sync_jobs()


async def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Heartbeat scheduler stopped")


async def sync_jobs() -> None:
    """
    Reload all active ScheduledAgent rows from DB and reconcile jobs.
    Called on startup and after any CRUD operation on scheduled_agents.
    """
    from backend.database import AsyncSessionLocal
    from backend.models import ScheduledAgent
    from sqlalchemy import select

    scheduler = get_scheduler()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ScheduledAgent).where(ScheduledAgent.is_active == True))
        agents = result.scalars().all()

    # Remove stale jobs (agents that were deleted or deactivated)
    active_ids = {a.id for a in agents}
    for job in scheduler.get_jobs():
        if job.id not in active_ids:
            job.remove()
            logger.info(f"Removed stale scheduler job: {job.id}")

    # Add or replace jobs for active agents
    for agent in agents:
        cron_kwargs = _CRON_MAP.get(agent.schedule_label, _CRON_MAP["weekly_monday"])
        trigger = CronTrigger(**cron_kwargs, timezone="UTC")
        scheduler.add_job(
            _fire_agent_run,
            trigger=trigger,
            id=agent.id,
            args=[agent.id],
            replace_existing=True,
            name=agent.name,
        )
        logger.info(f"Scheduled agent '{agent.name}' ({agent.id}) with {agent.schedule_label}")


def register_agent_job(agent_id: str, name: str, schedule_label: str) -> None:
    """Add or replace a single scheduler job (call after create/update)."""
    scheduler = get_scheduler()
    cron_kwargs = _CRON_MAP.get(schedule_label, _CRON_MAP["weekly_monday"])
    trigger = CronTrigger(**cron_kwargs, timezone="UTC")
    scheduler.add_job(
        _fire_agent_run,
        trigger=trigger,
        id=agent_id,
        args=[agent_id],
        replace_existing=True,
        name=name,
    )
    logger.info(f"Registered scheduler job for agent '{name}' ({agent_id})")


def remove_agent_job(agent_id: str) -> None:
    """Remove a scheduler job (call after delete/deactivate)."""
    scheduler = get_scheduler()
    job = scheduler.get_job(agent_id)
    if job:
        job.remove()
        logger.info(f"Removed scheduler job for agent {agent_id}")


def next_run_time(schedule_label: str) -> Optional[datetime]:
    """Return the next fire time for a given schedule label (UTC)."""
    cron_kwargs = _CRON_MAP.get(schedule_label, _CRON_MAP["weekly_monday"])
    trigger = CronTrigger(**cron_kwargs, timezone="UTC")
    return trigger.get_next_fire_time(None, datetime.now(timezone.utc))


# ------------------------------------------------------------------
# Job callback — runs in the asyncio event loop
# ------------------------------------------------------------------

async def _fire_agent_run(agent_id: str) -> None:
    """
    Execute a scheduled agent run:
    1. Load config from DB
    2. Create AgentRun record (status=running)
    3. Run AgentRunnerService in thread pool (blocking)
    4. Update AgentRun + ScheduledAgent with results
    5. Send email if configured
    """
    from backend.database import AsyncSessionLocal
    from backend.models import ScheduledAgent, AgentRun
    from backend.agent_runner import get_runner
    from sqlalchemy import select

    logger.info(f"Heartbeat firing for agent {agent_id}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledAgent).where(ScheduledAgent.id == agent_id)
        )
        agent_config = result.scalar_one_or_none()
        if not agent_config or not agent_config.is_active:
            logger.warning(f"Agent {agent_id} not found or inactive — skipping")
            return

        # Create run record
        run = AgentRun(
            id=_new_uuid(),
            scheduled_agent_id=agent_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.commit()
        run_id = run.id

        # Copy config values before closing session scope
        config_snapshot = _ConfigSnapshot(agent_config)

    # Execute in thread pool (agent calls are blocking)
    loop = asyncio.get_running_loop()
    runner = get_runner()
    outcome = await loop.run_in_executor(None, runner.execute, config_snapshot)

    # Persist results
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one_or_none()
        if run:
            run.status = "failed" if outcome.get("error") else "completed"
            run.report = outcome.get("report", "")
            run.findings_summary = outcome.get("findings_summary", "")
            run.key_findings = json.dumps(outcome.get("key_findings", []))
            run.material_change = outcome.get("material_change", False)
            run.alert_level = outcome.get("alert_level", "none")
            run.tickers_analyzed = json.dumps(outcome.get("tickers_analyzed", []))
            run.agents_used = json.dumps(outcome.get("agents_used", []))
            run.completed_at = datetime.now(timezone.utc)
            run.error = outcome.get("error")

        result2 = await db.execute(
            select(ScheduledAgent).where(ScheduledAgent.id == agent_id)
        )
        agent = result2.scalar_one_or_none()
        if agent:
            agent.last_run_at = datetime.now(timezone.utc)
            agent.last_run_status = run.status if run else "failed"
            agent.last_run_summary = outcome.get("findings_summary", "")

        await db.commit()

    # Send email notification if configured
    if config_snapshot.delivery_email and not outcome.get("error"):
        try:
            from backend.email_service import send_run_email
            await loop.run_in_executor(
                None,
                send_run_email,
                config_snapshot.delivery_email,
                config_snapshot.name,
                outcome,
            )
        except Exception as exc:
            logger.error(f"Email delivery failed for agent {agent_id}: {exc}")

    logger.info(
        f"Agent run {run_id} completed: {outcome.get('alert_level', 'none')} alert, "
        f"material_change={outcome.get('material_change', False)}"
    )


class _ConfigSnapshot:
    """Lightweight copy of ScheduledAgent fields for use outside SQLAlchemy session."""

    def __init__(self, agent):
        self.id = agent.id
        self.name = agent.name
        self.template = agent.template
        self.tickers = agent.tickers
        self.topics = agent.topics
        self.instruction = agent.instruction
        self.schedule_label = agent.schedule_label
        self.delivery_email = agent.delivery_email
        self.last_run_summary = agent.last_run_summary


def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
