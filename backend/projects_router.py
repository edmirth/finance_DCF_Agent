"""Project CRUD and memory API routes."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Project, ProjectDocument, ProjectSession, Session as DBSession
from backend.project_config import normalize_project_config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["projects"])


class CreateProjectRequest(BaseModel):
    title: str
    thesis: str
    tickers: Optional[list[str]] = None


class ProjectMemoryPatch(BaseModel):
    memory_doc: str


class ProjectPatch(BaseModel):
    title: Optional[str] = None
    thesis: Optional[str] = None
    config: Optional[dict] = None
    status: Optional[str] = None


def project_detail(project: Project, session_count: int = 0, document_count: int = 0) -> dict:
    config = json.loads(project.config) if project.config else {}
    return {
        "id": project.id,
        "title": project.title,
        "thesis": project.thesis,
        "config": config,
        "memory_doc": project.memory_doc,
        "status": project.status,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "session_count": session_count,
        "document_count": document_count,
    }


def project_summary(project: Project, session_count: int = 0, document_count: int = 0) -> dict:
    detail = project_detail(project, session_count, document_count)
    detail.pop("memory_doc", None)
    return detail


@router.post("/projects", status_code=201)
async def create_project(body: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    """Create a new investment thesis project."""
    from data.project_memory import initialize_memory_doc

    config_dict = normalize_project_config({"tickers": body.tickers, "preferred_agents": []})
    config = json.dumps(config_dict)
    memory_doc = initialize_memory_doc(body.title, body.thesis, tickers=config_dict.get("tickers", []))
    project = Project(
        title=body.title,
        thesis=body.thesis,
        config=config,
        memory_doc=memory_doc,
    )
    db.add(project)
    await db.commit()
    return project_detail(project)


@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List active projects with session and document counts."""
    result = await db.execute(
        select(Project).where(Project.status == "active").order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    out = []
    for project in projects:
        sc_result = await db.execute(
            select(func.count()).select_from(ProjectSession).where(ProjectSession.project_id == project.id)
        )
        session_count = sc_result.scalar() or 0
        dc_result = await db.execute(
            select(func.count()).select_from(ProjectDocument).where(ProjectDocument.project_id == project.id)
        )
        document_count = dc_result.scalar() or 0
        out.append(project_summary(project, session_count, document_count))
    return out


@router.get("/projects/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get full project detail including memory_doc."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    sc_result = await db.execute(
        select(func.count()).select_from(ProjectSession).where(ProjectSession.project_id == project.id)
    )
    session_count = sc_result.scalar() or 0
    dc_result = await db.execute(
        select(func.count()).select_from(ProjectDocument).where(ProjectDocument.project_id == project.id)
    )
    document_count = dc_result.scalar() or 0
    return project_detail(project, session_count, document_count)


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, patch: ProjectPatch, db: AsyncSession = Depends(get_db)):
    """Update project title, thesis, config, or status."""
    from data.project_memory import sync_project_memory

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing_config = json.loads(project.config) if project.config else {}
    next_title = patch.title if patch.title is not None else project.title
    next_thesis = patch.thesis if patch.thesis is not None else project.thesis
    next_config = existing_config

    if patch.title is not None:
        project.title = patch.title
    if patch.thesis is not None:
        project.thesis = patch.thesis
    if patch.config is not None:
        next_config = normalize_project_config(patch.config, existing=existing_config)
        project.config = json.dumps(next_config)
    if patch.status is not None:
        project.status = patch.status

    if patch.title is not None or patch.thesis is not None or patch.config is not None:
        project.memory_doc = sync_project_memory(
            project.memory_doc or "",
            title=next_title,
            thesis=next_thesis,
            tickers=next_config.get("tickers"),
        )
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return project_detail(project)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Archive a project and delete its Chroma collection."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.status = "archived"
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    try:
        from data.chroma_client import ProjectChromaClient

        chroma = ProjectChromaClient()
        await chroma.async_delete_collection(project_id)
    except Exception as e:
        logger.warning("Chroma cleanup failed for project %s: %s", project_id, e)
    return Response(status_code=204)


@router.get("/projects/{project_id}/memory")
async def get_project_memory(project_id: str, db: AsyncSession = Depends(get_db)):
    """Return the project memory document."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"memory_doc": project.memory_doc, "updated_at": project.updated_at.isoformat()}


@router.patch("/projects/{project_id}/memory")
async def patch_project_memory(project_id: str, body: ProjectMemoryPatch, db: AsyncSession = Depends(get_db)):
    """Manually overwrite the project memory document."""
    from data.project_memory import sync_project_memory

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    now = datetime.now(timezone.utc)
    project.memory_doc = sync_project_memory(
        body.memory_doc,
        now_iso=now.replace(tzinfo=timezone.utc).isoformat(timespec="seconds"),
    )
    project.updated_at = now
    await db.commit()
    return {"memory_doc": project.memory_doc, "updated_at": project.updated_at.isoformat()}


@router.get("/projects/{project_id}/sessions")
async def list_project_sessions(project_id: str, db: AsyncSession = Depends(get_db)):
    """List sessions linked to a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")
    ps_result = await db.execute(
        select(ProjectSession).where(ProjectSession.project_id == project_id).order_by(ProjectSession.created_at.desc())
    )
    project_sessions = ps_result.scalars().all()
    out = []
    for project_session in project_sessions:
        s_result = await db.execute(select(DBSession).where(DBSession.id == project_session.session_id))
        session = s_result.scalar_one_or_none()
        if session:
            out.append(
                {
                    "id": session.id,
                    "title": session.title,
                    "agent_type": session.agent_type,
                    "created_at": session.created_at.isoformat(),
                    "last_active_at": session.last_active_at.isoformat(),
                }
            )
    return out
