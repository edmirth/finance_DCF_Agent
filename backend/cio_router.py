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
from pathlib import Path
from typing import List, Optional

from anthropic import Anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_roles import ROLE_CATALOG, infer_role_identity, resolve_role_definition, validate_role_key
from backend.config import CIO_MODEL
from backend.database import get_db
from backend.heartbeat_service import create_heartbeat_run, ensure_agent_heartbeat_routine
from backend.models import ScheduledAgent, AgentRun, HireProposal, Project, ResearchTask
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

CEO_PROFILE_DIR = Path(
    os.getenv(
        "CEO_AGENT_HOME",
        Path(__file__).resolve().parent / "agent_profiles" / "ceo",
    )
)
CEO_STATE_FILE_NAME = "state.json"

CEO_INSTRUCTION_DOCS: dict[str, dict[str, str]] = {
    "system": {"filename": "SYSTEM.md", "title": "System"},
    "heartbeat": {"filename": "HEARTBEAT.md", "title": "Heartbeat"},
    "soul": {"filename": "SOUL.md", "title": "Soul"},
    "tools": {"filename": "TOOLS.md", "title": "Tools"},
}
CEO_OPEN_TASK_STATUSES = ("pending", "running", "in_review")
CEO_PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


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


def _load_ceo_profile_doc(filename: str) -> str:
    path = CEO_PROFILE_DIR / filename
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.exception("Failed to load CEO profile document: %s", path)
        return ""
    return content.replace("$AGENT_HOME", str(CEO_PROFILE_DIR))


def _resolve_ceo_instruction_doc(doc_key: str) -> tuple[dict[str, str], Path]:
    normalized = (doc_key or "").strip().lower()
    spec = CEO_INSTRUCTION_DOCS.get(normalized)
    if spec is None:
        raise HTTPException(status_code=404, detail="CEO instruction doc not found")
    return spec, CEO_PROFILE_DIR / spec["filename"]


def _ceo_instruction_docs() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "filename": spec["filename"],
            "title": spec["title"],
            "content": _load_ceo_profile_doc(spec["filename"]),
        }
        for key, spec in CEO_INSTRUCTION_DOCS.items()
    ]


def _ceo_state_path() -> Path:
    return CEO_PROFILE_DIR / CEO_STATE_FILE_NAME


def _default_ceo_runtime_state() -> dict[str, Optional[str]]:
    return {
        "status": "idle",
        "last_heartbeat_at": None,
        "last_heartbeat_message": None,
        "last_reviewed_task_id": None,
    }


def _load_ceo_runtime_state() -> dict[str, Optional[str]]:
    path = _ceo_state_path()
    state = _default_ceo_runtime_state()
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                state.update({key: raw.get(key) for key in state.keys()})
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load CEO runtime state: %s", path)
    normalized_status = str(state.get("status") or "idle").strip().lower()
    state["status"] = normalized_status if normalized_status in {"idle", "paused"} else "idle"
    return state


