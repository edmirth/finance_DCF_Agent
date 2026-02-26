"""
Async SQLAlchemy database engine and session factory.
Supports SQLite (default) and PostgreSQL (set DATABASE_URL env var).
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

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


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
