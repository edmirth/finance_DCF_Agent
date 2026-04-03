"""
Unit tests for arena/output.py

Covers:
  - extract_structured_memo(): happy path, malformed JSON, missing fields, LLM exception
  - derive_verdict(): BUY/WATCH/PASS boundary conditions + escalation override
"""
from __future__ import annotations
import json
import sys
import os
from unittest.mock import MagicMock, patch

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arena.output import extract_structured_memo
from backend.api_server import derive_verdict


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_state(ticker="AAPL", signals=None, thesis="Test thesis", conflicts=None):
    return {
        "ticker": ticker,
        "agent_signals": signals or {
            "fundamental": {"view": "bullish", "confidence": 0.8, "reasoning": "Strong FCF"},
            "risk": {"view": "cautious", "confidence": 0.6, "reasoning": "High leverage"},
        },
        "thesis_summary": thesis,
        "conflicts": conflicts or [],
        "raw_outputs": {"fundamental": "Some detailed analysis text here"},
        "consensus_score": 0.65,
        "next_action": "finalise",
        "round": 2,
    }


def _mock_anthropic_response(text: str):
    """Return a mock Anthropic messages.create() response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


VALID_MEMO_JSON = json.dumps({
    "thesis": "AAPL has strong FCF yield of 5% with services growth at 15% YoY.",
    "bear_case": "Multiple compression risk if rates rise above 5.5%; P/E at 28x is stretched.",
    "key_risks": [
        "China revenue concentration at 19% — geopolitical exposure",
        "iPhone unit growth stalling at -3% YoY",
        "Regulatory risk from EU DMA could cost $2B+ in fines",
    ],
    "valuation_range": {"bear": "$140", "base": "$185", "bull": "$220"},
    "what_would_make_this_wrong": "A sustained iPhone supercycle failure or loss of App Store margin pricing power.",
})


# ─── extract_structured_memo ──────────────────────────────────────────────────

class TestExtractStructuredMemo:
    def test_happy_path(self):
        state = _make_state()
        with patch("arena.output.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _mock_anthropic_response(VALID_MEMO_JSON)
            result = extract_structured_memo(state)

        assert result["thesis"] is not None
        assert "FCF" in result["thesis"]
        assert isinstance(result["key_risks"], list)
        assert len(result["key_risks"]) == 3
        assert result["valuation_range"]["base"] == "$185"
        assert result["bear_case"] is not None
        assert result["what_would_make_this_wrong"] is not None

    def test_malformed_json_returns_null_fields(self):
        state = _make_state()
        with patch("arena.output.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _mock_anthropic_response(
                "This is not JSON at all — sorry!"
            )
            result = extract_structured_memo(state)

        assert result["thesis"] is None
        assert result["bear_case"] is None
        assert result["key_risks"] is None
        assert result["valuation_range"] is None
        assert result["what_would_make_this_wrong"] is None

    def test_missing_fields_returns_none_for_missing_present_for_others(self):
        partial = json.dumps({
            "thesis": "Strong FCF.",
            "bear_case": "Valuation risk.",
            # key_risks, valuation_range, what_would_make_this_wrong intentionally missing
        })
        state = _make_state()
        with patch("arena.output.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _mock_anthropic_response(partial)
            result = extract_structured_memo(state)

        assert result["thesis"] == "Strong FCF."
        assert result["bear_case"] == "Valuation risk."
        assert result["key_risks"] is None
        assert result["valuation_range"] is None
        assert result["what_would_make_this_wrong"] is None

    def test_llm_exception_returns_null_fields_no_raise(self):
        state = _make_state()
        with patch("arena.output.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.side_effect = RuntimeError("API down")
            result = extract_structured_memo(state)

        # Must not raise, must return all-None dict
        assert result["thesis"] is None
        assert result["bear_case"] is None
        assert result["key_risks"] is None
        assert result["valuation_range"] is None
        assert result["what_would_make_this_wrong"] is None

    def test_markdown_fenced_json_is_stripped(self):
        fenced = f"```json\n{VALID_MEMO_JSON}\n```"
        state = _make_state()
        with patch("arena.output.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _mock_anthropic_response(fenced)
            result = extract_structured_memo(state)

        assert result["thesis"] is not None


# ─── derive_verdict ────────────────────────────────────────────────────────────

def _signals(views: list[str], confidence: float = 0.7) -> dict:
    return {f"agent_{i}": {"view": v, "confidence": confidence, "reasoning": ""} for i, v in enumerate(views)}


class TestDeriveVerdict:
    def test_buy_high_consensus_three_bullish(self):
        signals = _signals(["bullish", "bullish", "bullish", "neutral", "neutral"])
        verdict, conf = derive_verdict(0.75, signals)
        assert verdict == "BUY"
        assert conf == 0.75

    def test_watch_high_consensus_only_two_bullish(self):
        signals = _signals(["bullish", "bullish", "neutral", "neutral", "neutral"])
        verdict, _ = derive_verdict(0.75, signals)
        assert verdict == "WATCH"

    def test_pass_consensus_too_low(self):
        signals = _signals(["bullish", "neutral", "neutral", "neutral", "neutral"])
        verdict, _ = derive_verdict(0.35, signals)
        assert verdict == "PASS"

    def test_pass_three_bearish(self):
        signals = _signals(["bearish", "bearish", "bearish", "bullish", "neutral"])
        verdict, _ = derive_verdict(0.60, signals)
        assert verdict == "PASS"

    def test_watch_mid_consensus(self):
        signals = _signals(["bullish", "bullish", "neutral", "neutral", "cautious"])
        verdict, _ = derive_verdict(0.55, signals)
        assert verdict == "WATCH"

    def test_escalation_overrides_to_watch(self):
        # Even with consensus >= 0.70 and 4 bullish, escalation wins
        signals = _signals(["bullish", "bullish", "bullish", "bullish", "neutral"])
        verdict, _ = derive_verdict(0.80, signals, next_action="escalate_to_human")
        assert verdict == "WATCH"

    def test_cautious_does_not_count_toward_pass(self):
        # cautious = WATCH contributor, not PASS; only "bearish" view triggers PASS threshold
        signals = _signals(["cautious", "cautious", "cautious", "bullish", "neutral"])
        verdict, _ = derive_verdict(0.50, signals)
        assert verdict == "WATCH"
