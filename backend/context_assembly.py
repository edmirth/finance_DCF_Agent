"""
Context assembly middleware for project-grounded queries.

Assembles a <project_context> XML block from:
  1. Project thesis (verbatim)
  2. Memory document (capped at ~800 tokens)
  3. Top-K semantically relevant document chunks from ChromaDB (each capped at ~400 tokens)
  4. Project tickers from config

Total budget: ≤3500 tokens.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Project
from data.chroma_client import ProjectChromaClient

logger = logging.getLogger(__name__)

# Token budget constants (rough: 1 token ≈ 4 chars)
_CHARS_PER_TOKEN = 4
_MEMORY_DOC_MAX_TOKENS = 800
_CHUNK_MAX_TOKENS = 400
_MAX_CHUNKS = 5

_MEMORY_DOC_MAX_CHARS = _MEMORY_DOC_MAX_TOKENS * _CHARS_PER_TOKEN   # 3200
_CHUNK_MAX_CHARS = _CHUNK_MAX_TOKENS * _CHARS_PER_TOKEN              # 1600


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '...' if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


async def assemble_project_context(
    project_id: Optional[str],
    query: str,
    db: AsyncSession,
    chroma_client: ProjectChromaClient,
    top_k: int = 5,
) -> str:
    """
    Assemble a project context block for agent prompts.

    Returns empty string for non-project sessions (project_id is None).
    Returns XML-wrapped context block for project sessions.
    """
    if not project_id:
        return ""

    # Load project from SQLite
    result = await db.execute(select(Project).where(Project.id == project_id))
    project: Optional[Project] = result.scalar_one_or_none()

    if project is None:
        logger.warning("assemble_project_context: project %s not found", project_id)
        return ""

    # Parse config for tickers
    tickers: List[str] = []
    if project.config:
        try:
            config_dict = json.loads(project.config)
            tickers = config_dict.get("tickers", [])
        except (json.JSONDecodeError, AttributeError):
            pass

    # Cap memory_doc to budget
    memory_doc = _truncate(project.memory_doc or "", _MEMORY_DOC_MAX_CHARS)

    # Query ChromaDB for relevant chunks
    chunks: List[dict] = []
    try:
        raw_chunks = await chroma_client.async_query(project_id, query, n_results=top_k)
        for chunk in raw_chunks:
            truncated_text = _truncate(chunk.get("text", ""), _CHUNK_MAX_CHARS)
            chunks.append(
                {
                    "text": truncated_text,
                    "source": chunk.get("source", ""),
                    "score": chunk.get("score", 0.0),
                }
            )
    except Exception as exc:
        logger.warning("assemble_project_context: ChromaDB query failed for project %s: %s", project_id, exc)

    # Build XML context block
    parts: List[str] = []

    # Thesis section (always verbatim)
    parts.append(f"<thesis>\n{project.thesis}\n</thesis>")

    # Memory document section
    if memory_doc:
        parts.append(f"<memory_doc>\n{memory_doc}\n</memory_doc>")

    # Relevant document excerpts
    if chunks:
        excerpt_parts: List[str] = []
        for i, chunk in enumerate(chunks, start=1):
            source_attr = f' source="{chunk["source"]}"' if chunk["source"] else ""
            excerpt_parts.append(
                f'<excerpt index="{i}"{source_attr}>\n{chunk["text"]}\n</excerpt>'
            )
        parts.append("<document_excerpts>\n" + "\n".join(excerpt_parts) + "\n</document_excerpts>")

    # Project tickers
    if tickers:
        tickers_str = ", ".join(tickers)
        parts.append(f"<project_tickers>{tickers_str}</project_tickers>")

    context_body = "\n\n".join(parts)
    return f"<project_context>\n{context_body}\n</project_context>"
