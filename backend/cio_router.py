"""
CIO (Chief Investment Officer) Router

The CIO is the persistent orchestrator agent — the single entry point
the user always talks to. It has full awareness of the team and can:

  1. ANSWER    — respond directly using team context + its own knowledge
  2. DELEGATE  — trigger an existing agent to run now
  3. PROPOSE   — suggest hiring a new agent when a gap exists
  4. SURFACE   — pull recent findings from a specific agent into the conversation

The CIO builds its context dynamically on each request:
  - All active scheduled agents + their last run summaries
  - 5 most recent agent runs across the team

Endpoint:
  POST /cio/chat — send a message, returns response + optional action
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from anthropic import Anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_roles import ROLE_CATALOG, infer_role_identity, resolve_role_definition, validate_role_key
from backend.database import get_db
from backend.heartbeat_service import create_heartbeat_run, ensure_agent_heartbeat_routine
from backend.models import ScheduledAgent, AgentRun, HireProposal
from backend.scheduler import register_agent_job, next_run_time, SUPPORTED_SCHEDULE_LABELS
from backend.scheduled_agent_config import (
    normalize_tickers,
    validate_template,
    validate_ticker_requirement,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cio"])

_anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SCHEDULE_LABELS = {
    "daily_morning": "Daily at 7am",
    "pre_market":    "Weekdays at 6:30am",
    "weekly_monday": "Every Monday",
    "weekly_friday": "Every Friday",
    "monthly":       "Monthly",
}


def _validate_schedule_label(schedule_label: str) -> str:
    normalized = (schedule_label or "").strip()
    if normalized not in SUPPORTED_SCHEDULE_LABELS:
        raise ValueError(
            f"Invalid schedule_label. Must be one of: {sorted(SUPPORTED_SCHEDULE_LABELS)}"
        )
    return normalized


def _validate_proposal_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = (status or "").strip()
    if normalized not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid proposal status")
    return normalized


# ── Context builder ───────────────────────────────────────────────────────────

async def _build_team_context(db: AsyncSession) -> str:
    """Build a structured context string describing the current agent team and recent findings."""

    # Load all agents
    agents_result = await db.execute(
        select(ScheduledAgent).order_by(desc(ScheduledAgent.created_at))
    )
    agents = agents_result.scalars().all()

    # Load 5 most recent completed runs
    runs_result = await db.execute(
        select(AgentRun, ScheduledAgent.name.label("agent_name"))
        .join(ScheduledAgent, AgentRun.scheduled_agent_id == ScheduledAgent.id)
        .where(AgentRun.status == "completed")
        .order_by(desc(AgentRun.started_at))
        .limit(5)
    )
    recent_runs = runs_result.all()

    lines = ["## Your Research Team\n"]

    if not agents:
        lines.append("No agents hired yet. You have an empty team.\n")
    else:
        for a in agents:
            tickers = json.loads(a.tickers or "[]")
            status = "Active" if a.is_active else "Paused"
            role_identity = infer_role_identity(
                role_key=a.role_key,
                role_title=a.role_title,
                role_family=a.role_family,
                template=a.template,
            )
            role_label = role_identity["role_title"] or a.name
            ticker_str = ", ".join(tickers) if tickers else "no specific tickers"
            last_run = f"Last run: {a.last_run_at.strftime('%b %d') if a.last_run_at else 'never'}"
            reports_to = "CIO"
            if a.manager_agent_id:
                manager = next((candidate for candidate in agents if candidate.id == a.manager_agent_id), None)
                reports_to = manager.name if manager else "Unknown manager"
            summary = f"\n   Latest finding: {a.last_run_summary}" if a.last_run_summary else ""
            lines.append(
                f"- **{a.name}** [{role_label}] | Reports to: {reports_to} | {status} | Watches: {ticker_str} | {last_run}{summary}"
            )

    lines.append("\n## Recent Findings\n")

    if not recent_runs:
        lines.append("No research runs yet.\n")
    else:
        for run, agent_name in recent_runs:
            date = run.started_at.strftime("%b %d") if run.started_at else "unknown"
            alert = run.alert_level.upper() if run.alert_level != "none" else ""
            alert_str = f" [{alert}]" if alert else ""
            lines.append(
                f"- **{agent_name}** ({date}){alert_str}: {run.findings_summary[:200] if run.findings_summary else 'No summary'}"
            )

    return "\n".join(lines)


def _build_system_prompt(team_context: str) -> str:
    role_lines = "\n".join(
        f"- `{role.key}` — {role.title}: {role.description}"
        for role in ROLE_CATALOG.values()
    )
    return f"""You are the Chief Investment Officer (CIO) of Phronesis AI — a financial intelligence platform.

