"""
Pytest configuration and shared fixtures for the Finance DCF Agent test suite.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
import pytest
import pytest_asyncio

# Force tests onto an isolated SQLite database before any backend modules import
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TEST_DB_PATH = _PROJECT_ROOT / f"finance_agent_test_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
if _TEST_DB_PATH.exists():
    _TEST_DB_PATH.unlink()

# Ensure project root is on the path for all tests
sys.path.insert(0, str(_PROJECT_ROOT))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def run_db_migrations():
    """Run init_db() once per test session so schema migrations (ALTER TABLE) are applied."""
    from backend.database import init_db
    await init_db()
    yield
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
