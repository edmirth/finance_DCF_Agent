"""Chat session history API routes."""
from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import DBMessage, Session as DBSession


def create_sessions_router(evict_session_agents: Callable[[str], None]) -> APIRouter:
    router = APIRouter(tags=["sessions"])

    @router.get("/sessions")
    async def list_sessions(limit: int = 50, db: AsyncSession = Depends(get_db)):
        """List sessions most-recent first."""
        result = await db.execute(
            select(DBSession)
            .where(DBSession.agent_type != "arena")
            .order_by(DBSession.last_active_at.desc())
            .limit(limit)
        )
        sessions = result.scalars().all()
        return [
            {
                "id": s.id,
                "title": s.title,
                "agent_type": s.agent_type,
                "created_at": s.created_at.isoformat(),
                "last_active_at": s.last_active_at.isoformat(),
            }
            for s in sessions
        ]

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
        """Get a session with all its messages."""
        result = await db.execute(select(DBSession).where(DBSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        msgs = await db.execute(
            select(DBMessage).where(DBMessage.session_id == session_id).order_by(DBMessage.created_at)
        )
        messages = msgs.scalars().all()
        return {
            "id": session.id,
            "title": session.title,
            "agent_type": session.agent_type,
            "created_at": session.created_at.isoformat(),
            "last_active_at": session.last_active_at.isoformat(),
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "agent_type": m.agent_type,
                    "ticker": m.ticker,
                    "thinking_steps": json.loads(m.thinking_steps) if m.thinking_steps else [],
                    "follow_ups": json.loads(m.follow_ups) if m.follow_ups else [],
                    "chart_specs": json.loads(m.chart_specs) if m.chart_specs else {},
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }

    @router.delete("/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
        """Delete a session and all its messages."""
        result = await db.execute(select(DBSession).where(DBSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await db.delete(session)
        await db.commit()
        evict_session_agents(session_id)
        return Response(status_code=204)

    return router