You are the investor's persistent, trusted advisor and team orchestrator. You are always their first stop. You have full visibility into their research team and recent findings.

## Your Capabilities

1. **ANSWER** — Respond directly. Use team context, your investment knowledge, and recent findings.
2. **DELEGATE** — When an existing agent should run now to answer the question, delegate to it.
3. **PROPOSE** — When no existing agent covers the need, propose hiring a new one.
4. **SURFACE** — When recent findings from a specific agent are directly relevant, surface them.

## Available Agent Roles (for PROPOSE action)
{role_lines}

## Available Schedules
- `daily_morning`, `pre_market`, `weekly_monday`, `weekly_friday`, `monthly`

---

{team_context}

---

## Response Format

You MUST respond with valid JSON only:

{{
  "message": "Your conversational response to the investor. Be direct, specific, and professional. Reference actual agent names and findings when relevant. No fluff.",
  "action": null
}}

OR with an action:

{{
  "message": "Your explanation of what you're doing or proposing",
  "action": {{
    "type": "delegate",
    "agent_id": "<existing agent uuid>",
    "agent_name": "<agent name>",
    "reason": "One sentence on why this agent should run now"
  }}
}}

OR:

{{
  "message": "Your explanation of the gap and what you're proposing",
  "action": {{
    "type": "propose_hire",
    "role_key": "<role id>",
    "role_title": "<firm role title>",
    "name": "Agent name",
    "description": "One sentence description",
    "tickers": ["TICKER"],
    "topics": ["topic"],
    "instruction": "Detailed instruction for the agent. Be specific about what to watch, what thesis to monitor, what constitutes a material change.",
    "schedule_label": "weekly_monday"
  }}
}}

