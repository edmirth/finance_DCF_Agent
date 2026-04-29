from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api_server import app
from backend.database import AsyncSessionLocal
from backend.investment_pipeline import InvestmentPipeline
from backend.models import AgentRun, ScheduledAgent
from backend.scheduled_agents_router import _execute_run_background
from backend.scheduler import next_run_time


def test_next_run_time_market_open_uses_market_timezone():
    reference = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)

    actual = next_run_time("market_open", now=reference)

    assert actual == datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)


def test_investment_pipeline_blocks_when_mandate_cannot_load():
    class FakeOrchestrator:
        def __init__(self, *args, **kwargs):
            self.task_id = "task-1"

        def run(self):
            return {
                "sections": {
                    "fundamental": {
                        "title": "Fundamental",
                        "sentiment": "bullish",
                        "confidence": 0.7,
                        "key_points": ["Revenue growth remains strong."],
                    },
                    "risk": {
                        "title": "Risk",
                        "sentiment": "neutral",
                        "confidence": 0.6,
                        "key_points": ["Balance sheet is acceptable."],
                    },
                },
                "synthesis": {"summary": "Initial research completed."},
            }

    events: list[dict] = []
    pipeline = InvestmentPipeline(
        run_id="run-1",
        ticker="AAPL",
        selected_agents=["fundamental", "risk"],
        emit_fn=events.append,
        task_id="task-1",
    )

    with (
        patch("backend.investment_pipeline.ResearchOrchestrator", FakeOrchestrator),
        patch.object(InvestmentPipeline, "_load_mandate", return_value=({}, "database offline")),
        patch.object(InvestmentPipeline, "_persist_pipeline_results"),
    ):
        result = pipeline.run()

    assert result["risk_verdict"]["verdict"] == "vetoed"
    assert result["compliance_verdict"]["verdict"] == "blocked"
    assert result["pm_decision"]["action"] == "HOLD"
    assert result["pm_decision"]["blocked"] is True
    assert "MANDATE UNAVAILABLE" in result["pm_decision"]["rationale"]
    assert any(
        event.get("type") == "stage_complete" and event.get("stage") == "pm_decision"
        for event in events
    )


@pytest.mark.asyncio
async def test_create_scheduled_agent_rejects_missing_tickers_for_pipeline_templates():
    payload = {
        "name": f"Pipeline {uuid4()}",
        "template": "firm_pipeline",
        "tickers": [],
        "topics": [],
        "instruction": "Run the full pipeline",
        "schedule_label": "weekly_monday",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 400
    assert "requires at least one ticker" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_scheduled_agent_rejects_invalid_schedule_label():
    payload = {
        "name": f"Bad schedule {uuid4()}",
        "template": "market_pulse",
        "tickers": [],
        "topics": [],
        "instruction": "Daily market pulse",
        "schedule_label": "not_a_real_schedule",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 400
    assert "Invalid schedule_label" in response.json()["detail"]


@pytest.mark.asyncio
async def test_install_firm_routine_rejects_empty_tickers_for_pipeline_routine():
    payload = {
        "catalog_id": "weekly_ic",
        "tickers": [],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/firm/routines/install", json=payload)

    assert response.status_code == 400
    assert "requires at least one ticker" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_run_updates_next_run_at():
    agent_id = str(uuid4())
    run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        agent = ScheduledAgent(
            id=agent_id,
            name=f"Runner {agent_id[:8]}",
            description=None,
            template="market_pulse",
            tickers="[]",
            topics="[]",
            instruction="Pulse",
            schedule_label="market_open",
            delivery_email=None,
            delivery_inapp=True,
            is_active=True,
            next_run_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            created_at=created_at,
            updated_at=created_at,
        )
        run = AgentRun(
            id=run_id,
            scheduled_agent_id=agent_id,
            status="running",
            started_at=created_at,
        )
        db.add(agent)
        db.add(run)
        await db.commit()

    class FakeRunner:
        def execute(self, _snapshot):
            return {
                "report": "ok",
                "findings_summary": "complete",
                "key_findings": ["one"],
                "material_change": False,
                "alert_level": "none",
                "tickers_analyzed": [],
                "agents_used": ["market"],
                "error": None,
            }

    config_data = {
        "id": agent_id,
        "name": "Runner",
        "template": "market_pulse",
        "tickers": [],
        "topics": [],
        "instruction": "Pulse",
        "schedule_label": "market_open",
        "delivery_email": None,
        "last_run_summary": None,
    }

    with patch("backend.agent_runner.get_runner", return_value=FakeRunner()):
        await _execute_run_background(run_id, agent_id, config_data)

    async with AsyncSessionLocal() as db:
        refreshed_agent = await db.get(ScheduledAgent, agent_id)
        refreshed_run = await db.get(AgentRun, run_id)

    assert refreshed_run is not None
    assert refreshed_run.status == "completed"
    assert refreshed_agent is not None
    assert refreshed_agent.last_run_status == "completed"
    assert refreshed_agent.next_run_at is not None
    assert refreshed_agent.next_run_at.year != 2000
