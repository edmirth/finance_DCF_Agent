"""Core API routes that do not depend on runtime orchestration."""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse


def create_core_router(frontend_build_dir: str) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def root():
        """Serve frontend or health check."""
        index_path = os.path.join(frontend_build_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return {
            "status": "online",
            "service": "Financial Analysis API",
            "version": "1.0.0",
            "agents": ["research", "market", "portfolio", "earnings"],
        }

    @router.get("/agents")
    async def list_agents():
        """List available legacy chat agents."""
        return {
            "agents": [
                {
                    "id": "research",
                    "name": "Finance Q&A",
                    "description": (
                        "Your personal equity analyst. Ask about any stock — get a quick brief, then dig into "
                        "valuation, earnings, competitive position, SEC filings, or management commentary."
                    ),
                    "example": "I'm looking at NVDA — what should I know?",
                },
                {
                    "id": "market",
                    "name": "Market Analyst",
                    "description": "Market conditions, sentiment, and sector analysis",
                    "example": "What's the current market sentiment?",
                },
                {
                    "id": "portfolio",
                    "name": "Portfolio Analyzer",
                    "description": "Portfolio analysis with metrics, diversification, and tax optimization",
                    "example": (
                        "Analyze my portfolio: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, "
                        "{'ticker': 'MSFT', 'shares': 50, 'cost_basis': 250.00}]"
                    ),
                },
                {
                    "id": "earnings",
                    "name": "Earnings Analyst",
                    "description": "Fast earnings-focused equity research (15 min) with quarterly trends and estimates",
                    "example": "Analyze NVDA's latest earnings and forward outlook",
                },
            ]
        }

    return router
