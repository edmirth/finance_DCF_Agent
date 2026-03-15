"""
Async SQLAlchemy database engine and session factory.
Supports SQLite (default) and PostgreSQL (set DATABASE_URL env var).
"""
import os
import logging
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

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
        except OperationalError:
            pass  # Column already exists
        except Exception as e:
            logger.error(f"Unexpected error adding chart_specs column: {e}")
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


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