Rules:
- Only propose hiring if no existing agent covers the need. Don't duplicate.
- Prefer sector, desk, and firm-seat roles over raw methodology labels.
- Only delegate to agents that are active and relevant to the question.
- Keep messages concise and direct. You are a busy CIO, not a chatbot.
- Always reference specific agent names and findings when relevant.
- Return ONLY valid JSON. No markdown fences."""


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CioMessage(BaseModel):
    role: str     # 'user' | 'assistant'
    content: str  # text only (no action objects in history)


class CioChatRequest(BaseModel):
    messages: List[CioMessage]


class CioAction(BaseModel):
    type: str                          # delegate | propose_hire
    agent_id: Optional[str] = None     # for delegate
    agent_name: Optional[str] = None   # for delegate
    reason: Optional[str] = None       # for delegate
    # propose_hire fields
    role_key: Optional[str] = None
    role_title: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    tickers: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    instruction: Optional[str] = None
    schedule_label: Optional[str] = None
    manager_agent_id: Optional[str] = None
    proposal_id: Optional[str] = None
    proposal_status: Optional[str] = None


class CioChatResponse(BaseModel):
    message: str
    action: Optional[CioAction] = None


class HireFromCioRequest(BaseModel):
    action: CioAction
    delivery_inapp: bool = True
    delivery_email: Optional[str] = None


class HireProposalDecisionRequest(BaseModel):
    decision_note: Optional[str] = None


def _cio_chat_sync(system_prompt: str, messages: list[dict]) -> dict:
    response = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=system_prompt,
        messages=messages,
    )
    raw = response.content[0].text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


async def _lookup_agent_name(db: AsyncSession, agent_id: Optional[str]) -> Optional[str]:
    normalized = (agent_id or "").strip()
    if not normalized:
        return None
    result = await db.execute(
        select(ScheduledAgent.name).where(ScheduledAgent.id == normalized)
    )
    return result.scalar_one_or_none()


async def _validate_manager_agent_id(
    db: AsyncSession,
    manager_agent_id: Optional[str],
) -> Optional[str]:
    normalized = (manager_agent_id or "").strip() or None
    if not normalized:
        return None
    manager_name = await _lookup_agent_name(db, normalized)
    if not manager_name:
        raise HTTPException(status_code=400, detail="Manager agent not found")
    return normalized


async def _normalize_hire_request(
    db: AsyncSession,
    action: CioAction,
    *,
    delivery_inapp: bool = True,
    delivery_email: Optional[str] = None,
) -> dict:
    try:
        requested_role_key = validate_role_key(action.role_key) if action.role_key else None
        if requested_role_key:
            role = resolve_role_definition(role_key=requested_role_key)
            assert role is not None
            template = role.template
        else:
            template = validate_template(action.template or "thesis_guardian")
            role = resolve_role_definition(template=template)
        schedule_label = _validate_schedule_label(action.schedule_label or "weekly_monday")
        tickers = normalize_tickers(action.tickers or [])
        validate_ticker_requirement(template, tickers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    manager_agent_id = await _validate_manager_agent_id(db, action.manager_agent_id)
    role_identity = infer_role_identity(
        role_key=requested_role_key,
        role_title=action.role_title or (role.title if role else None),
        role_family=role.family if role else None,
        template=template,
    )
    return {
        "name": action.name or "New Agent",
        "description": action.description,
        "template": template,
        "role_key": role_identity["role_key"],
        "role_title": role_identity["role_title"],
        "role_family": role_identity["role_family"],
        "tickers": tickers,
        "topics": action.topics or [],
        "instruction": action.instruction or "",
        "schedule_label": schedule_label,
        "manager_agent_id": manager_agent_id,
        "delivery_inapp": delivery_inapp,
        "delivery_email": delivery_email,
    }


async def _proposal_to_dict(db: AsyncSession, proposal: HireProposal) -> dict:
    manager_name = await _lookup_agent_name(db, proposal.manager_agent_id)
    approved_agent_name = await _lookup_agent_name(db, proposal.approved_agent_id)
    return {
        "id": proposal.id,
        "proposed_by": proposal.proposed_by,
        "status": proposal.status,
        "name": proposal.name,
        "description": proposal.description,
        "template": proposal.template,
        "role_key": proposal.role_key,
        "role_title": proposal.role_title,
        "role_family": proposal.role_family,
        "tickers": json.loads(proposal.tickers or "[]"),
        "topics": json.loads(proposal.topics or "[]"),
        "instruction": proposal.instruction,
        "schedule_label": proposal.schedule_label,
        "manager_agent_id": proposal.manager_agent_id,
        "manager_agent_name": manager_name,
        "reports_to_label": manager_name or ("Unknown manager" if proposal.manager_agent_id else "CIO"),
        "delivery_email": proposal.delivery_email,
        "delivery_inapp": proposal.delivery_inapp,
        "approved_agent_id": proposal.approved_agent_id,
        "approved_agent_name": approved_agent_name,
        "decision_note": proposal.decision_note,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }


async def _create_hire_proposal(
    db: AsyncSession,
    action: CioAction,
    *,
    proposed_by: str = "cio",
    delivery_inapp: bool = True,
    delivery_email: Optional[str] = None,
) -> HireProposal:
    normalized = await _normalize_hire_request(
        db,
        action,
        delivery_inapp=delivery_inapp,
        delivery_email=delivery_email,
    )
    now = datetime.now(timezone.utc)
    proposal = HireProposal(
        id=str(uuid.uuid4()),
        proposed_by=proposed_by,
        status="pending",
        name=normalized["name"],
        description=normalized["description"],
        template=normalized["template"],
        role_key=normalized["role_key"],
        role_title=normalized["role_title"],
        role_family=normalized["role_family"],
        tickers=json.dumps(normalized["tickers"]),
        topics=json.dumps(normalized["topics"]),
        instruction=normalized["instruction"],
        schedule_label=normalized["schedule_label"],
        manager_agent_id=normalized["manager_agent_id"],
        delivery_email=normalized["delivery_email"],
        delivery_inapp=normalized["delivery_inapp"],
        created_at=now,
        updated_at=now,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _approve_hire_proposal(
    db: AsyncSession,
    proposal: HireProposal,
    *,
    decision_note: Optional[str] = None,
) -> ScheduledAgent:
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal.status}")

    manager_agent_id = await _validate_manager_agent_id(db, proposal.manager_agent_id)
    now = datetime.now(timezone.utc)
    agent = ScheduledAgent(
        id=str(uuid.uuid4()),
        name=proposal.name,
        description=proposal.description,
        template=proposal.template,
        role_key=proposal.role_key,
        role_title=proposal.role_title,
        role_family=proposal.role_family,
        tickers=proposal.tickers,
        topics=proposal.topics,
        instruction=proposal.instruction,
        schedule_label=proposal.schedule_label,
        manager_agent_id=manager_agent_id,
        delivery_email=proposal.delivery_email,
        delivery_inapp=proposal.delivery_inapp,
        is_active=True,
        next_run_at=next_run_time(proposal.schedule_label),
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    proposal.status = "approved"
    proposal.manager_agent_id = manager_agent_id
    proposal.approved_agent_id = agent.id
    proposal.decision_note = decision_note
    proposal.decided_at = now
    proposal.updated_at = now
    await db.commit()
    await db.refresh(agent)
    await ensure_agent_heartbeat_routine(db, agent)
    await db.refresh(proposal)
    await db.commit()
    register_agent_job(agent.id, agent.name, agent.schedule_label)
    return agent


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/cio/chat", response_model=CioChatResponse)
async def cio_chat(
    request: CioChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the CIO. Returns a response and optionally an action."""

    team_context = await _build_team_context(db)
    system_prompt = _build_system_prompt(team_context)

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    try:
        parsed = await run_in_threadpool(_cio_chat_sync, system_prompt, messages)
        action_data = parsed.get("action")
        action = CioAction(**action_data) if action_data else None
        message = parsed.get("message", "")

        if action and action.type == "propose_hire":
            try:
                proposal = await _create_hire_proposal(db, action)
                action.proposal_id = proposal.id
                action.proposal_status = proposal.status
            except HTTPException as exc:
                logger.warning("Failed to persist CIO hire proposal: %s", exc.detail)
                message = f"{message}\n\nI could not turn that suggestion into a valid hire proposal."
                action = None

        return CioChatResponse(
            message=message,
            action=action,
        )

    except json.JSONDecodeError:
        return CioChatResponse(
            message="I had trouble formulating my response. Could you rephrase that?",
            action=None,
        )
    except Exception as exc:
        logger.exception("cio_chat failed")
        return CioChatResponse(
            message="Something went wrong on my end. Please try again.",
            action=None,
        )


