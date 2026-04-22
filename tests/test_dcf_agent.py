"""
Tests for the two-stage DCF Agent pipeline.

Tests both Stage 1 (Data Fetch) and Stage 2 (Analysis) independently,
as well as the full pipeline integration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from agents.dcf_agent import (
    DataFetchAgent,
    AnalyzerAgent,
    DCFAgent,
    DCFDataPackage,
    CompanyData,
    FinancialMetrics,
    MarketData,
    DCFResult,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_company_data():
    """Sample company data"""
    return CompanyData(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3_000_000_000_000,  # $3T
        current_price=180.00,
        shares_outstanding=15_500_000_000,
        currency="USD",
    )


@pytest.fixture
def mock_financial_metrics():
    """Sample financial metrics"""
    return FinancialMetrics(
        latest_revenue=385_000_000_000,  # $385B
        revenue_growth_rate=0.08,
        historical_revenue=[385e9, 360e9, 340e9, 320e9, 300e9],
        gross_margin=0.43,
        operating_margin=0.30,
        net_margin=0.25,
        fcf_margin=0.28,
        latest_fcf=108_000_000_000,  # $108B
        fcf_growth_rate=0.10,
        historical_fcf=[108e9, 100e9, 90e9, 85e9, 80e9],
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
        historical_years=["2024", "2023", "2022", "2021", "2020"],
    )


@pytest.fixture
def mock_market_data():
    """Sample market data"""
    return MarketData(
        risk_free_rate=0.045,
        equity_risk_premium=0.055,
        sector_beta_avg=1.15,
        analyst_growth_consensus=0.10,
        analyst_target_price=200.0,
        recent_news_summary="Apple reported strong iPhone sales...",
    )


@pytest.fixture
def mock_data_package(mock_company_data, mock_financial_metrics, mock_market_data):
    """Complete data package"""
    return DCFDataPackage(
        company=mock_company_data,
        financials=mock_financial_metrics,
        market=mock_market_data,
        data_quality_score=0.95,
        data_issues=[],
    )


# =============================================================================
# Stage 1: Data Fetch Agent Tests
# =============================================================================

class TestDataFetchAgent:
    """Tests for DataFetchAgent (Stage 1)"""
    
    @patch('agents.dcf_agent.FinancialDataFetcher')
    @patch('agents.dcf_agent.get_tavily_client')
    def test_fetch_returns_data_package(self, mock_tavily, mock_fetcher_class):
        """Test that fetch returns a proper DCFDataPackage"""
        # Setup mocks
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
            "beta": 1.2,
            "total_debt": 110_000_000_000,
            "cash_and_equivalents": 65_000_000_000,
        }
        
        mock_tavily.return_value = MagicMock()
        
        # Execute
        agent = DataFetchAgent()
        result = agent.fetch("AAPL")
        
        # Assert
        assert isinstance(result, DCFDataPackage)
        assert result.company.ticker == "AAPL"
        assert result.company.company_name == "Apple Inc."
        assert result.financials.latest_revenue == 385_000_000_000
        assert result.data_quality_score > 0
    
    @patch('agents.dcf_agent.FinancialDataFetcher')
    @patch('agents.dcf_agent.get_tavily_client')
    def test_fetch_handles_missing_data(self, mock_tavily, mock_fetcher_class):
        """Test that missing data reduces quality score"""
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        
        # Return empty data
        mock_fetcher.get_stock_info.return_value = {}
        mock_fetcher.get_key_metrics.return_value = {}
        mock_tavily.return_value = MagicMock()
        
        agent = DataFetchAgent()
        result = agent.fetch("INVALID")
        
        # Quality should be penalized
        assert result.data_quality_score < 1.0
        assert len(result.data_issues) > 0
    
    def test_company_data_defaults(self):
        """Test that CompanyData has sensible defaults"""
        data = CompanyData(ticker="TEST")
        
        assert data.ticker == "TEST"
        assert data.company_name == ""
        assert data.market_cap == 0.0
        assert data.currency == "USD"


# =============================================================================
# Stage 2: Analyzer Agent Tests
# =============================================================================

class TestAnalyzerAgent:
    """Tests for AnalyzerAgent (Stage 2)"""
    
    def test_wacc_calculation(self, mock_data_package):
        """Test WACC calculation with debt"""
        agent = AnalyzerAgent()
        wacc = agent._calculate_wacc(mock_data_package)
        
        # WACC should be between 6% and 20%
        assert 0.06 <= wacc <= 0.20
    
    def test_wacc_equity_only(self, mock_data_package):
        """Test WACC when no debt"""
        mock_data_package.financials.total_debt = 0
        agent = AnalyzerAgent()
        wacc = agent._calculate_wacc(mock_data_package)
        
        # Should be cost of equity only
        expected_cost_of_equity = 0.045 + (1.2 * 0.055)  # rf + beta * erp
        assert abs(wacc - expected_cost_of_equity) < 0.01
    
    def test_growth_rate_uses_analyst_consensus(self, mock_data_package):
        """Test that analyst consensus is preferred"""
        agent = AnalyzerAgent()
        growth = agent._determine_growth_rate(mock_data_package)
        
        # Should use analyst consensus (0.10)
        assert growth == 0.10
    
    def test_growth_rate_fallback_to_historical(self, mock_data_package):
        """Test fallback to historical when no consensus"""
        mock_data_package.market.analyst_growth_consensus = None
        agent = AnalyzerAgent()
        growth = agent._determine_growth_rate(mock_data_package)
        
        # Should fall back to historical (0.08)
        assert growth == 0.08
    
    def test_dcf_calculation_positive_value(self, mock_data_package):
        """Test that DCF produces positive intrinsic value"""
        agent = AnalyzerAgent()
        value = agent._calculate_dcf(
            data=mock_data_package,
            growth_rate=0.08,
            fcf_margin=0.28,
            wacc=0.10,
            terminal_growth=0.025,
            years=5,
        )
        
        assert value > 0
        # Apple with these assumptions should be worth > $100/share
        assert value > 100
    
    def test_dcf_handles_zero_revenue(self, mock_data_package):
        """Test DCF returns 0 when no revenue"""
        mock_data_package.financials.latest_revenue = 0
        agent = AnalyzerAgent()
        value = agent._calculate_dcf(
            data=mock_data_package,
            growth_rate=0.08,
            fcf_margin=0.28,
            wacc=0.10,
            terminal_growth=0.025,
            years=5,
        )
        
        assert value == 0
    
    @patch('agents.dcf_agent.Anthropic')
    def test_analyze_returns_dcf_result(self, mock_anthropic, mock_data_package):
        """Test full analysis pipeline"""
        # Mock LLM response
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"recommendation": "BUY", "confidence": 0.75, "reasoning": "Strong FCF and growth", "key_risks": ["Competition", "Regulation"]}')]
        )
        
        agent = AnalyzerAgent()
        result = agent.analyze(mock_data_package)
        
        assert isinstance(result, DCFResult)
        assert result.ticker == "AAPL"
        assert result.recommendation in ["BUY", "HOLD", "SELL"]
        assert 0 <= result.confidence <= 1
        assert result.intrinsic_value > 0
    
    def test_sensitivity_notes_high_spread(self, mock_data_package):
        """Test sensitivity notes for high valuation spread"""
        agent = AnalyzerAgent()
        notes = agent._generate_sensitivity_notes(base=100, bull=250, bear=50)
        
        assert "High sensitivity" in notes
    
    def test_sensitivity_notes_low_spread(self, mock_data_package):
        """Test sensitivity notes for tight valuation"""
        agent = AnalyzerAgent()
        notes = agent._generate_sensitivity_notes(base=100, bull=120, bear=90)
        
        assert "Low sensitivity" in notes


# =============================================================================
# Full Pipeline Tests
# =============================================================================

class TestDCFAgentPipeline:
    """Integration tests for full DCF pipeline"""
    
    @patch('agents.dcf_agent.FinancialDataFetcher')
    @patch('agents.dcf_agent.get_tavily_client')
    @patch('agents.dcf_agent.Anthropic')
    def test_full_pipeline(self, mock_anthropic, mock_tavily, mock_fetcher_class):
        """Test end-to-end pipeline"""
        # Setup mocks
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
            "fcf_margin": 0.28,
            "beta": 1.2,
            "total_debt": 110_000_000_000,
            "cash_and_equivalents": 65_000_000_000,
            "shareholders_equity": 60_000_000_000,
            "effective_tax_rate": 0.15,
        }
        
        mock_tavily.return_value = MagicMock()
        
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"recommendation": "HOLD", "confidence": 0.65, "reasoning": "Fair value", "key_risks": ["Growth slowdown"]}')]
        )
        
        # Execute
        agent = DCFAgent()
        result = agent.analyze("AAPL")
        
        # Assert
        assert result.ticker == "AAPL"
        assert result.recommendation in ["BUY", "HOLD", "SELL"]
        assert result.intrinsic_value > 0
        assert result.bull_case_value > result.bear_case_value
    
    def test_format_report(self):
        """Test report formatting"""
        result = DCFResult(
            ticker="AAPL",
            current_price=180.0,
            intrinsic_value=200.0,
            upside_potential=0.11,
            bull_case_value=250.0,
            bear_case_value=160.0,
            wacc=0.095,
            terminal_growth_rate=0.025,
            revenue_growth_rate=0.08,
            fcf_margin=0.28,
            projection_years=5,
            recommendation="BUY",
            confidence=0.75,
            reasoning="Strong fundamentals and growth outlook.",
            key_risks=["Competition from Android", "China revenue exposure"],
            sensitivity_notes="Moderate sensitivity to assumptions.",
        )
        
        agent = DCFAgent()
        report = agent.format_report(result)
        
        assert "AAPL" in report
        assert "BUY" in report
        assert "$200.00" in report or "200.00" in report
        assert "Competition from Android" in report


# =============================================================================
# Data Structure Tests
# =============================================================================

class TestDataStructures:
    """Tests for data classes"""
    
    def test_dcf_data_package_to_dict(self, mock_data_package):
        """Test serialization to dict"""
        d = mock_data_package.to_dict()
        
        assert "company" in d
        assert "financials" in d
        assert "market" in d
        assert d["company"]["ticker"] == "AAPL"
    
    def test_financial_metrics_defaults(self):
        """Test FinancialMetrics defaults"""
        metrics = FinancialMetrics()
        
        assert metrics.beta == 1.0
        assert metrics.effective_tax_rate == 0.21
        assert metrics.historical_revenue == []
    
    def test_market_data_defaults(self):
        """Test MarketData defaults"""
        market = MarketData()
        
        assert market.risk_free_rate == 0.04
        assert market.equity_risk_premium == 0.055
        assert market.data_timestamp is not None
