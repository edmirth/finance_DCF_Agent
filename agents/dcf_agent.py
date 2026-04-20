"""
DCF Agent — Two-Stage Pipeline

Stage 1: Data Fetch Agent — gathers all financial data, metrics, market info
Stage 2: Analyzer Agent — performs DCF valuation and generates recommendation

This separation of concerns allows:
- Cleaner testing (mock data fetch, test analysis logic)
- Better error handling (data issues vs analysis issues)
- Potential parallelization of data fetches
- Easier extension (add more data sources without touching analysis)
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

from anthropic import Anthropic

from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configuration
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20250929"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class CompanyData:
    """Core company information"""
    ticker: str
    company_name: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: float = 0.0
    current_price: float = 0.0
    shares_outstanding: float = 0.0
    currency: str = "USD"


@dataclass
class FinancialMetrics:
    """Key financial metrics for DCF"""
    # Revenue & Profitability
    latest_revenue: float = 0.0
    revenue_growth_rate: float = 0.0
    historical_revenue: List[float] = field(default_factory=list)
    
    # Margins
    gross_margin: float = 0.0
    operating_margin: float = 0.0
    net_margin: float = 0.0
    fcf_margin: float = 0.0
    
    # Free Cash Flow
    latest_fcf: float = 0.0
    fcf_growth_rate: float = 0.0
    historical_fcf: List[float] = field(default_factory=list)
    
    # Balance Sheet
    total_debt: float = 0.0
    cash_and_equivalents: float = 0.0
    net_debt: float = 0.0
    shareholders_equity: float = 0.0
    
    # Capital Structure
    beta: float = 1.0
    effective_tax_rate: float = 0.21
    cost_of_debt: float = 0.05
    
    # Valuation Multiples (for sanity checks)
    pe_ratio: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    ev_to_revenue: Optional[float] = None
    fcf_yield: Optional[float] = None
    
    # Historical years for context
    historical_years: List[str] = field(default_factory=list)


@dataclass
class MarketData:
    """Market and macro data for DCF assumptions"""
    risk_free_rate: float = 0.04  # 10Y Treasury
    equity_risk_premium: float = 0.055  # Historical average
    sector_beta_avg: Optional[float] = None
    analyst_growth_consensus: Optional[float] = None
    analyst_target_price: Optional[float] = None
    recent_news_summary: str = ""
    data_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DCFDataPackage:
    """Complete data package passed from Stage 1 to Stage 2"""
    company: CompanyData
    financials: FinancialMetrics
    market: MarketData
    data_quality_score: float = 1.0  # 0-1, penalize missing data
    data_issues: List[str] = field(default_factory=list)
    fetch_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "company": asdict(self.company),
            "financials": asdict(self.financials),
            "market": asdict(self.market),
            "data_quality_score": self.data_quality_score,
            "data_issues": self.data_issues,
            "fetch_timestamp": self.fetch_timestamp,
        }


@dataclass
class DCFResult:
    """DCF valuation result"""
    ticker: str
    current_price: float
    
    # Base case
    intrinsic_value: float
    upside_potential: float  # percentage
    
    # Scenario analysis
    bull_case_value: float
    bear_case_value: float
    
    # Key assumptions used
    wacc: float
    terminal_growth_rate: float
    revenue_growth_rate: float
    fcf_margin: float
    projection_years: int
    
    # Recommendation
    recommendation: str  # BUY, HOLD, SELL
    confidence: float  # 0-1
    reasoning: str
    
    # Risk factors
    key_risks: List[str] = field(default_factory=list)
    sensitivity_notes: str = ""


# =============================================================================
# Stage 1: Data Fetch Agent
# =============================================================================

class DataFetchAgent:
    """
    Stage 1 of DCF Pipeline: Gathers all required financial data.
    
    Responsibilities:
    - Fetch company info (name, sector, market cap, price)
    - Fetch financial metrics (revenue, FCF, margins, balance sheet)
    - Fetch market data (risk-free rate, analyst estimates)
    - Validate data quality and flag issues
    - Package everything for the Analyzer Agent
    """
    
    def __init__(self):
        self.fetcher = FinancialDataFetcher()
        self.tavily = None
        try:
            self.tavily = get_tavily_client()
        except Exception as e:
            logger.warning(f"Tavily client not available: {e}")
    
    def fetch(self, ticker: str) -> DCFDataPackage:
        """
        Fetch all data needed for DCF analysis.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            DCFDataPackage with all data and quality metrics
        """
        ticker = ticker.strip().upper()
        logger.info(f"[DataFetchAgent] Starting data fetch for {ticker}")
        
        data_issues = []
        quality_score = 1.0
        
        # 1. Fetch company info
        company = self._fetch_company_info(ticker)
        if not company.company_name:
            data_issues.append("Could not fetch company information")
            quality_score -= 0.3
        
        # 2. Fetch financial metrics
        financials = self._fetch_financial_metrics(ticker)
        if financials.latest_revenue == 0:
            data_issues.append("Missing revenue data")
            quality_score -= 0.2
        if financials.latest_fcf == 0:
            data_issues.append("Missing free cash flow data")
            quality_score -= 0.2
        if not financials.historical_revenue:
            data_issues.append("Missing historical revenue for growth calculation")
            quality_score -= 0.1
        
        # 3. Fetch market data
        market = self._fetch_market_data(ticker, company.sector)
        if market.analyst_growth_consensus is None:
            data_issues.append("No analyst growth consensus available")
            quality_score -= 0.1
        
        # Ensure quality score doesn't go below 0
        quality_score = max(0.0, quality_score)
        
        logger.info(f"[DataFetchAgent] Completed fetch for {ticker}. Quality: {quality_score:.0%}, Issues: {len(data_issues)}")
        
        return DCFDataPackage(
            company=company,
            financials=financials,
            market=market,
            data_quality_score=quality_score,
            data_issues=data_issues,
        )
    
    def _fetch_company_info(self, ticker: str) -> CompanyData:
        """Fetch basic company information"""
        info = self.fetcher.get_stock_info(ticker)
        
        if not info:
            logger.warning(f"No company info returned for {ticker}")
            return CompanyData(ticker=ticker)
        
        return CompanyData(
            ticker=ticker,
            company_name=info.get("company_name", ""),
            sector=info.get("sector", ""),
            industry=info.get("industry", ""),
            market_cap=float(info.get("market_cap", 0) or 0),
            current_price=float(info.get("current_price", 0) or 0),
            currency=info.get("currency", "USD"),
        )
    
    def _fetch_financial_metrics(self, ticker: str) -> FinancialMetrics:
        """Fetch key financial metrics"""
        metrics = self.fetcher.get_key_metrics(ticker)
        
        if not metrics:
            logger.warning(f"No financial metrics returned for {ticker}")
            return FinancialMetrics()
        
        # Calculate FCF margin
        revenue = metrics.get("latest_revenue", 0) or 0
        fcf = metrics.get("latest_fcf", 0) or 0
        fcf_margin = fcf / revenue if revenue > 0 else 0
        
        # Calculate net debt
        total_debt = metrics.get("total_debt", 0) or 0
        cash = metrics.get("cash_and_equivalents", 0) or 0
        net_debt = total_debt - cash
        
        # Get cost of debt
        interest_expense = metrics.get("latest_interest_expense", 0) or 0
        cost_of_debt = interest_expense / total_debt if total_debt > 0 else 0.05
        
        return FinancialMetrics(
            latest_revenue=revenue,
            revenue_growth_rate=metrics.get("revenue_growth_rate") or 0,
            historical_revenue=metrics.get("historical_revenue", []),
            gross_margin=metrics.get("gross_margin") or 0,
            operating_margin=metrics.get("operating_margin") or 0,
            net_margin=metrics.get("net_margin") or 0,
            fcf_margin=fcf_margin,
            latest_fcf=fcf,
            fcf_growth_rate=metrics.get("fcf_growth_rate") or 0,
            historical_fcf=metrics.get("historical_fcf", []),
            total_debt=total_debt,
            cash_and_equivalents=cash,
            net_debt=net_debt,
            shareholders_equity=metrics.get("shareholders_equity", 0) or 0,
            beta=metrics.get("beta", 1.0) or 1.0,
            effective_tax_rate=metrics.get("effective_tax_rate", 0.21) or 0.21,
            cost_of_debt=cost_of_debt,
            pe_ratio=metrics.get("price_to_earnings"),
            ev_to_ebitda=metrics.get("ev_to_ebitda"),
            ev_to_revenue=metrics.get("ev_to_revenue"),
            fcf_yield=metrics.get("fcf_yield"),
            historical_years=metrics.get("historical_years", []),
        )
    
    def _fetch_market_data(self, ticker: str, sector: str) -> MarketData:
        """Fetch market and macro data"""
        market = MarketData()
        
        if not self.tavily:
            logger.warning("Tavily not available, using default market assumptions")
            return market
        
        try:
            # Search for current risk-free rate and analyst estimates
            query = f"{ticker} stock analyst price target consensus growth rate 2024 2025"
            result = self.tavily.search_text(
                query=query,
                topic="finance",
                search_depth="basic",
                max_results=3,
                include_answer="basic",
            )
            
            if result:
                market.recent_news_summary = result[:1500]  # Truncate to avoid token bloat
                
                # Try to extract analyst target from search results
                # This is a simple extraction - the Analyzer Agent will interpret it
                
        except Exception as e:
            logger.warning(f"Market data fetch failed: {e}")
        
        # Search for current 10Y Treasury rate
        try:
            rate_query = "current 10 year treasury yield rate today"
            rate_result = self.tavily.search_text(
                query=rate_query,
                topic="finance",
                search_depth="basic",
                max_results=2,
                include_answer="basic",
            )
            
            if rate_result:
                # Try to extract rate - look for patterns like "4.5%" or "4.50%"
                import re
                rate_match = re.search(r'(\d+\.?\d*)\s*%', rate_result)
                if rate_match:
                    rate = float(rate_match.group(1)) / 100
                    if 0.01 < rate < 0.15:  # Sanity check: 1% to 15%
                        market.risk_free_rate = rate
                        logger.info(f"Extracted risk-free rate: {rate:.2%}")
                        
        except Exception as e:
            logger.warning(f"Risk-free rate fetch failed: {e}")
        
        return market


# =============================================================================
# Stage 2: Analyzer Agent
# =============================================================================

class AnalyzerAgent:
    """
    Stage 2 of DCF Pipeline: Performs valuation analysis.
    
    Responsibilities:
    - Calculate WACC
    - Project future cash flows
    - Calculate terminal value
    - Run scenario analysis (bull/base/bear)
    - Generate investment recommendation
    """
    
    def __init__(self, model: str = SONNET_MODEL):
        self.model = model
        self.client = Anthropic()
        
    def analyze(self, data: DCFDataPackage) -> DCFResult:
        """
        Perform DCF analysis on the data package.
        
        Args:
            data: DCFDataPackage from Stage 1
            
        Returns:
            DCFResult with valuation and recommendation
        """
        ticker = data.company.ticker
        logger.info(f"[AnalyzerAgent] Starting DCF analysis for {ticker}")
        
        # 1. Calculate WACC
        wacc = self._calculate_wacc(data)
        logger.info(f"[AnalyzerAgent] WACC: {wacc:.2%}")
        
        # 2. Determine growth assumptions
        growth_rate = self._determine_growth_rate(data)
        terminal_growth = 0.025  # Standard 2.5% perpetual growth
        fcf_margin = data.financials.fcf_margin or 0.15
        projection_years = 5
        
        logger.info(f"[AnalyzerAgent] Growth: {growth_rate:.1%}, FCF margin: {fcf_margin:.1%}")
        
        # 3. Calculate intrinsic value (base case)
        base_value = self._calculate_dcf(
            data=data,
            growth_rate=growth_rate,
            fcf_margin=fcf_margin,
            wacc=wacc,
            terminal_growth=terminal_growth,
            years=projection_years,
        )
        
        # 4. Bull case: +50% growth, +20% margins, -10% WACC
        bull_value = self._calculate_dcf(
            data=data,
            growth_rate=growth_rate * 1.5,
            fcf_margin=fcf_margin * 1.2,
            wacc=wacc * 0.9,
            terminal_growth=terminal_growth,
            years=projection_years,
        )
        
        # 5. Bear case: -50% growth, -20% margins, +10% WACC
        bear_value = self._calculate_dcf(
            data=data,
            growth_rate=growth_rate * 0.5,
            fcf_margin=fcf_margin * 0.8,
            wacc=wacc * 1.1,
            terminal_growth=terminal_growth,
            years=projection_years,
        )
        
        # 6. Calculate upside potential
        current_price = data.company.current_price
        if current_price > 0:
            upside = (base_value - current_price) / current_price
        else:
            upside = 0
        
        # 7. Generate recommendation using LLM
        recommendation, confidence, reasoning, key_risks = self._generate_recommendation(
            data=data,
            base_value=base_value,
            bull_value=bull_value,
            bear_value=bear_value,
            upside=upside,
            wacc=wacc,
            growth_rate=growth_rate,
        )
        
        logger.info(f"[AnalyzerAgent] Complete. Base value: ${base_value:.2f}, Upside: {upside:.1%}, Rec: {recommendation}")
        
        return DCFResult(
            ticker=ticker,
            current_price=current_price,
            intrinsic_value=base_value,
            upside_potential=upside,
            bull_case_value=bull_value,
            bear_case_value=bear_value,
            wacc=wacc,
            terminal_growth_rate=terminal_growth,
            revenue_growth_rate=growth_rate,
            fcf_margin=fcf_margin,
            projection_years=projection_years,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            key_risks=key_risks,
            sensitivity_notes=self._generate_sensitivity_notes(base_value, bull_value, bear_value),
        )
    
    def _calculate_wacc(self, data: DCFDataPackage) -> float:
        """
        Calculate Weighted Average Cost of Capital.
        
        Uses simplified equity-only CAPM when debt data is limited.
        """
        rf = data.market.risk_free_rate
        erp = data.market.equity_risk_premium
        beta = data.financials.beta
        
        # Cost of equity via CAPM
        cost_of_equity = rf + (beta * erp)
        
        # If we have debt, calculate weighted average
        total_debt = data.financials.total_debt
        market_cap = data.company.market_cap
        
        if total_debt > 0 and market_cap > 0:
            total_capital = total_debt + market_cap
            weight_debt = total_debt / total_capital
            weight_equity = market_cap / total_capital
            
            cost_of_debt = data.financials.cost_of_debt
            tax_rate = data.financials.effective_tax_rate
            
            wacc = (weight_equity * cost_of_equity) + (weight_debt * cost_of_debt * (1 - tax_rate))
        else:
            # Equity-only WACC
            wacc = cost_of_equity
        
        # Sanity bounds: 6% to 20%
        wacc = max(0.06, min(0.20, wacc))
        
        return wacc
    
    def _determine_growth_rate(self, data: DCFDataPackage) -> float:
        """
        Determine revenue growth rate to use in projections.
        
        Priority:
        1. Analyst consensus (if available from market data)
        2. Historical revenue growth (from financials)
        3. Default based on sector
        """
        # Try analyst consensus first
        if data.market.analyst_growth_consensus is not None:
            return data.market.analyst_growth_consensus
        
        # Fall back to historical growth
        if data.financials.revenue_growth_rate:
            return data.financials.revenue_growth_rate
        
        # Default by sector (simplified)
        sector = data.company.sector.lower()
        if "tech" in sector or "software" in sector:
            return 0.15  # 15% for tech
        elif "health" in sector or "pharma" in sector:
            return 0.10  # 10% for healthcare
        elif "financial" in sector or "bank" in sector:
            return 0.05  # 5% for financials
        else:
            return 0.08  # 8% default
    
    def _calculate_dcf(
        self,
        data: DCFDataPackage,
        growth_rate: float,
        fcf_margin: float,
        wacc: float,
        terminal_growth: float,
        years: int,
    ) -> float:
        """
        Calculate intrinsic value per share using DCF.
        
        Projects FCF for N years with declining growth, then terminal value.
        """
        revenue = data.financials.latest_revenue
        if revenue <= 0:
            return 0.0
        
        # Growth decay factor: growth rate declines by 5% each year
        growth_decay = 0.95
        
        # Project future FCFs
        projected_fcfs = []
        current_growth = growth_rate
        current_revenue = revenue
        
        for year in range(1, years + 1):
            current_revenue *= (1 + current_growth)
            fcf = current_revenue * fcf_margin
            projected_fcfs.append(fcf)
            current_growth *= growth_decay  # Decay growth
        
        # Calculate present value of projected FCFs
        pv_fcfs = 0
        for year, fcf in enumerate(projected_fcfs, 1):
            discount_factor = 1 / ((1 + wacc) ** year)
            pv_fcfs += fcf * discount_factor
        
        # Terminal value (Gordon Growth Model)
        terminal_fcf = projected_fcfs[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** years)
        
        # Enterprise value
        enterprise_value = pv_fcfs + pv_terminal
        
        # Equity value = EV + Cash - Debt
        equity_value = enterprise_value + data.financials.cash_and_equivalents - data.financials.total_debt
        
        # Per share value
        shares = data.company.shares_outstanding
        if shares <= 0:
            # Estimate from market cap and price
            if data.company.current_price > 0:
                shares = data.company.market_cap / data.company.current_price
            else:
                shares = 1  # Avoid division by zero
        
        intrinsic_value = equity_value / shares if shares > 0 else 0
        
        return max(0, intrinsic_value)  # Can't be negative
    
    def _generate_recommendation(
        self,
        data: DCFDataPackage,
        base_value: float,
        bull_value: float,
        bear_value: float,
        upside: float,
        wacc: float,
        growth_rate: float,
    ) -> tuple:
        """
        Generate investment recommendation using LLM reasoning.
        
        Returns: (recommendation, confidence, reasoning, key_risks)
        """
        current_price = data.company.current_price
        
        prompt = f"""You are a senior equity analyst writing a DCF-based investment recommendation.