@router.post("/cio/delegate/{agent_id}", status_code=202)
async def cio_delegate(
    agent_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger an existing agent to run immediately (CIO delegation)."""
    from backend.scheduled_agents_router import _execute_run_background, _agent_to_dict

    result = await db.execute(select(ScheduledAgent).where(ScheduledAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Agent not found")

    run = AgentRun(
        id=str(uuid.uuid4()),
        scheduled_agent_id=agent_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    await ensure_agent_heartbeat_routine(db, agent)
    db.add(run)
    await db.flush()
    heartbeat_run = await create_heartbeat_run(
        db,
        agent,
        trigger_type="delegated",
        agent_run_id=run.id,
        started_at=run.started_at,
    )
    await db.commit()

    run_id = run.id
    config_data = _agent_to_dict(agent)
    background_tasks.add_task(
        _execute_run_background,
        run_id,
        agent_id,
        config_data,
        heartbeat_run.id,
        "delegated",
    )

    return {"run_id": run_id, "status": "running", "agent_name": agent.name}


@router.get("/cio/hire-proposals")
async def list_hire_proposals(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    normalized_status = _validate_proposal_status(status)
    query = select(HireProposal).order_by(desc(HireProposal.created_at))
    if normalized_status:
        query = query.where(HireProposal.status == normalized_status)
    result = await db.execute(query)
    proposals = result.scalars().all()
    return {"proposals": [await _proposal_to_dict(db, proposal) for proposal in proposals]}


@router.post("/cio/hire-proposals", status_code=201)
async def create_hire_proposal(
    request: HireFromCioRequest,
    db: AsyncSession = Depends(get_db),
):
    proposal = await _create_hire_proposal(
        db,
        request.action,
        delivery_inapp=request.delivery_inapp,
        delivery_email=request.delivery_email,
    )
    return await _proposal_to_dict(db, proposal)


@router.post("/cio/hire-proposals/{proposal_id}/approve")
async def approve_hire_proposal(
    proposal_id: str,
    request: HireProposalDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HireProposal).where(HireProposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Hire proposal not found")

    agent = await _approve_hire_proposal(db, proposal, decision_note=request.decision_note)
    return {
        "proposal": await _proposal_to_dict(db, proposal),
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "role_key": agent.role_key,
            "role_title": agent.role_title,
            "template": agent.template,
            "tickers": json.loads(agent.tickers or "[]"),
            "schedule_label": agent.schedule_label,
            "created_at": agent.created_at.isoformat(),
        },
    }


@router.post("/cio/hire-proposals/{proposal_id}/reject")
async def reject_hire_proposal(
    proposal_id: str,
    request: HireProposalDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HireProposal).where(HireProposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Hire proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal.status}")

    proposal.status = "rejected"
    proposal.decision_note = request.decision_note
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.updated_at = proposal.decided_at
    await db.commit()
    await db.refresh(proposal)
    return await _proposal_to_dict(db, proposal)


@router.post("/cio/hire", status_code=201)
async def cio_hire(
    request: HireFromCioRequest,
    db: AsyncSession = Depends(get_db),
):
    """Backward-compatible direct hire path: create and approve in one call."""
    proposal = await _create_hire_proposal(
        db,
        request.action,
        delivery_inapp=request.delivery_inapp,
        delivery_email=request.delivery_email,
    )
    agent = await _approve_hire_proposal(db, proposal)
    return {
        "proposal": await _proposal_to_dict(db, proposal),
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "role_key": agent.role_key,
            "role_title": agent.role_title,
            "template": agent.template,
            "tickers": json.loads(agent.tickers or "[]"),
            "schedule_label": agent.schedule_label,
            "created_at": agent.created_at.isoformat(),
        },
    }
