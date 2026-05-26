"""Serialization and document-export helpers for issue-board tasks."""
from __future__ import annotations

import io
import json
import re


def task_to_dict(task) -> dict:
    """Serialize a ResearchTask row to a JSON-safe dict."""
    try:
        selected = json.loads(task.selected_agents or "[]")
    except (json.JSONDecodeError, TypeError):
        selected = []
    try:
        completed = json.loads(task.completed_agents or "[]")
    except (json.JSONDecodeError, TypeError):
        completed = []
    try:
        findings = json.loads(task.findings or "{}")
    except (json.JSONDecodeError, TypeError):
        findings = {}
    try:
        synthesis = json.loads(task.pm_synthesis) if task.pm_synthesis else None
    except (json.JSONDecodeError, TypeError):
        synthesis = None

    return {
        "id": task.id,
        "ticker": task.ticker,
        "task_type": task.task_type,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "selected_agents": selected,
        "completed_agents": completed,
        "findings": findings,
        "pm_synthesis": synthesis,
        "overall_sentiment": task.overall_sentiment,
        "project_id": task.project_id,
        "parent_task_id": task.parent_task_id,
        "owner_agent_id": task.owner_agent_id,
        "assigned_agent_id": task.assigned_agent_id,
        "source_heartbeat_run_id": task.source_heartbeat_run_id,
        "triggered_by": task.triggered_by,
        "run_id": task.run_id,
        "mandate_check": task.mandate_check,
        "risk_check": task.risk_check,
        "compliance_check": task.compliance_check,
        "approval_status": task.approval_status,
        "notes": task.notes,
        "error": task.error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def task_message_to_dict(message) -> dict:
    try:
        metadata = json.loads(message.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return {
        "id": message.id,
        "task_id": message.task_id,
        "kind": message.kind,
        "role": message.role,
        "author_label": message.author_label,
        "author_agent_id": message.author_agent_id,
        "content": message.content,
        "metadata": metadata,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def task_document_to_dict(document) -> dict:
    return {
        "id": document.id,
        "task_id": document.task_id,
        "title": document.title,
        "document_type": document.document_type,
        "status": document.status,
        "revision": document.revision,
        "content_md": document.content_md,
        "created_by_agent_id": document.created_by_agent_id,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


def safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    normalized = re.sub(r"_+", "_", normalized).strip("._")
    return normalized or "document"


def _extract_snapshot_pairs(content_md: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    current_section: str | None = None
    for raw_line in (content_md or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            current_section = heading.group(1).strip().lower()
            continue
        if current_section != "snapshot":
            continue
        bullet = re.match(r"^-\s+([^:]+):\s+(.+)$", line)
        if bullet:
            pairs.append((bullet.group(1).strip(), bullet.group(2).strip()))
    return pairs


def _add_inline_markdown_runs(paragraph, text: str) -> None:
    if not text:
        return
    parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Menlo"
        else:
            paragraph.add_run(part)


def _render_markdown_section_to_docx(doc, body: str) -> None:
    lines = (body or "").splitlines()
    in_table = False
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal in_table, table_rows
        if len(table_rows) >= 2:
            headers = table_rows[0]
            data_rows = table_rows[1:]
            if data_rows and all(set(cell.replace("-", "").replace(":", "").strip()) == set() for cell in data_rows[0]):
                data_rows = data_rows[1:]
            table = doc.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            for idx, header in enumerate(headers):
                table.rows[0].cells[idx].text = header
            for row in data_rows:
                row_cells = table.add_row().cells
                for idx, cell in enumerate(row[: len(headers)]):
                    row_cells[idx].text = cell
        in_table = False
        table_rows = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            table_rows.append(cells)
            in_table = True
            continue
        if in_table:
            flush_table()

        if not stripped:
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 4)
            doc.add_heading(heading.group(2).strip(), level=level)
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            p = doc.add_paragraph(style="List Bullet")
            _add_inline_markdown_runs(p, bullet.group(1).strip())
            continue

        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if numbered:
            p = doc.add_paragraph(style="List Number")
            _add_inline_markdown_runs(p, numbered.group(1).strip())
            continue

        p = doc.add_paragraph()
        _add_inline_markdown_runs(p, stripped)

    if in_table:
        flush_table()


def _add_cover_page(doc, document, task) -> None:
    """Write a professional report cover block into *doc* (mutates in place)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.shared import Pt, RGBColor

    snapshot_pairs = _extract_snapshot_pairs(document.content_md or "")
    scope_value = next((v for lbl, v in snapshot_pairs if lbl.lower() == "scope"), None)
    analyst_value = next((v for lbl, v in snapshot_pairs if lbl.lower() == "analyst"), None)

    # Derive the display title
    report_title = document.title
    if document.document_type == "analysis":
        scope_label = scope_value or ((task.ticker or "").strip() if task else "")
        if scope_label and scope_label.upper() != "GENERAL":
            report_title = f"{scope_label.upper()} Equity Research Report"
        elif task and task.title:
            report_title = f"{task.title} — Equity Research Report"

    # ── Classification label ──────────────────────────────────────────────────
    label_para = doc.add_paragraph()
    label_run = label_para.add_run("EQUITY RESEARCH  ·  ANALYST NOTE")
    label_run.font.size = Pt(8)
    label_run.font.color.rgb = RGBColor(0x94, 0x97, 0x9E)  # slate-400
    label_run.font.bold = True

    # ── Thin top rule (paragraph border) ─────────────────────────────────────
    # Abuse the paragraph top border to draw a hairline above the label.
    pPr = label_para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    top = OxmlElement("w:top")
    top.set(qn("w:val"), "single")
    top.set(qn("w:sz"), "4")          # ½ pt
    top.set(qn("w:space"), "6")
    top.set(qn("w:color"), "E2E8F0")  # slate-200
    pBdr.append(top)
    pPr.append(pBdr)

    # ── Company / report title ────────────────────────────────────────────────
    title_para = doc.add_paragraph()
    title_run = title_para.add_run(report_title)
    title_run.bold = True
    title_run.font.size = Pt(26)
    title_run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)  # near-black

    # ── Issue brief (research mandate) ───────────────────────────────────────
    if task and task.title and task.title != report_title:
        brief_para = doc.add_paragraph()
        brief_run = brief_para.add_run(task.title)
        brief_run.font.size = Pt(11)
        brief_run.font.color.rgb = RGBColor(0x4B, 0x55, 0x63)  # slate-600

    # ── Metadata row: Analyst  |  Date ───────────────────────────────────────
    meta_parts: list[str] = []
    if analyst_value:
        meta_parts.append(f"Prepared by  {analyst_value}")
    updated_at = (
        document.updated_at.strftime("%B %d, %Y")
        if getattr(document, "updated_at", None)
        else None
    )
    if updated_at:
        meta_parts.append(updated_at)

    if meta_parts:
        meta_para = doc.add_paragraph()
        meta_run = meta_para.add_run("    ·    ".join(meta_parts))
        meta_run.font.size = Pt(10)
        meta_run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)  # slate-500

    # ── Spacer then thick bottom rule ────────────────────────────────────────
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(2)
    spacer.paragraph_format.space_after = Pt(0)

    rule_para = doc.add_paragraph()
    rPr = rule_para._p.get_or_add_pPr()
    rBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")       # 1½ pt — heavier rule
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "1E3A5F")  # dark navy
    rBdr.append(bottom)
    rPr.append(rBdr)
    rule_para.paragraph_format.space_after = Pt(14)


def build_task_document_docx(document, task) -> bytes:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Aptos"
    normal_style.font.size = Pt(11)
    doc.styles["Heading 1"].font.name = "Aptos Display"

    _add_cover_page(doc, document, task)
    _render_markdown_section_to_docx(doc, document.content_md or "")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