def _save_ceo_runtime_state(state: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    normalized = _default_ceo_runtime_state()
    normalized.update(state)
    normalized_status = str(normalized.get("status") or "idle").strip().lower()
    normalized["status"] = normalized_status if normalized_status in {"idle", "paused"} else "idle"
    path = _ceo_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to save CEO runtime state: %s", path)
        raise HTTPException(status_code=500, detail="Failed to save CEO state")
    return normalized


def _ceo_issue_scope_clause():
    return or_(
        ResearchTask.triggered_by == "manual_pm_review",
        and_(
            ResearchTask.owner_agent_id.is_(None),
            ResearchTask.assigned_agent_id.is_(None),
        ),
    )


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
        select(
            AgentRun,
            ScheduledAgent.name.label("agent_name"),
            ScheduledAgent.role_title.label("agent_role_title"),
        )
        .join(ScheduledAgent, AgentRun.scheduled_agent_id == ScheduledAgent.id)
        .where(AgentRun.status == "completed")
        .order_by(desc(AgentRun.started_at))
        .limit(5)
    )
    recent_runs = runs_result.all()
    proposal_result = await db.execute(
        select(HireProposal)
        .where(HireProposal.status == "pending")
        .order_by(desc(HireProposal.created_at))
        .limit(5)
    )
    pending_proposals = proposal_result.scalars().all()
    task_result = await db.execute(
        select(ResearchTask)
        .where(ResearchTask.status.in_(("pending", "running", "in_review")))
        .order_by(desc(ResearchTask.updated_at))
        .limit(5)
    )
    open_tasks = task_result.scalars().all()

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
            display_name = role_label
            ticker_str = ", ".join(tickers) if tickers else "no specific tickers"
            last_run = f"Last run: {a.last_run_at.strftime('%b %d') if a.last_run_at else 'never'}"
            reports_to = "CIO"
            if a.manager_agent_id:
                manager = next((candidate for candidate in agents if candidate.id == a.manager_agent_id), None)
                reports_to = (manager.role_title or manager.name) if manager else "Unknown manager"
            summary = f"\n   Latest finding: {a.last_run_summary}" if a.last_run_summary else ""
            lines.append(
                f"- **{display_name}** | Reports to: {reports_to} | {status} | Watches: {ticker_str} | {last_run}{summary}"
            )

    lines.append("\n## Recent Findings\n")

    if not recent_runs:
        lines.append("No research runs yet.\n")
    else:
        for run, agent_name, agent_role_title in recent_runs:
            date = run.started_at.strftime("%b %d") if run.started_at else "unknown"
            alert = run.alert_level.upper() if run.alert_level != "none" else ""
            alert_str = f" [{alert}]" if alert else ""
            lines.append(
                f"- **{agent_role_title or agent_name}** ({date}){alert_str}: {run.findings_summary[:200] if run.findings_summary else 'No summary'}"
            )

    lines.append("\n## Pending Hire Proposals\n")

    if not pending_proposals:
        lines.append("No pending hire proposals.\n")
    else:
        for proposal in pending_proposals:
            tickers = ", ".join(json.loads(proposal.tickers or "[]")) or "no specific tickers"
            lines.append(
                f"- **{proposal.role_title or proposal.name}** | Watches: {tickers}"
            )

    lines.append("\n## Open Issues\n")

    if not open_tasks:
        lines.append("No open issues.\n")
    else:
        for task in open_tasks:
            lines.append(
                f"- **{task.title}** | {task.status} | {task.priority} priority | Ticker: {task.ticker}"
            )

    return "\n".join(lines)


def _build_system_prompt(team_context: str) -> str:
    system_doc = _load_ceo_profile_doc("SYSTEM.md")
    heartbeat_doc = _load_ceo_profile_doc("HEARTBEAT.md")
    soul_doc = _load_ceo_profile_doc("SOUL.md")
    tools_doc = _load_ceo_profile_doc("TOOLS.md")
    role_lines = "\n".join(
        f"- `{role.key}` — {role.title}: {role.description}"
        for role in ROLE_CATALOG.values()
    )
    schedule_lines = "\n".join(
        f"- `{key}` — {label}"
        for key, label in SCHEDULE_LABELS.items()
    )
    return f"""You are the Chief Investment Officer (CIO) of Phronesis AI — a financial intelligence platform.

You are the investor's persistent, trusted advisor and team orchestrator. You are always their first stop. You have full visibility into their research team, current workload, and recent findings.

## CEO Operating Profile
{system_doc}

## CEO Persona Reference
{soul_doc}

## CEO Tool Surface
{tools_doc}

## CEO Heartbeat Checklist
{heartbeat_doc}

## Your Capabilities

1. **ANSWER** — Respond directly. Use team context, your investment knowledge, and recent findings.
2. **DELEGATE** — When an existing agent should run now to answer the question, delegate to it.
3. **PROPOSE** — When no existing agent covers the need, propose hiring a new one.
4. **SURFACE** — When recent findings from a specific agent are directly relevant, surface them.

## Available Agent Roles (for PROPOSE action)
{role_lines}

## Available Schedules
{schedule_lines}

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
- Treat CEO and CIO labels as the same leader seat.
- Keep messages concise and direct. You are a busy CIO, not a chatbot.
- Always reference specific agent names and findings when relevant.
- Return ONLY valid JSON. No markdown fences."""


def _ceo_issue_to_dict(task: ResearchTask, project_title: Optional[str]) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "ticker": task.ticker,
        "notes": task.notes,
        "project_id": task.project_id,
        "project_title": project_title,
        "selected_agents": json.loads(task.selected_agents or "[]"),
        "assigned_agent_id": task.assigned_agent_id,
        "owner_agent_id": task.owner_agent_id,
        "triggered_by": task.triggered_by,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


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


class CioTaskReviewResponse(CioChatResponse):
    task_id: str


class HireFromCioRequest(BaseModel):
    action: CioAction
    delivery_inapp: bool = True
    delivery_email: Optional[str] = None


class HireProposalDecisionRequest(BaseModel):
    decision_note: Optional[str] = None


class CioInstructionUpdateRequest(BaseModel):
    content: str