COMPANY: {data.company.company_name} ({data.company.ticker})
SECTOR: {data.company.sector}
INDUSTRY: {data.company.industry}

CURRENT PRICE: ${current_price:.2f}
MARKET CAP: ${data.company.market_cap:,.0f}

DCF VALUATION:
- Base Case Intrinsic Value: ${base_value:.2f} ({upside*100:+.1f}% vs current)
- Bull Case: ${bull_value:.2f} ({(bull_value/current_price-1)*100:+.1f}% vs current)
- Bear Case: ${bear_value:.2f} ({(bear_value/current_price-1)*100:+.1f}% vs current)

KEY ASSUMPTIONS:
- WACC: {wacc:.1%}
- Revenue Growth Rate: {growth_rate:.1%}
- FCF Margin: {data.financials.fcf_margin:.1%}
- Terminal Growth: 2.5%

FINANCIAL HEALTH:
- Revenue: ${data.financials.latest_revenue/1e9:.1f}B
- FCF: ${data.financials.latest_fcf/1e9:.1f}B
- Net Debt: ${data.financials.net_debt/1e9:.1f}B
- P/E: {data.financials.pe_ratio:.1f}x if data.financials.pe_ratio else 'N/A'
- EV/EBITDA: {data.financials.ev_to_ebitda:.1f}x if data.financials.ev_to_ebitda else 'N/A'

