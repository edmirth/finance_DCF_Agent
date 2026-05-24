"""Research library analysis CRUD routes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Analysis

router = APIRouter(tags=["analyses"])


class AnalysisPatch(BaseModel):
    tags: Optional[list[str]] = None


@router.get("/analyses")
async def list_analyses(
    ticker: Optional[str] = None,
    tag: Optional[str] = None,
    q: Optional[str] = None,
    agent_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List saved analyses with optional filters."""
    stmt = select(Analysis).order_by(Analysis.created_at.desc())
    if ticker:
        stmt = stmt.where(Analysis.ticker == ticker.upper())
    if agent_type:
        stmt = stmt.where(Analysis.agent_type == agent_type)
    if q:
        stmt = stmt.where(
            or_(
                Analysis.title.ilike(f"%{q}%"),
                Analysis.content.ilike(f"%{q}%"),
            )
        )
    result = await db.execute(stmt)
    analyses = result.scalars().all()

    rows = []
    for a in analyses:
        tags = json.loads(a.tags) if a.tags else []
        if tag and tag not in tags:
            continue
        rows.append(
            {
                "id": a.id,
                "ticker": a.ticker,
                "agent_type": a.agent_type,
                "title": a.title,
                "content_preview": a.content[:200],
                "tags": tags,
                "session_id": a.session_id,
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat(),
            }
        )
    return rows


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single analysis with full content."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {
        "id": analysis.id,
        "ticker": analysis.ticker,
        "agent_type": analysis.agent_type,
        "title": analysis.title,
        "content": analysis.content,
        "tags": json.loads(analysis.tags) if analysis.tags else [],
        "session_id": analysis.session_id,
        "created_at": analysis.created_at.isoformat(),
        "updated_at": analysis.updated_at.isoformat(),
    }


@router.patch("/analyses/{analysis_id}")
async def update_analysis(analysis_id: str, patch: AnalysisPatch, db: AsyncSession = Depends(get_db)):
    """Update analysis tags."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if patch.tags is not None:
        analysis.tags = json.dumps(patch.tags)
        analysis.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": analysis.id, "tags": json.loads(analysis.tags)}


@router.get("/analyses/{analysis_id}/export")
async def export_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)):
    """Download analysis as a .md file."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    date_str = analysis.created_at.strftime("%Y-%m-%d")
    filename = f"{analysis.ticker or 'analysis'}_{analysis.agent_type}_{date_str}.md"
    return Response(
        content=analysis.content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/analyses/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a saved analysis."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await db.delete(analysis)
    await db.commit()
    return Response(status_code=204)
