"""Issue document CRUD and export API routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ResearchTask, ResearchTaskDocument
from backend.task_activity import append_task_activity
from backend.task_api_contracts import (
    VALID_TASK_DOCUMENT_STATUSES,
    TaskDocumentCreate,
    TaskDocumentPatch,
)
from backend.task_serialization import (
    build_task_document_docx,
    safe_filename_part,
    task_document_to_dict,
)

router = APIRouter()


@router.get("/tasks/{task_id}/documents")
async def list_task_documents(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(ResearchTask.id).where(ResearchTask.id == task_id))
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(ResearchTaskDocument)
        .where(ResearchTaskDocument.task_id == task_id)
        .order_by(ResearchTaskDocument.updated_at.desc(), ResearchTaskDocument.created_at.desc())
    )
    rows = result.scalars().all()
    return {"documents": [task_document_to_dict(row) for row in rows]}


@router.post("/tasks/{task_id}/documents", status_code=201)
async def create_task_document(
    task_id: str,
    body: TaskDocumentCreate,
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(ResearchTask.id).where(ResearchTask.id == task_id))
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Document title required")

    status = (body.status or "draft").strip().lower()
    if status not in VALID_TASK_DOCUMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid document status")

    document = ResearchTaskDocument(
        task_id=task_id,
        title=title,
        document_type=(body.document_type or "analysis").strip().lower() or "analysis",
        status=status,
        content_md=body.content_md or "",
        created_by_agent_id=(body.created_by_agent_id or "").strip() or None,
    )
    db.add(document)
    await db.flush()
    await append_task_activity(
        db,
        task_id,
        f"Document created: {title}",
        metadata={"event": "document_created", "document_id": document.id},
    )
    await db.commit()
    await db.refresh(document)
    return task_document_to_dict(document)


@router.patch("/tasks/{task_id}/documents/{document_id}")
async def patch_task_document(
    task_id: str,
    document_id: str,
    body: TaskDocumentPatch,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchTaskDocument).where(
            ResearchTaskDocument.id == document_id,
            ResearchTaskDocument.task_id == task_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    changed = False
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Document title required")
        if document.title != title:
            document.title = title
            changed = True
    if body.content_md is not None and document.content_md != body.content_md:
        document.content_md = body.content_md
        changed = True
    if body.document_type is not None:
        document_type = body.document_type.strip().lower() or "analysis"
        if document.document_type != document_type:
            document.document_type = document_type
            changed = True
    if body.status is not None:
        status = body.status.strip().lower()
        if status not in VALID_TASK_DOCUMENT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid document status")
        if document.status != status:
            document.status = status
            changed = True

    if changed:
        document.revision += 1
        document.updated_at = datetime.utcnow()
        await append_task_activity(
            db,
            task_id,
            f"Document updated: {document.title}",
            metadata={"event": "document_updated", "document_id": document.id, "revision": document.revision},
        )
    await db.commit()
    await db.refresh(document)
    return task_document_to_dict(document)


@router.get("/tasks/{task_id}/documents/{document_id}/export.docx")
async def export_task_document_docx(
    task_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(ResearchTaskDocument).where(
            ResearchTaskDocument.id == document_id,
            ResearchTaskDocument.task_id == task_id,
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    content = await run_in_threadpool(build_task_document_docx, document, task)
    filename = f"{safe_filename_part(document.title)}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/tasks/{task_id}/documents/{document_id}", status_code=204)
async def delete_task_document(
    task_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchTaskDocument).where(
            ResearchTaskDocument.id == document_id,
            ResearchTaskDocument.task_id == task_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    title = document.title
    await db.delete(document)
    await append_task_activity(
        db,
        task_id,
        f"Document deleted: {title}",
        metadata={"event": "document_deleted", "document_id": document_id},
    )
    await db.commit()
    return Response(status_code=204)
