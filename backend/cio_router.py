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
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from anthropic import Anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_issue_plans import role_specific_deliverable, role_specific_plan_steps
from backend.agent_roles import ROLE_CATALOG, infer_role_identity, resolve_role_definition, validate_role_key
from backend.config import CIO_MODEL
from backend.database import AsyncSessionLocal, get_db
from backend.heartbeat_service import create_heartbeat_run, ensure_agent_heartbeat_routine, spawn_background
from backend.models import ScheduledAgent, AgentRun, HireProposal, Project, ResearchTask
from backend.scheduler import register_agent_job, next_run_time, SUPPORTED_SCHEDULE_LABELS
from backend.scheduled_agent_config import (
    normalize_tickers,
    validate_template,
    validate_ticker_requirement,
)
from shared.ticker_utils import COMPANY_NAME_MAP, extract_ticker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cio"])

_anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
SCOPE_RESOLUTION_MODEL = "claude-haiku-4-5-20251001"
_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,5}(?:\.[A-Z]{1,2})?$")

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
THEME_SCOPE_CANDIDATES: dict[str, list[str]] = {
    "ai": ["NVDA", "PLTR", "AMZN", "MSFT", "GOOGL"],
    "artificial intelligence": ["NVDA", "PLTR", "AMZN", "MSFT", "GOOGL"],
    "llm": ["NVDA", "MSFT", "AMZN", "GOOGL", "META"],
    "gpu": ["NVDA", "AMD", "AVGO", "TSM"],
    "semiconductor": ["NVDA", "AMD", "AVGO", "TSM", "ASML"],
    "chip": ["NVDA", "AMD", "AVGO", "TSM", "ASML"],
    "software": ["MSFT", "CRM", "NOW", "ORCL", "ADBE"],
    "cloud": ["AMZN", "MSFT", "GOOGL", "ORCL", "CRM"],
    "cybersecurity": ["PANW", "CRWD", "ZS", "OKTA"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "oil": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "banks": ["JPM", "BAC", "WFC", "GS", "MS"],
    "financials": ["JPM", "BAC", "GS", "MS", "BLK"],
    "consumer": ["AMZN", "WMT", "COST", "NKE", "MCD"],
    "healthcare": ["JNJ", "UNH", "PFE", "MRK", "ABBV"],
}
ROLE_THEME_SCOPE_CANDIDATES: dict[str, dict[str, list[str]]] = {
    "semis_analyst": {
        "ai": ["NVDA", "AMD", "AVGO", "TSM", "ASML"],
        "artificial intelligence": ["NVDA", "AMD", "AVGO", "TSM", "ASML"],
        "semiconductor": ["NVDA", "AMD", "AVGO", "TSM", "ASML"],
        "chip": ["NVDA", "AMD", "AVGO", "TSM", "ASML"],
    },
    "software_analyst": {
        "ai": ["MSFT", "GOOGL", "AMZN", "META", "ORCL"],
        "software": ["MSFT", "CRM", "NOW", "ORCL", "ADBE"],
        "cloud": ["AMZN", "MSFT", "GOOGL", "ORCL", "CRM"],
    },
    "energy_analyst": {
        "energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "oil": ["XOM", "CVX", "COP", "SLB", "EOG"],
    },
    "financials_analyst": {
        "financials": ["JPM", "BAC", "GS", "MS", "BLK"],
        "banks": ["JPM", "BAC", "WFC", "GS", "MS"],
    },
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


def _task_needs_ceo_review(task: ResearchTask) -> bool:
    return bool(
        task.triggered_by == "manual_pm_review"
        or (task.owner_agent_id is None and task.assigned_agent_id is None)
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
                f"- **{display_name}** [id:{a.id}] | Reports to: {reports_to} | {status} | Watches: {ticker_str} | {last_run}{summary}"
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
        "A new issue has been filed and needs to be staffed. Review and act immediately.",
        f"Title: {task.title}",
        f"Ticker: {task.ticker or 'Not specified'}",
        f"Task type: {task.task_type}",
        f"Priority: {task.priority}",
        f"Project: {project_title or 'No project'}",
        f"Project thesis: {project_thesis or 'No project thesis'}",
        f"Description: {task.notes or 'No description provided.'}",
        f"Current staffing: {', '.join(selected_agents) if selected_agents else 'Unstaffed — needs an agent'}",
        "",
        "Your job is to staff this issue RIGHT NOW. Decision rules:",
        "1. If any active agent on your team can cover this issue, DELEGATE to them immediately. Use their exact [id:...] from the team list.",
        "2. Only propose a hire if NO active agent can cover this. Do not propose a hire if an existing agent can do it.",
        "3. Do NOT answer directly — this issue needs an agent to run research, not a chat response.",
    ]
    return "\n".join(lines)


def _strip_llm_json_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from an LLM response.

    Falls back to extracting the first {...} object if fences are absent,
    so callers get a clean JSON string regardless of LLM formatting quirks.
    """
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        # Remove opening fence line and optional closing fence
        cleaned = cleaned.strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        # Strip trailing fence if present
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned
    # No fences — try to isolate the first JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _cio_chat_sync(system_prompt: str, messages: list[dict]) -> dict:
    response = _anthropic.messages.create(
        model=CIO_MODEL,
        max_tokens=1200,
        system=system_prompt,
        messages=messages,
        timeout=60.0,
    )
    raw = _strip_llm_json_fences(response.content[0].text)
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


async def _append_issue_activity(
    db: AsyncSession,
    task_id: str,
    content: str,
    *,
    author_label: str = "System",
    author_agent_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    from backend.models import ResearchTaskMessage

    db.add(
        ResearchTaskMessage(
            task_id=task_id,
            kind="activity",
            role="system",
            author_label=author_label,
            author_agent_id=author_agent_id,
            content=content,
            metadata_json=json.dumps(metadata or {}),
        )
    )


async def _record_cio_review_message(
    db: AsyncSession,
    task_id: str,
    content: str,
    *,
    action: Optional[dict] = None,
) -> None:
    from backend.models import ResearchTaskMessage

    message = (content or "").strip()
    if not message:
        return
    db.add(
        ResearchTaskMessage(
            task_id=task_id,
            kind="chat",
            role="assistant",
            author_label="CEO",
            content=message,
            metadata_json=json.dumps({"action": action} if action else {}),
        )
    )


async def _record_issue_agent_message(
    db: AsyncSession,
    task_id: str,
    *,
    author_label: str,
    author_agent_id: Optional[str],
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    from backend.models import ResearchTaskMessage

    message = (content or "").strip()
    if not message:
        return
    db.add(
        ResearchTaskMessage(
            task_id=task_id,
            kind="chat",
            role="assistant",
            author_label=author_label,
            author_agent_id=author_agent_id,
            content=message,
            metadata_json=json.dumps(metadata or {}),
        )
    )


async def _upsert_issue_document(
    db: AsyncSession,
    *,
    task_id: str,
    title: str,
    document_type: str,
    content_md: str,
    created_by_agent_id: Optional[str],
    status: str = "draft",
):
    from backend.models import ResearchTaskDocument

    result = await db.execute(
        select(ResearchTaskDocument).where(
            ResearchTaskDocument.task_id == task_id,
            ResearchTaskDocument.title == title,
            ResearchTaskDocument.document_type == document_type,
        )
    )
    document = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if document is None:
        document = ResearchTaskDocument(
            task_id=task_id,
            title=title,
            document_type=document_type,
            status=status,
            content_md=content_md,
            created_by_agent_id=created_by_agent_id,
            created_at=now,
            updated_at=now,
        )
        db.add(document)
        await db.flush()
        return document, True

    changed = False
    if document.content_md != content_md:
        document.content_md = content_md
        changed = True
    if document.status != status:
        document.status = status
        changed = True
    if document.created_by_agent_id != created_by_agent_id:
        document.created_by_agent_id = created_by_agent_id
        changed = True
    if changed:
        document.revision += 1
        document.updated_at = now
    return document, False


def _issue_plan_steps_for_agent(
    task: ResearchTask,
    agent: ScheduledAgent,
    *,
    resolved_tickers: list[str] | None = None,
) -> list[str]:
    template = agent.template
    role_key = (agent.role_key or "").strip()
    scope_reference = _resolved_scope_label(task, resolved_tickers)
    role_steps = role_specific_plan_steps(role_key, scope_reference)
    if role_steps is not None:
        return role_steps
    if template == "risk_analyst":
        return [
            f"Map the main downside scenarios and risk concentrations around {scope_reference}.",
            "Stress the thesis against liquidity, leverage, and drawdown risk.",
            "Flag the catalysts that could break the setup and what needs escalation.",
            "Write a risk note with the key failure modes and monitoring points.",
        ]
    if template in {"macro_analyst", "market_pulse"}:
        return [
            f"Frame the macro and market context that matters for {scope_reference}.",
            "Check rates, inflation, policy, and sector-rotation implications.",
            "Separate broad market noise from the drivers that should change the thesis.",
            "Write a macro brief with the implications for this issue and next watchpoints.",
        ]
    if template == "quant_analyst":
        return [
            f"Build the right factor and signal lens for {scope_reference}.",
            "Check momentum, revisions, relative performance, and supporting quant evidence.",
            "Highlight where the data confirms or conflicts with the working thesis.",
            "Write a quant note with the strongest supporting and contradicting signals.",
        ]
    return [
        "Clarify the exact research question and what a useful answer needs to contain.",
        f"Gather the relevant company, industry, and financial context for {scope_reference}.",
        "Review business quality, growth, margins, balance sheet, valuation, and key risks.",
        "Separate primary findings from open questions and missing evidence.",
        "Write a concise analyst output with the current take, supporting facts, and next actions.",
    ]


def _normalize_scope_tickers(values: list[str] | None, *, limit: int = 5) -> list[str]:
    cleaned = normalize_tickers(values or [])
    deduped: list[str] = []
    seen: set[str] = set()
    for ticker in cleaned:
        normalized = str(ticker or "").strip().upper()
        if not normalized or normalized == "GENERAL" or not _TICKER_PATTERN.fullmatch(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if len(deduped) >= limit:
            break
    return deduped


def _agent_coverage_tickers(agent: ScheduledAgent) -> list[str]:
    try:
        coverage = json.loads(agent.tickers or "[]")
    except Exception:
        coverage = []
    return _normalize_scope_tickers(coverage, limit=8)


def _mentioned_company_tickers(*parts: Any) -> list[str]:
    matches: list[str] = []
    for raw_part in parts:
        text = str(raw_part or "").strip()
        if not text:
            continue
        query_lower = text.lower()
        for company_name, ticker in COMPANY_NAME_MAP.items():
            if re.search(r"\b" + re.escape(company_name) + r"\b", query_lower):
                matches.append(ticker)
        inferred = extract_ticker(text)
        if inferred:
            matches.append(inferred)
    return _normalize_scope_tickers(matches)


def _looks_like_broad_scope_request(task: ResearchTask) -> bool:
    text = " ".join(
        part.strip().lower()
        for part in [task.title or "", task.notes or ""]
        if part and part.strip()
    )
    broad_markers = (
        "industry",
        "sector",
        "theme",
        "trend",
        "wave",
        "ecosystem",
        "value chain",
        "benefit",
        "beneficiaries",
        "players",
        "companies",
        "who wins",
        "who benefits",
        "around ai",
    )
    return any(marker in text for marker in broad_markers)


def _keyword_scope_candidates(task: ResearchTask, agent: ScheduledAgent) -> list[str]:
    text = " ".join(
        part.strip().lower()
        for part in [task.title or "", task.notes or ""]
        if part and part.strip()
    )
    if not text:
        return []

    role_candidates = ROLE_THEME_SCOPE_CANDIDATES.get(agent.role_key or "", {})
    matches: list[str] = []
    for keyword, tickers in role_candidates.items():
        if keyword in text:
            matches.extend(tickers)
    for keyword, tickers in THEME_SCOPE_CANDIDATES.items():
        if keyword in text:
            matches.extend(tickers)
    return _normalize_scope_tickers(matches)


def _scope_json_object(text: str) -> Optional[dict[str, Any]]:
    cleaned = _strip_llm_json_fences(text)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _resolve_scope_with_llm_sync(task: ResearchTask, agent: ScheduledAgent) -> dict[str, Any]:
    role_title = agent.role_title or agent.name
    coverage = ", ".join(_agent_coverage_tickers(agent)) or "Broad / general coverage"
    prompt = f"""You are helping a finance research agent determine which public companies to analyze.

Choose 1 to 5 PUBLIC company tickers that best match the issue below.
- Prefer directly mentioned companies.
- If the issue is about an industry, sector, or theme, pick the most relevant public beneficiaries.
- Bias toward the assigned analyst seat when helpful, but do not force irrelevant names.
- Return tickers only, not company names.
- If the issue is too vague to determine any public companies, return an empty list.

Return valid JSON only:
{{
  "tickers": ["AAPL", "MSFT"],
  "rationale": "one short sentence"
}}

Issue title: {task.title}
Issue notes: {task.notes or "No additional notes"}
Assigned role: {role_title}
Role template: {agent.template}
Coverage universe: {coverage}
"""
    response = _anthropic.messages.create(
        model=SCOPE_RESOLUTION_MODEL,
        max_tokens=220,
        messages=[{"role": "user", "content": prompt}],
        timeout=30.0,
    )
    text = response.content[0].text.strip()
    parsed = _scope_json_object(text) or {}
    raw_tickers = parsed.get("tickers") if isinstance(parsed.get("tickers"), list) else []
    normalized = _normalize_scope_tickers([str(value) for value in raw_tickers], limit=5)
    return {
        "tickers": normalized,
        "rationale": str(parsed.get("rationale") or "").strip(),
        "source": "llm",
    }


async def _resolve_task_scope_for_agent(task: ResearchTask, agent: ScheduledAgent) -> dict[str, Any]:
    explicit_ticker = (task.ticker or "").strip().upper()
    if explicit_ticker and explicit_ticker != "GENERAL":
        return {"tickers": [explicit_ticker], "source": "task_ticker", "rationale": ""}

    company_matches = _mentioned_company_tickers(task.title, task.notes)
    if company_matches:
        return {"tickers": company_matches, "source": "issue_text", "rationale": ""}

    heuristic_matches = _keyword_scope_candidates(task, agent)
    llm_matches: list[str] = []
    llm_rationale = ""
    if _agent_requires_explicit_scope(agent):
        try:
            llm_resolution = await run_in_threadpool(_resolve_scope_with_llm_sync, task, agent)
            llm_matches = _normalize_scope_tickers(llm_resolution.get("tickers") or [], limit=5)
            llm_rationale = str(llm_resolution.get("rationale") or "").strip()
        except Exception as exc:
            logger.warning("Scope resolution LLM failed for task %s: %s", task.id, exc)

    if llm_matches:
        return {"tickers": llm_matches, "source": "llm", "rationale": llm_rationale}
    if heuristic_matches:
        return {"tickers": heuristic_matches, "source": "theme_map", "rationale": ""}

    coverage = _agent_coverage_tickers(agent)
    if coverage and _looks_like_broad_scope_request(task):
        return {
            "tickers": coverage[: min(len(coverage), 4)],
            "source": "coverage_fallback",
            "rationale": "",
        }

    return {"tickers": [], "source": "unresolved", "rationale": ""}


def _resolved_scope_label(task: ResearchTask, resolved_tickers: list[str] | None = None) -> str:
    normalized = _normalize_scope_tickers(resolved_tickers or [], limit=5)
    if normalized:
        if len(normalized) == 1:
            return normalized[0]
        return ", ".join(normalized)
    return _issue_scope_label(task)


def _issue_scope_label(task: ResearchTask) -> str:
    ticker = (task.ticker or "").strip()
    if ticker and ticker.upper() != "GENERAL":
        return ticker
    source = " ".join(part.strip() for part in [task.title or "", task.notes or ""] if part and part.strip())
    inferred = extract_ticker(source)
    if inferred:
        return inferred.strip().upper()
    return "Not explicitly specified"


def _issue_scope_reference(task: ResearchTask) -> str:
    ticker = (task.ticker or "").strip()
    if ticker and ticker.upper() != "GENERAL":
        return ticker
    source = " ".join(part.strip() for part in [task.title or "", task.notes or ""] if part and part.strip())
    inferred = extract_ticker(source)
    if inferred:
        return inferred.strip().upper()
    return "the assigned company or scope"


def _coverage_universe_label(agent: ScheduledAgent) -> str:
    try:
        coverage = json.loads(agent.tickers or "[]") or []
    except Exception:
        coverage = []
    cleaned = [value for value in coverage if value and str(value).upper() != "GENERAL"]
    return ", ".join(cleaned) if cleaned else "Broad / general coverage"


def _task_has_explicit_scope(task: ResearchTask) -> bool:
    ticker = (task.ticker or "").strip()
    return bool(ticker and ticker.upper() != "GENERAL")


def _agent_requires_explicit_scope(agent: ScheduledAgent) -> bool:
    role = resolve_role_definition(role_key=agent.role_key, template=agent.template)
    if role is not None:
        return role.requires_tickers
    return agent.template != "market_pulse"


def _issue_objective(task: ResearchTask) -> str:
    if (task.notes or "").strip():
        return (task.notes or "").strip()
    return task.title


def _issue_deliverable_for_agent(agent: ScheduledAgent) -> str:
    template = agent.template
    role_key = (agent.role_key or "").strip()
    deliverable = role_specific_deliverable(role_key)
    if deliverable is not None:
        return deliverable
    if template == "risk_analyst":
        return "Risk note with downside scenarios, break conditions, and monitoring points."
    if template in {"macro_analyst", "market_pulse"}:
        return "Macro brief with the few market drivers that should change the issue view."
    if template == "quant_analyst":
        return "Quant note with the strongest confirming and contradicting signals."
    return "Structured analyst brief with the current view, supporting evidence, risks, and next actions."


def _render_issue_plan_chat_summary(
    task: ResearchTask,
    agent: ScheduledAgent,
    plan_title: str,
    *,
    resolved_tickers: list[str] | None = None,
) -> str:
    steps = _issue_plan_steps_for_agent(task, agent, resolved_tickers=resolved_tickers)[:3]
    step_block = "\n".join(f"- {step}" for step in steps)
    resolved_scope = _resolved_scope_label(task, resolved_tickers)
    return (
        "I've started the first pass on this issue.\n\n"
        f"**Objective**\n"
        f"{_issue_objective(task)}\n\n"
        f"**Working scope**\n"
        f"{resolved_scope}\n\n"
        f"**Plan**\n"
        f"{step_block}\n\n"
        f"**Expected output**\n"
        f"{_issue_deliverable_for_agent(agent)}\n\n"
        f"**Saved**\n"
        f"- **{plan_title}**\n"
        f"- Open the **Documents** tab to review the full plan."
    )


def _render_issue_plan_document(
    task: ResearchTask,
    agent: ScheduledAgent,
    *,
    resolved_tickers: list[str] | None = None,
) -> str:
    role_title = agent.role_title or agent.name
    coverage = _coverage_universe_label(agent)
    steps = _issue_plan_steps_for_agent(task, agent, resolved_tickers=resolved_tickers)
    bullet_block = "\n".join(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))
    resolved_scope = _resolved_scope_label(task, resolved_tickers)
    return (
        f"# {role_title} execution plan\n\n"
        f"## Objective\n"
        f"{_issue_objective(task)}\n\n"
        f"## Issue metadata\n"
        f"- Title: {task.title}\n"
        f"- Ticker / scope: {resolved_scope}\n"
        f"- Type: {task.task_type}\n"
        f"- Priority: {task.priority}\n"
        f"- Agent: {role_title}\n"
        f"- Coverage universe: {coverage}\n\n"
        f"## Assigned coverage\n"
        f"- Analyst lens: {role_title}\n"
        f"- Expected deliverable: {_issue_deliverable_for_agent(agent)}\n\n"
        f"## Planned approach\n"
        f"{bullet_block}\n"
    )


async def _run_cio_task_review(
    db: AsyncSession,
    task: ResearchTask,
    *,
    project_title: Optional[str] = None,
    project_thesis: Optional[str] = None,
) -> CioChatResponse:
    if project_title is None and task.project_id:
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
    now = datetime.now(timezone.utc)
    await _record_cio_review_message(
        db,
        task.id,
        response.message,
        action=response.action.model_dump() if response.action else None,
    )
    normalized_message = (response.message or "").lower()
    requires_follow_up = any(
        marker in normalized_message
        for marker in (
            "delegation was skipped",
            "could not be found",
            "issue no longer exists, so delegation was skipped",
            "is paused, so delegation was skipped",
        )
    )
    if response.action and response.action.type == "propose_hire":
        task.status = "in_review"
        task.error = None
        task.updated_at = now
        await _append_issue_activity(
            db,
            task.id,
            f"CEO proposed hiring {response.action.role_title or response.action.name or 'a new role'}.",
            author_label="CEO",
            metadata={"event": "ceo_hire_proposed", "action": response.action.model_dump()},
        )
    elif requires_follow_up:
        task.status = "in_review"
        task.error = "CEO review needs follow-up before this issue can be executed."
        task.completed_at = None
        task.updated_at = now
        await _append_issue_activity(
            db,
            task.id,
            "CEO review could not start execution and the issue needs follow-up.",
            author_label="CEO",
            metadata={"event": "ceo_review_follow_up_required"},
        )
    elif response.action is None and task.status in CEO_OPEN_TASK_STATUSES:
        # Don't close a task that already has an active run in flight.
        if task.run_id:
            await _append_issue_activity(
                db,
                task.id,
                "CEO reviewed this issue directly but left it open — an agent run is already in progress.",
                author_label="CEO",
                metadata={"event": "ceo_review_deferred_active_run", "run_id": task.run_id},
            )
        else:
            task.status = "done"
            task.error = None
            task.completed_at = task.completed_at or now
            task.updated_at = now
            await _append_issue_activity(
                db,
                task.id,
                "CEO reviewed this issue directly and closed it with a final answer.",
                author_label="CEO",
                metadata={"event": "ceo_review_completed"},
            )
    return response


async def _auto_review_task_with_cio(task_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    ResearchTask,
                    Project.title.label("project_title"),
                    Project.thesis.label("project_thesis"),
                )
                .outerjoin(Project, ResearchTask.project_id == Project.id)
                .where(ResearchTask.id == task_id)
            )
            row = result.one_or_none()
            if row is None:
                return

            task, project_title, project_thesis = row
            if not _task_needs_ceo_review(task):
                return
            if task.status not in CEO_OPEN_TASK_STATUSES:
                return

            await _run_cio_task_review(
                db,
                task,
                project_title=project_title,
                project_thesis=project_thesis,
            )
            await db.commit()
    except Exception as exc:
        logger.exception("Automatic CEO review failed for task %s", task_id)
        async with AsyncSessionLocal() as db:
            task = await db.get(ResearchTask, task_id)
            if task is None:
                return
            task.status = "in_review"
            task.error = (
                "CEO routing failed before the issue could be assigned. "
                "Review the issue and retry dispatch."
            )
            task.updated_at = datetime.now(timezone.utc)
            await _record_issue_agent_message(
                db,
                task_id,
                author_label="CEO",
                author_agent_id=None,
                content=(
                    "I could not complete routing for this issue, so it has been moved to review. "
                    "Retry the CEO review or assign the right analyst directly."
                ),
                metadata={
                    "event": "ceo_review_failed",
                    "error": str(exc),
                },
            )
            await _append_issue_activity(
                db,
                task_id,
                "CEO review failed before assignment. Manual review is required.",
                author_label="System",
                metadata={
                    "event": "ceo_review_failed",
                    "error": str(exc),
                },
            )
            await db.commit()


def queue_cio_review_for_task(task_id: str) -> None:
    spawn_background(_auto_review_task_with_cio(task_id))


async def _dispatch_agent_for_task(
    db: AsyncSession,
    task: ResearchTask,
    agent: ScheduledAgent,
    *,
    trigger_type: str,
    initiated_by: str,
    note: Optional[str] = None,
) -> dict:
    from backend.scheduled_agents_router import _agent_to_dict, _execute_run_background

    if not agent.is_active:
        raise HTTPException(status_code=409, detail=f"{agent.role_title or agent.name} is paused")

    if task.status == "cancelled":
        return {"run_id": None, "reused": False, "skipped": True}

    scope_resolution = await _resolve_task_scope_for_agent(task, agent)

    # Re-read the task after the (potentially slow) LLM scope resolution to
    # catch concurrent updates — another request may have already claimed it
    # or cancelled it while we were waiting.
    await db.refresh(task)
    if task.status == "cancelled":
        return {"run_id": None, "reused": False, "skipped": True}
    if task.run_id:
        # Another dispatch beat us to it; bail out to avoid a duplicate run.
        return {"run_id": task.run_id, "reused": True, "skipped": False}

    resolved_tickers = _normalize_scope_tickers(scope_resolution.get("tickers") or [], limit=5)

    if _agent_requires_explicit_scope(agent) and not resolved_tickers:
        role_title = agent.role_title or agent.name
        reason = (
            f"{role_title} needs an explicit ticker or company scope before it can start. "
            "Add a concrete company, ticker, or a clearer industry/theme so the analyst can resolve the right names."
        )
        task.assigned_agent_id = agent.id
        task.status = "in_review"
        task.run_id = None
        task.error = reason
        task.updated_at = datetime.now(timezone.utc)
        await _record_issue_agent_message(
            db,
            task.id,
            author_label=role_title,
            author_agent_id=agent.id,
            content=reason,
            metadata={
                "event": "issue_scope_required",
                "scope_source": scope_resolution.get("source"),
            },
        )
        await _append_issue_activity(
            db,
            task.id,
            reason,
            author_label=role_title,
            author_agent_id=agent.id,
            metadata={
                "event": "issue_scope_required",
                "agent_id": agent.id,
                "status": "in_review",
                "scope_source": scope_resolution.get("source"),
            },
        )
        await db.commit()
        return {"run_id": None, "reused": False, "skipped": True, "reason": "scope_required"}

    existing_run = None
    if task.run_id:
        existing_run_result = await db.execute(select(AgentRun).where(AgentRun.id == task.run_id))
        existing_run = existing_run_result.scalar_one_or_none()
    if (
        existing_run is not None
        and existing_run.status == "running"
        and existing_run.scheduled_agent_id == agent.id
    ):
        task.assigned_agent_id = agent.id
        task.updated_at = datetime.now(timezone.utc)
        await _append_issue_activity(
            db,
            task.id,
            f"{initiated_by} kept {agent.role_title or agent.name} on the active issue run.",
            author_label=initiated_by,
            metadata={"event": "issue_run_reused", "agent_id": agent.id, "run_id": existing_run.id},
        )
        await db.commit()
        return {"run_id": existing_run.id, "reused": True, "skipped": False}

    active_run_result = await db.execute(
        select(AgentRun)
        .where(
            AgentRun.scheduled_agent_id == agent.id,
            AgentRun.status == "running",
        )
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    active_run = active_run_result.scalar_one_or_none()
    if active_run is not None:
        role_title = agent.role_title or agent.name
        task.assigned_agent_id = agent.id
        task.run_id = None
        task.status = "pending"
        task.error = (
            f"{role_title} is already working another issue. "
            "This issue stays queued until the active run finishes."
        )
        task.updated_at = datetime.now(timezone.utc)
        await _append_issue_activity(
            db,
            task.id,
            f"{initiated_by} tried to start {role_title}, but the agent already has an active run. "
            "This issue remains queued.",
            author_label=initiated_by,
            author_agent_id=agent.id,
            metadata={
                "event": "issue_agent_busy",
                "agent_id": agent.id,
                "active_run_id": active_run.id,
            },
        )
        await db.commit()
        return {
            "run_id": active_run.id,
            "reused": False,
            "skipped": True,
            "reason": "agent_busy",
        }

    now = datetime.now(timezone.utc)
    await ensure_agent_heartbeat_routine(db, agent)
    run = AgentRun(
        id=str(uuid.uuid4()),
        scheduled_agent_id=agent.id,
        status="running",
        started_at=now,
    )
    db.add(run)
    await db.flush()
    heartbeat_run = await create_heartbeat_run(
        db,
        agent,
        trigger_type=trigger_type,
        agent_run_id=run.id,
        started_at=now,
    )

    task.assigned_agent_id = agent.id
    task.run_id = run.id
    task.status = "running"
    task.started_at = task.started_at or now
    task.updated_at = now
    task.error = None
    role_title = agent.role_title or agent.name
    plan_title = f"{role_title} execution plan"
    plan_content = _render_issue_plan_document(task, agent, resolved_tickers=resolved_tickers)
    plan_steps = _issue_plan_steps_for_agent(task, agent)[:5]
    plan_document, created_plan = await _upsert_issue_document(
        db,
        task_id=task.id,
        title=plan_title,
        document_type="plan",
        content_md=plan_content,
        created_by_agent_id=agent.id,
        status="published",
    )
    await _record_issue_agent_message(
        db,
        task.id,
        author_label=role_title,
        author_agent_id=agent.id,
        content=_render_issue_plan_chat_summary(task, agent, plan_title, resolved_tickers=resolved_tickers),
        metadata={
            "event": "issue_plan_created",
            "run_id": run.id,
            "document_id": plan_document.id,
            "document_title": plan_title,
            "document_type": "plan",
            "objective": _issue_objective(task),
            "scope": _resolved_scope_label(task, resolved_tickers),
            "resolved_tickers": resolved_tickers,
            "steps": plan_steps,
            "deliverable": _issue_deliverable_for_agent(agent),
        },
    )

    activity_message = f"{initiated_by} dispatched {agent.role_title or agent.name} to work on this issue."
    if note:
        activity_message = f"{activity_message} {note}"
    await _append_issue_activity(
        db,
        task.id,
        activity_message,
        author_label=initiated_by,
        author_agent_id=agent.id,
        metadata={
            "event": "issue_run_started",
            "agent_id": agent.id,
            "run_id": run.id,
            "plan_document_title": plan_title,
            "plan_document_created": created_plan,
            "resolved_tickers": resolved_tickers,
            "scope_source": scope_resolution.get("source"),
        },
    )

    config_data = _agent_to_dict(agent)
    runtime_scope = _resolved_scope_label(task, resolved_tickers)
    issue_specific_instruction = "\n\n".join(
        part
        for part in [
            (agent.instruction or "").strip(),
            "CURRENT ISSUE",
            f"Title: {task.title}",
            f"Objective: {_issue_objective(task)}",
            f"Resolved scope: {runtime_scope}",
            (
                "Analyze the listed companies as the working scope for this issue. "
                "If multiple companies are in scope, compare them and highlight the most relevant winners, risks, "
                "and differences for the user's request."
                if len(resolved_tickers) > 1
                else "Treat the resolved company scope above as the active name you must analyze for this issue."
            ),
            f"Required deliverable: {_issue_deliverable_for_agent(agent)}",
            "This is an issue-specific run. Do not produce a generic standing brief; answer the issue directly.",
        ]
        if part
    )
    config_data["instruction"] = issue_specific_instruction
    if resolved_tickers:
        config_data["tickers"] = resolved_tickers
    await db.commit()

    spawn_background(
        _execute_run_background(
            run.id,
            agent.id,
            config_data,
            heartbeat_run.id,
            trigger_type,
            task.id,
        )
    )
    return {"run_id": run.id, "reused": False, "skipped": False}


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

    if proposal.source_task_id:
        task_result = await db.execute(select(ResearchTask).where(ResearchTask.id == proposal.source_task_id))
        source_task = task_result.scalar_one_or_none()
        if source_task is not None and source_task.status not in {"done", "cancelled"}:
            await _dispatch_agent_for_task(
                db,
                source_task,
                agent,
                trigger_type="delegated",
                initiated_by="CEO",
                note="Approved hire attached to the source issue.",
            )
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
        elif action and action.type == "delegate" and source_task_id and action.agent_id:
            task_result = await db.execute(select(ResearchTask).where(ResearchTask.id == source_task_id))
            task = task_result.scalar_one_or_none()
            agent_result = await db.execute(select(ScheduledAgent).where(ScheduledAgent.id == action.agent_id))
            agent = agent_result.scalar_one_or_none()
            if task is None:
                message = f"{message}\n\nThe issue no longer exists, so delegation was skipped."
                action = None
            elif agent is None:
                message = f"{message}\n\nThe selected agent could not be found."
                action = None
            elif not agent.is_active:
                message = f"{message}\n\n{agent.role_title or agent.name} is paused, so delegation was skipped."
                action = None
            else:
                await _dispatch_agent_for_task(
                    db,
                    task,
                    agent,
                    trigger_type="delegated",
                    initiated_by="CEO",
                    note=action.reason,
                )

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

    response = await _run_cio_task_review(
        db,
        task,
        project_title=project_title,
        project_thesis=project_thesis,
    )
    await db.commit()

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
        "action": response.action.model_dump() if response.action else None,
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

    response = await _run_cio_task_review(db, task)
    await db.commit()
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
