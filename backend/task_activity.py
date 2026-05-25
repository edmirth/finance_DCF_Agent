"""Shared issue activity helpers."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ResearchTaskMessage


async def append_task_activity(
    db: AsyncSession,
    task_id: str,
    content: str,
    *,
    author_label: str = "System",
    author_agent_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
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
