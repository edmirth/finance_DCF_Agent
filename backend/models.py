"""
SQLAlchemy ORM models for the Finance DCF Agent persistence layer.

Tables:
  sessions          — chat sessions (one per conversation)
  messages          — individual messages within a session
  analyses          — auto-saved analysis reports
  watchlists        — named ticker watchlists
  watchlist_tickers — individual tickers within a watchlist
  projects          — investment thesis workspaces
  project_sessions  — links sessions to a project
  project_documents — uploaded files + chroma chunk references
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    agent_type: Mapped[str] = mapped_column(String(50), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[List["DBMessage"]] = relationship(
        "DBMessage", back_populates="session", cascade="all, delete-orphan", order_by="DBMessage.created_at"
    )
    analyses: Mapped[List["Analysis"]] = relationship(
        "Analysis", back_populates="session", cascade="all, delete-orphan"
    )


class DBMessage(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))          # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, default="")
    agent_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ticker: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    thinking_steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    follow_ups: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # JSON
    chart_specs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["Session"] = relationship("Session", back_populates="messages")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    ticker: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    agent_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")   # JSON array of strings
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="analyses")


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="My Watchlist")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tickers: Mapped[List["WatchlistTicker"]] = relationship(
        "WatchlistTicker", back_populates="watchlist", cascade="all, delete-orphan", order_by="WatchlistTicker.added_at"
    )


class WatchlistTicker(Base):
    __tablename__ = "watchlist_tickers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    watchlist_id: Mapped[str] = mapped_column(String(36), ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    watchlist: Mapped["Watchlist"] = relationship("Watchlist", back_populates="tickers")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    thesis: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    memory_doc: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project_sessions: Mapped[List["ProjectSession"]] = relationship(
        "ProjectSession", back_populates="project", cascade="all, delete-orphan"
    )
    documents: Mapped[List["ProjectDocument"]] = relationship(
        "ProjectDocument", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectSession(Base):
    __tablename__ = "project_sessions"
    __table_args__ = (
        UniqueConstraint("project_id", "session_id", name="uq_project_session"),
        Index("ix_project_sessions_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="project_sessions")
    session: Mapped["Session"] = relationship("Session")


class ProjectDocument(Base):
    __tablename__ = "project_documents"
    __table_args__ = (
        Index("ix_project_documents_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(50))
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    chroma_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="documents")