class CioAgentStatusUpdateRequest(BaseModel):
    status: str


def _build_task_review_prompt(
    task: ResearchTask,
    project_title: Optional[str],
    project_thesis: Optional[str],
) -> str:
    try:
        selected_agents = json.loads(task.selected_agents or "[]")
    except (json.JSONDecodeError, TypeError):
        selected_agents = []

    lines = [
        "Review this issue for the PM workflow.",
        f"Title: {task.title}",
        f"Ticker: {task.ticker}",
        f"Task type: {task.task_type}",
        f"Priority: {task.priority}",
        f"Project: {project_title or 'No project'}",
        f"Project thesis: {project_thesis or 'No project thesis'}",
        f"Description: {task.notes or 'No description provided.'}",
        f"Current staffing: {', '.join(selected_agents) if selected_agents else 'Unstaffed'}",
        (
            "Decide whether you should answer directly, delegate to an existing agent, "
            "or propose a hire. If staffing is missing, propose the right hire or delegation."
        ),
    ]
    return "\n".join(lines)


def _cio_chat_sync(system_prompt: str, messages: list[dict]) -> dict:
    response = _anthropic.messages.create(
        model=CIO_MODEL,
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
        select(ScheduledAgent.name, ScheduledAgent.role_title).where(ScheduledAgent.id == normalized)
    )
    row = result.one_or_none()
    if not row:
        return None
    return row[1] or row[0]


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


def _same_ticker_scope(left: list[str], right: list[str]) -> bool:
    return sorted(left) == sorted(right)


async def _find_duplicate_pending_proposal(
    db: AsyncSession,
    *,
    role_key: Optional[str],
    template: str,
    tickers: list[str],
    manager_agent_id: Optional[str],
) -> Optional[HireProposal]:
    result = await db.execute(
        select(HireProposal)
        .where(HireProposal.status == "pending")
        .order_by(desc(HireProposal.created_at))
    )
    for proposal in result.scalars().all():
        same_role = (
            (role_key and proposal.role_key == role_key)
            or (not role_key and proposal.template == template)
        )
        if not same_role:
            continue
        if (proposal.manager_agent_id or None) != manager_agent_id:
            continue
        proposal_tickers = json.loads(proposal.tickers or "[]")
        if _same_ticker_scope(proposal_tickers, tickers):
            return proposal
    return None


