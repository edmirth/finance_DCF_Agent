"""
Pytest configuration and shared fixtures for the Finance DCF Agent test suite.
"""
from __future__ import annotations
import sys
import os
import pytest
import pytest_asyncio

# Ensure project root is on the path for all tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def run_db_migrations():
    """Run init_db() once per test session so schema migrations (ALTER TABLE) are applied."""
    from backend.database import init_db
    await init_db()
