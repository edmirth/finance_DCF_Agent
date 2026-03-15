"""
Unit tests for backend API architecture safeguards.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.api_server as api_server


@pytest.fixture(autouse=True)
def clear_agent_cache():
    """Keep cache state isolated across tests."""
    api_server.agents_cache.clear()
    yield
    api_server.agents_cache.clear()


class TestAgentCaching:
    def test_build_agent_cache_key_scopes_stateful_agents_to_session(self):
        key = api_server._build_agent_cache_key("research", "claude-test", "session-123")

        assert key == "research_claude-test_session-123"

    def test_build_agent_cache_key_disables_shared_cache_without_session(self):
        key = api_server._build_agent_cache_key("earnings", "claude-test", None)

        assert key is None

    def test_stateless_agents_share_global_cache(self):
        created_agent = object()

        with patch.object(api_server, "create_dcf_agent", return_value=created_agent) as mock_factory:
            first = api_server.get_or_create_agent("dcf", "claude-test")
            second = api_server.get_or_create_agent("dcf", "claude-test")

        assert first is created_agent
        assert second is created_agent
        assert mock_factory.call_count == 1

    def test_stateful_agents_are_isolated_per_session(self):
        session_a_agent = object()
        session_b_agent = object()

        with patch.object(
            api_server,
            "create_finance_qa_agent",
            side_effect=[session_a_agent, session_b_agent],
        ) as mock_factory:
            first = api_server.get_or_create_agent("research", "claude-test", session_id="session-a")
            second = api_server.get_or_create_agent("research", "claude-test", session_id="session-b")

        assert first is session_a_agent
        assert second is session_b_agent
        assert mock_factory.call_count == 2

    def test_stateful_agents_without_session_are_not_cached(self):
        first_agent = object()
        second_agent = object()

        with patch.object(
            api_server,
            "create_earnings_agent",
            side_effect=[first_agent, second_agent],
        ) as mock_factory:
            first = api_server.get_or_create_agent("earnings", "claude-test")
            second = api_server.get_or_create_agent("earnings", "claude-test")

        assert first is first_agent
        assert second is second_agent
        assert mock_factory.call_count == 2
        assert api_server.agents_cache == {}


class TestAsyncExecution:
    def test_fetch_json_uses_threadpool_wrapper(self):
        async def run_test():
            threadpool_mock = AsyncMock(return_value={"ok": True})

            with patch.object(api_server, "run_in_threadpool", threadpool_mock):
                result = await api_server._fetch_json(
                    "https://example.com/data",
                    params={"symbol": "AAPL"},
                    timeout=12,
                )

            assert result == {"ok": True}
            threadpool_mock.assert_awaited_once_with(
                api_server._requests_get_json,
                "https://example.com/data",
                params={"symbol": "AAPL"},
                timeout=12,
            )

        asyncio.run(run_test())

    def test_chat_generates_session_id_for_stateful_agents(self):
        async def run_test():
            fake_agent = MagicMock()
            get_agent_mock = MagicMock(return_value=fake_agent)
            threadpool_mock = AsyncMock(return_value="answer")

            with patch.object(api_server, "get_or_create_agent", get_agent_mock), patch.object(
                api_server,
                "run_in_threadpool",
                threadpool_mock,
            ):
                response = await api_server.chat(
                    api_server.ChatMessage(message="Tell me about Apple", agent_type="research")
                )

            assert response.response == "answer"
            assert response.session_id != "default"
            assert get_agent_mock.call_args.kwargs["session_id"] == response.session_id
            threadpool_mock.assert_awaited_once_with(fake_agent.chat, "Tell me about Apple")

        asyncio.run(run_test())
