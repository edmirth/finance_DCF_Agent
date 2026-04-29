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
  scheduled_agents  — user-configured persistent agent workers
  agent_runs        — execution history for scheduled agents
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
    share_slug: Mapped[Optional[str]] = mapped_column(String(12), nullable=True, unique=True, index=True)
    checklist_answers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
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


class ScheduledAgent(Base):
    """A user-configured persistent agent worker with a heartbeat schedule."""
    __tablename__ = "scheduled_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Template: earnings_watcher | market_pulse | thesis_guardian | portfolio_heartbeat | firm_pipeline
    template: Mapped[str] = mapped_column(String(50))
    tickers: Mapped[str] = mapped_column(Text, default="[]")        # JSON array of ticker strings
    topics: Mapped[str] = mapped_column(Text, default="[]")         # JSON array of topic strings
    instruction: Mapped[str] = mapped_column(Text, default="")      # User's thesis / instruction
    # Schedule: daily_morning | pre_market | weekly_monday | weekly_friday | monthly
    schedule_label: Mapped[str] = mapped_column(String(50), default="weekly_monday")
    delivery_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_inapp: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # completed | failed
    last_run_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs: Mapped[List["AgentRun"]] = relationship(
        "AgentRun", back_populates="scheduled_agent", cascade="all, delete-orphan",
        order_by="AgentRun.started_at.desc()"
    )


class AgentRun(Base):
    """A single execution of a ScheduledAgent."""
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_scheduled_agent_id", "scheduled_agent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scheduled_agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scheduled_agents.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | completed | failed
    report: Mapped[str] = mapped_column(Text, default="")
    findings_summary: Mapped[str] = mapped_column(Text, default="")
    material_change: Mapped[bool] = mapped_column(default=False)
    alert_level: Mapped[str] = mapped_column(String(10), default="none")  # high | medium | low | none
    key_findings: Mapped[str] = mapped_column(Text, default="[]")          # JSON array of strings
    tickers_analyzed: Mapped[str] = mapped_column(Text, default="[]")     # JSON array
    agents_used: Mapped[str] = mapped_column(Text, default="[]")          # JSON array
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scheduled_agent: Mapped["ScheduledAgent"] = relationship("ScheduledAgent", back_populates="runs")


class ResearchTask(Base):
    """
    A research task / "issue" — the unit of work in the firm.
    Like a Jira ticket but for investment research.

    Status flow:
      pending  → running  → in_review  → done
                                       ↘ cancelled / failed
    """
    __tablename__ = "research_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    task_type: Mapped[str] = mapped_column(String(50), default="ad_hoc")
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")

    # Agents lifecycle
    selected_agents: Mapped[str] = mapped_column(Text, default="[]")     # JSON array
    completed_agents: Mapped[str] = mapped_column(Text, default="[]")    # JSON array

    # Findings (JSON of all agent outputs, keyed by agent name)
    findings: Mapped[str] = mapped_column(Text, default="{}")            # JSON object
    pm_synthesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    overall_sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Linkage / triggering
    parent_task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    triggered_by: Mapped[str] = mapped_column(String(50), default="manual")
    run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # Governance / mandate gates
    mandate_check: Mapped[str] = mapped_column(String(20), default="not_run")
    risk_check: Mapped[str] = mapped_column(String(20), default="not_run")
    compliance_check: Mapped[str] = mapped_column(String(20), default="not_run")
    approval_status: Mapped[str] = mapped_column(String(20), default="not_required")

    # Notes / errors
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InvestmentMandate(Base):
    """
    Singleton row (id='default') storing the firm's investment mandate.
    Every agent reads this at run-time to understand the firm's rules,
    return target, position limits, and restricted tickers.
    """
    __tablename__ = "investment_mandate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    firm_name: Mapped[str] = mapped_column(String(255), default="My Investment Firm")
    mandate_text: Mapped[str] = mapped_column(Text, default="")
    benchmark: Mapped[str] = mapped_column(String(100), default="S&P 500")
    target_return_pct: Mapped[float] = mapped_column(default=12.0)
    max_position_pct: Mapped[float] = mapped_column(default=5.0)
    max_sector_pct: Mapped[float] = mapped_column(default=25.0)
    max_portfolio_beta: Mapped[float] = mapped_column(default=1.3)
    max_drawdown_pct: Mapped[float] = mapped_column(default=15.0)
    strategy_style: Mapped[str] = mapped_column(String(50), default="blend")
    investment_horizon: Mapped[str] = mapped_column(String(50), default="12 months")
    restricted_tickers: Mapped[str] = mapped_column(Text, default="[]")   # JSON array
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
