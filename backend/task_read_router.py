"""Read-oriented issue board API routes."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ResearchTask, ResearchTaskMessage
from backend.task_api_contracts import (
    VALID_TASK_MESSAGE_KINDS,
    VALID_TASK_MESSAGE_ROLES,
    VALID_TASK_STATUSES,
    VALID_TASK_TYPES,
    TaskMessageCreate,
)
from backend.task_serialization import (
    task_message_to_dict,
    task_to_dict,
)

router = APIRouter()


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    ticker: Optional[str] = None,
    task_type: Optional[str] = None,
    project_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    """List tasks. Optional filters: status, ticker, task_type, project_id, agent_id."""
    conditions = []
    if status:
        if status not in VALID_TASK_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        conditions.append(ResearchTask.status == status)
    if ticker:
        conditions.append(ResearchTask.ticker == ticker.upper())
    if task_type:
        if task_type not in VALID_TASK_TYPES:
            raise HTTPException(status_code=400, detail="Invalid task_type filter")
        conditions.append(ResearchTask.task_type == task_type)
    if project_id:
        conditions.append(ResearchTask.project_id == project_id)
    if agent_id:
        conditions.append(
            or_(
                ResearchTask.assigned_agent_id == agent_id,
                ResearchTask.owner_agent_id == agent_id,
            )
        )

    stmt = select(ResearchTask)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(ResearchTask.created_at)).limit(min(max(limit, 1), 1000))

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"tasks": [task_to_dict(task) for task in rows]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_to_dict(task)


@router.get("/tasks/{task_id}/messages")
async def list_task_messages(
    task_id: str,
    kind: Optional[str] = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(ResearchTask.id).where(ResearchTask.id == task_id))
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if kind and kind not in VALID_TASK_MESSAGE_KINDS:
        raise HTTPException(status_code=400, detail="Invalid message kind")

    stmt = select(ResearchTaskMessage).where(ResearchTaskMessage.task_id == task_id)
    if kind:
        stmt = stmt.where(ResearchTaskMessage.kind == kind)
    stmt = stmt.order_by(ResearchTaskMessage.created_at.asc()).limit(min(max(limit, 1), 1000))

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"messages": [task_message_to_dict(row) for row in rows]}


@router.post("/tasks/{task_id}/messages", status_code=201)
async def create_task_message(
    task_id: str,
    body: TaskMessageCreate,
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(ResearchTask.id).where(ResearchTask.id == task_id))
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    kind = (body.kind or "chat").strip().lower()
    if kind not in VALID_TASK_MESSAGE_KINDS:
        raise HTTPException(status_code=400, detail="Invalid message kind")

    role = (body.role or "user").strip().lower()
    if role not in VALID_TASK_MESSAGE_ROLES:
        raise HTTPException(status_code=400, detail="Invalid message role")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content required")

    message = ResearchTaskMessage(
        task_id=task_id,
        kind=kind,
        role=role,
        author_label=(body.author_label or "You").strip() or "You",
        author_agent_id=(body.author_agent_id or "").strip() or None,
        content=content,
        metadata_json=json.dumps(body.metadata or {}),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return task_message_to_dict(message)


@router.get("/tasks/{task_id}/related-work")
async def get_task_related_work(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    parent_task = None
    if task.parent_task_id:
        parent_result = await db.execute(select(ResearchTask).where(ResearchTask.id == task.parent_task_id))
        parent_row = parent_result.scalar_one_or_none()
        if parent_row is not None:
            parent_task = task_to_dict(parent_row)

    child_result = await db.execute(
        select(ResearchTask)
        .where(ResearchTask.parent_task_id == task.id)
        .order_by(ResearchTask.created_at.asc())
    )
    sub_issues = [task_to_dict(row) for row in child_result.scalars().all()]

    same_project_issues: list[dict[str, Any]] = []
    if task.project_id:
        project_result = await db.execute(
            select(ResearchTask)
            .where(
                ResearchTask.project_id == task.project_id,
                ResearchTask.id != task.id,
            )
            .order_by(ResearchTask.updated_at.desc())
            .limit(20)
        )
        same_project_issues = [task_to_dict(row) for row in project_result.scalars().all()]

    return {
        "parent_task": parent_task,
        "sub_issues": sub_issues,
        "same_project_issues": same_project_issues,
    }


@router.get("/tasks/stats/board")
async def task_board_stats(db: AsyncSession = Depends(get_db)):
    """Aggregated counts per status for the board header."""
    result = await db.execute(
        select(ResearchTask.status, func.count(ResearchTask.id)).group_by(ResearchTask.status)
    )
    counts = {status: 0 for status in VALID_TASK_STATUSES}
    for status, total in result.all():
        if status in counts:
            counts[status] = total
    return {"counts": counts}
