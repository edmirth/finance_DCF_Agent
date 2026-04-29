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

import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

from anthropic import Anthropic

from data.financial_data import FinancialDataFetcher

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
    levered_value: float = 0.0  # Debt-adjusted intrinsic value (Custom Levered DCF)


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
        """Fetch market and macro data from Financial Datasets AI."""
        market = MarketData()

        try:
            data = self.fetcher._make_request(
                "/macro/interest-rates/snapshot", params={"bank": "FED"}
            )
            if data:
                rates = data if isinstance(data, list) else data.get("interest_rates", [])
                for entry in rates if isinstance(rates, list) else [rates]:
                    rate_val = entry.get("rate") or entry.get("value")
                    if rate_val is not None:
                        rate = float(rate_val) / 100
                        if 0.01 < rate < 0.15:
                            market.risk_free_rate = rate
                            logger.info(f"Risk-free rate from Financial Datasets AI: {rate:.2%}")
                            break
        except Exception as e:
            logger.warning(f"Risk-free rate fetch failed: {e}")

        return market


# =============================================================================
# Stage 2: Analyzer Agent
# =============================================================================

class AnalyzerAgent:
    """
    Stage 2 of DCF Pipeline: Performs valuation analysis via FMP DCF API.

    Calls FMP's /stable/custom-discounted-cash-flow with our agent-determined
    assumptions (growth rate, beta, risk-free rate) so that FMP handles the
    full WACC calculation (debt + equity weighted) and FCF projection engine.

    Three scenarios are run:
      Bull  — growth × 1.5, beta × 0.9
      Base  — growth as-determined, beta as-fetched
      Bear  — growth × 0.5, beta × 1.1

    Falls back to FMP's pre-calculated simple DCF if the custom endpoint fails.
    """

    def __init__(self, model: str = SONNET_MODEL):
        self.model = model
        self.client = Anthropic()
        self.fetcher = FinancialDataFetcher()

    def analyze(self, data: DCFDataPackage) -> DCFResult:
        ticker = data.company.ticker
        logger.info(f"[AnalyzerAgent] Starting FMP DCF analysis for {ticker}")

        growth_rate = self._determine_growth_rate(data)
        beta        = data.financials.beta
        # FMP custom DCF expects rates as percentages (4.2, not 0.042)
        rf_pct  = data.market.risk_free_rate * 100
        erp_pct = data.market.equity_risk_premium * 100
        terminal_growth_pct = 2.5

        logger.info(
            f"[AnalyzerAgent] Inputs — growth: {growth_rate:.1%}, beta: {beta:.2f}, "
            f"rf: {rf_pct:.2f}%, erp: {erp_pct:.2f}%"
        )

        shared_kwargs = dict(
            beta=beta,
            risk_free_rate_pct=rf_pct,
            market_risk_premium_pct=erp_pct,
            long_term_growth_rate=terminal_growth_pct,
        )

        # ── Custom DCF (unlevered) — three scenarios ──────────────────────────
        base_result = self.fetcher.get_fmp_dcf(
            ticker, revenue_growth_pct=growth_rate, **shared_kwargs
        )
        bull_result = self.fetcher.get_fmp_dcf(
            ticker, revenue_growth_pct=growth_rate * 1.5,
            beta=beta * 0.9, risk_free_rate_pct=rf_pct,
            market_risk_premium_pct=erp_pct, long_term_growth_rate=terminal_growth_pct,
        )
        bear_result = self.fetcher.get_fmp_dcf(
            ticker, revenue_growth_pct=growth_rate * 0.5,
            beta=beta * 1.1, risk_free_rate_pct=rf_pct,
            market_risk_premium_pct=erp_pct, long_term_growth_rate=terminal_growth_pct,
        )

        # ── Custom Levered DCF — base scenario only (debt-adjusted comparison) ─
        levered_result = self.fetcher.get_fmp_dcf(
            ticker, revenue_growth_pct=growth_rate, levered=True, **shared_kwargs
        )

        base_value   = base_result.get("dcf") or 0.0
        bull_value   = bull_result.get("dcf") or 0.0
        bear_value   = bear_result.get("dcf") or 0.0
        levered_value = levered_result.get("dcf") or 0.0
        # wacc comes back as a percentage from FMP (8.99 = 8.99%)
        wacc = (base_result.get("wacc") or 0.0) / 100

        # Fallback: if custom DCF unavailable (plan tier / no key), use
        # both simple pre-calculated FMP endpoints
        if base_value == 0:
            logger.warning("[AnalyzerAgent] Custom DCF returned zero — falling back to simple FMP DCF")
            simple         = self.fetcher.get_fmp_dcf(ticker)
            simple_levered = self.fetcher.get_fmp_dcf(ticker, levered=True)
            base_value    = simple.get("dcf") or 0.0
            levered_value = simple_levered.get("dcf") or 0.0
            bull_value    = base_value * 1.40
            bear_value    = base_value * 0.65

        current_price = data.company.current_price
        upside = (base_value - current_price) / current_price if current_price > 0 else 0.0

        recommendation, confidence, reasoning, key_risks = self._generate_recommendation(
            data=data,
            base_value=base_value,
            bull_value=bull_value,
            bear_value=bear_value,
            levered_value=levered_value,
            upside=upside,
            wacc=wacc,
            growth_rate=growth_rate,
        )

        logger.info(
            f"[AnalyzerAgent] Done — base: ${base_value:.2f}, "
            f"upside: {upside:.1%}, rec: {recommendation}"
        )

        return DCFResult(
            ticker=ticker,
            current_price=current_price,
            intrinsic_value=base_value,
            upside_potential=upside,
            bull_case_value=bull_value,
            bear_case_value=bear_value,
            levered_value=levered_value,
            wacc=wacc,
            terminal_growth_rate=terminal_growth_pct / 100,
            revenue_growth_rate=growth_rate,
            fcf_margin=data.financials.fcf_margin,
            projection_years=5,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            key_risks=key_risks,
            sensitivity_notes=self._generate_sensitivity_notes(base_value, bull_value, bear_value),
        )

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
    
    def _generate_recommendation(
        self,
        data: DCFDataPackage,
        base_value: float,
        bull_value: float,
        bear_value: float,
        levered_value: float,
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

DCF VALUATION (Unlevered — Custom DCF):
- Base Case:  ${base_value:.2f} ({upside*100:+.1f}% vs current)
- Bull Case:  ${bull_value:.2f} ({(bull_value/current_price-1)*100:+.1f}% vs current)
- Bear Case:  ${bear_value:.2f} ({(bear_value/current_price-1)*100:+.1f}% vs current)
- Levered (debt-adjusted) Base: ${levered_value:.2f} ({(levered_value/current_price-1)*100:+.1f}% vs current) [Custom Levered DCF]

KEY ASSUMPTIONS:
- WACC: {wacc:.1%}
- Revenue Growth Rate: {growth_rate:.1%}
- FCF Margin: {data.financials.fcf_margin:.1%}
- Terminal Growth: 2.5%

FINANCIAL HEALTH:
- Revenue: ${data.financials.latest_revenue/1e9:.1f}B
- FCF: ${data.financials.latest_fcf/1e9:.1f}B
- Net Debt: ${data.financials.net_debt/1e9:.1f}B
- P/E: {f"{data.financials.pe_ratio:.1f}x" if data.financials.pe_ratio else "N/A"}
- EV/EBITDA: {f"{data.financials.ev_to_ebitda:.1f}x" if data.financials.ev_to_ebitda else "N/A"}

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

Unlevered DCF (Custom DCF):
  • Bull Case: ${result.bull_case_value:,.2f}  ({(result.bull_case_value/result.current_price-1)*100:+.1f}%)
  • Base Case: ${result.intrinsic_value:,.2f}  ({upside_pct:+.1f}%)
  • Bear Case: ${result.bear_case_value:,.2f}  ({(result.bear_case_value/result.current_price-1)*100:+.1f}%)

Levered DCF (Custom Levered DCF — debt adjusted):
  • Base Case: ${result.levered_value:,.2f}  ({(result.levered_value/result.current_price-1)*100:+.1f}%)

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
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="DCF Valuation Agent")
    parser.add_argument("ticker", help="Stock ticker to analyze")
    parser.add_argument("--model", default=SONNET_MODEL, help="LLM model to use")
    
    args = parser.parse_args()
    
    agent = DCFAgent(model=args.model)
    result = agent.analyze(args.ticker)
    
    print(agent.format_report(result))


if __name__ == "__main__":
    main()
