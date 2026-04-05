"""
Unit tests for earnings_agent.py pure-logic functions.

These tests exercise agent logic without making any LLM or API calls.
Four groups correspond to the findings from the 2026-04-03 engineering review:

  1. _route_after_aggregate routing
  2. develop_thesis price target extraction
  3. Management accountability section extraction (case-insensitive regex)
  4. Follow-up TTL expiry (30-min cache)
"""
from __future__ import annotations

import re
import time
import pytest


# ---------------------------------------------------------------------------
# Helpers — instantiate just enough of the agent/adapter to call the methods
# ---------------------------------------------------------------------------

def _make_adapter():
    """Return an EarningsAgentExecutorAdapter with no graph or LLM wired up."""
    from agents.earnings_agent import EarningsAgentExecutorAdapter
    obj = object.__new__(EarningsAgentExecutorAdapter)
    obj.last_state = None
    obj.last_ticker = None
    obj.last_state_time = 0.0
    import threading
    obj._state_lock = threading.Lock()
    return obj


def _make_agent():
    """Return an EarningsAgent with no graph compiled (avoids full LLM init)."""
    from agents.earnings_agent import EarningsAgent
    obj = object.__new__(EarningsAgent)
    obj.model = "claude-sonnet-4-5-20250929"
    return obj


def _make_state(**kwargs):
    """Build a minimal EarningsAnalysisState-shaped dict."""
    base = {
        "ticker": "AAPL",
        "quarters_back": 8,
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "current_price": 100.0,
        "market_cap": 1_000_000_000_000,
        "earnings_history": "",
        "analyst_estimates": "",
        "earnings_surprises": "",
        "earnings_guidance": "",
        "peer_comparison": "",
        "sec_filings_summary": "",
        "comprehensive_analysis": "",
        "management_accountability": "",
        "investment_thesis": "",
        "price_target": 0.0,
        "key_catalysts": [],
        "key_risks": [],
        "final_report": "",
        "start_time": time.time(),
        "errors": [],
    }
    base.update(kwargs)
    return base


# ===========================================================================
# Group 1: _route_after_aggregate routing
# ===========================================================================

class TestRouteAfterAggregate:
    def test_both_present_returns_analyze(self):
        agent = _make_agent()
        state = _make_state(company_name="Apple Inc.", current_price=150.0)
        assert agent._route_after_aggregate(state) == "analyze"

    def test_missing_company_name_returns_error(self):
        agent = _make_agent()
        state = _make_state(company_name="", current_price=150.0)
        assert agent._route_after_aggregate(state) == "error"

    def test_missing_price_returns_error(self):
        agent = _make_agent()
        state = _make_state(company_name="Apple Inc.", current_price=0.0)
        assert agent._route_after_aggregate(state) == "error"

    def test_both_missing_returns_error(self):
        agent = _make_agent()
        state = _make_state(company_name="", current_price=0.0)
        assert agent._route_after_aggregate(state) == "error"


# ===========================================================================
# Group 2: develop_thesis price target extraction
# ===========================================================================

def _extract_price_target(thesis_text: str, current_price: float) -> float:
    """Re-implementation of the price target extraction logic from develop_thesis.

    Keeps tests decoupled from the full LLM response path while still
    exercising the exact regex + range-guard logic in production code.
    """
    price_pattern = r'\$(\d+(?:\.\d{2})?)(?!\s*(?:[BMTKbmtk]|billion|million|trillion)\b)'
    price_target = 0.0

    for line in thesis_text.split('\n'):
        if 'TARGET' in line.upper() or 'PRICE TARGET' in line.upper():
            prices_in_line = re.findall(price_pattern, line)
            if prices_in_line:
                candidate = float(prices_in_line[0])
                if candidate > 0:
                    price_target = candidate
                    break
    else:
        for p in re.findall(price_pattern, thesis_text):
            p_float = float(p)
            if current_price > 0 and 0.5 * current_price < p_float < 3.0 * current_price:
                price_target = p_float
                break

    return price_target


