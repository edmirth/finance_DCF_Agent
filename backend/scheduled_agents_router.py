"""
Scheduled Agents REST API Router

Endpoints:
  GET    /scheduled-agents              — list all agents
  POST   /scheduled-agents              — create agent
  GET    /scheduled-agents/{id}         — get agent detail
  PATCH  /scheduled-agents/{id}         — update agent
  DELETE /scheduled-agents/{id}         — delete agent
  POST   /scheduled-agents/{id}/run     — trigger manual run (async)
  GET    /scheduled-agents/{id}/runs    — list run history
  GET    /agent-runs/{run_id}           — get single run detail
  GET    /inbox                         — all runs across all agents (paginated)
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_roles import infer_role_identity, resolve_role_definition, validate_role_key
from backend.database import get_db, AsyncSessionLocal
from backend.heartbeat_service import (
    create_heartbeat_run,
    dispatch_manager_heartbeat_actions,
    ensure_agent_heartbeat_routine,
    finalize_heartbeat_run,
    heartbeat_run_to_dict,
    plan_manager_heartbeat_actions,
    routine_map_for_agents,
    routine_to_dict,
    update_task_from_delegated_run,
)
from backend.models import ScheduledAgent, AgentRun, HeartbeatRun
from backend.scheduler import (
    register_agent_job,
    remove_agent_job,
    next_run_time,
    SUPPORTED_SCHEDULE_LABELS,
)
from backend.scheduled_agent_config import (
    normalize_tickers,
    validate_template,
    validate_ticker_requirement,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scheduled-agents"])


def _validate_schedule_label(schedule_label: str) -> str:
    normalized = (schedule_label or "").strip()
    if normalized not in SUPPORTED_SCHEDULE_LABELS:
        raise ValueError(
            f"Invalid schedule_label. Must be one of: {sorted(SUPPORTED_SCHEDULE_LABELS)}"
        )
    return normalized


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class ScheduledAgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template: Optional[str] = None         # internal execution template; role_key preferred
    role_key: Optional[str] = None
    tickers: List[str] = []
    topics: List[str] = []
    instruction: str = ""
    schedule_label: str = "weekly_monday"  # daily_morning | pre_market | weekly_monday | ...
    manager_agent_id: Optional[str] = None
    delivery_email: Optional[str] = None
    delivery_inapp: bool = True


class ScheduledAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    role_key: Optional[str] = None
    tickers: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    instruction: Optional[str] = None
    schedule_label: Optional[str] = None
    manager_agent_id: Optional[str] = None
    delivery_email: Optional[str] = None
    delivery_inapp: Optional[bool] = None
    is_active: Optional[bool] = None


def _agent_to_dict(
    agent: ScheduledAgent,
    manager_name: Optional[str] = None,
    heartbeat_routine=None,
) -> dict:
    reports_to_label = manager_name or ("Unknown manager" if agent.manager_agent_id else "CIO")
    role_identity = infer_role_identity(
        role_key=agent.role_key,
        role_title=agent.role_title,
        role_family=agent.role_family,
        template=agent.template,
    )
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "template": agent.template,
        "role_key": role_identity["role_key"],
        "role_title": role_identity["role_title"],
        "role_family": role_identity["role_family"],
        "tickers": json.loads(agent.tickers or "[]"),
        "topics": json.loads(agent.topics or "[]"),
        "instruction": agent.instruction,
        "schedule_label": agent.schedule_label,
        "manager_agent_id": agent.manager_agent_id,
        "manager_agent_name": manager_name,
        "reports_to_label": reports_to_label,
        "delivery_email": agent.delivery_email,
        "delivery_inapp": agent.delivery_inapp,
        "is_active": agent.is_active,
        "last_run_at": agent.last_run_at.isoformat() if agent.last_run_at else None,
        "next_run_at": agent.next_run_at.isoformat() if agent.next_run_at else None,
        "last_run_status": agent.last_run_status,
        "last_run_summary": agent.last_run_summary,
        "heartbeat_routine": routine_to_dict(heartbeat_routine),
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


async def _manager_name_map(db: AsyncSession, agents: list[ScheduledAgent]) -> dict[str, str]:
    manager_ids = sorted({a.manager_agent_id for a in agents if a.manager_agent_id})
    if not manager_ids:
        return {}
    result = await db.execute(
        select(ScheduledAgent.id, ScheduledAgent.name).where(ScheduledAgent.id.in_(manager_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _validate_manager_agent(
    db: AsyncSession,
    manager_agent_id: Optional[str],
    current_agent_id: Optional[str] = None,
) -> Optional[str]:
    manager_id = (manager_agent_id or "").strip() or None
    if not manager_id:
        return None
    if current_agent_id and manager_id == current_agent_id:
        raise HTTPException(status_code=400, detail="An agent cannot report to itself")
    result = await db.execute(select(ScheduledAgent).where(ScheduledAgent.id == manager_id))
    manager = result.scalar_one_or_none()
    if not manager:
        raise HTTPException(status_code=400, detail="Manager agent not found")
    return manager.id


def _run_to_dict(run: AgentRun) -> dict:
    return {
        "id": run.id,
        "scheduled_agent_id": run.scheduled_agent_id,
        "status": run.status,
        "report": run.report,
        "findings_summary": run.findings_summary,
        "key_findings": json.loads(getattr(run, "key_findings", None) or "[]"),
        "material_change": bool(run.material_change),
        "alert_level": run.alert_level,
        "tickers_analyzed": json.loads(run.tickers_analyzed or "[]"),
        "agents_used": json.loads(run.agents_used or "[]"),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/scheduled-agents")
async def list_scheduled_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledAgent).order_by(desc(ScheduledAgent.created_at))
    )
    agents = result.scalars().all()
    manager_names = await _manager_name_map(db, agents)
    routines = await routine_map_for_agents(db, [agent.id for agent in agents])
    return {"agents": [_agent_to_dict(a, manager_names.get(a.manager_agent_id or ""), routines.get(a.id)) for a in agents]}


@router.post("/scheduled-agents", status_code=201)
async def create_scheduled_agent(
    payload: ScheduledAgentCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        requested_role_key = validate_role_key(payload.role_key) if payload.role_key else None
        if requested_role_key:
            role = resolve_role_definition(role_key=requested_role_key)
            assert role is not None
            template = role.template
        else:
            template = validate_template(payload.template or "")
            role = resolve_role_definition(template=template)
        schedule_label = _validate_schedule_label(payload.schedule_label)
        tickers = normalize_tickers(payload.tickers)
        validate_ticker_requirement(template, tickers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    now = datetime.now(timezone.utc)
    nrt = next_run_time(schedule_label)
    manager_agent_id = await _validate_manager_agent(db, payload.manager_agent_id)
    role_identity = infer_role_identity(
        role_key=requested_role_key,
        role_title=role.title if role else None,
        role_family=role.family if role else None,
        template=template,
    )

    agent = ScheduledAgent(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        template=template,
        role_key=role_identity["role_key"],
        role_title=role_identity["role_title"],
        role_family=role_identity["role_family"],
        tickers=json.dumps(tickers),
        topics=json.dumps(payload.topics),
        instruction=payload.instruction,
        schedule_label=schedule_label,
        manager_agent_id=manager_agent_id,
        delivery_email=payload.delivery_email,
        delivery_inapp=payload.delivery_inapp,
        is_active=True,
        next_run_at=nrt,
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    routine = await ensure_agent_heartbeat_routine(db, agent)
    await db.commit()

    # Register with scheduler
    register_agent_job(agent.id, agent.name, agent.schedule_label)

    manager_name = None
    if manager_agent_id:
        result = await db.execute(select(ScheduledAgent.name).where(ScheduledAgent.id == manager_agent_id))
        manager_name = result.scalar_one_or_none()
    return _agent_to_dict(agent, manager_name, routine)


@router.get("/scheduled-agents/{agent_id}")
async def get_scheduled_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledAgent).where(ScheduledAgent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    routine = await ensure_agent_heartbeat_routine(db, agent)
    await db.commit()
    manager_name = None
    if agent.manager_agent_id:
        result = await db.execute(
            select(ScheduledAgent.name).where(ScheduledAgent.id == agent.manager_agent_id)
        )
        manager_name = result.scalar_one_or_none()
    return _agent_to_dict(agent, manager_name, routine)


@router.patch("/scheduled-agents/{agent_id}")
async def update_scheduled_agent(
    agent_id: str,
    payload: ScheduledAgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledAgent).where(ScheduledAgent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if payload.name is not None:
        agent.name = payload.name
    if payload.description is not None:
        agent.description = payload.description
    current_tickers = json.loads(agent.tickers or "[]")
    template = agent.template
    role_key = agent.role_key
    role_title = agent.role_title
    role_family = agent.role_family
    if payload.tickers is not None:
        current_tickers = normalize_tickers(payload.tickers)
        agent.tickers = json.dumps(current_tickers)
    if payload.topics is not None:
        agent.topics = json.dumps(payload.topics)
    if payload.instruction is not None:
        agent.instruction = payload.instruction
    if payload.schedule_label is not None:
        try:
            agent.schedule_label = _validate_schedule_label(payload.schedule_label)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        agent.next_run_at = next_run_time(agent.schedule_label)
    if "role_key" in payload.model_fields_set:
        try:
            if payload.role_key:
                role_key = validate_role_key(payload.role_key)
                role = resolve_role_definition(role_key=role_key)
                assert role is not None
                template = role.template
                role_title = role.title
                role_family = role.family
            else:
                role_key = None
                role = resolve_role_definition(template=template)
                role_title = role.title if role else role_title
                role_family = role.family if role else role_family
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if "manager_agent_id" in payload.model_fields_set:
        agent.manager_agent_id = await _validate_manager_agent(db, payload.manager_agent_id, agent.id)
    if payload.delivery_email is not None:
        agent.delivery_email = payload.delivery_email
    if payload.delivery_inapp is not None:
        agent.delivery_inapp = payload.delivery_inapp
    if payload.is_active is not None:
        agent.is_active = payload.is_active

    agent.template = template
    role_identity = infer_role_identity(
        role_key=role_key,
        role_title=role_title,
        role_family=role_family,
        template=template,
    )
    agent.role_key = role_identity["role_key"]
    agent.role_title = role_identity["role_title"]
    agent.role_family = role_identity["role_family"]

    try:
        validate_ticker_requirement(agent.template, current_tickers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    agent.updated_at = datetime.now(timezone.utc)
    routine = await ensure_agent_heartbeat_routine(db, agent)
    await db.commit()
    await db.refresh(agent)

    # Sync scheduler job
    if agent.is_active:
        register_agent_job(agent.id, agent.name, agent.schedule_label)
    else:
        remove_agent_job(agent.id)

    manager_name = None
    if agent.manager_agent_id:
        result = await db.execute(
            select(ScheduledAgent.name).where(ScheduledAgent.id == agent.manager_agent_id)
        )
        manager_name = result.scalar_one_or_none()
    return _agent_to_dict(agent, manager_name, routine)


@router.delete("/scheduled-agents/{agent_id}", status_code=204)
async def delete_scheduled_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledAgent).where(ScheduledAgent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    remove_agent_job(agent_id)
    await db.delete(agent)
    await db.commit()


@router.post("/scheduled-agents/{agent_id}/run", status_code=202)
async def trigger_manual_run(
    agent_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an immediate run (non-blocking — returns run ID instantly)."""
    result = await db.execute(
        select(ScheduledAgent).where(ScheduledAgent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Create pending run record
    now = datetime.now(timezone.utc)
    routine = await ensure_agent_heartbeat_routine(db, agent)
    run = AgentRun(
        id=str(uuid.uuid4()),
        scheduled_agent_id=agent_id,
        status="running",
        started_at=now,
    )
    db.add(run)
    await db.flush()
    heartbeat_run = await create_heartbeat_run(
        db,
        agent,
        trigger_type="manual",
        agent_run_id=run.id,
        started_at=now,
    )
    await db.commit()

    run_id = run.id
    config_data = _agent_to_dict(agent)

    # Execute in background
    background_tasks.add_task(
        _execute_run_background,
        run_id,
        agent_id,
        config_data,
        heartbeat_run.id,
        "manual",
    )

    return {"run_id": run_id, "status": "running", "message": "Run started"}


@router.get("/scheduled-agents/{agent_id}/runs")
async def list_agent_runs(
    agent_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.scheduled_agent_id == agent_id)
        .order_by(desc(AgentRun.started_at))
        .limit(limit)
    )
    runs = result.scalars().all()
    return {"runs": [_run_to_dict(r) for r in runs]}


@router.get("/agent-runs/{run_id}")
async def get_agent_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(run)


@router.get("/scheduled-agents/{agent_id}/heartbeat-runs")
async def list_heartbeat_runs(
    agent_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HeartbeatRun)
        .where(HeartbeatRun.scheduled_agent_id == agent_id)
        .order_by(desc(HeartbeatRun.started_at))
        .limit(limit)
    )
    runs = result.scalars().all()
    return {"runs": [heartbeat_run_to_dict(run) for run in runs]}


