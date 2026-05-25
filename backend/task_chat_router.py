"""Issue chat API routes."""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ResearchTask, ResearchTaskMessage
from backend.task_activity import append_task_activity
from backend.task_api_contracts import TaskChatRequest
from backend.task_serialization import task_message_to_dict

logger = logging.getLogger(__name__)

TaskReplyHandler = Callable[..., Awaitable[dict[str, Any]]]


def create_task_chat_router(run_task_chat_reply: TaskReplyHandler) -> APIRouter:
    router = APIRouter()

    @router.post("/tasks/{task_id}/chat")
    async def create_task_chat_turn(
        task_id: str,
        body: TaskChatRequest,
        db: AsyncSession = Depends(get_db),
    ):
        result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        prompt = body.content.strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="Message content required")

        user_message = ResearchTaskMessage(
            task_id=task_id,
            kind="chat",
            role="user",
            author_label="You",
            content=prompt,
        )
        db.add(user_message)
        await db.flush()

        thread_result = await db.execute(
            select(ResearchTaskMessage)
            .where(
                ResearchTaskMessage.task_id == task_id,
                ResearchTaskMessage.kind == "chat",
            )
            .order_by(ResearchTaskMessage.created_at.asc())
            .limit(50)
        )
        thread_messages = thread_result.scalars().all()
        try:
            reply = await run_task_chat_reply(
                db,
                task,
                prompt,
                target_agent_id=body.agent_id,
                thread_messages=thread_messages,
            )
        except Exception:
            logger.exception("task chat reply failed for task %s", task_id)
            reply = {
                "author_label": "System",
                "author_agent_id": None,
                "content": "The issue reply path failed. Retry the message or run the assigned agent again.",
                "action": None,
            }

        assistant_message = ResearchTaskMessage(
            task_id=task_id,
            kind="chat",
            role="assistant",
            author_label=reply["author_label"],
            author_agent_id=reply["author_agent_id"],
            content=reply["content"],
            metadata_json=json.dumps({"action": reply["action"]} if reply["action"] else {}),
        )
        db.add(assistant_message)

        if reply["action"]:
            action_type = reply["action"].get("type")
            activity_content = f"CEO action suggested: {action_type.replace('_', ' ')}"
            await append_task_activity(
                db,
                task_id,
                activity_content,
                author_label="CEO",
                metadata={"event": "ceo_action", "action": reply["action"]},
            )

        await db.commit()
        await db.refresh(user_message)
        await db.refresh(assistant_message)
        return {
            "user_message": task_message_to_dict(user_message),
            "assistant_message": task_message_to_dict(assistant_message),
            "action": reply["action"],
        }

    return router
