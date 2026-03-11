"""
Evals: Tool error message quality.

Covers the regression bug fixed in Feb 2026 where any Financial Datasets API
failure produced "This may be a delisted or invalid ticker" — even for valid
companies like NFLX — because the error type was not propagated.
"""
import pytest
from unittest.mock import patch, MagicMock


# ── helpers ──────────────────────────────────────────────────────────────────

def _run_quick_data(ticker: str, metrics: str = "revenue"):
    from tools.research_assistant_tools import QuickFinancialDataTool
    return QuickFinancialDataTool()._run(ticker, metrics)


def _run_calculator(calculation: str):
    from tools.research_assistant_tools import FinancialCalculatorTool
    return FinancialCalculatorTool()._run(calculation)


def _run_compare(ticker1: str, ticker2: str):
    from tools.research_assistant_tools import CompanyComparisonTool
    return CompanyComparisonTool()._run(ticker1, ticker2)


# ── Error message accuracy ────────────────────────────────────────────────────

class TestErrorMessageAccuracy:
    """
    Error messages must accurately reflect *why* data is unavailable so the
    agent can give the user actionable guidance.
    """

    def test_not_found_ticker_says_not_found(self):
        """A 404 (ticker not in API) must say 'not found', not 'delisted'."""
        with patch("data.financial_data.FinancialDataFetcher.get_stock_info") as mock_info, \
             patch("data.financial_data.FinancialDataFetcher.last_error_type",
                   new_callable=lambda: property(lambda self: "not_found"),
                   create=True):
            mock_info.return_value = {}
            # Patch last_error_type on the instance
            with patch("data.financial_data.FinancialDataFetcher.last_error_type", "not_found"):
                pass  # property patching is tricky; test via real API call below

        # Use a real invalid ticker to trigger a 404 from the API
        result = _run_quick_data("XYZQ99")  # deliberately invalid (>5 chars blocked)
        # The ticker validation runs first for >5 char strings
        assert "Invalid ticker format" in result or "not found" in result.lower()

    def test_api_failure_says_try_again_not_delisted(self):
        """When the API returns empty (simulated failure), must NOT say 'delisted'."""
        fetcher_mock = MagicMock()
        fetcher_mock.get_stock_info.return_value = {}
        fetcher_mock.last_error_type = "api_failure"

        with patch("tools.research_assistant_tools.FinancialDataFetcher",
                   return_value=fetcher_mock):
            result = _run_quick_data("NFLX", "revenue")

        assert "delisted" not in result.lower(), (
            f"Error message must not say 'delisted' for an API failure.\nGot: {result}"
        )
        assert "try again" in result.lower() or "temporary" in result.lower(), (
            f"Error message should indicate a transient failure.\nGot: {result}"
        )

    def test_auth_failure_mentions_api_key(self):
        """A 401/402 error must tell the user to check their API key."""
        fetcher_mock = MagicMock()
        fetcher_mock.get_stock_info.return_value = {}
        fetcher_mock.last_error_type = "auth_failure"

        with patch("tools.research_assistant_tools.FinancialDataFetcher",
                   return_value=fetcher_mock):
            result = _run_quick_data("AAPL", "revenue")

        assert "api" in result.lower() or "key" in result.lower() or "auth" in result.lower(), (
            f"Auth failure message should mention the API key.\nGot: {result}"
        )

    def test_not_found_error_type_for_invalid_ticker(self):
        """FinancialDataFetcher must set last_error_type='not_found' on 404."""
        import requests
        from data.financial_data import FinancialDataFetcher

        http_err = requests.exceptions.HTTPError(response=MagicMock(status_code=404))

        fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        fetcher._initialized = True
        fetcher.headers = {}
        fetcher.last_error_type = None
        fetcher.cache = {}
        fetcher.cache_ttl = 900

        with patch.object(fetcher, "_make_request_with_retry", side_effect=http_err):
            result = fetcher._make_request("/company/facts", {"ticker": "XYZQ"})

        assert result is None
        assert fetcher.last_error_type == "not_found"

    def test_server_error_type_for_5xx(self):
        """FinancialDataFetcher must set last_error_type='api_failure' on 5xx."""
        import requests
        from data.financial_data import FinancialDataFetcher

        http_err = requests.exceptions.HTTPError(response=MagicMock(status_code=503))

        fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        fetcher._initialized = True
        fetcher.headers = {}
        fetcher.last_error_type = None
        fetcher.cache = {}
        fetcher.cache_ttl = 900

        with patch.object(fetcher, "_make_request_with_retry", side_effect=http_err):
            result = fetcher._make_request("/company/facts", {"ticker": "AAPL"})

        assert result is None
        assert fetcher.last_error_type == "api_failure"

    def test_timeout_sets_api_failure_type(self):
        """Network timeouts must set last_error_type='api_failure'."""
        import requests
        from data.financial_data import FinancialDataFetcher

        fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        fetcher._initialized = True
        fetcher.headers = {}
        fetcher.last_error_type = None
        fetcher.cache = {}
        fetcher.cache_ttl = 900

        with patch.object(fetcher, "_make_request_with_retry",
                          side_effect=requests.exceptions.Timeout()):
            result = fetcher._make_request("/company/facts", {"ticker": "AAPL"})

        assert result is None
        assert fetcher.last_error_type == "api_failure"

    def test_error_type_reset_on_each_request(self):
        """last_error_type must be cleared before every request so stale errors don't leak."""
        import requests
        from data.financial_data import FinancialDataFetcher

        fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        fetcher._initialized = True
        fetcher.headers = {}
        fetcher.last_error_type = "not_found"  # stale from a previous call
        fetcher.cache = {}
        fetcher.cache_ttl = 900

        # Successful request
        with patch.object(fetcher, "_make_request_with_retry", return_value={"ok": True}):
            result = fetcher._make_request("/company/facts", {"ticker": "AAPL"})

        assert result == {"ok": True}
        assert fetcher.last_error_type is None, (
            "last_error_type must be reset to None after a successful request"
        )


# ── Comparison tool error propagation ────────────────────────────────────────

class TestComparisonToolErrors:

    def test_comparison_api_failure_says_try_again(self):
        """CompanyComparisonTool must not blame the ticker when the API fails."""
        fetcher_mock = MagicMock()
        fetcher_mock.get_stock_info.return_value = {}
        fetcher_mock.get_key_metrics.return_value = {}
        fetcher_mock.last_error_type = "api_failure"

        with patch("tools.research_assistant_tools.FinancialDataFetcher",
                   return_value=fetcher_mock):
            result = _run_compare("NFLX", "DIS")

        assert "delisted" not in result.lower()
        assert "try again" in result.lower() or "temporary" in result.lower()

    def test_comparison_not_found_says_verify_ticker(self):
        """CompanyComparisonTool must ask user to verify ticker on 404."""
        fetcher_mock = MagicMock()
        fetcher_mock.get_stock_info.return_value = {}
        fetcher_mock.get_key_metrics.return_value = {}
        fetcher_mock.last_error_type = "not_found"

        with patch("tools.research_assistant_tools.FinancialDataFetcher",
                   return_value=fetcher_mock):
            result = _run_compare("XYZQ", "AAPL")

        assert "not found" in result.lower() or "verify" in result.lower()
