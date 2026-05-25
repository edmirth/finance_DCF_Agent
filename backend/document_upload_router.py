"""Standalone document upload and text extraction API routes."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.document_text_extraction import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_UPLOAD_SIZE,
    extract_text_from_file,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


@router.post("/upload-document")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document and extract its text content."""
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
        text = extract_text_from_file(file.filename, content)
    except Exception as e:
        logger.error("Failed to extract text from %s: %s", file.filename, e)
        raise HTTPException(status_code=500, detail=f"Failed to extract text: {str(e)}")

    return {"filename": file.filename, "content": text, "file_type": ext}
