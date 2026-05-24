"""System-level API routes."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Callable

from fastapi import APIRouter


def create_system_router(get_agents_cache_size: Callable[[], int]) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/health")
    async def health_check():
        """Detailed health check."""
        api_keys = {
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "financial_datasets": bool(os.getenv("FINANCIAL_DATASETS_API_KEY")),
            "tavily": bool(os.getenv("TAVILY_API_KEY")),
            "fred": bool(os.getenv("FRED_API_KEY")),
            "massive": bool(os.getenv("MASSIVE_API_KEY")),
        }

        return {
            "status": "healthy",
            "api_keys_configured": api_keys,
            "agents_cached": get_agents_cache_size(),
            "timestamp": datetime.now().isoformat(),
        }

    return router