@router.get("/inbox")
async def get_inbox(
    limit: int = 30,
    alert_level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """All agent runs across all agents, newest first, with agent name included."""
    query = (
        select(AgentRun, ScheduledAgent.name.label("agent_name"))
        .join(ScheduledAgent, AgentRun.scheduled_agent_id == ScheduledAgent.id)
    )
    if alert_level:
        query = query.where(AgentRun.alert_level == alert_level)
    query = query.order_by(desc(AgentRun.started_at)).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for run, agent_name in rows:
        d = _run_to_dict(run)
        d["agent_name"] = agent_name
        items.append(d)

    return {"items": items}


# ------------------------------------------------------------------
# Background task helper
# ------------------------------------------------------------------

async def _execute_run_background(
    run_id: str,
    agent_id: str,
    config_data: dict,
    heartbeat_run_id: Optional[str] = None,
    trigger_type: str = "manual",
    linked_task_id: Optional[str] = None,
) -> None:
    """Execute an agent run in the background and persist results."""
    from backend.agent_runner import get_runner

    class _Snapshot:
        def __init__(self, d):
            self.id = d["id"]
            self.name = d["name"]
            self.template = d["template"]
            self.tickers = json.dumps(d["tickers"])
            self.topics = json.dumps(d["topics"])
            self.instruction = d["instruction"]
            self.schedule_label = d["schedule_label"]
            self.delivery_email = d["delivery_email"]
            self.last_run_summary = d["last_run_summary"]

    snapshot = _Snapshot(config_data)
    loop = asyncio.get_running_loop()
    runner = get_runner()

    try:
        outcome = await loop.run_in_executor(None, runner.execute, snapshot)
    except Exception as exc:
        outcome = {
            "report": "", "findings_summary": "", "material_change": False,
            "alert_level": "none", "tickers_analyzed": [], "agents_used": [],
            "error": str(exc),
        }

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
        heartbeat_run = None
        if heartbeat_run_id:
            heartbeat_result = await db.execute(
                select(HeartbeatRun).where(HeartbeatRun.id == heartbeat_run_id)
            )
            heartbeat_run = heartbeat_result.scalar_one_or_none()
        elif agent:
            heartbeat_run = await create_heartbeat_run(
                db,
                agent,
                trigger_type=trigger_type,
                agent_run_id=run_id,
                started_at=run.started_at if run else datetime.now(timezone.utc),
            )
        if agent:
            completed_at = datetime.now(timezone.utc)
            agent.last_run_at = datetime.now(timezone.utc)
            agent.last_run_status = run.status if run else "failed"
            agent.last_run_summary = outcome.get("findings_summary", "")
            agent.next_run_at = next_run_time(agent.schedule_label, now=completed_at)
            delivery_email = agent.delivery_email
            await finalize_heartbeat_run(db, heartbeat_run, agent, outcome)
            if linked_task_id:
                await update_task_from_delegated_run(db, linked_task_id, agent, run_id, outcome)
            planned_dispatches = await plan_manager_heartbeat_actions(db, agent, heartbeat_run)
        else:
            delivery_email = None
            await finalize_heartbeat_run(db, heartbeat_run, None, outcome)
            planned_dispatches = []

        await db.commit()

    if planned_dispatches:
        dispatch_manager_heartbeat_actions(planned_dispatches)

    # Send email notification (same as scheduled path)
    if delivery_email and not outcome.get("error"):
        try:
            from backend.email_service import send_run_email
            loop = asyncio.get_running_loop()
            agent_name = config_data.get("name", "Agent")
            await loop.run_in_executor(None, send_run_email, delivery_email, agent_name, outcome)
        except Exception as exc:
            logger.error(f"Email delivery failed for manual run {run_id}: {exc}")
