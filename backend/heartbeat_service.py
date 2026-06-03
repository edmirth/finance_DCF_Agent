"""
Heartbeat service helpers.

This module layers a first-class routine and wake-up log on top of the
existing scheduled-agent system without breaking current routes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
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
    ResearchTaskDocument,
    ResearchTaskMessage,
    ScheduledAgent,
)
from shared.ticker_utils import extract_ticker

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


def _issue_output_title(task: ResearchTask, agent: ScheduledAgent | None, outcome: dict | None = None) -> str:
    role_title = agent.role_title if agent and agent.role_title else (agent.name if agent else "Agent")
    resolved_scope = [
        str(value).strip().upper()
        for value in ((outcome or {}).get("tickers_analyzed") or [])
        if str(value).strip() and str(value).strip().upper() != "GENERAL"
    ]
    scope_label = ", ".join(resolved_scope) if resolved_scope else _issue_scope_label(task)
    if "analyst" in role_title.lower():
        if scope_label != "Not explicitly specified":
            return f"{scope_label} Equity Research Report"
        return f"{role_title} Research Report"
    return f"{role_title} output"


def _derived_issue_scope(task: ResearchTask) -> str | None:
    source = " ".join(part.strip() for part in [task.title or "", task.notes or ""] if part and part.strip())
    inferred = extract_ticker(source)
    return inferred.strip().upper() if inferred else None


def _issue_scope_label(task: ResearchTask) -> str:
    ticker = (task.ticker or "").strip()
    if ticker and ticker.upper() != "GENERAL":
        return ticker
    inferred = _derived_issue_scope(task)
    if inferred:
        return inferred
    return "Not explicitly specified"


def _strip_duplicate_heading_line(report: str, scope_label: str) -> str:
    lines = [line.rstrip() for line in (report or "").strip().splitlines()]
    if len(lines) >= 2 and lines[0].strip().upper() == scope_label.upper():
        second = lines[1].strip()
        if second.startswith("#") or scope_label.upper() in second.upper():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _extract_report_summary(report: str) -> str:
    lines = [line.strip() for line in (report or "").splitlines()]
    for line in lines:
        if not line or line.startswith("#") or line.startswith("- ") or re.match(r"^\d+[.)]\s+", line):
            continue
        if len(line) >= 30:
            return line
    compact = re.sub(r"\s+", " ", (report or "").strip())
    for sentence in re.split(r"(?<=[.!?])\s+", compact):
        sentence = sentence.strip()
        if len(sentence) >= 30:
            return sentence
    return ""


def _extract_report_key_findings(report: str) -> list[str]:
    findings: list[str] = []
    lines = [line.strip() for line in (report or "").splitlines()]
    for line in lines:
        if line.startswith(("- ", "* ", "• ")):
            findings.append(line[2:].strip())
        elif re.match(r"^\d+[.)]\s+", line):
            findings.append(re.sub(r"^\d+[.)]\s+", "", line).strip())
        if len(findings) >= 5:
            break
    if findings:
        return findings

    compact = re.sub(r"\s+", " ", (report or "").strip())
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", compact) if len(sentence.strip()) >= 35]
    return sentences[:4]


def _extract_report_suggestions(report: str) -> list[str]:
    if not report:
        return []
    match = re.search(
        r"(?:^|\n)##\s*(?:Agent Suggestions|Next Steps|Action Items|Risks And Watch Items)\s*\n(?P<body>.*?)(?=\n##\s+|\Z)",
        report,
        flags=re.IGNORECASE | re.DOTALL,
    )
    source = match.group("body") if match else report
    suggestions: list[str] = []
    for line in source.splitlines():
        item = line.strip()
        if item.startswith(("- ", "* ", "• ")):
            suggestions.append(item[2:].strip())
        elif re.match(r"^\d+[.)]\s+", item):
            suggestions.append(re.sub(r"^\d+[.)]\s+", "", item).strip())
        if len(suggestions) >= 5:
            break
    if suggestions:
        return suggestions
    compact = re.sub(r"\s+", " ", source)
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", compact)
        if len(sentence.strip()) >= 35 and any(word in sentence.lower() for word in ["watch", "track", "compare", "review", "stress", "monitor", "next"])
    ][:4]


def _normalize_report_markdown(report: str) -> str:
    cleaned_lines: list[str] = []
    skip_internal_block = False
    for raw_line in (report or "").splitlines():
        line = raw_line.strip()
        if not line:
            skip_internal_block = False
            cleaned_lines.append("")
            continue
        upper = line.upper()
        if re.match(r"^(CURRENT ISSUE|ASSIGNMENT|USER REQUEST|ISSUE METADATA|TASK METADATA):?\s*$", upper):
            skip_internal_block = True
            continue
        if skip_internal_block and re.match(r"^(TITLE|OBJECTIVE|TASK TYPE|PRIORITY|RESOLVED SCOPE|REQUIRED DELIVERABLE):\s+", upper):
            continue
        if re.match(r"^(TASK TYPE|PRIORITY):\s+", upper):
            continue
        heading_match = re.match(r"^([A-Z][A-Z /&()\-]{4,}):\s*$", line)
        inline_label_match = re.match(r"^([A-Z][A-Z /&()\-]{2,}):\s+(.+)$", line)
        if heading_match:
            cleaned_lines.append(f"### {heading_match.group(1).title()}")
            continue
        if " — " in line and line.upper() == line and len(line) <= 100:
            cleaned_lines.append(f"## {line.title()}")
            continue
        if inline_label_match:
            label = inline_label_match.group(1).title()
            cleaned_lines.append(f"**{label}:** {inline_label_match.group(2).strip()}")
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _issue_output_content(task: ResearchTask, agent: ScheduledAgent | None, outcome: dict) -> str:
    role_title = agent.role_title if agent and agent.role_title else (agent.name if agent else "Agent")
    resolved_scope = [
        str(value).strip().upper()
        for value in (outcome.get("tickers_analyzed") or [])
        if str(value).strip() and str(value).strip().upper() != "GENERAL"
    ]
    scope_label = ", ".join(resolved_scope) if resolved_scope else _issue_scope_label(task)
    if "analyst" in role_title.lower():
        report_heading = (
            f"{scope_label} Equity Research Report"
            if scope_label != "Not explicitly specified"
            else f"{task.title} Equity Research Report"
        )
    else:
        report_heading = f"{role_title} output"
    _raw_report_val = outcome.get("report") or ""
    raw_report = ("\n\n".join(str(v) for v in _raw_report_val) if isinstance(_raw_report_val, list) else str(_raw_report_val)).strip()
    report = _normalize_report_markdown(_strip_duplicate_heading_line(raw_report, scope_label))
    _raw_summary_val = outcome.get("findings_summary") or ""
    summary = (("\n".join(str(v) for v in _raw_summary_val) if isinstance(_raw_summary_val, list) else str(_raw_summary_val))).strip()
    if not summary or summary == "Research completed. See full report for details.":
        summary = _extract_report_summary(report)
    key_findings = [str(item).strip() for item in (outcome.get("key_findings") or []) if str(item).strip()]
    if not key_findings:
        key_findings = _extract_report_key_findings(report)
    key_findings_block = "\n".join(f"- {item}" for item in key_findings if item) or "- None recorded"
    suggestions = _extract_report_suggestions(report)
    suggestions_block = "\n".join(f"- {item}" for item in suggestions if item)
    parts = [
        f"# {report_heading}",
        "",
        "## Snapshot",
        f"- Scope: {scope_label}",
        f"- Analyst: {role_title}",
        "",
        "## Executive summary",
        summary or "No summary was saved for this run.",
        "",
        "## Key findings",
        key_findings_block,
    ]
    if suggestions_block:
        parts.extend(["", "## Agent suggestions", suggestions_block])
    if report:
        parts.extend(["", "## Detailed analysis", report])
    elif outcome.get("error"):
        parts.extend(["", "## Run failure", str(outcome.get("error"))])
    return "\n".join(parts).strip() + "\n"


def _render_issue_output_chat_summary(
    *,
    document_title: str,
    outcome: dict,
) -> str:
    if outcome.get("error"):
        return (
            "The run finished, but it failed before a clean analyst output was produced.\n\n"
            f"**What failed**\n"
            f"{outcome.get('error')}\n\n"
            f"**Saved**\n"
            f"- **{document_title}**\n"
            f"- Failure details captured for review\n\n"
            "Open the **Documents** tab for the saved failure output."
        )

    _fs = outcome.get("findings_summary") or ""
    summary = (("\n".join(str(v) for v in _fs) if isinstance(_fs, list) else str(_fs))).strip() or (
        "I completed the first pass and saved the issue output."
    )
    key_findings = [str(item).strip() for item in (outcome.get("key_findings") or []) if str(item).strip()]
    findings_block = "\n".join(f"- {item}" for item in key_findings[:3])
    parts = [
        "I finished the first pass on this issue.",
        "",
        "**Bottom line**",
        summary,
    ]
    if findings_block:
        parts.extend(["", "**Top findings**", findings_block])
    parts.extend(
        [
            "",
            "**Saved**",
            f"- **{document_title}**",
            "- Ready for review",
            "",
            "Open the **Documents** tab for the full output.",
        ]
    )
    return "\n".join(parts)


def _issue_failure_next_action(task: ResearchTask, role_title: str) -> str:
    scope = _issue_scope_label(task)
    return (
        f"Check the latest {role_title} run for missing data or provider errors, then rerun the issue"
        f"{'' if scope == 'Not explicitly specified' else f' for {scope}'}."
    )


async def _upsert_task_output_document(
    db: AsyncSession,
    task: ResearchTask,
    agent: ScheduledAgent | None,
    outcome: dict,
) -> tuple[ResearchTaskDocument, bool]:
    title = _issue_output_title(task, agent, outcome)
    content_md = _issue_output_content(task, agent, outcome)
    status = "published" if not outcome.get("error") else "draft"
    result = await db.execute(
        select(ResearchTaskDocument).where(
            ResearchTaskDocument.task_id == task.id,
            ResearchTaskDocument.title == title,
            ResearchTaskDocument.document_type == "analysis",
        )
    )
    document = result.scalar_one_or_none()
    now = datetime.utcnow()
    if document is None:
        document = ResearchTaskDocument(
            task_id=task.id,
            title=title,
            document_type="analysis",
            status=status,
            revision=1,
            content_md=content_md,
            created_by_agent_id=agent.id if agent else None,
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
    if document.created_by_agent_id != (agent.id if agent else None):
        document.created_by_agent_id = agent.id if agent else None
        changed = True
    if changed:
        document.revision += 1
        document.updated_at = now
    return document, False


async def _append_task_assistant_message(
    db: AsyncSession,
    task_id: str,
    *,
    author_label: str,
    author_agent_id: str | None,
    content: str,
    metadata: dict | None = None,
) -> None:
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


async def _append_task_activity_message(
    db: AsyncSession,
    task_id: str,
    content: str,
    *,
    author_label: str,
    author_agent_id: str | None,
    metadata: dict | None = None,
) -> None:
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

    now = datetime.utcnow()
    role_title = assigned_agent.role_title if assigned_agent and assigned_agent.role_title else (
        assigned_agent.name if assigned_agent else "Agent"
    )
    document, created_document = await _upsert_task_output_document(db, task, assigned_agent, outcome)

    if outcome.get("error"):
        task.status = "failed"
        task.error = outcome.get("error")
        task.completed_at = None
        await _append_task_assistant_message(
            db,
            task.id,
            author_label=role_title,
            author_agent_id=assigned_agent.id if assigned_agent else None,
            content=_render_issue_output_chat_summary(
                document_title=document.title,
                outcome=outcome,
            ),
            metadata={
                "event": "issue_run_failed",
                "agent_run_id": run_id,
                "document_id": document.id,
                "document_title": document.title,
                "document_type": document.document_type,
                "summary": None,
                "key_findings": [],
                "error": outcome.get("error"),
                "next_action": _issue_failure_next_action(task, role_title),
            },
        )
        await _append_task_activity_message(
            db,
            task.id,
            f"{role_title} run failed and saved the latest failure output on the issue.",
            author_label=role_title,
            author_agent_id=assigned_agent.id if assigned_agent else None,
            metadata={
                "event": "issue_output_saved",
                "agent_run_id": run_id,
                "document_id": document.id,
                "document_created": created_document,
                "status": "failed",
            },
        )
    else:
        task.status = "done"
        task.error = None
        task.completed_at = now
        await _append_task_assistant_message(
            db,
            task.id,
            author_label=role_title,
            author_agent_id=assigned_agent.id if assigned_agent else None,
            content=_render_issue_output_chat_summary(
                document_title=document.title,
                outcome=outcome,
            ),
            metadata={
                "event": "issue_run_completed",
                "agent_run_id": run_id,
                "document_id": document.id,
                "document_title": document.title,
                "document_type": document.document_type,
                "summary": outcome.get("findings_summary") or "",
                "key_findings": [item for item in (outcome.get("key_findings") or []) if item][:5],
                "error": None,
            },
        )
        await _append_task_activity_message(
            db,
            task.id,
            f"{role_title} finished the issue run and saved the latest output on the issue.",
            author_label=role_title,
            author_agent_id=assigned_agent.id if assigned_agent else None,
            metadata={
                "event": "issue_output_saved",
                "agent_run_id": run_id,
                "document_id": document.id,
                "document_created": created_document,
                "status": "completed",
            },
        )

    task.updated_at = now


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
