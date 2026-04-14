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
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend.models import ScheduledAgent, AgentRun
from backend.scheduler import register_agent_job, next_run_time

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cio"])

_anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TEMPLATE_LABELS = {
    "earnings_watcher":    "Earnings Watcher",
    "market_pulse":        "Market Pulse",
    "thesis_guardian":     "Thesis Guardian",
    "portfolio_heartbeat": "Portfolio Heartbeat",
    "arena_analyst":       "Arena Analyst",
}

SCHEDULE_LABELS = {
    "daily_morning": "Daily at 7am",
    "pre_market":    "Weekdays at 6:30am",
    "weekly_monday": "Every Monday",
    "weekly_friday": "Every Friday",
    "monthly":       "Monthly",
}


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
            template_label = TEMPLATE_LABELS.get(a.template, a.template)
            ticker_str = ", ".join(tickers) if tickers else "no specific tickers"
            last_run = f"Last run: {a.last_run_at.strftime('%b %d') if a.last_run_at else 'never'}"
            summary = f"\n   Latest finding: {a.last_run_summary}" if a.last_run_summary else ""
            lines.append(
                f"- **{a.name}** [{template_label}] | {status} | Watches: {ticker_str} | {last_run}{summary}"
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
    return f"""You are the Chief Investment Officer (CIO) of Phronesis AI — a financial intelligence platform.

You are the investor's persistent, trusted advisor and team orchestrator. You are always their first stop. You have full visibility into their research team and recent findings.

## Your Capabilities

1. **ANSWER** — Respond directly. Use team context, your investment knowledge, and recent findings.
2. **DELEGATE** — When an existing agent should run now to answer the question, delegate to it.
3. **PROPOSE** — When no existing agent covers the need, propose hiring a new one.
4. **SURFACE** — When recent findings from a specific agent are directly relevant, surface them.

## Available Agent Templates (for PROPOSE action)
- `earnings_watcher` — Deep earnings analysis for specific tickers
- `market_pulse` — Daily macro & market conditions brief
- `thesis_guardian` — Monitors a specific investment thesis against market changes
- `portfolio_heartbeat` — Weekly health check across a set of holdings
- `arena_analyst` — Full investment committee debate (5 specialists) on a ticker

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
    "name": "Agent name",
    "description": "One sentence description",
    "template": "<template id>",
    "tickers": ["TICKER"],
    "topics": ["topic"],
    "instruction": "Detailed instruction for the agent. Be specific about what to watch, what thesis to monitor, what constitutes a material change.",
    "schedule_label": "weekly_monday"
  }}
}}

Rules:
- Only propose hiring if no existing agent covers the need. Don't duplicate.
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
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    tickers: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    instruction: Optional[str] = None
    schedule_label: Optional[str] = None


class CioChatResponse(BaseModel):
    message: str
    action: Optional[CioAction] = None


class HireFromCioRequest(BaseModel):
    action: CioAction
    delivery_inapp: bool = True
    delivery_email: Optional[str] = None


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
        response = _anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            system=system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        action_data = parsed.get("action")

        return CioChatResponse(
            message=parsed.get("message", ""),
            action=CioAction(**action_data) if action_data else None,
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
    db.add(run)
    await db.commit()

    run_id = run.id
    config_data = _agent_to_dict(agent)
    background_tasks.add_task(_execute_run_background, run_id, agent_id, config_data)

    return {"run_id": run_id, "status": "running", "agent_name": agent.name}


@router.post("/cio/hire", status_code=201)
async def cio_hire(
    request: HireFromCioRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent from a CIO proposal."""
    a = request.action
    now = datetime.now(timezone.utc)

    agent = ScheduledAgent(
        id=str(uuid.uuid4()),
        name=a.name or "New Agent",
        description=a.description,
        template=a.template or "thesis_guardian",
        tickers=json.dumps(a.tickers or []),
        topics=json.dumps(a.topics or []),
        instruction=a.instruction or "",
        schedule_label=a.schedule_label or "weekly_monday",
        delivery_email=request.delivery_email,
        delivery_inapp=request.delivery_inapp,
        is_active=True,
        next_run_at=next_run_time(a.schedule_label or "weekly_monday"),
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    register_agent_job(agent.id, agent.name, agent.schedule_label)

    return {
        "id": agent.id,
        "name": agent.name,
        "template": agent.template,
        "tickers": a.tickers or [],
        "schedule_label": agent.schedule_label,
        "created_at": agent.created_at.isoformat(),
    }
