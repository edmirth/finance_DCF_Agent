"""
Tests for Level 1 — agents read raw_outputs before reasoning.

What we verify:
  1. _build_peer_context() returns "" on a blank state (round 1, no peers).
  2. _build_peer_context() injects other agents' raw findings and skips own entry.
  3. Falls back gracefully to agent_signals when raw_outputs is absent.
  4. End-to-end: after round 1, raw_outputs is populated in ThesisState so that
     round 2 agents can read it. Verified by patching run_active_agents and
     inspecting the state passed to each agent stub.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_state(**overrides) -> dict:
    """Minimal ThesisState for unit tests."""
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


def _fake_signal(view: str = "bullish", conf: float = 0.80) -> dict:
    return {
        "view": view,
        "confidence": conf,
        "reasoning": f"Fake {view} signal for testing.",
    }


# ---------------------------------------------------------------------------
# Unit tests — _build_peer_context (fundamental agent)
# ---------------------------------------------------------------------------

class TestBuildPeerContext:
    """Import and exercise the helper directly without hitting any API."""

    def setup_method(self):
        from arena.fundamental_agent import _build_peer_context
        self._fn = _build_peer_context

    def test_empty_state_returns_empty_string(self):
        """Round 1 — no peers have written anything yet."""
        state = _blank_state()
        result = self._fn(state)
        assert result == "", f"Expected '' but got: {result!r}"

    def test_own_entry_excluded(self):
        """fundamental should not see its own raw_output in the context."""
        state = _blank_state(
            raw_outputs={"fundamental": "My own findings..."},
        )
        result = self._fn(state)
        assert result == "", "Own entry should be excluded from peer context."

    def test_other_agent_raw_output_included(self):
        """When risk agent has written findings, fundamental should see them."""
        risk_findings = "RISK ANALYSIS — AAPL\nTail risk: low."
        state = _blank_state(
            raw_outputs={"risk": risk_findings},
        )
        result = self._fn(state)
        assert "RISK" in result
        assert risk_findings in result
        assert "Use this context to calibrate" in result

    def test_multiple_peers_all_included(self):
        """All peers except 'fundamental' itself should appear."""
        state = _blank_state(
            raw_outputs={
                "risk":        "Risk findings here.",
                "macro":       "Macro findings here.",
                "fundamental": "My own — should be excluded.",
            },
        )
        result = self._fn(state)
        assert "RISK" in result
        assert "MACRO" in result
        assert "My own" not in result

    def test_signal_only_fallback_when_no_raw(self):
        """
        If a peer has a signal but no raw_output (e.g. it ran but had an error
        saving raw_outputs), the signal summary should still appear.
        """
        state = _blank_state(
            raw_outputs={},
            agent_signals={"risk": _fake_signal("bearish", 0.75)},
        )
        result = self._fn(state)
        assert "RISK" in result
        assert "bearish" in result

    def test_raw_takes_priority_over_signal(self):
        """
        When both raw_outputs and agent_signals exist for the same peer,
        only the raw text should appear (no duplicate).
        """
        state = _blank_state(
            raw_outputs={"risk": "Full risk report text."},
            agent_signals={"risk": _fake_signal("bearish")},
        )
        result = self._fn(state)
        # Full report text present
        assert "Full risk report text." in result
        # Signal-only label NOT present (raw took priority)
        assert "signal only" not in result.lower()


# ---------------------------------------------------------------------------
# Unit tests — same helper exists in all five agent modules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module_name,agent_key", [
    ("arena.quant_agent",      "quant"),
    ("arena.macro_agent",      "macro"),
    ("arena.risk_agent",       "risk"),
    ("arena.sentiment_agent",  "sentiment"),
])
def test_peer_context_helper_present_in_all_agents(module_name, agent_key):
    """Each agent module must export _build_peer_context and exclude itself."""
    import importlib
    mod = importlib.import_module(module_name)
    fn = getattr(mod, "_build_peer_context", None)
    assert fn is not None, f"{module_name} missing _build_peer_context"

    # Own entry must be excluded
    state = _blank_state(
        raw_outputs={agent_key: f"My own {agent_key} findings."},
    )
    result = fn(state)
    assert result == "", (
        f"{module_name}._build_peer_context should exclude its own key '{agent_key}' "
        f"but returned: {result!r}"
    )

    # Peer entry must be included
    state2 = _blank_state(
        raw_outputs={"fundamental": "Fundamental findings from peer."},
    )
    result2 = fn(state2)
    assert "FUNDAMENTAL" in result2, (
        f"{module_name}._build_peer_context should include peer 'fundamental' findings"
    )


# ---------------------------------------------------------------------------
# Integration test — raw_outputs propagates through the arena loop
# ---------------------------------------------------------------------------

class TestRawOutputsPropagation:
    """
    Verify that after round 1, each agent's raw findings are accumulated in
    the state so that round 2 agents can read them.

    We patch the five run_*_agent functions to return deterministic stub data
    so no API calls are made.
    """

    STUB_RAW = {
        "fundamental": "FUNDAMENTAL stub findings.",
        "quant":       "QUANT stub findings.",
        "macro":       "MACRO stub findings.",
        "risk":        "RISK stub findings.",
        "sentiment":   "SENTIMENT stub findings.",
    }

    def _make_stub(self, agent_name: str):
        """Returns a fake run_*_agent function for the given agent."""
        raw_text = self.STUB_RAW[agent_name]

        def stub(state):
            existing_raw = dict(state.get("raw_outputs", {}))
            existing_raw[agent_name] = raw_text
            return {
                "agent_signals": {agent_name: _fake_signal("bullish", 0.85)},
                "raw_outputs":   existing_raw,
            }
        return stub

    def test_raw_outputs_accumulate_after_round1(self):
        """
        After run_active_agents executes round 1, the returned state dict
        should contain raw_outputs for every active agent.
        """
        from arena.agents import run_active_agents

        patches = {
            "arena.fundamental_agent.run_fundamental_agent": self._make_stub("fundamental"),
            "arena.quant_agent.run_quant_agent":             self._make_stub("quant"),
            "arena.macro_agent.run_macro_agent":             self._make_stub("macro"),
            "arena.risk_agent.run_risk_agent":               self._make_stub("risk"),
            "arena.sentiment_agent.run_sentiment_agent":     self._make_stub("sentiment"),
        }

        state = _blank_state(
            active_agents=["fundamental", "quant", "macro", "risk", "sentiment"],
            round=0,
        )

        with (
            patch("arena.fundamental_agent.run_fundamental_agent", self._make_stub("fundamental")),
            patch("arena.quant_agent.run_quant_agent",             self._make_stub("quant")),
            patch("arena.macro_agent.run_macro_agent",             self._make_stub("macro")),
            patch("arena.risk_agent.run_risk_agent",               self._make_stub("risk")),
            patch("arena.sentiment_agent.run_sentiment_agent",     self._make_stub("sentiment")),
        ):
            result = run_active_agents(state)

        raw = result.get("raw_outputs", {})
        for agent_name in ["fundamental", "quant", "macro", "risk", "sentiment"]:
            assert agent_name in raw, f"raw_outputs missing '{agent_name}' after round 1"
            assert self.STUB_RAW[agent_name] in raw[agent_name]

    def test_round2_agents_receive_round1_raw_outputs(self):
        """
        Simulate round 2: state already has round 1 raw_outputs.
        Each round-2 agent stub must receive a state where raw_outputs
        is populated with the other agents' round-1 findings.
        """
        from arena.agents import run_active_agents

        # Simulate state entering round 2 — round 1 raw_outputs already present
        state = _blank_state(
            active_agents=["fundamental", "risk"],
            round=1,
            raw_outputs={
                "quant":     self.STUB_RAW["quant"],
                "macro":     self.STUB_RAW["macro"],
                "sentiment": self.STUB_RAW["sentiment"],
            },
        )

        states_seen = {}

        def capturing_stub(agent_name):
            def stub(s):
                states_seen[agent_name] = dict(s)  # capture a snapshot
                existing_raw = dict(s.get("raw_outputs", {}))
                existing_raw[agent_name] = self.STUB_RAW[agent_name]
                return {
                    "agent_signals": {agent_name: _fake_signal("bullish", 0.85)},
                    "raw_outputs":   existing_raw,
                }
            return stub

        with (
            patch("arena.fundamental_agent.run_fundamental_agent", capturing_stub("fundamental")),
            patch("arena.risk_agent.run_risk_agent",               capturing_stub("risk")),
        ):
            run_active_agents(state)

        # Both agents should have seen quant/macro/sentiment from round 1
        for agent_name in ["fundamental", "risk"]:
            seen = states_seen[agent_name].get("raw_outputs", {})
            assert "quant" in seen,     f"{agent_name} did not see 'quant' raw_output in round 2"
            assert "macro" in seen,     f"{agent_name} did not see 'macro' raw_output in round 2"
            assert "sentiment" in seen, f"{agent_name} did not see 'sentiment' raw_output in round 2"
