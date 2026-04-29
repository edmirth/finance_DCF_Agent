"""
Targeted tests for the two-stage DCF pipeline.

These cover the refactored fetch/analyze split and the FMP fallback path
introduced by the newer DCF implementation.
"""

from unittest.mock import MagicMock, patch

import pytest

from agents.dcf_agent import (
    AnalyzerAgent,
    CompanyData,
    DCFAgent,
    DCFDataPackage,
    FinancialMetrics,
    MarketData,
    DataFetchAgent,
)


@pytest.fixture
def sample_data_package():
    return DCFDataPackage(
        company=CompanyData(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            industry="Consumer Electronics",
            market_cap=3_000_000_000_000,
            current_price=180.0,
        ),
        financials=FinancialMetrics(
            latest_revenue=385_000_000_000,
            revenue_growth_rate=0.08,
            historical_revenue=[300e9, 320e9, 340e9, 360e9, 385e9],
            gross_margin=0.43,
            operating_margin=0.30,
            net_margin=0.25,
            fcf_margin=0.28,
            latest_fcf=108_000_000_000,
            fcf_growth_rate=0.10,
            historical_fcf=[80e9, 85e9, 90e9, 100e9, 108e9],
            total_debt=110_000_000_000,
            cash_and_equivalents=65_000_000_000,
            net_debt=45_000_000_000,
            shareholders_equity=60_000_000_000,
            beta=1.2,
            effective_tax_rate=0.15,
            cost_of_debt=0.04,
            pe_ratio=28.0,
            ev_to_ebitda=22.0,
            ev_to_revenue=7.5,
            fcf_yield=0.036,
        ),
        market=MarketData(
            risk_free_rate=0.045,
            equity_risk_premium=0.055,
            analyst_growth_consensus=0.10,
        ),
        data_quality_score=0.95,
    )


class TestDataFetchAgent:
    @patch("agents.dcf_agent.FinancialDataFetcher")
    def test_fetch_returns_populated_package(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get_stock_info.return_value = {
            "company_name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "market_cap": 3_000_000_000_000,
            "current_price": 180.0,
        }
        mock_fetcher.get_key_metrics.return_value = {
            "latest_revenue": 385_000_000_000,
            "latest_fcf": 108_000_000_000,
            "revenue_growth_rate": 0.08,
            "historical_revenue": [300e9, 320e9, 340e9, 360e9, 385e9],
            "gross_margin": 0.43,
            "operating_margin": 0.30,
            "net_margin": 0.25,
            "fcf_growth_rate": 0.10,
            "historical_fcf": [80e9, 85e9, 90e9, 100e9, 108e9],
            "total_debt": 110_000_000_000,
            "cash_and_equivalents": 65_000_000_000,
            "shareholders_equity": 60_000_000_000,
            "beta": 1.2,
            "effective_tax_rate": 0.15,
            "latest_interest_expense": 4_400_000_000,
        }
        mock_fetcher._make_request.return_value = {
            "interest_rates": [{"rate": 4.5}]
        }

        result = DataFetchAgent().fetch("aapl")

        assert result.company.ticker == "AAPL"
        assert result.company.company_name == "Apple Inc."
        assert result.financials.net_debt == 45_000_000_000
        assert result.financials.cost_of_debt == pytest.approx(0.04)
        assert result.market.risk_free_rate == pytest.approx(0.045)
        assert result.data_quality_score == pytest.approx(0.9)
        assert result.data_issues == ["No analyst growth consensus available"]

    @patch("agents.dcf_agent.FinancialDataFetcher")
    def test_fetch_penalizes_missing_data(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get_stock_info.return_value = {}
        mock_fetcher.get_key_metrics.return_value = {}
        mock_fetcher._make_request.return_value = None

        result = DataFetchAgent().fetch("invalid")

        assert result.company.ticker == "INVALID"
        assert result.data_quality_score == pytest.approx(0.1)
        assert "Could not fetch company information" in result.data_issues
        assert "Missing revenue data" in result.data_issues
        assert "Missing free cash flow data" in result.data_issues


class TestAnalyzerAgent:
    @patch("agents.dcf_agent.Anthropic")
    @patch("agents.dcf_agent.FinancialDataFetcher")
    def test_growth_rate_uses_sector_default_when_inputs_missing(
        self,
        mock_fetcher_class,
        mock_anthropic,
        sample_data_package,
    ):
        mock_fetcher_class.return_value = MagicMock()
        mock_anthropic.return_value = MagicMock()
        sample_data_package.market.analyst_growth_consensus = None
        sample_data_package.financials.revenue_growth_rate = 0.0

        growth = AnalyzerAgent()._determine_growth_rate(sample_data_package)

        assert growth == pytest.approx(0.15)

    @patch("agents.dcf_agent.Anthropic")
    @patch("agents.dcf_agent.FinancialDataFetcher")
    def test_analyze_falls_back_to_simple_fmp_when_custom_zero(
        self,
        mock_fetcher_class,
        mock_anthropic,
        sample_data_package,
    ):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get_fmp_dcf.side_effect = [
            {},
            {},
            {},
            {},
            {"dcf": 150.0, "stock_price": 180.0},
            {"dcf": 140.0, "stock_price": 180.0},
        ]
        mock_anthropic.return_value = MagicMock()

        agent = AnalyzerAgent()
        with patch.object(
            agent,
            "_generate_recommendation",
            return_value=("HOLD", 0.6, "Fallback path used.", ["Scenario spread"]),
        ):
            result = agent.analyze(sample_data_package)

        assert result.intrinsic_value == pytest.approx(150.0)
        assert result.bull_case_value == pytest.approx(210.0)
        assert result.bear_case_value == pytest.approx(97.5)
        assert result.levered_value == pytest.approx(140.0)
        assert result.upside_potential == pytest.approx((150.0 - 180.0) / 180.0)
        assert mock_fetcher.get_fmp_dcf.call_count == 6

    @patch("agents.dcf_agent.Anthropic")
    @patch("agents.dcf_agent.FinancialDataFetcher")
    def test_generate_recommendation_falls_back_when_llm_errors(
        self,
        mock_fetcher_class,
        mock_anthropic,
        sample_data_package,
    ):
        mock_fetcher_class.return_value = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("llm unavailable")
        mock_anthropic.return_value = mock_client

        agent = AnalyzerAgent()
        recommendation, confidence, reasoning, key_risks = agent._generate_recommendation(
            data=sample_data_package,
            base_value=250.0,
            bull_value=300.0,
            bear_value=180.0,
            levered_value=230.0,
            upside=(250.0 - 180.0) / 180.0,
            wacc=0.10,
            growth_rate=0.10,
        )

        assert recommendation == "BUY"
        assert confidence == 0.5
        assert "upside potential" in reasoning.lower()
        assert key_risks == ["Model-based recommendation, verify assumptions"]


class TestDCFAgent:
    def test_analyze_chains_fetch_and_analyze(self, sample_data_package):
        expected = MagicMock()

        with patch.object(DataFetchAgent, "fetch", return_value=sample_data_package) as mock_fetch, patch.object(
            AnalyzerAgent,
            "analyze",
            return_value=expected,
        ) as mock_analyze, patch("agents.dcf_agent.Anthropic"), patch(
            "agents.dcf_agent.FinancialDataFetcher"
        ):
            result = DCFAgent().analyze("AAPL")

        assert result is expected
        mock_fetch.assert_called_once_with("AAPL")
        mock_analyze.assert_called_once_with(sample_data_package)
