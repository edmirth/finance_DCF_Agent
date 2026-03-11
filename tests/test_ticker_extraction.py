"""
Evals: Ticker extraction logic across all three extraction sites.

Covers the regression bugs fixed in Feb 2026:
- "FY" (Fiscal Year) being extracted as a ticker symbol
- "NVIDIA" (6-char company name) not mapping to "NVDA"
- Company names written out in full not resolving to their ticker
"""
import re
import pytest
from unittest.mock import patch

# ── helpers ──────────────────────────────────────────────────────────────────

def _earnings_extract(query: str):
    """Call the Earnings Agent's _extract_ticker without instantiating the full agent."""
    # Import here so the module is loaded after conftest adds the project root
    from agents.earnings_agent import EarningsAgentExecutorAdapter
    obj = object.__new__(EarningsAgentExecutorAdapter)
    obj.last_state = None
    return obj._extract_ticker(query)


def _qa_extract(message: str):
    """Call the Finance Q&A Agent's _extract_ticker without API calls."""
    from agents.finance_qa_agent import FinanceQAAgent
    obj = object.__new__(FinanceQAAgent)
    return obj._extract_ticker(message)


def _backend_extract(query: str):
    from backend.api_server import extract_ticker_from_query
    return extract_ticker_from_query(query)


# ── Earnings Agent: _extract_ticker ──────────────────────────────────────────

class TestEarningsAgentTickerExtraction:
    """Regression tests for EarningsAgentExecutorAdapter._extract_ticker()"""

    # --- The specific query that triggered the FY/NVIDIA bug ---
    def test_nvidia_fy_query_regression(self):
        """'NVIDIA just reported FY 2025 earnings' must return NVDA, not FY."""
        query = (
            "NVIDIA just reported FY 2025 earnings. Compare reported earnings to "
            "analyst estimates from the last few days. Show insider trading activity "
            "for the quarter leading up to the report. Pull management's forward "
            "guidance from the most recent 10-K (Item 7, MD&A). What are analysts "
            "saying about the results and how did the market react?"
        )
        assert _earnings_extract(query) == "NVDA"

    # --- FY must never be returned as a ticker ---
    def test_fy_is_not_a_ticker(self):
        assert _earnings_extract("Show me FY 2025 results") != "FY"

    def test_fy_with_year_not_a_ticker(self):
        assert _earnings_extract("Apple FY2024 revenue beat") != "FY"

    def test_fy_lowercase_not_a_ticker(self):
        # lowercase "fy" won't match all-caps pattern anyway, but guard it
        ticker = _earnings_extract("fy 2025 guidance")
        assert ticker != "FY"

    # --- Company full names must map to tickers ---
    def test_company_name_nvidia(self):
        assert _earnings_extract("NVIDIA reported record earnings") == "NVDA"

    def test_company_name_apple(self):
        assert _earnings_extract("APPLE beat estimates this quarter") == "AAPL"

    def test_company_name_microsoft(self):
        assert _earnings_extract("MICROSOFT announced layoffs last week") == "MSFT"

    def test_company_name_palantir(self):
        assert _earnings_extract("PALANTIR earnings for FY25") == "PLTR"

    def test_company_name_amazon(self):
        assert _earnings_extract("AMAZON cloud growth exceeded FY targets") == "AMZN"

    # --- Ticker symbol present explicitly ---
    def test_explicit_ticker_dollar_sign(self):
        assert _earnings_extract("$NVDA earnings beat") == "NVDA"

    def test_explicit_ticker_in_parentheses(self):
        assert _earnings_extract("Nvidia (NVDA) reported Q4 results") == "NVDA"

    def test_known_ticker_in_query(self):
        assert _earnings_extract("NVDA just hit an ATH") == "NVDA"

    def test_known_ticker_tsla(self):
        assert _earnings_extract("TSLA Q4 FY 2025 delivery numbers") == "TSLA"

    # --- SEC filing references must not be extracted as tickers ---
    def test_md_a_not_a_ticker(self):
        result = _earnings_extract("Pull the MD&A section from the 10-K")
        assert result != "MD"

    def test_item_not_a_ticker(self):
        result = _earnings_extract("See ITEM 7 in the annual report")
        assert result != "ITEM"

    # --- No ticker in query ---
    def test_no_ticker_returns_none(self):
        assert _earnings_extract("What are the latest market trends?") is None


# ── Finance Q&A Agent: _extract_ticker ───────────────────────────────────────

class TestFinanceQATickerExtraction:
    """Tests for FinanceQAAgent._extract_ticker()"""

    def test_fy_not_extracted_as_ticker(self):
        assert _qa_extract("How has FY 2025 been for the market?") != "FY"

    def test_dollar_sign_ticker(self):
        assert _qa_extract("What's $AAPL trading at?") == "AAPL"

    def test_parentheses_ticker(self):
        assert _qa_extract("Apple (AAPL) revenue trend") == "AAPL"

    def test_all_caps_ticker(self):
        assert _qa_extract("Tell me about MSFT margins") == "MSFT"

    def test_mda_not_a_ticker(self):
        result = _qa_extract("What does the MD&A say about guidance?")
        assert result != "MD"

    def test_ytd_not_a_ticker(self):
        result = _qa_extract("YTD returns for the S&P 500")
        assert result != "YTD"

    def test_common_words_excluded(self):
        # Words like SELL, HOLD, RATE, etc. must not be extracted
        assert _qa_extract("Should I SELL or HOLD at this RATE?") is None or \
               _qa_extract("Should I SELL or HOLD at this RATE?") not in {"SELL", "HOLD", "RATE"}

    def test_no_ticker_returns_none(self):
        assert _qa_extract("What is the current interest rate environment?") is None


# ── Backend API: extract_ticker_from_query ───────────────────────────────────

class TestBackendTickerExtraction:
    """Tests for backend.api_server.extract_ticker_from_query()"""

    def test_nvidia_fy_query(self):
        assert _backend_extract("NVIDIA just reported FY 2025 earnings") == "NVDA"

    def test_fy_not_returned(self):
        assert _backend_extract("Compare FY 2025 results to estimates") != "FY"

    def test_dollar_sign_highest_priority(self):
        assert _backend_extract("$TSLA earnings beat") == "TSLA"

    def test_company_name_map_nvidia(self):
        assert _backend_extract("nvidia earnings beat expectations") == "NVDA"

    def test_company_name_map_apple(self):
        assert _backend_extract("apple reported strong iphone sales") == "AAPL"

    def test_ticker_with_earnings_context(self):
        # Pattern 2: ticker followed by "earnings"
        assert _backend_extract("NVDA earnings report") == "NVDA"

    def test_ttm_not_a_ticker(self):
        result = _backend_extract("Revenue TTM for the sector")
        assert result != "TTM"

    def test_md_not_a_ticker(self):
        result = _backend_extract("Item 7 MD&A guidance section")
        assert result != "MD"

    def test_sec_not_a_ticker(self):
        result = _backend_extract("Pull the SEC filing for AAPL")
        # SEC should be in blacklist; AAPL should be returned
        assert result == "AAPL"

    def test_ipo_not_a_ticker(self):
        result = _backend_extract("Looking for recent IPO candidates")
        assert result != "IPO"
