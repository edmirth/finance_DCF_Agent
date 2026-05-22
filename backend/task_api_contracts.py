"""Pydantic contracts and constants for issue-board task endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


VALID_TASK_STATUSES = {"pending", "running", "in_review", "done", "cancelled", "failed"}
VALID_TASK_TYPES = {
    "initiate_coverage",
    "earnings",
    "thesis_update",
    "sector_screen",
    "risk_review",
    "ad_hoc",
}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_TASK_MESSAGE_KINDS = {"chat", "activity"}
VALID_TASK_MESSAGE_ROLES = {"user", "assistant", "system"}
VALID_TASK_DOCUMENT_STATUSES = {"draft", "published"}

TASK_TYPE_TITLES = {
    "initiate_coverage": "Initiate Coverage",
    "earnings": "Earnings Analysis",
    "thesis_update": "Thesis Update",
    "sector_screen": "Sector Screen",
    "risk_review": "Risk Review",
    "ad_hoc": "Ad-hoc Research",
}


class TaskCreate(BaseModel):
    ticker: Optional[str] = None
    task_type: Optional[str] = "ad_hoc"
    title: Optional[str] = None
    priority: Optional[str] = "medium"
    selected_agents: Optional[List[str]] = None
    project_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    owner_agent_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    source_heartbeat_run_id: Optional[str] = None
    triggered_by: Optional[str] = "manual"
    notes: Optional[str] = None


class TaskPatch(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    project_id: Optional[str] = None
    overall_sentiment: Optional[str] = None
    completed_agents: Optional[List[str]] = None
    findings: Optional[Dict[str, Any]] = None
    pm_synthesis: Optional[Dict[str, Any]] = None
    owner_agent_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    source_heartbeat_run_id: Optional[str] = None
    mandate_check: Optional[str] = None
    risk_check: Optional[str] = None
    compliance_check: Optional[str] = None
    approval_status: Optional[str] = None
    error: Optional[str] = None


class TaskMessageCreate(BaseModel):
    kind: Optional[str] = "chat"
    role: Optional[str] = "user"
    author_label: Optional[str] = "You"
    author_agent_id: Optional[str] = None
    content: str
    metadata: Optional[Dict[str, Any]] = None


class TaskChatRequest(BaseModel):
    content: str
    agent_id: Optional[str] = None


class TaskDocumentCreate(BaseModel):
    title: str
    content_md: Optional[str] = ""
    document_type: Optional[str] = "analysis"
    status: Optional[str] = "draft"
    created_by_agent_id: Optional[str] = None


class TaskDocumentPatch(BaseModel):
    title: Optional[str] = None
    content_md: Optional[str] = None
    document_type: Optional[str] = None
    status: Optional[str] = None
