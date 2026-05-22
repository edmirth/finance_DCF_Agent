from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend import cio_router
from backend.api_server import app, ResearchConnectionManager
from backend.database import AsyncSessionLocal, SyncSessionLocal
from backend.models import AgentRun, HeartbeatRun, ResearchTask, ResearchTaskDocument, ResearchTaskMessage, ScheduledAgent
from backend.research_orchestrator import (
    ResearchOrchestrator,
    _create_minimal_state,
    run_specialist_agent_once,
)


@pytest.mark.asyncio
async def test_research_start_normalizes_and_dedupes_selected_agents(monkeypatch):
    captured: dict = {}

    class DummyResearchOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            return {}

    monkeypatch.setattr("backend.api_server.ResearchOrchestrator", DummyResearchOrchestrator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/research/start",
            json={
                "ticker": "aapl",
                "agents": [" risk ", "DCF", "risk"],
                "title": "Check drawdown setup",
                "focus": "Concentrate on downside from margin compression.",
            },
        )

    assert response.status_code == 200
    await asyncio.sleep(0)
    assert captured["ticker"] == "AAPL"
    assert captured["selected_agents"] == ["risk", "dcf"]
    assert captured["assignment_title"] == "Check drawdown setup"
    assert captured["assignment_focus"] == "Concentrate on downside from margin compression."


@pytest.mark.asyncio
async def test_research_start_rejects_invalid_agents():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/research/start",
            json={"ticker": "AAPL", "agents": ["bogus"]},
        )

    assert response.status_code == 400
    assert "Invalid agents" in response.json()["detail"]


@pytest.mark.asyncio
async def test_research_start_rejects_explicit_empty_agent_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/research/start",
            json={"ticker": "AAPL", "agents": []},
        )

    assert response.status_code == 400
    assert "At least one valid agent must be selected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_research_start_rejects_invalid_ticker_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/research/start",
            json={"ticker": "apple inc", "agents": ["risk"]},
        )

    assert response.status_code == 400
    assert "Invalid ticker format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_normalizes_and_dedupes_selected_agents():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={
                "ticker": "aapl",
                "selected_agents": [" fundamental ", "DCF", "dcf"],
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["selected_agents"] == ["fundamental", "dcf"]


@pytest.mark.asyncio
async def test_create_task_without_selected_agents_remains_unstaffed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 201
    assert response.json()["selected_agents"] == []


@pytest.mark.asyncio
async def test_create_task_with_direct_assignee_dispatches_agent_run():
    agent_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/tasks",
                json={
                    "ticker": "AAPL",
                    "title": "Direct analyst assignment",
                    "assigned_agent_id": agent_id,
                    "triggered_by": "manual_assignment",
                },
            )

    assert response.status_code == 201
    body = response.json()
    assert body["assigned_agent_id"] == agent_id
    assert body["status"] == "running"
    assert body["run_id"]

    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, body["run_id"])
        docs_result = await db.execute(
            select(ResearchTaskDocument).where(ResearchTaskDocument.task_id == body["id"])
        )
        plan_documents = docs_result.scalars().all()
        chat_result = await db.execute(
            select(ResearchTaskMessage).where(
                ResearchTaskMessage.task_id == body["id"],
                ResearchTaskMessage.kind == "chat",
                ResearchTaskMessage.role == "assistant",
            )
        )
        assistant_messages = chat_result.scalars().all()

    assert run is not None
    assert run.status == "running"
    assert run.scheduled_agent_id == agent_id
    assert any(doc.document_type == "plan" for doc in plan_documents)
    assert any("execution plan" in (doc.title or "").lower() for doc in plan_documents)
    assert any("started the first pass on this issue" in message.content.lower() for message in assistant_messages)
    assert any("documents" in message.content.lower() for message in assistant_messages)
    assert any(
        message.metadata_json
        and "issue_plan_created" in message.metadata_json
        and "steps" in message.metadata_json
        and "objective" in message.metadata_json
        for message in assistant_messages
    )


