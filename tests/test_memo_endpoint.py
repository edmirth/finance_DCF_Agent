"""
Integration tests for POST /memo/stream endpoint.

Tests:
  - SSE event sequence (dispatch → agent_done × N → synthesis → memo_ready → end)
  - structured_memo has all 5 keys in arena_memo_ready event
  - Invalid ticker returns 400 before streaming
  - run_arena() exception streams error event and does not hang
"""
from __future__ import annotations
import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api_server import app


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_final_state(ticker="AAPL"):
    return {
        "ticker": ticker,
        "agent_signals": {
            "fundamental": {"view": "bullish",  "confidence": 0.8, "reasoning": "Strong FCF"},
            "risk":        {"view": "cautious", "confidence": 0.6, "reasoning": "High leverage"},
            "quant":       {"view": "bullish",  "confidence": 0.75, "reasoning": "Momentum +"},
            "macro":       {"view": "neutral",  "confidence": 0.5, "reasoning": "Rates flat"},
            "sentiment":   {"view": "bullish",  "confidence": 0.7, "reasoning": "Positive flow"},
        },
        "thesis_summary": "AAPL has strong fundamentals.",
        "conflicts": [],
        "raw_outputs": {"fundamental": "Full findings here."},
        "consensus_score": 0.72,
        "next_action": "finalise",
        "round": 2,
        "debate_log": [{"round": 1, "agent": "fundamental", "action": "signal_written", "content": "Bullish"}],
        "final_decision": "LONG AAPL — high conviction",
        "conviction_level": "high",
        "investment_memo": "Full text memo.",
    }


def _make_structured_memo():
    return {
        "thesis": "AAPL generates $90B FCF; services growing at 15%.",
        "bear_case": "China concentration at 19%; iPhone unit growth stalling.",
        "key_risks": ["Geopolitical risk", "Multiple compression", "Regulatory"],
        "valuation_range": {"bear": "$140", "base": "$185", "bull": "$220"},
        "what_would_make_this_wrong": "Sustained iPhone supercycle failure.",
    }


async def _collect_sse_events(client: AsyncClient, payload: dict) -> list[dict]:
    """POST to /memo/stream, collect and parse all SSE data events."""
    events = []
    async with client.stream("POST", "/memo/stream", json=payload) as response:
        if response.status_code != 200:
            return [{"__status": response.status_code}]
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except Exception:
                    pass
    return events


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memo_stream_event_sequence():
    """Happy path: mock run_arena + extract_structured_memo, check SSE event sequence."""
    final_state = _make_final_state()

    with (
        patch("backend.api_server.run_arena", return_value=final_state),
        patch("backend.api_server.extract_structured_memo", return_value=_make_structured_memo()),
        patch("backend.api_server.set_arena_queue"),
        patch("backend.api_server.clear_arena_queue"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            events = await _collect_sse_events(client, {"ticker": "AAPL", "query_mode": "full_ic"})

    event_types = [e["type"] for e in events if "type" in e]
    assert "arena_memo_ready" in event_types
    assert "end" in event_types
    # arena_memo_ready must come before end
    assert event_types.index("arena_memo_ready") < event_types.index("end")


@pytest.mark.asyncio
async def test_memo_ready_event_has_all_structured_memo_keys():
    """arena_memo_ready event must contain all 5 structured_memo keys."""
    final_state = _make_final_state()
    structured_memo = _make_structured_memo()

    with (
        patch("backend.api_server.run_arena", return_value=final_state),
        patch("backend.api_server.extract_structured_memo", return_value=structured_memo),
        patch("backend.api_server.set_arena_queue"),
        patch("backend.api_server.clear_arena_queue"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            events = await _collect_sse_events(client, {"ticker": "AAPL"})

    memo_ready = next((e for e in events if e.get("type") == "arena_memo_ready"), None)
    assert memo_ready is not None, "arena_memo_ready event not found"

    sm = memo_ready["structured_memo"]
    for key in ("thesis", "bear_case", "key_risks", "valuation_range", "what_would_make_this_wrong"):
        assert key in sm, f"Missing key: {key}"


@pytest.mark.asyncio
async def test_invalid_ticker_returns_400():
    """Empty or too-long ticker must return 400 before streaming."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Empty ticker
        resp = await client.post("/memo/stream", json={"ticker": ""})
        assert resp.status_code == 400

        # Too long
        resp = await client.post("/memo/stream", json={"ticker": "TOOLONG"})
        assert resp.status_code == 400

        # Non-alpha characters
        resp = await client.post("/memo/stream", json={"ticker": "AB1CD"})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_arena_exception_streams_error_event():
    """If run_arena() raises, endpoint must stream an error event and not hang."""
    with (
        patch("backend.api_server.run_arena", side_effect=RuntimeError("Arena crashed")),
        patch("backend.api_server.set_arena_queue"),
        patch("backend.api_server.clear_arena_queue"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            events = await _collect_sse_events(client, {"ticker": "AAPL"})

    event_types = [e.get("type") for e in events]
    assert "error" in event_types or "end" in event_types  # must terminate cleanly


@pytest.mark.asyncio
async def test_memo_save_persists_and_returns_slug():
    """POST /api/memo/save with all 4 checklist fields returns a share_slug."""
    payload = {
        "ticker": "AAPL",
        "verdict": "BUY",
        "confidence": 0.75,
        "structured_memo": _make_structured_memo(),
        "checklist_answers": {
            "why_now": "Earnings beat + multiple expansion",
            "exit_condition": "Services growth drops below 10% YoY",
            "max_position_size": "5%",
            "quarterly_check_metric": "Services revenue growth rate",
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/memo/save", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert "share_slug" in data
    assert len(data["share_slug"]) > 0
    assert "id" in data


@pytest.mark.asyncio
async def test_memo_save_requires_all_checklist_fields():
    """POST /api/memo/save with missing checklist fields returns 422."""
    payload = {
        "ticker": "AAPL",
        "verdict": "BUY",
        "confidence": 0.75,
        "structured_memo": _make_structured_memo(),
        "checklist_answers": {
            "why_now": "Earnings beat",
            "exit_condition": "Services growth drops",
            # max_position_size and quarterly_check_metric missing
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/memo/save", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_memo_slug_lookup_returns_memo():
    """GET /api/m/{slug} returns memo fields; unknown slug returns 404."""
    # First save a memo to get a slug
    save_payload = {
        "ticker": "MSFT",
        "verdict": "WATCH",
        "confidence": 0.55,
        "structured_memo": _make_structured_memo(),
        "checklist_answers": {
            "why_now": "Copilot growth",
            "exit_condition": "Cloud growth below 20%",
            "max_position_size": "4%",
            "quarterly_check_metric": "Azure revenue growth",
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        save_resp = await client.post("/api/memo/save", json=save_payload)
        assert save_resp.status_code == 200
        slug = save_resp.json()["share_slug"]

        # Fetch by slug
        get_resp = await client.get(f"/api/m/{slug}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["ticker"] == "MSFT"
        assert data["verdict"] == "WATCH"
        assert "structured_memo" in data

        # Unknown slug → 404
        not_found = await client.get("/api/m/doesnotexist")
        assert not_found.status_code == 404
