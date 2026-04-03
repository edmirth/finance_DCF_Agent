"""
Tests for Level 2 — dynamic sequential graph with per-agent LangGraph nodes.

What we verify:
  Unit tests (1-10):
    - sequence_start_node is a pure no-op
    - route_from_sequence_start dispatches to active_agents[0] or sequence_done
    - sequence_advance_node pops the queue and writes a debate_log entry
    - sequence_done_node increments round, snapshots signals, resets active_agents

  Integration tests (11-16):
    - signal_history accumulates one entry per round across 2 rounds
    - quick_screen runs only fundamental + risk (no quant/macro/sentiment)
    - macro_view runs only macro + sentiment (skips all financial agents)
    - risk_node receives fundamental's raw_outputs in its state (sequential handoff)
    - fundamental_node does NOT see risk's raw_outputs (risk hasn't run yet)
    - round 2 agents see all round-1 raw_outputs (cross-round peer context)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_state(**overrides) -> dict:
    base = {
        "query":            "Should we long AAPL?",
        "ticker":           "AAPL",
        "query_mode":       "full_ic",
        "thesis_summary":   "",
        "agent_signals":    {},
        "signal_history":   [],
        "conflicts":        [],
        "debate_log":       [],
        "raw_outputs":      {},
        "consensus_score":  0.0,
        "next_action":      "",
        "round":            0,
        "active_agents":    [],
        "final_decision":   None,
        "conviction_level": None,
        "investment_memo":  None,
    }
    base.update(overrides)
    return base


def _fake_signal(view: str = "bullish", conf: float = 0.85) -> dict:
    return {"view": view, "confidence": conf, "reasoning": f"Fake {view} signal."}


def _make_agent_stub(agent_name: str, view: str = "bullish", conf: float = 0.85):
    """Returns a fake run_*_agent function for integration tests."""
    raw_text = f"{agent_name.upper()} stub findings."

    def stub(state):
        existing_raw = dict(state.get("raw_outputs", {}))
        existing_raw[agent_name] = raw_text
        return {
            "agent_signals": {agent_name: _fake_signal(view, conf)},
            "raw_outputs":   existing_raw,
        }
    return stub


# ---------------------------------------------------------------------------
# Unit tests — sequence_start_node
# ---------------------------------------------------------------------------

def test_sequence_start_is_noop():
    from arena.agents import sequence_start_node
    state = _blank_state(active_agents=["fundamental", "risk"])
    result = sequence_start_node(state)
    assert result == {}, f"Expected {{}} but got {result!r}"


def test_sequence_start_noop_empty_state():
    from arena.agents import sequence_start_node
    result = sequence_start_node(_blank_state())
    assert result == {}


# ---------------------------------------------------------------------------
# Unit tests — route_from_sequence_start
# ---------------------------------------------------------------------------

def test_route_dispatches_first_agent():
    from arena.agents import route_from_sequence_start
    state = _blank_state(active_agents=["risk", "macro"])
    assert route_from_sequence_start(state) == "risk"


def test_route_dispatches_first_of_full_sequence():
    from arena.agents import route_from_sequence_start
    state = _blank_state(active_agents=["fundamental", "risk", "macro", "quant", "sentiment"])
    assert route_from_sequence_start(state) == "fundamental"


def test_route_empty_queue_returns_sequence_done():
    from arena.agents import route_from_sequence_start
    state = _blank_state(active_agents=[])
    assert route_from_sequence_start(state) == "sequence_done"


def test_route_missing_active_agents_returns_sequence_done():
    from arena.agents import route_from_sequence_start
    state = _blank_state()
    del state["active_agents"]
    assert route_from_sequence_start(state) == "sequence_done"


# ---------------------------------------------------------------------------
# Unit tests — sequence_advance_node
# ---------------------------------------------------------------------------

def test_sequence_advance_pops_first_agent():
    from arena.agents import sequence_advance_node
    state = _blank_state(
        active_agents=["fundamental", "risk"],
        agent_signals={"fundamental": _fake_signal("bullish", 0.80)},
        round=0,
    )
    result = sequence_advance_node(state)
    assert result["active_agents"] == ["risk"]


def test_sequence_advance_writes_debate_log_entry():
    from arena.agents import sequence_advance_node
    state = _blank_state(
        active_agents=["fundamental", "risk"],
        agent_signals={"fundamental": _fake_signal("bullish", 0.80)},
        round=0,
    )
    result = sequence_advance_node(state)
    log = result["debate_log"]
    assert len(log) == 1
    entry = log[0]
    assert entry["agent"] == "fundamental"
    assert entry["action"] == "signal_written"
    assert entry["round"] == 1          # preview: 0 + 1
    assert "bullish" in entry["content"]


def test_sequence_advance_empty_queue_no_crash():
    from arena.agents import sequence_advance_node
    result = sequence_advance_node(_blank_state(active_agents=[]))
    assert result["active_agents"] == []
    assert result["debate_log"] == []


def test_sequence_advance_missing_signal_graceful():
    from arena.agents import sequence_advance_node
    # Agent ran but produced no signal (shouldn't happen, but must not crash)
    state = _blank_state(
        active_agents=["quant"],
        agent_signals={},   # quant's signal is missing
        round=1,
    )
    result = sequence_advance_node(state)
    assert result["active_agents"] == []
    assert result["debate_log"][0]["agent"] == "quant"
    assert result["debate_log"][0]["round"] == 2    # preview: 1 + 1


# ---------------------------------------------------------------------------
# Unit tests — sequence_done_node
# ---------------------------------------------------------------------------

def test_sequence_done_increments_round():
    from arena.agents import sequence_done_node
    state = _blank_state(round=0, query_mode="quick_screen")
    result = sequence_done_node(state)
    assert result["round"] == 1


def test_sequence_done_snapshots_agent_signals():
    from arena.agents import sequence_done_node
    signals = {"fundamental": _fake_signal("bullish"), "risk": _fake_signal("cautious")}
    state = _blank_state(round=0, agent_signals=signals, query_mode="quick_screen")
    result = sequence_done_node(state)
    # signal_history is returned as [snapshot] for operator.add to append
    assert result["signal_history"] == [signals]


def test_sequence_done_resets_active_agents_quick_screen():
    from arena.agents import sequence_done_node
    state = _blank_state(round=0, active_agents=[], query_mode="quick_screen")
    result = sequence_done_node(state)
    assert result["active_agents"] == ["fundamental", "risk"]


def test_sequence_done_resets_active_agents_macro_view():
    from arena.agents import sequence_done_node
    state = _blank_state(round=0, active_agents=[], query_mode="macro_view")
    result = sequence_done_node(state)
    assert result["active_agents"] == ["macro", "sentiment"]


def test_sequence_done_resets_active_agents_full_ic():
    from arena.agents import sequence_done_node
    state = _blank_state(round=0, active_agents=[], query_mode="full_ic")
    result = sequence_done_node(state)
    assert result["active_agents"] == ["fundamental", "risk", "macro", "quant", "sentiment"]


def test_sequence_done_unknown_mode_falls_back_to_full_ic():
    from arena.agents import sequence_done_node
    state = _blank_state(round=0, active_agents=[], query_mode="nonexistent_mode")
    result = sequence_done_node(state)
    # Must produce a non-empty sequence (falls back to full_ic)
    assert len(result["active_agents"]) > 0


# ---------------------------------------------------------------------------
# Test 1 — graph compiles
# ---------------------------------------------------------------------------

def test_build_arena_compiles():
    from arena.graph import build_arena
    arena = build_arena()
    assert arena is not None


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------

ALL_AGENTS = ["fundamental", "quant", "macro", "risk", "sentiment"]
PATCH_TARGETS = {
    "fundamental": "arena.fundamental_agent.run_fundamental_agent",
    "quant":       "arena.quant_agent.run_quant_agent",
    "macro":       "arena.macro_agent.run_macro_agent",
    "risk":        "arena.risk_agent.run_risk_agent",
    "sentiment":   "arena.sentiment_agent.run_sentiment_agent",
}


def _run_arena_with_stubs(query_mode: str, view: str = "bullish", conf: float = 0.85):
    """Run the arena with all 5 agents stubbed out. Returns final state."""
    from arena.run import run_arena
    patches = {
        name: patch(target, _make_agent_stub(name, view, conf))
        for name, target in PATCH_TARGETS.items()
    }
    with (
        patches["fundamental"],
        patches["quant"],
        patches["macro"],
        patches["risk"],
        patches["sentiment"],
    ):
        return run_arena(query="Test query", ticker="AAPL", query_mode=query_mode)


def _agents_in_debate_log(result: dict) -> list[str]:
    """Return list of agent names that wrote signal_written entries."""
    return [
        e["agent"]
        for e in result.get("debate_log", [])
        if e["action"] == "signal_written"
    ]


# ---------------------------------------------------------------------------
# Integration test 11 — signal_history accumulates across 2 rounds
# ---------------------------------------------------------------------------

def test_signal_history_accumulates_across_rounds():
    """
    Force 2 debate rounds (all agents neutral at 0.3 confidence → consensus=0.3 < 0.7).
    signal_history should have exactly 2 entries after the arena completes.
    """
    result = _run_arena_with_stubs("quick_screen", view="neutral", conf=0.3)
    history = result.get("signal_history", [])
    assert len(history) == 2, (
        f"Expected 2 signal_history entries (one per round), got {len(history)}: {history}"
    )
    # Each entry should be a dict with agent signals
    for snapshot in history:
        assert isinstance(snapshot, dict)
        assert "fundamental" in snapshot
        assert "risk" in snapshot


# ---------------------------------------------------------------------------
# Integration test 12 — quick_screen runs only fundamental + risk
# ---------------------------------------------------------------------------

def test_quick_screen_runs_only_two_agents():
    result = _run_arena_with_stubs("quick_screen")
    agents_ran = set(_agents_in_debate_log(result))

    assert "fundamental" in agents_ran, "fundamental should run in quick_screen"
    assert "risk" in agents_ran, "risk should run in quick_screen"
    assert "quant" not in agents_ran, "quant should NOT run in quick_screen"
    assert "macro" not in agents_ran, "macro should NOT run in quick_screen"
    assert "sentiment" not in agents_ran, "sentiment should NOT run in quick_screen"


# ---------------------------------------------------------------------------
# Integration test 13 — macro_view skips all financial agents
# ---------------------------------------------------------------------------

def test_macro_view_skips_financials():
    result = _run_arena_with_stubs("macro_view")
    agents_ran = set(_agents_in_debate_log(result))

    assert "macro" in agents_ran,      "macro should run in macro_view"
    assert "sentiment" in agents_ran,  "sentiment should run in macro_view"
    assert "fundamental" not in agents_ran, "fundamental should NOT run in macro_view"
    assert "risk" not in agents_ran,        "risk should NOT run in macro_view"
    assert "quant" not in agents_ran,       "quant should NOT run in macro_view"


# ---------------------------------------------------------------------------
# Integration test 14 — risk sees fundamental's raw_output (sequential handoff)
# ---------------------------------------------------------------------------

def test_risk_sees_fundamental_output():
    """
    In quick_screen (fundamental → risk), when risk_node runs, the state it
    receives must already contain raw_outputs["fundamental"] written by
    fundamental in the preceding super-step.
    """
    from arena.run import run_arena
    states_seen = {}

    def capturing_risk(state):
        states_seen["risk"] = dict(state)
        return _make_agent_stub("risk")(state)

    with (
        patch("arena.fundamental_agent.run_fundamental_agent", _make_agent_stub("fundamental")),
        patch("arena.risk_agent.run_risk_agent", capturing_risk),
        patch("arena.quant_agent.run_quant_agent", _make_agent_stub("quant")),
        patch("arena.macro_agent.run_macro_agent", _make_agent_stub("macro")),
        patch("arena.sentiment_agent.run_sentiment_agent", _make_agent_stub("sentiment")),
    ):
        run_arena(query="Test", ticker="AAPL", query_mode="quick_screen")

    assert "risk" in states_seen, "risk stub was never called"
    raw = states_seen["risk"].get("raw_outputs", {})
    assert "fundamental" in raw, (
        f"risk did not see fundamental's raw_output. raw_outputs keys: {list(raw.keys())}"
    )


# ---------------------------------------------------------------------------
# Integration test 15 — fundamental does NOT see risk's output
# ---------------------------------------------------------------------------

def test_fundamental_does_not_see_risk_output():
    """
    fundamental runs first; risk has not run yet, so raw_outputs["risk"]
    must be absent when fundamental executes.
    """
    from arena.run import run_arena
    states_seen = {}

    def capturing_fundamental(state):
        states_seen["fundamental"] = dict(state)
        return _make_agent_stub("fundamental")(state)

    with (
        patch("arena.fundamental_agent.run_fundamental_agent", capturing_fundamental),
        patch("arena.risk_agent.run_risk_agent", _make_agent_stub("risk")),
        patch("arena.quant_agent.run_quant_agent", _make_agent_stub("quant")),
        patch("arena.macro_agent.run_macro_agent", _make_agent_stub("macro")),
        patch("arena.sentiment_agent.run_sentiment_agent", _make_agent_stub("sentiment")),
    ):
        run_arena(query="Test", ticker="AAPL", query_mode="quick_screen")

    assert "fundamental" in states_seen, "fundamental stub was never called"
    raw = states_seen["fundamental"].get("raw_outputs", {})
    assert "risk" not in raw, (
        f"fundamental should not see risk's output (risk hasn't run yet). "
        f"raw_outputs keys: {list(raw.keys())}"
    )


# ---------------------------------------------------------------------------
# Integration test 16 — round 2 agents see round-1 raw_outputs
# ---------------------------------------------------------------------------

def test_round2_agents_see_round1_raw_outputs():
    """
    Force 2 rounds via low consensus. In round 2, fundamental should receive
    a state where raw_outputs already contains all round-1 agents' findings.
    """
    from arena.run import run_arena

    call_counts = {"fundamental": 0}
    states_seen_round2 = {}

    def capturing_fundamental(state):
        call_counts["fundamental"] += 1
        if call_counts["fundamental"] == 2:
            # This is the round-2 call
            states_seen_round2["state"] = dict(state)
        return _make_agent_stub("fundamental", view="neutral", conf=0.3)(state)

    with (
        patch("arena.fundamental_agent.run_fundamental_agent", capturing_fundamental),
        patch("arena.risk_agent.run_risk_agent",
              _make_agent_stub("risk", view="neutral", conf=0.3)),
        patch("arena.quant_agent.run_quant_agent", _make_agent_stub("quant")),
        patch("arena.macro_agent.run_macro_agent", _make_agent_stub("macro")),
        patch("arena.sentiment_agent.run_sentiment_agent", _make_agent_stub("sentiment")),
    ):
        run_arena(query="Test", ticker="AAPL", query_mode="quick_screen")

    assert call_counts["fundamental"] == 2, (
        f"Expected fundamental to run twice (2 rounds), ran {call_counts['fundamental']} times. "
        "Check that consensus forces round 2."
    )

    raw = states_seen_round2["state"].get("raw_outputs", {})
    assert "fundamental" in raw, "round-2 fundamental should see round-1 fundamental output"
    assert "risk" in raw, "round-2 fundamental should see round-1 risk output"