@pytest.mark.asyncio
async def test_create_task_with_direct_assignee_resolves_broad_scope_and_dispatches(monkeypatch):
    agent_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    captured: dict[str, object] = {}

    def fake_execute_run_background(
        run_id: str,
        agent_id: str,
        config_data: dict,
        heartbeat_run_id=None,
        trigger_type: str = "manual",
        linked_task_id=None,
    ):
        captured["run_id"] = run_id
        captured["agent_id"] = agent_id
        captured["config_data"] = config_data
        async def _noop() -> None:
            return None
        return _noop()

    async def fake_resolve_scope(task, agent):
        return {
            "tickers": ["NVDA", "PLTR", "AMZN"],
            "source": "llm",
            "rationale": "Representative AI beneficiaries.",
        }

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    monkeypatch.setattr("backend.cio_router._resolve_task_scope_for_agent", fake_resolve_scope)
    monkeypatch.setattr("backend.scheduled_agents_router._execute_run_background", fake_execute_run_background)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post(
                "/tasks",
                json={
                    "title": "Analyze the AI value chain",
                    "assigned_agent_id": agent_id,
                    "triggered_by": "manual_assignment",
                },
            )

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "GENERAL"
    assert body["assigned_agent_id"] == agent_id
    assert body["status"] == "running"
    assert body["run_id"] is not None
    assert body["error"] is None
    assert captured["config_data"]["tickers"] == ["NVDA", "PLTR", "AMZN"]
    assert "Analyze the listed companies as the working scope for this issue." in captured["config_data"]["instruction"]
    assert "Resolved scope: NVDA, PLTR, AMZN" in captured["config_data"]["instruction"]


@pytest.mark.asyncio
async def test_create_task_accepts_valid_project_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_response = await client.post(
            "/projects",
            json={"title": "Semis Coverage", "thesis": "Track the AI capex chain."},
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            "/tasks",
            json={"ticker": "NVDA", "project_id": project_id},
        )

    assert response.status_code == 201
    assert response.json()["project_id"] == project_id


@pytest.mark.asyncio
async def test_create_task_rejects_invalid_project_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={"ticker": "AAPL", "project_id": "missing-project"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid project_id"


@pytest.mark.asyncio
async def test_create_task_rejects_invalid_ticker_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={"ticker": "apple inc"},
        )

    assert response.status_code == 400
    assert "Invalid ticker format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_allows_missing_ticker_and_defaults_to_general():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={"title": "Analyze AI value chain"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "GENERAL"
    assert body["title"] == "Analyze AI value chain"


