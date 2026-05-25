"""Project document upload, listing, and deletion routes."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.document_text_extraction import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_UPLOAD_SIZE,
    extract_text_from_file,
)
from backend.models import Project, ProjectDocument

logger = logging.getLogger(__name__)
router = APIRouter(tags=["project-documents"])


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_project_document(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to a project: extract text, embed in Chroma, save record."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    try:
        raw_text = extract_text_from_file(file.filename, content)
    except Exception as e:
        logger.error("Failed to extract text from %s: %s", file.filename, e)
        raise HTTPException(status_code=500, detail=f"Failed to extract text: {str(e)}")

    doc_id = str(uuid.uuid4())
    doc = ProjectDocument(
        id=doc_id,
        project_id=project_id,
        filename=file.filename,
        file_type=ext,
        raw_text=raw_text,
        chunk_count=0,
        chroma_ids="[]",
    )
    db.add(doc)
    await db.flush()

    chroma_ids: list[str] = []
    try:
        from data.chroma_client import ProjectChromaClient

        chroma = ProjectChromaClient()
        chroma_ids = await chroma.async_add_document_chunks(project_id, doc_id, file.filename, raw_text)
        doc.chunk_count = len(chroma_ids)
        doc.chroma_ids = json.dumps(chroma_ids)
    except Exception as e:
        logger.warning("Chroma embedding failed for %s: %s", file.filename, e)

    try:
        from data.project_memory import (
            format_document_summary_entry,
            generate_document_summary,
            patch_memory_section,
        )
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model="claude-haiku-4-5-20251001", max_tokens=400)
        summary = generate_document_summary(file.filename, raw_text, llm)
        project.memory_doc = patch_memory_section(
            project.memory_doc or "",
            "Uploaded Document Summaries",
            format_document_summary_entry(file.filename, summary, document_id=doc_id),
            mode="append",
        )
        project.updated_at = datetime.now(timezone.utc)
    except Exception as e:
        logger.warning("Document summary generation failed for %s: %s", file.filename, e)

    await db.commit()
    await db.refresh(doc)

    return {
        "id": doc.id,
        "project_id": doc.project_id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "chunk_count": doc.chunk_count,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


@router.get("/projects/{project_id}/documents")
async def list_project_documents(project_id: str, db: AsyncSession = Depends(get_db)):
    """List documents for a project without raw text in the response."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    docs_result = await db.execute(
        select(ProjectDocument)
        .where(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.uploaded_at.desc())
    )
    docs = docs_result.scalars().all()
    return [
        {
            "id": d.id,
            "project_id": d.project_id,
            "filename": d.filename,
            "file_type": d.file_type,
            "chunk_count": d.chunk_count,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ]


@router.delete("/projects/{project_id}/documents/{doc_id}")
async def delete_project_document(project_id: str, doc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a project document and its Chroma chunks."""
    from data.project_memory import remove_document_summary

    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.id == doc_id,
            ProjectDocument.project_id == project_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.chroma_ids:
        try:
            from data.chroma_client import ProjectChromaClient

            chroma = ProjectChromaClient()
            ids = json.loads(doc.chroma_ids)
            if ids:
                await chroma.async_delete_chunks(project_id, ids)
        except Exception as e:
            logger.warning("Chroma chunk deletion failed for doc %s: %s", doc_id, e)

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if project is not None:
        project.memory_doc = remove_document_summary(
            project.memory_doc or "",
            doc.filename,
            document_id=doc.id,
        )
        project.updated_at = datetime.now(timezone.utc)

    await db.delete(doc)
    await db.commit()
    return Response(status_code=204)