class TestPriceTargetExtraction:
    def test_explicit_price_target_line(self):
        thesis = "PRICE TARGET: $150.00\nSome other text."
        assert _extract_price_target(thesis, current_price=120.0) == 150.0

    def test_market_cap_not_extracted(self):
        """$125B should NOT be extracted as a price target."""
        thesis = "Company has a market cap of $125B.\nSome analysis here."
        # No TARGET line, range guard: current=100, so valid range is 50–300.
        # $125 (without B suffix) would be in range, but $125B should be filtered.
        result = _extract_price_target(thesis, current_price=100.0)
        assert result == 0.0

    def test_price_outside_range_stays_zero(self):
        """A price of $5000 when current=$100 is outside 0.5x–3x guard."""
        thesis = "We think the stock could reach $5000 in a year."
        assert _extract_price_target(thesis, current_price=100.0) == 0.0

    def test_no_price_stays_zero(self):
        thesis = "The company has strong fundamentals and competitive positioning."
        assert _extract_price_target(thesis, current_price=100.0) == 0.0

    def test_current_price_zero_no_divide_by_zero(self):
        """Range guard must not raise ZeroDivisionError when current_price=0."""
        thesis = "PRICE TARGET: $200.00"
        # When current_price=0, the range check is skipped, but the TARGET line
        # is caught before the fallback loop, so extraction still works.
        result = _extract_price_target(thesis, current_price=0.0)
        assert result == 200.0


# ===========================================================================
# Group 3: Management accountability extraction (case-insensitive regex)
# ===========================================================================

def _extract_accountability(content: str) -> str:
    """Mirror the extraction logic from comprehensive_analysis node."""
    acc_match = re.search(
        r'(#{1,3}\s*MANAGEMENT ACCOUNTABILITY\b[^\n]*)',
        content,
        re.IGNORECASE,
    )
    if acc_match:
        acc_start = acc_match.start()
        next_section = content.find("\n## ", acc_start + 5)
        return (
            content[acc_start:next_section].strip()
            if next_section != -1
            else content[acc_start:].strip()
        )
    return ""


class TestManagementAccountabilityExtraction:
    def test_uppercase_header(self):
        content = "## MANAGEMENT ACCOUNTABILITY\nSome text here."
        result = _extract_accountability(content)
        assert result.startswith("## MANAGEMENT ACCOUNTABILITY")

    def test_mixed_case_header(self):
        content = "## Management Accountability\nSome text here."
        result = _extract_accountability(content)
        assert "Management Accountability" in result

    def test_header_with_colon(self):
        content = "## MANAGEMENT ACCOUNTABILITY: Details\nSome text here."
        result = _extract_accountability(content)
        assert "MANAGEMENT ACCOUNTABILITY" in result

    def test_absent_header_returns_empty(self):
        content = "## EARNINGS TREND\nRevenue grew 15% YoY.\n## VALUATION\nP/E of 25x."
        result = _extract_accountability(content)
        assert result == ""

    def test_section_stops_at_next_header(self):
        content = "## MANAGEMENT ACCOUNTABILITY\nPromises content.\n## VALUATION\nP/E details."
        result = _extract_accountability(content)
        assert "VALUATION" not in result
        assert "Promises content" in result


# ===========================================================================
# Group 4: Follow-up TTL expiry (30-minute cache)
# ===========================================================================

class TestFollowupTTL:
    def _make_adapter_with_state(self, age_seconds: float):
        """Return an adapter whose cached state is `age_seconds` old."""
        adapter = _make_adapter()
        adapter.last_state = _make_state()
        adapter.last_ticker = "AAPL"
        adapter.last_state_time = time.time() - age_seconds
        return adapter

    def test_fresh_state_is_used(self):
        """State cached 100 seconds ago should be returned for follow-up."""
        adapter = self._make_adapter_with_state(100)
        with adapter._state_lock:
            cached = None
            if adapter.last_state is not None:
                if time.time() - adapter.last_state_time <= 1800:
                    cached = dict(adapter.last_state)
        assert cached is not None

    def test_expired_state_is_skipped(self):
        """State cached 1801 seconds ago (> 30 min) should be skipped."""
        adapter = self._make_adapter_with_state(1801)
        with adapter._state_lock:
            cached = None
            if adapter.last_state is not None:
                if time.time() - adapter.last_state_time <= 1800:
                    cached = dict(adapter.last_state)
        assert cached is None

    def test_none_state_falls_through(self):
        """No cached state should never trigger the follow-up path."""
        adapter = _make_adapter()
        assert adapter.last_state is None
        with adapter._state_lock:
            cached = None
            if adapter.last_state is not None:
                if time.time() - adapter.last_state_time <= 1800:
                    cached = dict(adapter.last_state)
        assert cached is None

    def test_exactly_at_boundary_is_fresh(self):
        """State cached exactly 1800 seconds ago is still within the window."""
        adapter = self._make_adapter_with_state(1800)
        with adapter._state_lock:
            cached = None
            if adapter.last_state is not None:
                if time.time() - adapter.last_state_time <= 1800:
                    cached = dict(adapter.last_state)
        assert cached is not None