async def _find_duplicate_active_agent(
    db: AsyncSession,
    *,
    role_key: Optional[str],
    template: str,
    tickers: list[str],
    manager_agent_id: Optional[str],
) -> Optional[ScheduledAgent]:
    result = await db.execute(
        select(ScheduledAgent)
        .where(ScheduledAgent.is_active.is_(True))
        .order_by(desc(ScheduledAgent.created_at))
    )
    for agent in result.scalars().all():
        same_role = (
            (role_key and agent.role_key == role_key)
            or (not role_key and agent.template == template)
        )
        if not same_role:
            continue
        if (agent.manager_agent_id or None) != manager_agent_id:
            continue
        agent_tickers = json.loads(agent.tickers or "[]")
        if _same_ticker_scope(agent_tickers, tickers):
            return agent
    return None


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
    display_name = role_identity["role_title"] or action.name or "New Agent"
    return {
        "name": display_name,
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
    source_task_title = None
    if proposal.source_task_id:
        task_result = await db.execute(
            select(ResearchTask.title).where(ResearchTask.id == proposal.source_task_id)
        )
        source_task_title = task_result.scalar_one_or_none()
    return {
        "id": proposal.id,
        "proposed_by": proposal.proposed_by,
        "status": proposal.status,
        "name": proposal.role_title or proposal.name,
        "description": proposal.description,
        "template": proposal.template,
        "role_key": proposal.role_key,
        "role_title": proposal.role_title,
        "role_family": proposal.role_family,
        "tickers": json.loads(proposal.tickers or "[]"),
        "topics": json.loads(proposal.topics or "[]"),
        "instruction": proposal.instruction,
        "rationale": proposal.rationale,
        "schedule_label": proposal.schedule_label,
        "source_task_id": proposal.source_task_id,
        "source_task_title": source_task_title,
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
    source_task_id: Optional[str] = None,
    rationale: Optional[str] = None,
    delivery_inapp: bool = True,
    delivery_email: Optional[str] = None,
) -> HireProposal:
    normalized = await _normalize_hire_request(
        db,
        action,
        delivery_inapp=delivery_inapp,
        delivery_email=delivery_email,
    )
    duplicate_pending = await _find_duplicate_pending_proposal(
        db,
        role_key=normalized["role_key"],
        template=normalized["template"],
        tickers=normalized["tickers"],
        manager_agent_id=normalized["manager_agent_id"],
    )
    if duplicate_pending is not None:
        return duplicate_pending

    duplicate_agent = await _find_duplicate_active_agent(
        db,
        role_key=normalized["role_key"],
        template=normalized["template"],
        tickers=normalized["tickers"],
        manager_agent_id=normalized["manager_agent_id"],
    )
    if duplicate_agent is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A matching active agent already exists: {duplicate_agent.role_title or duplicate_agent.name}",
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
        rationale=rationale,
        schedule_label=normalized["schedule_label"],
        source_task_id=source_task_id,
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
        name=proposal.role_title or proposal.name,
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


async def _run_cio_response(
    db: AsyncSession,
    messages: list[dict],
    *,
    proposed_by: str = "cio",
    source_task_id: Optional[str] = None,
) -> CioChatResponse:
    team_context = await _build_team_context(db)
    system_prompt = _build_system_prompt(team_context)

    try:
        parsed = await run_in_threadpool(_cio_chat_sync, system_prompt, messages)
        action_data = parsed.get("action")
        action = CioAction(**action_data) if action_data else None
        message = parsed.get("message", "")

        if action and action.type == "propose_hire":
            try:
                proposal = await _create_hire_proposal(
                    db,
                    action,
                    proposed_by=proposed_by,
                    source_task_id=source_task_id,
                    rationale=message,
                )
                action.proposal_id = proposal.id
                action.proposal_status = proposal.status
            except HTTPException as exc:
                logger.warning("Failed to persist CIO hire proposal: %s", exc.detail)
                message = f"{message}\n\n{exc.detail}"
                action = None

        return CioChatResponse(message=message, action=action)

    except json.JSONDecodeError:
        return CioChatResponse(
            message="I had trouble formulating my response. Please retry the review.",
            action=None,
        )
    except Exception:
        logger.exception("cio response generation failed")
        return CioChatResponse(
            message="Something went wrong on my end. Please try again.",
            action=None,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/cio/chat", response_model=CioChatResponse)
async def cio_chat(
    request: CioChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the CIO. Returns a response and optionally an action."""
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    return await _run_cio_response(db, messages)


@router.get("/cio/agent")
async def get_cio_agent_page(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    normalized_limit = min(max(limit, 1), 100)
    runtime_state = _load_ceo_runtime_state()

    recent_issues_result = await db.execute(
        select(ResearchTask, Project.title.label("project_title"))
        .outerjoin(Project, ResearchTask.project_id == Project.id)
        .where(_ceo_issue_scope_clause())
        .order_by(desc(ResearchTask.updated_at), desc(ResearchTask.created_at))
        .limit(normalized_limit)
    )
    recent_issues = [
        _ceo_issue_to_dict(task, project_title)
        for task, project_title in recent_issues_result.all()
    ]

    active_team_result = await db.execute(
        select(ScheduledAgent)
        .where(ScheduledAgent.is_active.is_(True))
        .order_by(desc(ScheduledAgent.updated_at), desc(ScheduledAgent.created_at))
    )
    active_team = active_team_result.scalars().all()

    pending_proposals_result = await db.execute(
        select(HireProposal)
        .where(HireProposal.status == "pending")
        .order_by(desc(HireProposal.created_at))
        .limit(10)
    )
    pending_proposals = pending_proposals_result.scalars().all()

    return {
        "agent": {
            "id": "synthetic-ceo",
            "name": "CEO",
            "title": "Firm Lead",
            "status": runtime_state["status"],
            "aliases": ["CIO", "PM / CIO"],
            "model": CIO_MODEL,
            "profile_path": str(CEO_PROFILE_DIR),
            "last_heartbeat_at": runtime_state["last_heartbeat_at"],
            "last_heartbeat_message": runtime_state["last_heartbeat_message"],
            "last_reviewed_task_id": runtime_state["last_reviewed_task_id"],
        },
        "stats": {
            "recent_issue_count": len(recent_issues),
            "pending_hire_count": len(pending_proposals),
            "active_team_count": len(active_team),
        },
        "recent_issues": recent_issues,
        "pending_hire_proposals": [await _proposal_to_dict(db, proposal) for proposal in pending_proposals],
        "active_team": [
            {
                "id": agent.id,
                "name": agent.name,
                "role_key": agent.role_key,
                "role_title": agent.role_title,
                "role_family": agent.role_family,
                "template": agent.template,
                "tickers": json.loads(agent.tickers or "[]"),
                "reports_to_label": (await _lookup_agent_name(db, agent.manager_agent_id)) or "CEO",
                "schedule_label": agent.schedule_label,
                "last_run_at": agent.last_run_at.isoformat() if agent.last_run_at else None,
                "last_run_summary": agent.last_run_summary,
            }
            for agent in active_team
        ],
        "instructions": _ceo_instruction_docs(),
    }


@router.put("/cio/agent/status")
async def update_cio_agent_status(
    request: CioAgentStatusUpdateRequest,
):
    normalized_status = (request.status or "").strip().lower()
    if normalized_status not in {"idle", "paused"}:
        raise HTTPException(status_code=400, detail="Invalid CEO status")
    state = _save_ceo_runtime_state({"status": normalized_status})
    return state


@router.post("/cio/agent/heartbeat")
async def run_cio_agent_heartbeat(
    db: AsyncSession = Depends(get_db),
):
    runtime_state = _load_ceo_runtime_state()
    if runtime_state["status"] == "paused":
        raise HTTPException(status_code=409, detail="CEO is paused")

    task_result = await db.execute(
        select(
            ResearchTask,
            Project.title.label("project_title"),
            Project.thesis.label("project_thesis"),
        )
        .outerjoin(Project, ResearchTask.project_id == Project.id)
        .where(
            and_(
                _ceo_issue_scope_clause(),
                ResearchTask.status.in_(CEO_OPEN_TASK_STATUSES),
            )
        )
        .order_by(desc(ResearchTask.updated_at), desc(ResearchTask.created_at))
        .limit(50)
    )
    task_rows = task_result.all()

    if not task_rows:
        updated_state = _save_ceo_runtime_state(
            {
                "status": "idle",
                "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
                "last_heartbeat_message": "No open CEO issues to review.",
                "last_reviewed_task_id": None,
            }
        )
        return {
            "status": updated_state["status"],
            "message": updated_state["last_heartbeat_message"],
            "task_id": None,
            "task_title": None,
            "action": None,
            "reviewed_at": updated_state["last_heartbeat_at"],
        }

    sorted_rows = sorted(
        task_rows,
        key=lambda row: (
            CEO_PRIORITY_RANK.get(row[0].priority, 99),
            -datetime.fromisoformat(
                (row[0].updated_at or row[0].created_at).isoformat()
            ).timestamp(),
        ),
    )
    task, project_title, project_thesis = sorted_rows[0]

    prompt = _build_task_review_prompt(task, project_title, project_thesis)
    response = await _run_cio_response(
        db,
        [{"role": "user", "content": prompt}],
        proposed_by=f"issue:{task.id}",
        source_task_id=task.id,
    )

    reviewed_at = datetime.now(timezone.utc).isoformat()
    updated_state = _save_ceo_runtime_state(
        {
            "status": "idle",
            "last_heartbeat_at": reviewed_at,
            "last_heartbeat_message": response.message,
            "last_reviewed_task_id": task.id,
        }
    )

    return {
        "status": updated_state["status"],
        "message": response.message,
        "task_id": task.id,
        "task_title": task.title,
        "action": response.action.dict() if response.action else None,
        "reviewed_at": reviewed_at,
    }


@router.put("/cio/agent/instructions/{doc_key}")
async def update_cio_instruction_doc(
    doc_key: str,
    request: CioInstructionUpdateRequest,
):
    spec, path = _resolve_ceo_instruction_doc(doc_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.content, encoding="utf-8")
    except OSError:
        logger.exception("Failed to update CEO instruction doc: %s", path)
        raise HTTPException(status_code=500, detail="Failed to save CEO instruction doc")

    return {
        "key": doc_key,
        "filename": spec["filename"],
        "title": spec["title"],
        "content": _load_ceo_profile_doc(spec["filename"]),
    }


@router.post("/cio/review-task/{task_id}", response_model=CioTaskReviewResponse)
async def review_task_with_cio(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project_title: Optional[str] = None
    project_thesis: Optional[str] = None
    if task.project_id:
        project_result = await db.execute(
            select(Project.title, Project.thesis).where(Project.id == task.project_id)
        )
        project_row = project_result.one_or_none()
        if project_row is not None:
            project_title, project_thesis = project_row

    prompt = _build_task_review_prompt(task, project_title, project_thesis)
    response = await _run_cio_response(
        db,
        [{"role": "user", "content": prompt}],
        proposed_by=f"issue:{task.id}",
        source_task_id=task.id,
    )
    return CioTaskReviewResponse(task_id=task.id, message=response.message, action=response.action)


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
