from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api_server import app, ResearchConnectionManager
from backend.database import AsyncSessionLocal, SyncSessionLocal
from backend.models import ResearchTask
from backend.research_orchestrator import ResearchOrchestrator, _create_minimal_state


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
async def test_list_tasks_can_filter_by_agent_id():
    agent_id = "agent-filter-test"

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
                "assigned_agent_id": "someone-else",
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
async def test_task_chat_creates_issue_thread_messages(monkeypatch):
    async def fake_reply(db, task, prompt, *, target_agent_id, thread_messages):
        return {
            "author_label": "CEO",
            "author_agent_id": None,
            "content": f"Replying to: {prompt}",
            "action": None,
        }

    monkeypatch.setattr("backend.api_server._run_task_chat_reply", fake_reply)

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
