"""
Async SQLAlchemy database engine and session factory.
Supports SQLite (default) and PostgreSQL (set DATABASE_URL env var).
"""
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

# Default to SQLite alongside api_server.py; override with DATABASE_URL env var
_db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./finance_agent.db")

# For PostgreSQL upgrade: set DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
engine = create_async_engine(
    _db_url,
    echo=False,
    # SQLite needs check_same_thread=False; harmless on Postgres
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Synchronous engine and session factory for use in tool _run() methods
# (which run in threadpool and cannot use async sessions)
_sync_db_url = _db_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2").replace("+aiopg", "+psycopg2")
sync_engine = create_engine(
    _sync_db_url,
    connect_args={"check_same_thread": False} if "sqlite" in _sync_db_url else {},
)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables if they don't exist. Called on app startup."""
    # Import models so they register with Base.metadata
    import backend.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migration: add chart_specs column if it doesn't exist yet
        try:
            await conn.execute(text("ALTER TABLE messages ADD COLUMN chart_specs TEXT"))
        except OperationalError as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                pass  # Column already exists — expected on re-start
            else:
                logger.error(f"Unexpected OperationalError adding chart_specs column: {e}")
        except Exception as e:
            logger.error(f"Unexpected error adding chart_specs column: {e}")
        # Idempotent migration: add share_slug + checklist_answers to analyses
        for _col, _ddl in [
            ("share_slug", "ALTER TABLE analyses ADD COLUMN share_slug TEXT"),
            ("checklist_answers", "ALTER TABLE analyses ADD COLUMN checklist_answers TEXT"),
        ]:
            try:
                await conn.execute(text(_ddl))
            except OperationalError as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    pass
                else:
                    logger.error(f"Unexpected OperationalError adding {_col} column: {e}")
            except Exception as e:
                logger.error(f"Unexpected error adding {_col} column: {e}")
        # Idempotent migration: create project tables if they don't exist yet
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                thesis TEXT NOT NULL DEFAULT '',
                config TEXT,
                memory_doc TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_status ON projects (status)"))
        except OperationalError:
            pass  # Index already exists
        except Exception as e:
            logger.error(f"Unexpected error creating ix_projects_status index: {e}")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                created_at DATETIME NOT NULL,
                UNIQUE(project_id, session_id)
            )
        """))
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_sessions_project_id ON project_sessions (project_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_sessions_session_id ON project_sessions (session_id)"))
        except OperationalError:
            pass  # Indexes already exist
        except Exception as e:
            logger.error(f"Unexpected error creating project_sessions indexes: {e}")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_documents (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                raw_text TEXT,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                chroma_ids TEXT,
                uploaded_at DATETIME NOT NULL
            )
        """))
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_documents_project_id ON project_documents (project_id)"))
        except OperationalError:
            pass  # Index already exists
        except Exception as e:
            logger.error(f"Unexpected error creating project_documents index: {e}")
        # Idempotent migration: scheduled_agents + agent_runs tables
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scheduled_agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                template TEXT NOT NULL,
                tickers TEXT NOT NULL DEFAULT '[]',
                topics TEXT NOT NULL DEFAULT '[]',
                instruction TEXT NOT NULL DEFAULT '',
                schedule_label TEXT NOT NULL DEFAULT 'weekly_monday',
                role_key TEXT,
                role_title TEXT,
                role_family TEXT,
                manager_agent_id TEXT,
                delivery_email TEXT,
                delivery_inapp INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_run_at DATETIME,
                next_run_at DATETIME,
                last_run_status TEXT,
                last_run_summary TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scheduled_agents_is_active ON scheduled_agents (is_active)"))
        except OperationalError:
            pass
        except Exception as e:
            logger.error(f"Unexpected error creating ix_scheduled_agents_is_active index: {e}")
        for _col in ["role_key", "role_title", "role_family", "manager_agent_id"]:
            try:
                await conn.execute(text(f"ALTER TABLE scheduled_agents ADD COLUMN {_col} TEXT"))
            except OperationalError as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    pass
                else:
                    logger.error(f"Unexpected OperationalError adding {_col} column: {e}")
            except Exception as e:
                logger.error(f"Unexpected error adding {_col} column: {e}")
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scheduled_agents_manager_agent_id ON scheduled_agents (manager_agent_id)"))
        except OperationalError:
            pass
        except Exception as e:
            logger.error(f"Unexpected error creating ix_scheduled_agents_manager_agent_id index: {e}")
        for _idx, _col in [
            ("ix_scheduled_agents_role_key", "role_key"),
            ("ix_scheduled_agents_role_family", "role_family"),
        ]:
            try:
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {_idx} ON scheduled_agents ({_col})"))
            except OperationalError:
                pass
            except Exception as e:
                logger.error(f"Unexpected error creating {_idx} index: {e}")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                scheduled_agent_id TEXT NOT NULL REFERENCES scheduled_agents(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'running',
                report TEXT NOT NULL DEFAULT '',
                findings_summary TEXT NOT NULL DEFAULT '',
                material_change INTEGER NOT NULL DEFAULT 0,
                alert_level TEXT NOT NULL DEFAULT 'none',
                tickers_analyzed TEXT NOT NULL DEFAULT '[]',
                agents_used TEXT NOT NULL DEFAULT '[]',
                started_at DATETIME NOT NULL,
                completed_at DATETIME,
                error TEXT
            )
        """))
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_runs_scheduled_agent_id ON agent_runs (scheduled_agent_id)"))
        except OperationalError:
            pass
        except Exception as e:
            logger.error(f"Unexpected error creating ix_agent_runs_scheduled_agent_id index: {e}")
        # Idempotent migration: add key_findings column to agent_runs
        try:
            await conn.execute(text("ALTER TABLE agent_runs ADD COLUMN key_findings TEXT NOT NULL DEFAULT '[]'"))
        except OperationalError as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.error(f"Unexpected OperationalError adding key_findings column: {e}")
        # Idempotent migration: agent_routines and heartbeat_runs
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_routines (
                id TEXT PRIMARY KEY,
                scheduled_agent_id TEXT NOT NULL REFERENCES scheduled_agents(id) ON DELETE CASCADE,
                routine_type TEXT NOT NULL DEFAULT 'heartbeat',
                schedule_label TEXT NOT NULL DEFAULT 'weekly_monday',
                timezone_name TEXT NOT NULL DEFAULT 'America/New_York',
                is_active INTEGER NOT NULL DEFAULT 1,
                last_run_at DATETIME,
                next_run_at DATETIME,
                last_run_status TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                UNIQUE(scheduled_agent_id, routine_type)
            )
        """))
        for _idx in [
            "CREATE INDEX IF NOT EXISTS ix_agent_routines_scheduled_agent_id ON agent_routines (scheduled_agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_routines_is_active ON agent_routines (is_active)",
        ]:
            try:
                await conn.execute(text(_idx))
            except OperationalError:
                pass
            except Exception as e:
                logger.error(f"Unexpected error creating agent_routines index: {e}")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS heartbeat_runs (
                id TEXT PRIMARY KEY,
                scheduled_agent_id TEXT NOT NULL REFERENCES scheduled_agents(id) ON DELETE CASCADE,
                agent_routine_id TEXT REFERENCES agent_routines(id) ON DELETE SET NULL,
                agent_run_id TEXT REFERENCES agent_runs(id) ON DELETE SET NULL,
                trigger_type TEXT NOT NULL DEFAULT 'scheduled',
                status TEXT NOT NULL DEFAULT 'running',
                summary TEXT NOT NULL DEFAULT '',
                alert_level TEXT NOT NULL DEFAULT 'none',
                material_change INTEGER NOT NULL DEFAULT 0,
                context_json TEXT NOT NULL DEFAULT '{}',
                outcome_json TEXT NOT NULL DEFAULT '{}',
                started_at DATETIME NOT NULL,
                completed_at DATETIME,
                error TEXT
            )
        """))
        for _idx in [
            "CREATE INDEX IF NOT EXISTS ix_heartbeat_runs_scheduled_agent_id ON heartbeat_runs (scheduled_agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_heartbeat_runs_agent_routine_id ON heartbeat_runs (agent_routine_id)",
            "CREATE INDEX IF NOT EXISTS ix_heartbeat_runs_started_at ON heartbeat_runs (started_at)",
            "CREATE INDEX IF NOT EXISTS ix_heartbeat_runs_trigger_type ON heartbeat_runs (trigger_type)",
        ]:
            try:
                await conn.execute(text(_idx))
            except OperationalError:
                pass
            except Exception as e:
                logger.error(f"Unexpected error creating heartbeat_runs index: {e}")
        # Idempotent migration: hire_proposals table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hire_proposals (
                id TEXT PRIMARY KEY,
                proposed_by TEXT NOT NULL DEFAULT 'cio',
                status TEXT NOT NULL DEFAULT 'pending',
                name TEXT NOT NULL,
                description TEXT,
                template TEXT NOT NULL,
                role_key TEXT,
                role_title TEXT,
                role_family TEXT,
                tickers TEXT NOT NULL DEFAULT '[]',
                topics TEXT NOT NULL DEFAULT '[]',
                instruction TEXT NOT NULL DEFAULT '',
                schedule_label TEXT NOT NULL DEFAULT 'weekly_monday',
                manager_agent_id TEXT REFERENCES scheduled_agents(id) ON DELETE SET NULL,
                delivery_email TEXT,
                delivery_inapp INTEGER NOT NULL DEFAULT 1,
                approved_agent_id TEXT REFERENCES scheduled_agents(id) ON DELETE SET NULL,
                decision_note TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                decided_at DATETIME
            )
        """))
        for _idx in [
            "CREATE INDEX IF NOT EXISTS ix_hire_proposals_status ON hire_proposals (status)",
            "CREATE INDEX IF NOT EXISTS ix_hire_proposals_role_key ON hire_proposals (role_key)",
            "CREATE INDEX IF NOT EXISTS ix_hire_proposals_role_family ON hire_proposals (role_family)",
            "CREATE INDEX IF NOT EXISTS ix_hire_proposals_created_at ON hire_proposals (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_hire_proposals_manager_agent_id ON hire_proposals (manager_agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_hire_proposals_approved_agent_id ON hire_proposals (approved_agent_id)",
        ]:
            try:
                await conn.execute(text(_idx))
            except OperationalError:
                pass
            except Exception as e:
                logger.error(f"Unexpected error creating hire_proposals index: {e}")
        # Idempotent migration: research_tasks (firm "issues" board)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS research_tasks (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'ad_hoc',
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority TEXT NOT NULL DEFAULT 'medium',
                selected_agents TEXT NOT NULL DEFAULT '[]',
                completed_agents TEXT NOT NULL DEFAULT '[]',
                findings TEXT NOT NULL DEFAULT '{}',
                pm_synthesis TEXT,
                overall_sentiment TEXT,
                parent_task_id TEXT REFERENCES research_tasks(id) ON DELETE SET NULL,
                owner_agent_id TEXT REFERENCES scheduled_agents(id) ON DELETE SET NULL,
                assigned_agent_id TEXT REFERENCES scheduled_agents(id) ON DELETE SET NULL,
                source_heartbeat_run_id TEXT REFERENCES heartbeat_runs(id) ON DELETE SET NULL,
                triggered_by TEXT NOT NULL DEFAULT 'manual',
                run_id TEXT,
                mandate_check TEXT NOT NULL DEFAULT 'not_run',
                risk_check TEXT NOT NULL DEFAULT 'not_run',
                compliance_check TEXT NOT NULL DEFAULT 'not_run',
                approval_status TEXT NOT NULL DEFAULT 'not_required',
                notes TEXT,
                error TEXT,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                updated_at DATETIME NOT NULL
            )
        """))
        for _col in ["owner_agent_id", "assigned_agent_id", "source_heartbeat_run_id"]:
            try:
                await conn.execute(text(f"ALTER TABLE research_tasks ADD COLUMN {_col} TEXT"))
            except OperationalError as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    pass
                else:
                    logger.error(f"Unexpected OperationalError adding research_tasks {_col} column: {e}")
            except Exception as e:
                logger.error(f"Unexpected error adding research_tasks {_col} column: {e}")
        for _idx in [
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_status ON research_tasks (status)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_ticker ON research_tasks (ticker)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_created_at ON research_tasks (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_parent_task_id ON research_tasks (parent_task_id)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_run_id ON research_tasks (run_id)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_owner_agent_id ON research_tasks (owner_agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_assigned_agent_id ON research_tasks (assigned_agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_research_tasks_source_heartbeat_run_id ON research_tasks (source_heartbeat_run_id)",
        ]:
            try:
                await conn.execute(text(_idx))
            except OperationalError:
                pass
            except Exception as e:
                logger.error(f"Unexpected error creating research_tasks index: {e}")
        # Idempotent migration: investment_mandate singleton table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS investment_mandate (
                id TEXT PRIMARY KEY DEFAULT 'default',
                firm_name TEXT NOT NULL DEFAULT 'My Investment Firm',
                mandate_text TEXT NOT NULL DEFAULT '',
                benchmark TEXT NOT NULL DEFAULT 'S&P 500',
                target_return_pct REAL NOT NULL DEFAULT 12.0,
                max_position_pct REAL NOT NULL DEFAULT 5.0,
                max_sector_pct REAL NOT NULL DEFAULT 25.0,
                max_portfolio_beta REAL NOT NULL DEFAULT 1.3,
                max_drawdown_pct REAL NOT NULL DEFAULT 15.0,
                strategy_style TEXT NOT NULL DEFAULT 'blend',
                investment_horizon TEXT NOT NULL DEFAULT '12 months',
                restricted_tickers TEXT NOT NULL DEFAULT '[]',
                updated_at DATETIME NOT NULL
            )
        """))
        # Seed default row if the table is empty
        await conn.execute(text("""
            INSERT OR IGNORE INTO investment_mandate (id, updated_at)
            VALUES ('default', CURRENT_TIMESTAMP)
        """))


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