DATA QUALITY: {data.data_quality_score:.0%}
DATA ISSUES: {', '.join(data.data_issues) if data.data_issues else 'None'}

RECENT MARKET CONTEXT:
{data.market.recent_news_summary[:800] if data.market.recent_news_summary else 'No recent news available'}

---

Provide your investment recommendation in exactly this JSON format:
{{
  "recommendation": "BUY" | "HOLD" | "SELL",
  "confidence": 0.0 to 1.0,
  "reasoning": "2-3 sentence explanation citing specific valuation metrics",
  "key_risks": ["risk 1", "risk 2", "risk 3"]
}}

RECOMMENDATION THRESHOLDS:
- BUY: Base case upside > 20% AND bear case upside > -15%
- SELL: Base case upside < -15% OR bear case upside < -40%
- HOLD: Everything else

Adjust confidence based on:
- Data quality score (low quality = lower confidence)
- Valuation range (wide bull/bear spread = lower confidence)
- Consistency with valuation multiples

Respond with ONLY the JSON object."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            
            text = response.content[0].text.strip()
            
            # Parse JSON
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()
            
            parsed = json.loads(text)
            
            recommendation = parsed.get("recommendation", "HOLD").upper()
            if recommendation not in ["BUY", "HOLD", "SELL"]:
                recommendation = "HOLD"
            
            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            
            reasoning = parsed.get("reasoning", "DCF analysis complete.")
            key_risks = parsed.get("key_risks", [])[:5]  # Max 5 risks
            
            return recommendation, confidence, reasoning, key_risks
            
        except Exception as e:
            logger.error(f"LLM recommendation generation failed: {e}")
            
            # Fallback to rule-based recommendation
            if upside > 0.20:
                recommendation = "BUY"
            elif upside < -0.15:
                recommendation = "SELL"
            else:
                recommendation = "HOLD"
            
            return (
                recommendation,
                0.5,
                f"DCF analysis suggests {upside*100:+.1f}% upside potential.",
                ["Model-based recommendation, verify assumptions"],
            )
    
    def _generate_sensitivity_notes(self, base: float, bull: float, bear: float) -> str:
        """Generate sensitivity analysis notes"""
        spread = (bull - bear) / base if base > 0 else 0
        
        if spread > 1.0:
            return "High sensitivity: Wide valuation range indicates significant assumption uncertainty."
        elif spread > 0.5:
            return "Moderate sensitivity: Valuation is reasonably sensitive to growth assumptions."
        else:
            return "Low sensitivity: Valuation is relatively stable across scenarios."


