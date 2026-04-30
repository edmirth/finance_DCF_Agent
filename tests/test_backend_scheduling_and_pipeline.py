from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.api_server import app
from backend.agent_runner import AgentRunnerService
from backend.database import AsyncSessionLocal
from backend.heartbeat_service import plan_manager_heartbeat_actions
from backend.investment_pipeline import InvestmentPipeline
from backend.models import AgentRun, ScheduledAgent, HireProposal, AgentRoutine, HeartbeatRun, ResearchTask
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
async def test_create_specialist_agent_defaults_to_cio_manager():
    payload = {
        "name": f"Semis {uuid4()}",
        "role_key": "semis_analyst",
        "tickers": ["AAPL"],
        "topics": ["moat"],
        "instruction": "Own the long-term fundamental work.",
        "schedule_label": "weekly_monday",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["role_key"] == "semis_analyst"
    assert body["role_title"] == "Semis Analyst"
    assert body["template"] == "fundamental_analyst"
    assert body["reports_to_label"] == "CIO"
    assert body["manager_agent_id"] is None
    assert body["heartbeat_routine"]["routine_type"] == "heartbeat"
    assert body["heartbeat_routine"]["schedule_label"] == "weekly_monday"


@pytest.mark.asyncio
async def test_create_scheduled_agent_with_manager_returns_manager_label():
    manager_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        manager = ScheduledAgent(
            id=manager_id,
            name=f"Lead {manager_id[:8]}",
            description=None,
            template="market_pulse",
            tickers="[]",
            topics="[]",
            instruction="Lead the desk",
            schedule_label="weekly_monday",
            manager_agent_id=None,
            delivery_email=None,
            delivery_inapp=True,
            is_active=True,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(manager)
        await db.commit()

    payload = {
        "name": f"Risk {uuid4()}",
        "role_key": "risk_manager",
        "tickers": ["NVDA"],
        "topics": [],
        "instruction": "Track revisions and momentum.",
        "schedule_label": "weekly_monday",
        "manager_agent_id": manager_id,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["role_key"] == "risk_manager"
    assert body["role_title"] == "Risk Manager"
    assert body["template"] == "risk_analyst"
    assert body["manager_agent_id"] == manager_id
    assert body["manager_agent_name"] == manager.name
    assert body["reports_to_label"] == manager.name


@pytest.mark.asyncio
async def test_create_scheduled_agent_rejects_unknown_manager():
    payload = {
        "name": f"Risk {uuid4()}",
        "role_key": "risk_manager",
        "tickers": ["TSLA"],
        "topics": [],
        "instruction": "Own downside surveillance.",
        "schedule_label": "weekly_monday",
        "manager_agent_id": str(uuid4()),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Manager agent not found"


@pytest.mark.asyncio
async def test_create_scheduled_agent_rejects_invalid_role_key():
    payload = {
        "name": f"Role {uuid4()}",
        "role_key": "not_a_real_role",
        "tickers": ["AAPL"],
        "topics": [],
        "instruction": "Test role validation.",
        "schedule_label": "weekly_monday",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 400
    assert "Invalid role_key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cio_chat_persists_hire_proposal():
    payload = {
        "messages": [
            {"role": "user", "content": "We need semis coverage for NVDA."},
        ]
    }

    mocked_response = {
        "message": "We have a semis coverage gap. I am proposing a dedicated seat.",
        "action": {
            "type": "propose_hire",
            "role_key": "semis_analyst",
            "role_title": "Semis Analyst",
            "name": f"Semis {uuid4()}",
            "description": "Own semiconductor coverage for the PM.",
            "tickers": ["NVDA"],
            "topics": ["AI demand"],
            "instruction": "Cover NVDA and track AI demand, pricing, and hyperscaler capex.",
            "schedule_label": "weekly_monday",
        },
    }

    with patch("backend.cio_router._cio_chat_sync", return_value=mocked_response):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/cio/chat", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["action"]["proposal_status"] == "pending"
    proposal_id = body["action"]["proposal_id"]
    assert proposal_id

    async with AsyncSessionLocal() as db:
        proposal = await db.get(HireProposal, proposal_id)

    assert proposal is not None
    assert proposal.status == "pending"
    assert proposal.role_key == "semis_analyst"


@pytest.mark.asyncio
async def test_cio_review_task_persists_hire_proposal():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_response = await client.post(
            "/projects",
            json={"title": "Semis Coverage", "thesis": "Review AI capex names."},
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/tasks",
            json={
                "ticker": "NVDA",
                "project_id": project_id,
                "title": "Review NVDA staffing",
                "notes": "Need the PM to decide coverage and staffing.",
            },
        )
        task_id = task_response.json()["id"]

    mocked_response = {
        "message": "This issue needs dedicated semiconductor coverage.",
        "action": {
            "type": "propose_hire",
            "role_key": "semis_analyst",
            "role_title": "Semis Analyst",
            "name": f"Semis {uuid4()}",
            "description": "Own semiconductor coverage for the PM.",
            "tickers": ["NVDA"],
            "topics": ["AI demand"],
            "instruction": "Cover NVDA and monitor AI demand, pricing power, and hyperscaler capex.",
            "schedule_label": "weekly_monday",
        },
    }

    with patch("backend.cio_router._cio_chat_sync", return_value=mocked_response):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/cio/review-task/{task_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["action"]["proposal_status"] == "pending"
    proposal_id = body["action"]["proposal_id"]
    assert proposal_id

    async with AsyncSessionLocal() as db:
        proposal = await db.get(HireProposal, proposal_id)

    assert proposal is not None
    assert proposal.status == "pending"
    assert proposal.proposed_by == f"issue:{task_id}"


@pytest.mark.asyncio
async def test_hire_proposal_approve_creates_agent():
    proposal_payload = {
        "action": {
            "type": "propose_hire",
            "role_key": "risk_manager",
            "role_title": "Risk Manager",
            "name": f"Risk {uuid4()}",
            "description": "Own downside surveillance.",
            "tickers": ["TSLA"],
            "topics": ["balance sheet"],
            "instruction": "Track downside scenarios, liquidity, and leverage.",
            "schedule_label": "weekly_monday",
        }
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post("/cio/hire-proposals", json=proposal_payload)

    assert create_response.status_code == 201
    proposal_id = create_response.json()["id"]

    with patch("backend.cio_router.register_agent_job"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            approve_response = await client.post(
                f"/cio/hire-proposals/{proposal_id}/approve",
                json={"decision_note": "Add this seat."},
            )

    assert approve_response.status_code == 200
    body = approve_response.json()
    assert body["proposal"]["status"] == "approved"
    assert body["proposal"]["decision_note"] == "Add this seat."
    assert body["agent"]["role_key"] == "risk_manager"
    assert body["agent"]["template"] == "risk_analyst"

    async with AsyncSessionLocal() as db:
        proposal = await db.get(HireProposal, proposal_id)
        agent = await db.get(ScheduledAgent, body["agent"]["id"])

    assert proposal is not None
    assert proposal.status == "approved"
    assert proposal.approved_agent_id == body["agent"]["id"]
    assert agent is not None
    assert agent.role_key == "risk_manager"


@pytest.mark.asyncio
async def test_hire_proposal_reject_marks_proposal_rejected():
    proposal_payload = {
        "action": {
            "type": "propose_hire",
            "role_key": "macro_strategist",
            "role_title": "Macro Strategist",
            "name": f"Macro {uuid4()}",
            "description": "Own the macro overlay.",
            "tickers": [],
            "topics": ["Fed"],
            "instruction": "Track rates, policy, and macro regime shifts.",
            "schedule_label": "weekly_monday",
        }
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post("/cio/hire-proposals", json=proposal_payload)

    assert create_response.status_code == 201
    proposal_id = create_response.json()["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        reject_response = await client.post(
            f"/cio/hire-proposals/{proposal_id}/reject",
            json={"decision_note": "Not needed right now."},
        )

    assert reject_response.status_code == 200
    body = reject_response.json()
    assert body["status"] == "rejected"
    assert body["decision_note"] == "Not needed right now."

    async with AsyncSessionLocal() as db:
        proposal = await db.get(HireProposal, proposal_id)

    assert proposal is not None
    assert proposal.status == "rejected"
    assert proposal.approved_agent_id is None


@pytest.mark.asyncio
async def test_manager_heartbeat_plans_task_and_delegated_run():
    manager_id = str(uuid4())
    report_id = str(uuid4())
    heartbeat_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        manager = ScheduledAgent(
            id=manager_id,
            name="PM Desk",
            description="Leads the desk",
            template="market_pulse",
            tickers='["QQQ"]',
            topics="[]",
            instruction="Own the desk",
            schedule_label="weekly_monday",
            delivery_email=None,
            delivery_inapp=True,
            is_active=True,
            created_at=created_at,
            updated_at=created_at,
        )
        report = ScheduledAgent(
            id=report_id,
            name="Semis Analyst",
            description="Own semis coverage",
            template="fundamental_analyst",
            tickers='["NVDA"]',
            topics="[]",
            instruction="Track demand and pricing.",
            schedule_label="weekly_monday",
            manager_agent_id=manager_id,
            delivery_email=None,
            delivery_inapp=True,
            is_active=True,
            created_at=created_at,
            updated_at=created_at,
        )
        heartbeat = HeartbeatRun(
            id=heartbeat_id,
            scheduled_agent_id=manager_id,
            trigger_type="scheduled",
            status="completed",
            summary="Manager heartbeat complete.",
            outcome_json="{}",
            started_at=created_at,
            completed_at=created_at,
        )
        db.add(manager)
        db.add(report)
        db.add(heartbeat)
        await db.commit()

        dispatches = await plan_manager_heartbeat_actions(db, manager, heartbeat)
        await db.commit()

        task_result = await db.execute(
            select(ResearchTask).where(
                ResearchTask.owner_agent_id == manager_id,
                ResearchTask.assigned_agent_id == report_id,
            )
        )
        task = task_result.scalar_one_or_none()

    assert len(dispatches) == 1
    assert dispatches[0]["agent_id"] == report_id
    assert dispatches[0]["linked_task_id"] == task.id
    assert task is not None
    assert task.ticker == "NVDA"
    assert task.triggered_by == "manager_heartbeat"
    assert task.owner_agent_id == manager_id
    assert task.assigned_agent_id == report_id
    assert task.status == "running"


@pytest.mark.asyncio
async def test_delegated_run_updates_assigned_research_task():
    agent_id = str(uuid4())
    run_id = str(uuid4())
    heartbeat_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        agent = ScheduledAgent(
            id=agent_id,
            name="Risk Manager",
            description=None,
            template="risk_analyst",
            tickers='["TSLA"]',
            topics="[]",
            instruction="Watch downside risk.",
            schedule_label="market_open",
            delivery_email=None,
            delivery_inapp=True,
            is_active=True,
            next_run_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            created_at=created_at,
            updated_at=created_at,
        )
        task = ResearchTask(
            id=task_id,
            ticker="TSLA",
            task_type="risk_review",
            title="Risk follow-up",
            status="running",
            priority="high",
            selected_agents='["risk"]',
            owner_agent_id=None,
            assigned_agent_id=agent_id,
            triggered_by="manager_heartbeat",
            created_at=created_at,
            started_at=created_at,
            updated_at=created_at,
        )
        run = AgentRun(
            id=run_id,
            scheduled_agent_id=agent_id,
            status="running",
            started_at=created_at,
        )
        heartbeat = HeartbeatRun(
            id=heartbeat_id,
            scheduled_agent_id=agent_id,
            agent_run_id=run_id,
            trigger_type="delegated",
            status="running",
            started_at=created_at,
        )
        db.add(agent)
        db.add(task)
        db.add(run)
        db.add(heartbeat)
        await db.commit()

    class FakeRunner:
        def execute(self, _snapshot):
            return {
                "report": "ok",
                "findings_summary": "Risk flags updated",
                "key_findings": ["Liquidity remains acceptable."],
                "material_change": False,
                "alert_level": "low",
                "tickers_analyzed": ["TSLA"],
                "agents_used": ["risk"],
                "error": None,
            }

    config_data = {
        "id": agent_id,
        "name": "Risk Manager",
        "template": "risk_analyst",
        "tickers": ["TSLA"],
        "topics": [],
        "instruction": "Watch downside risk.",
        "schedule_label": "market_open",
        "delivery_email": None,
        "last_run_summary": None,
    }

    with patch("backend.agent_runner.get_runner", return_value=FakeRunner()):
        await _execute_run_background(
            run_id,
            agent_id,
            config_data,
            heartbeat_id,
            "delegated",
            task_id,
        )

    async with AsyncSessionLocal() as db:
        refreshed_task = await db.get(ResearchTask, task_id)
        refreshed_heartbeat = await db.get(HeartbeatRun, heartbeat_id)

    assert refreshed_task is not None
    assert refreshed_task.status == "in_review"
    assert refreshed_task.run_id == run_id
    assert "risk" in (refreshed_task.completed_agents or "")
    assert refreshed_heartbeat is not None
    assert refreshed_heartbeat.status == "completed"


def test_agent_runner_executes_specialist_template():
    runner = AgentRunnerService()
    config = SimpleNamespace(
        template="fundamental_analyst",
        tickers='["AAPL"]',
        topics="[]",
        instruction="Own the core coverage.",
        last_run_summary="",
    )

    fake_section = SimpleNamespace(
        title="Fundamental Analysis",
        sentiment="bullish",
        confidence=0.76,
        key_points=["Revenue growth remains healthy.", "Margins are stabilizing."],
        content="Detailed fundamental write-up.",
        error=None,
    )

    with (
        patch("backend.research_orchestrator.run_specialist_agent_once", return_value=fake_section),
        patch.object(
            AgentRunnerService,
            "_synthesize",
            return_value={
                "full_report": "report",
                "summary": "summary",
                "key_findings": ["Revenue growth remains healthy."],
                "material_change": True,
                "alert_level": "medium",
            },
        ),
    ):
        outcome = runner.execute(config)

    assert outcome["error"] is None
    assert outcome["agents_used"] == ["fundamental"]
    assert outcome["tickers_analyzed"] == ["AAPL"]
    assert outcome["findings_summary"] == "summary"


@pytest.mark.asyncio
async def test_create_scheduled_agent_rejects_removed_arena_template():
    payload = {
        "name": f"Removed arena {uuid4()}",
        "template": "arena_analyst",
        "tickers": ["AAPL"],
        "topics": [],
        "instruction": "Run the old arena flow",
        "schedule_label": "weekly_monday",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scheduled-agents", json=payload)

    assert response.status_code == 400
    assert "Invalid template" in response.json()["detail"]


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
async def test_public_agent_catalog_excludes_arena():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/agents")

    assert response.status_code == 200
    ids = [agent["id"] for agent in response.json()["agents"]]
    assert "arena" not in ids


@pytest.mark.asyncio
async def test_root_health_agent_list_excludes_arena(monkeypatch):
    monkeypatch.setattr("backend.api_server.FRONTEND_BUILD_DIR", "/tmp/codex-no-frontend-build")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "arena" not in response.json()["agents"]


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
        routine_result = await db.execute(
            select(AgentRoutine).where(AgentRoutine.scheduled_agent_id == agent_id)
        )
        heartbeat_result = await db.execute(
            select(HeartbeatRun).where(HeartbeatRun.agent_run_id == run_id)
        )
        routine = routine_result.scalar_one_or_none()
        heartbeat_run = heartbeat_result.scalar_one_or_none()

    assert refreshed_run is not None
    assert refreshed_run.status == "completed"
    assert refreshed_agent is not None
    assert refreshed_agent.last_run_status == "completed"
    assert refreshed_agent.next_run_at is not None
    assert refreshed_agent.next_run_at.year != 2000
    assert routine is not None
    assert routine.routine_type == "heartbeat"
    assert routine.last_run_status == "completed"
    assert heartbeat_run is not None
    assert heartbeat_run.trigger_type == "manual"
    assert heartbeat_run.status == "completed"
    assert heartbeat_run.agent_routine_id == routine.id