@pytest.mark.asyncio
async def test_create_task_infers_ticker_from_title_when_missing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={"title": "Do an analysis on Palantir for me"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "PLTR"


def test_run_specialist_agent_once_blocks_when_shared_data_is_missing():
    section = run_specialist_agent_once(
        "fundamental",
        "AAPL",
        assignment_title="Fundamental coverage",
        shared_data={},
    )

    assert section.error is not None
    assert "critical financial data is missing" in section.error.lower()
    assert section.content == ""
    assert section.key_points == []


@pytest.mark.asyncio
async def test_list_tasks_can_filter_by_agent_id():
    agent_id = f"agent-filter-{uuid4()}"
    other_agent_id = f"agent-filter-{uuid4()}"

    async with AsyncSessionLocal() as db:
        created_at = datetime.now(timezone.utc)
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover assigned issues.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ScheduledAgent(
                id=other_agent_id,
                name="Risk Manager",
                description="Risk coverage",
                template="risk_analyst",
                role_key="risk_manager",
                role_title="Risk Manager",
                role_family="risk",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover assigned issues.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assigned = await client.post(
            "/tasks",
            json={
                "title": "Assigned to agent",
                "assigned_agent_id": agent_id,
            },
        )
        owned = await client.post(
            "/tasks",
            json={
                "title": "Owned by agent",
                "owner_agent_id": agent_id,
            },
        )
        unrelated = await client.post(
            "/tasks",
            json={
                "title": "Unrelated task",
                "assigned_agent_id": other_agent_id,
            },
        )
        response = await client.get("/tasks", params={"agent_id": agent_id, "limit": 50})

    assert assigned.status_code == 201
    assert owned.status_code == 201
    assert unrelated.status_code == 201
    assert response.status_code == 200
    titles = {task["title"] for task in response.json()["tasks"]}
    assert "Assigned to agent" in titles
    assert "Owned by agent" in titles
    assert "Unrelated task" not in titles


@pytest.mark.asyncio
async def test_refresh_task_work_queue_requeues_unassigned_pending_issue():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/tasks",
            json={"title": "Route this issue through the CEO"},
        )
        task_id = create_response.json()["id"]

        queued: list[str] = []

        with patch("backend.cio_router.queue_cio_review_for_task", side_effect=lambda task_id: queued.append(task_id)):
            response = await client.post("/tasks/refresh-work")

    assert response.status_code == 200
    body = response.json()
    assert body["queued_for_ceo"] >= 1
    assert task_id in queued


@pytest.mark.asyncio
async def test_refresh_task_work_queue_moves_ceo_answered_pending_issue_to_review():
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ResearchTask(
                id=task_id,
                ticker="GENERAL",
                task_type="ad_hoc",
                title="CEO already answered this",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=None,
                source_heartbeat_run_id=None,
                triggered_by="manual_pm_review",
                notes="CEO already looked at this",
                status="pending",
                run_id=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTaskMessage(
                id=str(uuid4()),
                task_id=task_id,
                kind="chat",
                role="assistant",
                author_label="CEO",
                author_agent_id=None,
                content="I'll answer this directly as CEO.",
                metadata_json=json.dumps({"event": "ceo_review_completed"}),
                created_at=created_at,
            )
        )
        await db.commit()

    queued: list[str] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.queue_cio_review_for_task", side_effect=lambda value: queued.append(value)):
            response = await client.post("/tasks/refresh-work")

    assert response.status_code == 200
    body = response.json()
    assert body["moved_to_review"] >= 1
    assert body["tasks_moved_to_done"] >= 1
    assert task_id not in queued

    async with AsyncSessionLocal() as db:
        task = await db.get(ResearchTask, task_id)

    assert task is not None
    assert task.status == "done"
    assert task.error is None


@pytest.mark.asyncio
async def test_refresh_task_work_queue_redispatches_assigned_pending_issue():
    agent_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="AAPL",
                task_type="ad_hoc",
                title="Restart this analyst issue",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_assignment",
                notes="Restart the work",
                status="pending",
                run_id=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post("/tasks/refresh-work")

    assert response.status_code == 200
    body = response.json()
    assert body["redispatched"] >= 1

    async with AsyncSessionLocal() as db:
        task = await db.get(ResearchTask, task_id)

    assert task is not None
    assert task.status == "running"
    assert task.run_id is not None


@pytest.mark.asyncio
async def test_refresh_task_work_queue_recovers_stale_running_issue_then_redispatches():
    agent_id = str(uuid4())
    task_id = str(uuid4())
    stale_run_id = str(uuid4())
    stale_heartbeat_id = str(uuid4())
    created_at = datetime.now(timezone.utc) - timedelta(hours=3)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            AgentRun(
                id=stale_run_id,
                scheduled_agent_id=agent_id,
                status="running",
                started_at=created_at,
            )
        )
        db.add(
            HeartbeatRun(
                id=stale_heartbeat_id,
                scheduled_agent_id=agent_id,
                agent_run_id=stale_run_id,
                trigger_type="manual",
                status="running",
                started_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="AAPL",
                task_type="ad_hoc",
                title="Recover this stale analyst issue",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_assignment",
                notes="Restart the stale work",
                status="running",
                run_id=stale_run_id,
                created_at=created_at,
                started_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post("/tasks/refresh-work")

    assert response.status_code == 200
    body = response.json()
    assert body["stale_runs_recovered"] >= 1
    assert body["tasks_returned_to_queue"] >= 1
    assert body["redispatched"] >= 1

    async with AsyncSessionLocal() as db:
        old_run = await db.get(AgentRun, stale_run_id)
        stale_heartbeat = await db.get(HeartbeatRun, stale_heartbeat_id)
        task = await db.get(ResearchTask, task_id)

    assert old_run is not None
    assert old_run.status == "failed"
    assert old_run.completed_at is not None
    assert stale_heartbeat is not None
    assert stale_heartbeat.status == "failed"
    assert task is not None
    assert task.status == "running"
    assert task.run_id is not None
    assert task.run_id != stale_run_id


@pytest.mark.asyncio
async def test_refresh_task_work_queue_backfills_scope_for_review_issue_and_redispatches():
    agent_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Equity Research Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="equity_research_analyst",
                role_title="Equity Research Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="GENERAL",
                task_type="ad_hoc",
                title="Do an analysis on apple",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_assignment",
                notes="No issue brief yet.",
                status="in_review",
                run_id=None,
                error="Equity Research Analyst needs an explicit ticker or company scope before it can start. Update the issue with a concrete company or symbol, then dispatch it again.",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post("/tasks/refresh-work")

    assert response.status_code == 200
    body = response.json()
    assert body["redispatched"] >= 1

    async with AsyncSessionLocal() as db:
        task = await db.get(ResearchTask, task_id)

    assert task is not None
    assert task.ticker == "AAPL"
    assert task.error is None
    assert task.status == "running"
    assert task.run_id is not None


@pytest.mark.asyncio
async def test_run_task_now_closes_scope_blocked_issue_when_ceo_already_answered():
    agent_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["GENERAL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="GENERAL",
                task_type="ad_hoc",
                title="Hire my first analyst",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_pm_review",
                notes="Need coverage guidance.",
                status="in_review",
                run_id=None,
                error="Generalist Analyst needs an explicit ticker or company scope before it can start. Update the issue with a concrete company or symbol, then dispatch it again.",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTaskMessage(
                id=str(uuid4()),
                task_id=task_id,
                kind="chat",
                role="assistant",
                author_label="CEO",
                author_agent_id=None,
                content="We already have active coverage for this.",
                metadata_json=json.dumps({"event": "ceo_review_completed"}),
                created_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/tasks/{task_id}/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "completed"
    assert body["run_id"] is None
    assert body["task"]["status"] == "done"

    async with AsyncSessionLocal() as db:
        task = await db.get(ResearchTask, task_id)

    assert task is not None
    assert task.status == "done"
    assert task.error is None


@pytest.mark.asyncio
async def test_task_chat_creates_issue_thread_messages(monkeypatch):
    async def fake_reply(db, task, prompt, *, target_agent_id, thread_messages):
        return {
            "author_label": "CEO",
            "author_agent_id": None,
            "content": f"Replying to: {prompt}",
            "action": None,
        }

    monkeypatch.setattr("backend.api_server._run_task_chat_reply", fake_reply)
    monkeypatch.setattr("backend.cio_router.queue_cio_review_for_task", lambda _task_id: None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task_response = await client.post("/tasks", json={"title": "Analyze the AI stack"})
        task_id = task_response.json()["id"]

        response = await client.post(
            f"/tasks/{task_id}/chat",
            json={"content": "Go deeper on which names matter first."},
        )
        messages = await client.get(f"/tasks/{task_id}/messages", params={"kind": "chat"})

    assert response.status_code == 200
    body = response.json()
    assert body["assistant_message"]["author_label"] == "CEO"
    assert "Go deeper" in body["assistant_message"]["content"]
    assert messages.status_code == 200
    assert len(messages.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_task_chat_uses_issue_documents_when_live_agent_reply_fails():
    agent_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover assigned issues.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            task_response = await client.post(
                "/tasks",
                json={
                    "title": "Apple follow-up",
                    "ticker": "AAPL",
                    "assigned_agent_id": agent_id,
                },
            )
            task_id = task_response.json()["id"]
            await client.post(
                f"/tasks/{task_id}/documents",
                json={
                    "title": "Apple report",
                    "content_md": "# Apple report\n\nRevenue growth stayed resilient despite FX pressure.",
                    "document_type": "brief",
                },
            )

            with patch(
                "backend.api_server._anthropic_text_response_sync",
                side_effect=RuntimeError("provider offline"),
            ):
                response = await client.post(
                    f"/tasks/{task_id}/chat",
                    json={"content": "Any report made here on the apple stock?"},
                )

    assert response.status_code == 200
    assistant_message = response.json()["assistant_message"]["content"]
    assert "Apple report" in assistant_message
    assert "Open the Documents tab" in assistant_message


@pytest.mark.asyncio
async def test_task_chat_answers_status_from_issue_state_without_live_model():
    agent_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover assigned issues.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            task_response = await client.post(
                "/tasks",
                json={
                    "title": "Apple status check",
                    "ticker": "AAPL",
                    "assigned_agent_id": agent_id,
                },
            )
            task_id = task_response.json()["id"]

            with patch(
                "backend.api_server._anthropic_text_response_sync",
                side_effect=AssertionError("live model should not be called for status query"),
            ):
                response = await client.post(
                    f"/tasks/{task_id}/chat",
                    json={"content": "status?"},
                )

    assert response.status_code == 200
    assistant_message = response.json()["assistant_message"]["content"]
    assert "Issue status: running." in assistant_message
    assert "Linked run status: running." in assistant_message


@pytest.mark.asyncio
async def test_task_documents_round_trip():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task_response = await client.post("/tasks", json={"title": "Draft semis overview"})
        task_id = task_response.json()["id"]

        created = await client.post(
            f"/tasks/{task_id}/documents",
            json={
                "title": "Semis market map",
                "content_md": "# Semis\n\nStart here.",
                "document_type": "brief",
            },
        )
        document_id = created.json()["id"]
        updated = await client.patch(
            f"/tasks/{task_id}/documents/{document_id}",
            json={"content_md": "# Semis\n\nUpdated body."},
        )
        listed = await client.get(f"/tasks/{task_id}/documents")

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert listed.status_code == 200
    assert listed.json()["documents"][0]["title"] == "Semis market map"


@pytest.mark.asyncio
async def test_task_related_work_returns_parent_children_and_project_peers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_response = await client.post(
            "/projects",
            json={"title": "AI Infra", "thesis": "Track the capex chain"},
        )
        project_id = project_response.json()["id"]

        parent = await client.post(
            "/tasks",
            json={"title": "Parent issue", "project_id": project_id},
        )
        parent_id = parent.json()["id"]
        child = await client.post(
            "/tasks",
            json={"title": "Child issue", "parent_task_id": parent_id, "project_id": project_id},
        )
        peer = await client.post(
            "/tasks",
            json={"title": "Peer issue", "project_id": project_id},
        )

        response = await client.get(f"/tasks/{parent_id}/related-work")

    assert child.status_code == 201
    assert peer.status_code == 201
    assert response.status_code == 200
    body = response.json()
    assert {task["title"] for task in body["sub_issues"]} == {"Child issue"}
    assert {task["title"] for task in body["same_project_issues"]} >= {"Child issue", "Peer issue"}


@pytest.mark.asyncio
async def test_create_task_rejects_explicit_empty_agent_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/tasks",
            json={"ticker": "AAPL", "selected_agents": []},
        )

    assert response.status_code == 400
    assert "At least one valid agent must be selected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_research_pm_suggest_rejects_invalid_ticker_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/research/pm-suggest",
            json={"ticker": "apple inc"},
        )

    assert response.status_code == 400
    assert "Invalid ticker format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_run_task_pipeline_rejects_invalid_saved_selected_agents():
    async with AsyncSessionLocal() as db:
        task = ResearchTask(
            ticker="AAPL",
            task_type="ad_hoc",
            title="Bad selected agents",
            selected_agents='["bogus"]',
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/tasks/{task_id}/run")

    assert response.status_code == 400
    assert "invalid selected_agents" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_run_task_now_dispatches_assigned_issue_even_from_review():
    agent_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Equity Research Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="equity_research_analyst",
                role_title="Equity Research Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="AAPL",
                task_type="ad_hoc",
                title="Run now from review",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_assignment",
                notes="Start this issue now",
                status="in_review",
                run_id=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post(f"/tasks/{task_id}/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "dispatch"
    assert body["task"]["status"] == "running"
    assert body["run_id"] is not None
    assert body["skipped"] is False

    async with AsyncSessionLocal() as db:
        task = await db.get(ResearchTask, task_id)
        run = await db.get(AgentRun, body["run_id"])

    assert task is not None
    assert task.status == "running"
    assert task.run_id == body["run_id"]
    assert run is not None
    assert run.status == "running"
    assert run.scheduled_agent_id == agent_id


@pytest.mark.asyncio
async def test_run_task_now_resolves_broad_scope_for_assigned_issue(monkeypatch):
    agent_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    captured: dict[str, object] = {}

    def fake_execute_run_background(
        run_id: str,
        agent_id: str,
        config_data: dict,
        heartbeat_run_id=None,
        trigger_type: str = "manual",
        linked_task_id=None,
    ):
        captured["run_id"] = run_id
        captured["config_data"] = config_data
        async def _noop() -> None:
            return None
        return _noop()

    async def fake_resolve_scope(task, agent):
        return {
            "tickers": ["NVDA", "PLTR", "AMZN"],
            "source": "llm",
            "rationale": "Representative AI beneficiaries.",
        }

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Generalist Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="generalist_analyst",
                role_title="Generalist Analyst",
                role_family="coverage",
                tickers='["GENERAL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="GENERAL",
                task_type="ad_hoc",
                title="Analyze the AI value chain",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_assignment",
                notes="Find the public companies most exposed to the AI wave.",
                status="in_review",
                run_id=None,
                error="Generalist Analyst needs an explicit ticker or company scope before it can start.",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    monkeypatch.setattr("backend.cio_router._resolve_task_scope_for_agent", fake_resolve_scope)
    monkeypatch.setattr("backend.scheduled_agents_router._execute_run_background", fake_execute_run_background)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post(f"/tasks/{task_id}/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "dispatch"
    assert body["task"]["status"] == "running"
    assert body["task"]["assigned_agent_id"] == agent_id
    assert body["run_id"] is not None
    assert captured["config_data"]["tickers"] == ["NVDA", "PLTR", "AMZN"]
    assert "Resolved scope: NVDA, PLTR, AMZN" in captured["config_data"]["instruction"]


@pytest.mark.asyncio
async def test_run_task_now_dispatches_assigned_issue_even_from_done():
    agent_id = str(uuid4())
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ScheduledAgent(
                id=agent_id,
                name="Equity Research Analyst",
                description="General coverage",
                template="fundamental_analyst",
                role_key="equity_research_analyst",
                role_title="Equity Research Analyst",
                role_family="coverage",
                tickers='["AAPL"]',
                topics="[]",
                instruction="Cover the issue and return a concise brief.",
                schedule_label="weekly_monday",
                delivery_email=None,
                delivery_inapp=True,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.add(
            ResearchTask(
                id=task_id,
                ticker="AAPL",
                task_type="ad_hoc",
                title="Run now from done",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=agent_id,
                source_heartbeat_run_id=None,
                triggered_by="manual_assignment",
                notes="Run this issue again",
                status="done",
                run_id=None,
                created_at=created_at,
                updated_at=created_at,
                completed_at=created_at,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.spawn_background", side_effect=lambda coro: coro.close()):
            response = await client.post(f"/tasks/{task_id}/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "dispatch"
    assert body["task"]["status"] == "running"
    assert body["run_id"] is not None
    assert body["skipped"] is False

@pytest.mark.asyncio
async def test_run_task_now_requeues_unassigned_issue_for_ceo_review():
    task_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        db.add(
            ResearchTask(
                id=task_id,
                ticker="AAPL",
                task_type="ad_hoc",
                title="Route me through the CEO",
                priority="medium",
                selected_agents="[]",
                project_id=None,
                parent_task_id=None,
                owner_agent_id=None,
                assigned_agent_id=None,
                source_heartbeat_run_id=None,
                triggered_by="manual_pm_review",
                notes="Need CEO routing",
                status="in_review",
                run_id=None,
                error="Old routing error",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await db.commit()

    queued: list[str] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("backend.cio_router.queue_cio_review_for_task", side_effect=lambda value: queued.append(value)):
            response = await client.post(f"/tasks/{task_id}/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "ceo_review_queued"
    assert body["run_id"] is None
    assert body["skipped"] is False
    assert queued == [task_id]

    async with AsyncSessionLocal() as db:
        task = await db.get(ResearchTask, task_id)

    assert task is not None
    assert task.status == "pending"
    assert task.error is None


def test_minimal_state_carries_assignment_context():
    state = _create_minimal_state(
        "AAPL",
        {},
        assignment_title="Stress-test valuation",
        assignment_focus="Focus on capex and buyback sustainability.",
    )

    assert state["query"].startswith("Stress-test valuation")
    assert "Focus: Focus on capex and buyback sustainability." in state["query"]
    assert state["thesis_summary"] == "Focus on capex and buyback sustainability."


def test_research_orchestrator_persists_assignment_context_in_task_record():
    orchestrator = ResearchOrchestrator(
        run_id="run-assignment-context",
        ticker="AAPL",
        selected_agents=["fundamental"],
        emit_fn=lambda _: None,
        assignment_title="Check services durability",
        assignment_focus="Focus on mix shift and margin durability.",
    )

    task_id = orchestrator._create_task_record()
    assert task_id is not None

    with SyncSessionLocal() as db:
        task = db.query(ResearchTask).filter(ResearchTask.id == task_id).one()
        assert task.title == "Check services durability"
        assert task.notes == "Focus on mix shift and margin durability."


class _DummyWebSocket:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, data: dict):
        if self.fail:
            raise RuntimeError("socket closed")
        self.sent.append(data)


@pytest.mark.asyncio
async def test_research_connection_manager_prunes_failed_websockets():
    manager = ResearchConnectionManager()
    healthy = _DummyWebSocket()
    failing = _DummyWebSocket(fail=True)

    await manager.connect("run-1", healthy)
    await manager.connect("run-1", failing)
    await manager.broadcast("run-1", {"type": "ping"})

    assert healthy.accepted is True
    assert healthy.sent == [{"type": "ping"}]
    assert manager._connections["run-1"] == [healthy]


@pytest.mark.asyncio
async def test_research_connection_manager_removes_empty_run_bucket():
    manager = ResearchConnectionManager()
    ws = _DummyWebSocket()

    await manager.connect("run-2", ws)
    manager.disconnect("run-2", ws)

    assert "run-2" not in manager._connections