# =============================================================================
# DCF Agent — Main Interface
# =============================================================================

class DCFAgent:
    """
    Two-stage DCF Agent: Data Fetch → Analysis
    
    Usage:
        agent = DCFAgent()
        result = agent.analyze("AAPL")
        print(result.recommendation)
    """
    
    def __init__(self, model: str = SONNET_MODEL):
        self.data_agent = DataFetchAgent()
        self.analyzer_agent = AnalyzerAgent(model=model)
        self.model = model
    
    def analyze(self, ticker: str) -> DCFResult:
        """
        Run full DCF analysis pipeline.
        
        Stage 1: Fetch all required data
        Stage 2: Analyze and generate recommendation
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            DCFResult with valuation and recommendation
        """
        logger.info(f"[DCFAgent] Starting two-stage analysis for {ticker}")
        
        # Stage 1: Data Fetch
        data_package = self.data_agent.fetch(ticker)
        
        # Check if we have enough data to proceed
        if data_package.data_quality_score < 0.3:
            logger.warning(f"Data quality too low ({data_package.data_quality_score:.0%}), analysis may be unreliable")
        
        # Stage 2: Analysis
        result = self.analyzer_agent.analyze(data_package)
        
        return result
    
    def format_report(self, result: DCFResult) -> str:
        """Format DCFResult as a readable report"""
        
        upside_pct = result.upside_potential * 100
        
        report = f"""
{'='*80}
DCF VALUATION ANALYSIS — {result.ticker}
{'='*80}

RECOMMENDATION: {result.recommendation}
Confidence: {result.confidence:.0%}

{result.reasoning}

{'─'*80}
VALUATION SUMMARY
{'─'*80}

Current Stock Price:     ${result.current_price:,.2f}
Intrinsic Value (Base):  ${result.intrinsic_value:,.2f}  ({upside_pct:+.1f}%)

Scenario Analysis:
  • Bull Case: ${result.bull_case_value:,.2f}  ({(result.bull_case_value/result.current_price-1)*100:+.1f}%)
  • Base Case: ${result.intrinsic_value:,.2f}  ({upside_pct:+.1f}%)
  • Bear Case: ${result.bear_case_value:,.2f}  ({(result.bear_case_value/result.current_price-1)*100:+.1f}%)

{'─'*80}
KEY ASSUMPTIONS
{'─'*80}

  • WACC:                {result.wacc:.2%}
  • Revenue Growth Rate: {result.revenue_growth_rate:.1%}
  • FCF Margin:          {result.fcf_margin:.1%}
  • Terminal Growth:     {result.terminal_growth_rate:.1%}
  • Projection Period:   {result.projection_years} years

{'─'*80}
KEY RISKS
{'─'*80}
"""
        
        for i, risk in enumerate(result.key_risks, 1):
            report += f"  {i}. {risk}\n"
        
        report += f"""
{'─'*80}
SENSITIVITY NOTES
{'─'*80}

{result.sensitivity_notes}

{'='*80}
"""
        
        return report


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Command-line interface for DCF Agent"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DCF Valuation Agent")
    parser.add_argument("ticker", help="Stock ticker to analyze")
    parser.add_argument("--model", default=SONNET_MODEL, help="LLM model to use")
    
    args = parser.parse_args()
    
    agent = DCFAgent(model=args.model)
    result = agent.analyze(args.ticker)
    
    print(agent.format_report(result))


if __name__ == "__main__":
    main()
