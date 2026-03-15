"""
Project memory document management.

Provides functions to initialize, patch, trim, synchronize, and persist the
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

SECTION_PLACEHOLDERS = {
    "Key Assumptions": "- (to be populated)",
    "Violated or Revised Assumptions": "- (none yet)",
    "Key Companies & Tickers": "- (to be populated)",
    "Accumulated Conclusions": "- (none yet)",
    "Open Questions": "- (to be populated)",
    "Uploaded Document Summaries": "(none yet)",
    "Live Data Snapshots": "- (none yet)",
}

_PLACEHOLDER_LINES = {
    "(to be populated)",
    "(none yet)",
    "- (to be populated)",
    "- (none yet)",
}

# ---------------------------------------------------------------------------
# initialize_memory_doc
# ---------------------------------------------------------------------------

def initialize_memory_doc(title: str, thesis: str, tickers: Optional[list[str]] = None) -> str:
    """Return a freshly initialised memory document for a new project."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ticker_lines = "\n".join(f"- {ticker}" for ticker in (tickers or [])) or SECTION_PLACEHOLDERS["Key Companies & Tickers"]
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
{ticker_lines}

## Accumulated Conclusions
- (none yet)

## Open Questions
- (to be populated)

## Uploaded Document Summaries
{SECTION_PLACEHOLDERS["Uploaded Document Summaries"]}

## Live Data Snapshots
{SECTION_PLACEHOLDERS["Live Data Snapshots"]}
"""


def _extract_section_body(memory_doc: str, section_name: str) -> str:
    """Return the raw body for a ``## section`` or an empty string if missing."""
    pattern = re.compile(
        r"(## " + re.escape(section_name) + r"\n)(.*?)(?=\n## |\Z)",
        re.DOTALL,
    )
    match = pattern.search(memory_doc)
    return match.group(2) if match else ""


def _clean_section_body(body: str) -> str:
    """Strip placeholder lines while preserving meaningful content order."""
    cleaned_lines = [line for line in body.splitlines() if line.strip() not in _PLACEHOLDER_LINES]
    return "\n".join(cleaned_lines).strip()


def _normalise_text_list(values: Optional[list[Any]]) -> list[str]:
    """Normalize arbitrary list-like values to non-empty stripped strings."""
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Remove duplicates case-insensitively while preserving order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _extract_section_bullets(memory_doc: str, section_name: str) -> list[str]:
    """Return bullet content for the named section without placeholders."""
    body = _clean_section_body(_extract_section_body(memory_doc, section_name))
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def _replace_section_with_bullets(
    memory_doc: str,
    section_name: str,
    items: list[str],
) -> str:
    """Replace a section with bullet lines or its default placeholder."""
    deduped = _dedupe_preserve_order(_normalise_text_list(items))
    if deduped:
        body = "\n".join(f"- {item}" for item in deduped)
    else:
        body = SECTION_PLACEHOLDERS.get(section_name, "")
    return patch_memory_section(memory_doc, section_name, body, mode="replace")


def _merge_section_bullets(
    memory_doc: str,
    section_name: str,
    new_items: list[str],
    *,
    prepend: bool = False,
    max_items: Optional[int] = None,
) -> str:
    """Merge bullet items into a section, preserving order and removing duplicates."""
    existing_items = _extract_section_bullets(memory_doc, section_name)
    combined = list(new_items) + existing_items if prepend else existing_items + list(new_items)
    deduped = _dedupe_preserve_order(_normalise_text_list(combined))
    if max_items is not None:
        deduped = deduped[:max_items]
    return _replace_section_with_bullets(memory_doc, section_name, deduped)


