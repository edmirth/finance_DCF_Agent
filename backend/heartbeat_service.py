"""
Heartbeat service helpers.

This module layers a first-class routine and wake-up log on top of the
existing scheduled-agent system without breaking current routes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import MARKET_SCHEDULE_TIMEZONE
from backend.models import (
    AgentRoutine,
    AgentRun,
    HeartbeatRun,
    HireProposal,
    ResearchTask,
    ScheduledAgent,
)

HEARTBEAT_ROUTINE_TYPE = "heartbeat"
ACTIVE_TASK_STATUSES = ("pending", "running", "in_review")
MANAGER_HEARTBEAT_TRIGGER = "manager_heartbeat"

logger = logging.getLogger(__name__)
_background_coroutines: set[asyncio.Task] = set()

TASK_SELECTION_BY_TEMPLATE: dict[str, list[str]] = {
    "fundamental_analyst": ["fundamental"],
    "quant_analyst": ["quant"],
    "risk_analyst": ["risk"],
    "macro_analyst": ["macro"],
    "market_pulse": ["macro"],
    "sentiment_analyst": ["sentiment"],
    "earnings_watcher": ["fundamental"],
    "thesis_guardian": ["fundamental", "risk", "macro"],
    "portfolio_heartbeat": ["risk", "macro"],
    "firm_pipeline": ["fundamental", "quant", "risk", "macro", "sentiment"],
}


def _new_uuid() -> str:
    return str(uuid.uuid4())


def spawn_background(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_coroutines.add(task)
    task.add_done_callback(_background_coroutines.discard)
    return task


def routine_to_dict(routine: AgentRoutine | None) -> dict | None:
    if routine is None:
        return None
    return {
        "id": routine.id,
        "routine_type": routine.routine_type,
        "schedule_label": routine.schedule_label,
        "timezone_name": routine.timezone_name,
        "is_active": routine.is_active,
        "last_run_at": routine.last_run_at.isoformat() if routine.last_run_at else None,
        "next_run_at": routine.next_run_at.isoformat() if routine.next_run_at else None,
        "last_run_status": routine.last_run_status,
        "created_at": routine.created_at.isoformat(),
        "updated_at": routine.updated_at.isoformat(),
    }


def heartbeat_run_to_dict(run: HeartbeatRun) -> dict:
    return {
        "id": run.id,
        "scheduled_agent_id": run.scheduled_agent_id,
        "agent_routine_id": run.agent_routine_id,
        "agent_run_id": run.agent_run_id,
        "trigger_type": run.trigger_type,
        "status": run.status,
        "summary": run.summary,
        "alert_level": run.alert_level,
        "material_change": bool(run.material_change),
        "context": json.loads(run.context_json or "{}"),
        "outcome": json.loads(run.outcome_json or "{}"),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


async def ensure_agent_heartbeat_routine(
    db: AsyncSession,
    agent: ScheduledAgent,
) -> AgentRoutine:
    result = await db.execute(
        select(AgentRoutine).where(
            AgentRoutine.scheduled_agent_id == agent.id,
            AgentRoutine.routine_type == HEARTBEAT_ROUTINE_TYPE,
        )
    )
    routine = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    changed = False
    if routine is None:
        routine = AgentRoutine(
            id=_new_uuid(),
            scheduled_agent_id=agent.id,
            routine_type=HEARTBEAT_ROUTINE_TYPE,
            created_at=now,
        )
        db.add(routine)
        changed = True

    for attr, value in [
        ("schedule_label", agent.schedule_label),
        ("timezone_name", MARKET_SCHEDULE_TIMEZONE),
        ("is_active", agent.is_active),
        ("last_run_at", agent.last_run_at),
        ("next_run_at", agent.next_run_at),
        ("last_run_status", agent.last_run_status),
    ]:
        if getattr(routine, attr) != value:
            setattr(routine, attr, value)
            changed = True

    if changed:
        routine.updated_at = now
        await db.flush()
    return routine


async def routine_map_for_agents(
    db: AsyncSession,
    agent_ids: list[str],
) -> dict[str, AgentRoutine]:
    if not agent_ids:
        return {}
    result = await db.execute(
        select(AgentRoutine).where(
            AgentRoutine.scheduled_agent_id.in_(agent_ids),
            AgentRoutine.routine_type == HEARTBEAT_ROUTINE_TYPE,
        )
    )
    routines = result.scalars().all()
    return {routine.scheduled_agent_id: routine for routine in routines}


async def build_heartbeat_context(
    db: AsyncSession,
    agent: ScheduledAgent,
) -> dict:
    direct_reports_count = await db.scalar(
        select(func.count())
        .select_from(ScheduledAgent)
        .where(ScheduledAgent.manager_agent_id == agent.id)
    )

    pending_hire_query = (
        select(func.count())
        .select_from(HireProposal)
        .where(HireProposal.status == "pending")
    )
    if agent.manager_agent_id is None:
        pending_hire_proposals_count = await db.scalar(pending_hire_query)
    else:
        pending_hire_proposals_count = await db.scalar(
            pending_hire_query.where(HireProposal.manager_agent_id == agent.id)
        )

    open_research_tasks_count = await db.scalar(
        select(func.count())
        .select_from(ResearchTask)
        .where(ResearchTask.status.in_(ACTIVE_TASK_STATUSES))
    )

    running_agent_runs_count = await db.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.scheduled_agent_id == agent.id,
            AgentRun.status == "running",
        )
    )

    return {
        "agent_id": agent.id,
        "role_key": agent.role_key,
        "role_title": agent.role_title,
        "role_family": agent.role_family,
        "schedule_label": agent.schedule_label,
        "watch_count": len(json.loads(agent.tickers or "[]")),
        "direct_reports_count": direct_reports_count or 0,
        "pending_hire_proposals_count": pending_hire_proposals_count or 0,
        "open_research_tasks_count": open_research_tasks_count or 0,
        "running_agent_runs_count": running_agent_runs_count or 0,
        "manager_agent_id": agent.manager_agent_id,
    }


async def create_heartbeat_run(
    db: AsyncSession,
    agent: ScheduledAgent,
    *,
    trigger_type: str,
    agent_run_id: str | None = None,
    started_at: datetime | None = None,
) -> HeartbeatRun:
    routine = await ensure_agent_heartbeat_routine(db, agent)
    heartbeat = HeartbeatRun(
        id=_new_uuid(),
        scheduled_agent_id=agent.id,
        agent_routine_id=routine.id,
        agent_run_id=agent_run_id,
        trigger_type=trigger_type,
        status="running",
        context_json=json.dumps(await build_heartbeat_context(db, agent)),
        started_at=started_at or datetime.now(timezone.utc),
    )
    db.add(heartbeat)
    await db.flush()
    return heartbeat


async def finalize_heartbeat_run(
    db: AsyncSession,
    heartbeat_run: HeartbeatRun | None,
    agent: ScheduledAgent | None,
    outcome: dict,
) -> None:
    if heartbeat_run is None:
        return

    completed_at = datetime.now(timezone.utc)
    heartbeat_run.status = "failed" if outcome.get("error") else "completed"
    heartbeat_run.summary = outcome.get("findings_summary", "")
    heartbeat_run.alert_level = outcome.get("alert_level", "none")
    heartbeat_run.material_change = outcome.get("material_change", False)
    heartbeat_run.outcome_json = json.dumps(
        {
            "key_findings": outcome.get("key_findings", []),
            "agents_used": outcome.get("agents_used", []),
            "tickers_analyzed": outcome.get("tickers_analyzed", []),
            "report_present": bool(outcome.get("report")),
        }
    )
    heartbeat_run.completed_at = completed_at
    heartbeat_run.error = outcome.get("error")

    if agent is not None:
        routine = await ensure_agent_heartbeat_routine(db, agent)
        routine.last_run_at = agent.last_run_at
        routine.next_run_at = agent.next_run_at
        routine.last_run_status = agent.last_run_status
        routine.updated_at = completed_at


def selected_agents_for_template(template: str) -> list[str]:
    return list(TASK_SELECTION_BY_TEMPLATE.get(template, ["fundamental"]))


def task_type_for_agent(agent: ScheduledAgent) -> str:
    template = agent.template
    if template == "risk_analyst":
        return "risk_review"
    if template in {"market_pulse", "macro_analyst"}:
        return "sector_screen"
    if template == "earnings_watcher":
        return "earnings"
    if template == "fundamental_analyst":
        return "thesis_update"
    return "ad_hoc"


def task_priority_for_agent(agent: ScheduledAgent) -> str:
    return "high" if agent.template == "risk_analyst" else "medium"


def resolve_task_ticker(manager: ScheduledAgent, report: ScheduledAgent) -> str:
    for raw in [report.tickers, manager.tickers]:
        try:
            tickers = json.loads(raw or "[]")
        except Exception:
            tickers = []
        if tickers:
            return str(tickers[0]).upper()
    return "SPY"


def delegated_task_title(manager: ScheduledAgent, report: ScheduledAgent, ticker: str) -> str:
    return f"{report.name} delegated by {manager.name}: {ticker}"


def manager_assignment_note(manager: ScheduledAgent, report: ScheduledAgent) -> str:
    focus = (report.instruction or "").strip()
    base = f"Delegated by manager heartbeat from {manager.name} to {report.name}."
    return base if not focus else f"{base}\n\nFocus: {focus}"


def report_config_snapshot(report: ScheduledAgent) -> dict:
    return {
        "id": report.id,
        "name": report.name,
        "template": report.template,
        "tickers": json.loads(report.tickers or "[]"),
        "topics": json.loads(report.topics or "[]"),
        "instruction": report.instruction,
        "schedule_label": report.schedule_label,
        "delivery_email": report.delivery_email,
        "last_run_summary": report.last_run_summary,
        "role_key": report.role_key,
        "role_title": report.role_title,
        "role_family": report.role_family,
    }


async def update_task_from_delegated_run(
    db: AsyncSession,
    task_id: str | None,
    assigned_agent: ScheduledAgent | None,
    run_id: str,
    outcome: dict,
) -> None:
    if not task_id:
        return

    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return

    try:
        findings = json.loads(task.findings or "{}")
    except Exception:
        findings = {}
    key = assigned_agent.name if assigned_agent else "delegated_agent"
    findings[key] = {
        "summary": outcome.get("findings_summary", ""),
        "key_findings": outcome.get("key_findings", []),
        "alert_level": outcome.get("alert_level", "none"),
        "material_change": outcome.get("material_change", False),
        "error": outcome.get("error"),
        "agent_run_id": run_id,
    }
    task.findings = json.dumps(findings)
    task.run_id = run_id

    try:
        completed = json.loads(task.completed_agents or "[]")
    except Exception:
        completed = []
    for name in selected_agents_for_template(assigned_agent.template if assigned_agent else "fundamental_analyst"):
        if name not in completed:
            completed.append(name)
    task.completed_agents = json.dumps(completed)

    task.status = "failed" if outcome.get("error") else "in_review"
    task.error = outcome.get("error")
    task.updated_at = datetime.utcnow()


async def plan_manager_heartbeat_actions(
    db: AsyncSession,
    manager: ScheduledAgent | None,
    heartbeat_run: HeartbeatRun | None,
) -> list[dict]:
    if manager is None or heartbeat_run is None or heartbeat_run.status != "completed":
        return []

    reports_result = await db.execute(
        select(ScheduledAgent)
        .where(
            ScheduledAgent.manager_agent_id == manager.id,
            ScheduledAgent.is_active == True,
        )
        .order_by(ScheduledAgent.created_at.asc())
    )
    reports = reports_result.scalars().all()
    if not reports:
        return []

    dispatches: list[dict] = []
    delegated_agent_ids: list[str] = []
    delegated_task_ids: list[str] = []

    for report in reports:
        ticker = resolve_task_ticker(manager, report)
        task_result = await db.execute(
            select(ResearchTask)
            .where(
                ResearchTask.owner_agent_id == manager.id,
                ResearchTask.assigned_agent_id == report.id,
                ResearchTask.ticker == ticker,
                ResearchTask.status.in_(ACTIVE_TASK_STATUSES),
            )
            .order_by(desc(ResearchTask.created_at))
        )
        task = task_result.scalars().first()
        if task and task.status == "in_review":
            continue

        running_count = await db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.scheduled_agent_id == report.id,
                AgentRun.status == "running",
            )
        )
        if running_count:
            continue

        now = datetime.utcnow()
        if task is None:
            task = ResearchTask(
                id=_new_uuid(),
                ticker=ticker,
                task_type=task_type_for_agent(report),
                title=delegated_task_title(manager, report, ticker),
                status="pending",
                priority=task_priority_for_agent(report),
                selected_agents=json.dumps(selected_agents_for_template(report.template)),
                parent_task_id=None,
                owner_agent_id=manager.id,
                assigned_agent_id=report.id,
                source_heartbeat_run_id=heartbeat_run.id,
                triggered_by=MANAGER_HEARTBEAT_TRIGGER,
                notes=manager_assignment_note(manager, report),
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            await db.flush()
        else:
            task.source_heartbeat_run_id = heartbeat_run.id
            task.notes = task.notes or manager_assignment_note(manager, report)
            task.updated_at = now

        await ensure_agent_heartbeat_routine(db, report)
        run = AgentRun(
            id=_new_uuid(),
            scheduled_agent_id=report.id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()
        delegated_heartbeat = await create_heartbeat_run(
            db,
            report,
            trigger_type="delegated",
            agent_run_id=run.id,
            started_at=run.started_at,
        )

        task.status = "running"
        task.started_at = task.started_at or now
        task.run_id = run.id
        task.source_heartbeat_run_id = heartbeat_run.id
        task.updated_at = now

        delegated_agent_ids.append(report.id)
        delegated_task_ids.append(task.id)
        dispatches.append(
            {
                "run_id": run.id,
                "agent_id": report.id,
                "config_data": report_config_snapshot(report),
                "heartbeat_run_id": delegated_heartbeat.id,
                "trigger_type": "delegated",
                "linked_task_id": task.id,
            }
        )

    if delegated_agent_ids:
        try:
            outcome = json.loads(heartbeat_run.outcome_json or "{}")
        except Exception:
            outcome = {}
        outcome["delegated_agent_ids"] = delegated_agent_ids
        outcome["delegated_task_ids"] = delegated_task_ids
        heartbeat_run.outcome_json = json.dumps(outcome)

    return dispatches


def dispatch_manager_heartbeat_actions(dispatches: list[dict]) -> None:
    if not dispatches:
        return
    from backend.scheduled_agents_router import _execute_run_background

    for dispatch in dispatches:
        spawn_background(
            _execute_run_background(
                dispatch["run_id"],
                dispatch["agent_id"],
                dispatch["config_data"],
                dispatch["heartbeat_run_id"],
                dispatch["trigger_type"],
                dispatch["linked_task_id"],
            )
        )
