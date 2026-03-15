"""
Project memory document management.

Provides functions to initialize, patch, trim, and persist the
structured markdown memory document stored in projects.memory_doc.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section headers (order matters — defines document structure)
# ---------------------------------------------------------------------------

SECTION_HEADERS = [
    "Thesis",
    "Key Assumptions",
    "Violated or Revised Assumptions",
    "Thesis Health",
    "Key Companies & Tickers",
    "Accumulated Conclusions",
    "Open Questions",
    "Uploaded Document Summaries",
    "Live Data Snapshots",
]

# ---------------------------------------------------------------------------
# initialize_memory_doc
# ---------------------------------------------------------------------------

def initialize_memory_doc(title: str, thesis: str) -> str:
    """Return a freshly initialised memory document for a new project."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"""# Project Memory: {title}
_Last updated: {now}_

## Thesis
{thesis}

## Key Assumptions
- (to be populated)

## Violated or Revised Assumptions
- (none yet)

## Thesis Health
**Status**: Not assessed
**Rationale**: No analysis sessions completed yet.

## Key Companies & Tickers
- (to be populated)

## Accumulated Conclusions
- (none yet)

## Open Questions
- (to be populated)

## Uploaded Document Summaries
(none yet)

## Live Data Snapshots
- (none yet)
"""


# ---------------------------------------------------------------------------
# patch_memory_section
# ---------------------------------------------------------------------------

def patch_memory_section(
    memory_doc: str,
    section_name: str,
    new_content: str,
    mode: str = "replace",
) -> str:
    """Locate ``## {section_name}`` and replace/prepend/append its content.

    Args:
        memory_doc:   The full memory document string.
        section_name: Name of the section (must be in SECTION_HEADERS).
        new_content:  Text to inject (no leading ``## `` heading needed).
        mode:         ``"replace"`` | ``"prepend"`` | ``"append"``

    Returns:
        Updated document string.  If the section is not found, the original
        document is returned unchanged.
    """
    # Regex: capture everything from ``## {section_name}`` up to (but not
    # including) the next ``## `` heading or end-of-string.
    pattern = re.compile(
        r"(## " + re.escape(section_name) + r"\n)(.*?)(?=\n## |\Z)",
        re.DOTALL,
    )
    match = pattern.search(memory_doc)
    if not match:
        return memory_doc

    heading = match.group(1)       # e.g. "## Thesis\n"
    existing = match.group(2)      # current section body

    if mode == "replace":
        body = new_content
    elif mode == "prepend":
        body = new_content + "\n" + existing.rstrip("\n")
    elif mode == "append":
        body = existing.rstrip("\n") + "\n" + new_content
    else:
        raise ValueError(f"Unknown mode: {mode!r}. Use 'replace', 'prepend', or 'append'.")

    # Ensure the body ends with a newline so the next section separates cleanly.
    if body and not body.endswith("\n"):
        body += "\n"

    return memory_doc[: match.start()] + heading + body + memory_doc[match.end() :]


# ---------------------------------------------------------------------------
# trim_memory_doc
# ---------------------------------------------------------------------------

def trim_memory_doc(
    memory_doc: str,
    max_conclusions: int = 20,
    max_questions: int = 10,
) -> str:
    """Truncate overlong sections to keep the memory doc within token budget.

    - ``Accumulated Conclusions``: keeps the *most recent* ``max_conclusions``
      bullet lines (lines starting with ``- ``).
    - ``Open Questions``:          keeps the *most recent* ``max_questions``
      bullet lines.
    All other sections are left untouched.
    """
    def _trim_section_bullets(doc: str, section: str, max_bullets: int) -> str:
        pattern = re.compile(
            r"(## " + re.escape(section) + r"\n)(.*?)(?=\n## |\Z)",
            re.DOTALL,
        )
        m = pattern.search(doc)
        if not m:
            return doc
        body = m.group(2)
        lines = body.splitlines()
        bullets = [l for l in lines if l.strip().startswith("- ")]
        non_bullets = [l for l in lines if not l.strip().startswith("- ")]
        if len(bullets) <= max_bullets:
            return doc
        # Keep most recent (last N)
        kept_bullets = bullets[-max_bullets:]
        new_body = "\n".join(non_bullets + kept_bullets) + "\n"
        heading = m.group(1)
        return doc[: m.start()] + heading + new_body + doc[m.end() :]

    memory_doc = _trim_section_bullets(memory_doc, "Accumulated Conclusions", max_conclusions)
    memory_doc = _trim_section_bullets(memory_doc, "Open Questions", max_questions)
    return memory_doc


# ---------------------------------------------------------------------------
# generate_document_summary
# ---------------------------------------------------------------------------

def generate_document_summary(filename: str, raw_text: str, llm: Any) -> str:
    """Call the supplied LLM to produce a ≤200-word summary of a document.

    Args:
        filename: Original file name (used for context in the prompt).
        raw_text: Full extracted text of the document.
        llm:      LangChain-compatible chat model (e.g. ChatOpenAI with Haiku).

    Returns:
        Plain-text summary string (≤200 words).
    """
    from langchain_core.messages import HumanMessage, SystemMessage  # local import

    # Truncate raw text to avoid huge prompts (~4000 chars ≈ ~1000 tokens)
    truncated = raw_text[:4000]
    if len(raw_text) > 4000:
        truncated += "\n...[truncated]"

    messages = [
        SystemMessage(
            content=(
                "You are a financial research analyst. "
                "Summarise the provided document in ≤200 words. "
                "Focus on key financial figures, investment thesis relevance, "
                "and any forward-looking statements."
            )
        ),
        HumanMessage(
            content=f"Document: {filename}\n\n{truncated}"
        ),
    ]
    response = llm.invoke(messages)
    return response.content.strip()


# ---------------------------------------------------------------------------
# update_project_memory  (async, called as background task)
# ---------------------------------------------------------------------------

async def update_project_memory(
    project_id: str,
    memory_patch: dict,
    db: AsyncSession,
) -> None:
    """Apply a memory patch dict to project.memory_doc in SQLite.

    Patch keys (all optional):
        conclusions          (list[str])   — prepend to Accumulated Conclusions
        violated_assumptions (list[str])   — append to Violated or Revised Assumptions
        thesis_health        (dict)        — replace Thesis Health (keys: status, rationale)
        open_questions       (list[str])   — append to Open Questions

    Implements single-retry optimistic locking: if another writer updated
    ``updated_at`` between our read and write we re-read, re-apply, and retry
    once before logging and dropping.
    """
    from backend.models import Project  # avoid circular import at module level

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for attempt in range(2):
        try:
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project: Optional[Project] = result.scalar_one_or_none()
            if project is None:
                logger.warning("update_project_memory: project %s not found", project_id)
                return

            snapshot_updated_at = project.updated_at
            memory_doc: str = project.memory_doc or ""

            # --- Apply patch ---

            conclusions: list = memory_patch.get("conclusions") or []
            if conclusions:
                bullet_block = "\n".join(
                    f"- [{today} — agent] {c}" for c in conclusions
                )
                memory_doc = patch_memory_section(
                    memory_doc, "Accumulated Conclusions", bullet_block, mode="prepend"
                )

            violated: list = memory_patch.get("violated_assumptions") or []
            if violated:
                bullet_block = "\n".join(
                    f"- {today}: {v}" for v in violated
                )
                memory_doc = patch_memory_section(
                    memory_doc, "Violated or Revised Assumptions", bullet_block, mode="append"
                )

            thesis_health: Optional[dict] = memory_patch.get("thesis_health")
            if thesis_health:
                status = thesis_health.get("status", "Not assessed")
                rationale = thesis_health.get("rationale", "")
                health_content = f"**Status**: {status}\n**Rationale**: {rationale}"
                memory_doc = patch_memory_section(
                    memory_doc, "Thesis Health", health_content, mode="replace"
                )

            questions: list = memory_patch.get("open_questions") or []
            if questions:
                bullet_block = "\n".join(f"- {q}" for q in questions)
                memory_doc = patch_memory_section(
                    memory_doc, "Open Questions", bullet_block, mode="append"
                )

            # --- Trim ---
            memory_doc = trim_memory_doc(memory_doc)

            # --- Update last-updated timestamp in header ---
            now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
            memory_doc = re.sub(
                r"_Last updated: .*?_",
                f"_Last updated: {now_iso}_",
                memory_doc,
                count=1,
            )

            # --- Optimistic write (check updated_at hasn't changed) ---
            stmt = (
                update(Project)
                .where(
                    Project.id == project_id,
                    Project.updated_at == snapshot_updated_at,
                )
                .values(
                    memory_doc=memory_doc,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            result = await db.execute(stmt)
            await db.commit()

            if result.rowcount == 0:
                if attempt == 0:
                    logger.info(
                        "update_project_memory: optimistic lock miss for %s, retrying",
                        project_id,
                    )
                    continue  # re-read and retry
                else:
                    logger.warning(
                        "update_project_memory: optimistic lock miss twice for %s, dropping patch",
                        project_id,
                    )
            return

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "update_project_memory: error on attempt %d for %s: %s",
                attempt + 1,
                project_id,
                exc,
                exc_info=True,
            )
            try:
                await db.rollback()
            except Exception:
                pass
            return