def _touch_last_updated(memory_doc: str, now_iso: Optional[str] = None) -> str:
    """Update the document header timestamp."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return re.sub(
        r"_Last updated: .*?_",
        f"_Last updated: {now_iso}_",
        memory_doc,
        count=1,
    )


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
    cleaned_existing = _clean_section_body(existing)

    if mode == "replace":
        body = new_content
    elif mode == "prepend":
        body = new_content if not cleaned_existing else new_content + "\n" + cleaned_existing
    elif mode == "append":
        body = new_content if not cleaned_existing else cleaned_existing + "\n" + new_content
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
    max_snapshots: int = 10,
    max_companies: int = 15,
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
    memory_doc = _trim_section_bullets(memory_doc, "Live Data Snapshots", max_snapshots)
    memory_doc = _trim_section_bullets(memory_doc, "Key Companies & Tickers", max_companies)
    return memory_doc


def sync_project_memory(
    memory_doc: str,
    *,
    title: Optional[str] = None,
    thesis: Optional[str] = None,
    tickers: Optional[list[str]] = None,
    now_iso: Optional[str] = None,
) -> str:
    """Keep memory_doc aligned with canonical project fields."""
    if title is not None:
        memory_doc = re.sub(
            r"^# Project Memory: .*$",
            f"# Project Memory: {title}",
            memory_doc,
            count=1,
            flags=re.MULTILINE,
        )

    if thesis is not None:
        memory_doc = patch_memory_section(memory_doc, "Thesis", thesis.strip(), mode="replace")

    if tickers is not None:
        normalized_tickers = [ticker.upper() for ticker in _normalise_text_list(tickers)]
        memory_doc = _replace_section_with_bullets(memory_doc, "Key Companies & Tickers", normalized_tickers)

    return _touch_last_updated(memory_doc, now_iso=now_iso)


def format_document_summary_entry(
    filename: str,
    summary: str,
    *,
    document_id: Optional[str] = None,
) -> str:
    """Format one uploaded-document summary block for insertion into memory_doc."""
    lines = [f"### {filename}"]
    if document_id:
        lines.append(f"<!-- project_doc:{document_id} -->")
    lines.append(summary.strip())
    return "\n".join(line for line in lines if line)


def remove_document_summary(
    memory_doc: str,
    filename: str,
    *,
    document_id: Optional[str] = None,
) -> str:
    """Remove one uploaded-document summary block from memory_doc."""
    section_name = "Uploaded Document Summaries"
    body = _extract_section_body(memory_doc, section_name)
    if not body:
        return memory_doc

    cleaned_body = _clean_section_body(body)
    updated_body = cleaned_body

    if document_id:
        exact_pattern = re.compile(
            r"(?:^|\n)### "
            + re.escape(filename)
            + r"\n<!-- project_doc:"
            + re.escape(document_id)
            + r" -->\n.*?(?=\n### |\Z)",
            re.DOTALL,
        )
        updated_body, exact_count = exact_pattern.subn("", updated_body, count=1)
        if exact_count == 0:
            legacy_exact_pattern = re.compile(
                r"(?:^|\n)### "
                + re.escape(filename)
                + r"\n.*?(?=\n### |\Z)",
                re.DOTALL,
            )
            updated_body = legacy_exact_pattern.sub("", updated_body, count=1)
    else:
        filename_pattern = re.compile(
            r"(?:^|\n)### " + re.escape(filename) + r"\n.*?(?=\n### |\Z)",
            re.DOTALL,
        )
        updated_body = filename_pattern.sub("", updated_body, count=1)

    updated_body = updated_body.strip()
    updated_body = re.sub(r"\n{3,}", "\n\n", updated_body)
    replacement = updated_body or SECTION_PLACEHOLDERS[section_name]
    return patch_memory_section(memory_doc, section_name, replacement, mode="replace")


def apply_memory_patch(
    memory_doc: str,
    memory_patch: dict,
    *,
    today: Optional[str] = None,
    now_iso: Optional[str] = None,
) -> str:
    """Apply a structured memory patch to a memory_doc and return the updated text."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conclusions = _normalise_text_list(memory_patch.get("conclusions"))
    if conclusions:
        dated = [f"[{today} - agent] {item}" for item in conclusions]
        memory_doc = _merge_section_bullets(
            memory_doc,
            "Accumulated Conclusions",
            dated,
            prepend=True,
        )

    violated = _normalise_text_list(memory_patch.get("violated_assumptions"))
    if violated:
        dated = [f"{today}: {item}" for item in violated]
        memory_doc = _merge_section_bullets(
            memory_doc,
            "Violated or Revised Assumptions",
            dated,
        )

    thesis_health: Optional[dict] = memory_patch.get("thesis_health")
    if thesis_health:
        status = thesis_health.get("status", "Not assessed")
        rationale = thesis_health.get("rationale", "")
        health_content = f"**Status**: {status}\n**Rationale**: {rationale}"
        memory_doc = patch_memory_section(
            memory_doc, "Thesis Health", health_content, mode="replace"
        )

    assumptions = _normalise_text_list(memory_patch.get("assumptions"))
    if assumptions:
        memory_doc = _merge_section_bullets(memory_doc, "Key Assumptions", assumptions)

    questions = _normalise_text_list(memory_patch.get("open_questions"))
    if questions:
        memory_doc = _merge_section_bullets(memory_doc, "Open Questions", questions)

    companies = [item.upper() if re.fullmatch(r"[A-Za-z]{1,6}", item) else item for item in _normalise_text_list(memory_patch.get("key_companies"))]
    if companies:
        memory_doc = _merge_section_bullets(memory_doc, "Key Companies & Tickers", companies)

    snapshots = _normalise_text_list(memory_patch.get("live_data_snapshots"))
    if snapshots:
        memory_doc = _merge_section_bullets(
            memory_doc,
            "Live Data Snapshots",
            snapshots,
            prepend=True,
            max_items=10,
        )

    memory_doc = trim_memory_doc(memory_doc)
    return _touch_last_updated(memory_doc, now_iso=now_iso)


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
        assumptions          (list[str])   — merge into Key Assumptions
        open_questions       (list[str])   — merge into Open Questions
        key_companies        (list[str])   — merge into Key Companies & Tickers
        live_data_snapshots  (list[str])   — prepend into Live Data Snapshots

    Implements single-retry optimistic locking: if another writer updated
    ``updated_at`` between our read and write we re-read, re-apply, and retry
    once before logging and dropping.
    """
    from backend.models import Project  # avoid circular import at module level

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

            now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
            memory_doc = apply_memory_patch(
                memory_doc,
                memory_patch,
                now_iso=now_iso,
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
