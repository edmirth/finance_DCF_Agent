"""
Portfolio Analysis Tools

Tools for analyzing investment portfolios including:
- Portfolio metrics (P&L, concentration risk, position sizing)
- Sector diversification analysis (Herfindahl index)
- Tax loss harvesting opportunities
"""

import os
import numpy as np
from typing import Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class PortfolioMetricsInput(BaseModel):
    """Input for portfolio metrics calculation"""
    portfolio_json: str = Field(
        description="JSON string of portfolio holdings: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, ...]"
    )


class DiversificationAnalysisInput(BaseModel):
    """Input for diversification analysis"""
    portfolio_json: str = Field(
        description="JSON string of portfolio holdings: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, ...]"
    )


class TaxLossHarvestInput(BaseModel):
    """Input for tax loss harvesting analysis"""
    portfolio_json: str = Field(
        description="JSON string of portfolio holdings: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, ...]"
    )
    min_loss_threshold: float = Field(
        default=1000.0,
        description="Minimum loss amount to consider for harvesting (default: $1000)"
    )


# ============================================================================
# PORTFOLIO TOOLS
# ============================================================================

class CalculatePortfolioMetricsTool(BaseTool):
    """Calculate comprehensive portfolio metrics"""

    name: str = "calculate_portfolio_metrics"
    description: str = """Calculate key portfolio metrics including risk, return, and performance measures.

    Provides:
    - Total portfolio value and P&L
    - Portfolio concentration risk
    - Top winners and losers
    - Position-level analysis

    Use this when the user asks:
    - "How is my portfolio performing?"
    - "Calculate my portfolio metrics"
    - "Show me my portfolio summary"
    """
    args_schema: type[BaseModel] = PortfolioMetricsInput

    def _run(self, portfolio_json: str) -> str:
        """Calculate portfolio metrics"""
        try:
            import json
            from data.financial_data import FinancialDataFetcher

            # Parse portfolio
            holdings = json.loads(portfolio_json)
            if not holdings:
                return "Portfolio is empty. Please provide holdings in format: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, ...]"

            fetcher = FinancialDataFetcher()

            # Fetch current prices and calculate positions
            positions = []
            total_value = 0
            total_cost = 0

            for holding in holdings:
                ticker = holding.get('ticker')
                shares = holding.get('shares')
                cost_basis = holding.get('cost_basis', 0)

                # Validate required fields
                if not ticker or shares is None:
                    logger.warning(f"Skipping invalid holding (missing ticker or shares): {holding}")
                    continue

                ticker = str(ticker).upper()

                try:
                    shares = float(shares)
                    cost_basis = float(cost_basis)
                except (ValueError, TypeError):
                    logger.warning(f"Skipping {ticker}: non-numeric shares or cost_basis")
                    continue

                if shares <= 0:
                    logger.warning(f"Skipping {ticker}: shares must be positive, got {shares}")
                    continue
                if cost_basis < 0:
                    logger.warning(f"Skipping {ticker}: cost_basis cannot be negative, got {cost_basis}")
                    continue

                # Get current stock info
                stock_info = fetcher.get_stock_info(ticker)
                current_price = stock_info.get('current_price', 0)

                if current_price == 0:
                    logger.warning(f"Could not fetch price for {ticker}, skipping")
                    continue

                market_value = shares * current_price
                total_cost_position = shares * cost_basis
                pnl = market_value - total_cost_position
                pnl_pct = (pnl / total_cost_position * 100) if total_cost_position > 0 else None  # None = zero/unknown cost basis

                positions.append({
                    'ticker': ticker,
                    'shares': shares,
                    'cost_basis': cost_basis,
                    'current_price': current_price,
                    'market_value': market_value,
                    'total_cost': total_cost_position,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'weight': 0  # Will calculate after getting total
                })

                total_value += market_value
                total_cost += total_cost_position

            # Calculate weights
            for pos in positions:
                pos['weight'] = (pos['market_value'] / total_value * 100) if total_value > 0 else 0

            # Sort by market value
            positions.sort(key=lambda x: x['market_value'], reverse=True)

            # Calculate overall metrics
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

            # Concentration risk (top 3 positions)
            top3_weight = sum(pos['weight'] for pos in positions[:3])

            # Format output
            output = "## Portfolio Metrics\n\n"
            output += f"**Portfolio Summary:**\n"
            output += f"  • Total Value: ${total_value:,.2f}\n"
            output += f"  • Total Cost Basis: ${total_cost:,.2f}\n"
            output += f"  • Total P&L: ${total_pnl:,.2f} ({total_pnl_pct:+.2f}%)\n"
            output += f"  • Number of Positions: {len(positions)}\n\n"

            output += f"**Risk Metrics:**\n"
            output += f"  • Top 3 Concentration: {top3_weight:.1f}%\n"

            # Simple risk classification
            if top3_weight > 60:
                risk_level = "HIGH (concentrated)"
            elif top3_weight > 40:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW (diversified)"
            output += f"  • Concentration Risk: {risk_level}\n\n"

            output += f"**Top 5 Holdings:**\n\n"
            output += "| Ticker | Shares | Value | Weight | P&L | P&L % |\n"
            output += "|--------|--------|-------|--------|-----|-------|\n"

            for pos in positions[:5]:
                pnl_pct_str = f"{pos['pnl_pct']:+.1f}%" if pos['pnl_pct'] is not None else "N/A"
                output += f"| **{pos['ticker']}** | {pos['shares']:,.0f} | ${pos['market_value']:,.0f} | "
                output += f"{pos['weight']:.1f}% | ${pos['pnl']:,.0f} | {pnl_pct_str} |\n"

            # Winners and Losers (exclude positions with no cost basis)
            winners = sorted([p for p in positions if p['pnl'] > 0 and p['pnl_pct'] is not None], key=lambda x: x['pnl_pct'], reverse=True)[:3]
            losers = sorted([p for p in positions if p['pnl'] < 0 and p['pnl_pct'] is not None], key=lambda x: x['pnl_pct'])[:3]

            if winners:
                output += "\n**Top Winners:**\n"
                for pos in winners:
                    output += f"  • {pos['ticker']}: ${pos['pnl']:,.0f} ({pos['pnl_pct']:+.1f}%)\n"  # pnl_pct guaranteed non-None here

            if losers:
                output += "\n**Top Losers:**\n"
                for pos in losers:
                    output += f"  • {pos['ticker']}: ${pos['pnl']:,.0f} ({pos['pnl_pct']:+.1f}%)\n"  # pnl_pct guaranteed non-None here

            output += f"\n**Next Steps:** Use `analyze_diversification` to check sector exposure or `identify_tax_loss_harvesting` for tax optimization."

            return output

        except json.JSONDecodeError:
            return "Invalid portfolio JSON format. Expected: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, ...]"
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            return f"Error calculating portfolio metrics: {str(e)}"

    async def _arun(self, portfolio_json: str) -> str:
        return self._run(portfolio_json)


class AnalyzeDiversificationTool(BaseTool):
    """Analyze portfolio diversification"""

    name: str = "analyze_diversification"
    description: str = """Analyze portfolio diversification across sectors and industries.

    Provides:
    - Sector allocation breakdown
    - Industry concentration
    - Diversification score
    - Recommendations for better diversification

    Use this when the user asks:
    - "Is my portfolio diversified?"
    - "What sectors am I exposed to?"
    - "Show me sector allocation"
    """
    args_schema: type[BaseModel] = DiversificationAnalysisInput

    def _run(self, portfolio_json: str) -> str:
        """Analyze diversification"""
        try:
            import json
            from data.financial_data import FinancialDataFetcher
            from collections import defaultdict

            # Parse portfolio
            holdings = json.loads(portfolio_json)
            if not holdings:
                return "Portfolio is empty. Please provide holdings."

            fetcher = FinancialDataFetcher()

            # Track sector and industry allocations
            sector_values = defaultdict(float)
            total_value = 0

            for holding in holdings:
                ticker = holding.get('ticker')
                shares = holding.get('shares')

                if not ticker or shares is None:
                    continue

                ticker = str(ticker).upper()
                try:
                    shares = float(shares)
                except (ValueError, TypeError):
                    continue
                if shares <= 0:
                    continue

                # Get stock info for sector/industry
                stock_info = fetcher.get_stock_info(ticker)
                current_price = stock_info.get('current_price', 0)
                sector = stock_info.get('sector', 'Unknown')

                if current_price == 0:
                    continue

                market_value = shares * current_price
                sector_values[sector] += market_value
                total_value += market_value

            # Calculate percentages
            sector_allocation = []
            for sector, value in sector_values.items():
                weight = (value / total_value * 100) if total_value > 0 else 0
                sector_allocation.append({
                    'sector': sector,
                    'value': value,
                    'weight': weight
                })

            sector_allocation.sort(key=lambda x: x['weight'], reverse=True)

            # Diversification score (inverse of Herfindahl index)
            weights = [s['weight']/100 for s in sector_allocation]
            herfindahl = sum(w**2 for w in weights)
            diversification_score = (1 - herfindahl) * 100

            # Format output
            output = "## Diversification Analysis\n\n"
            output += f"**Diversification Score:** {diversification_score:.1f}/100 "

            if diversification_score > 75:
                output += "(Well Diversified)\n\n"
            elif diversification_score > 50:
                output += "(Moderately Diversified)\n\n"
            else:
                output += "(Concentrated)\n\n"

            output += "**Sector Allocation:**\n\n"
            output += "| Sector | Value | Weight |\n"
            output += "|--------|-------|--------|\n"

            for sector in sector_allocation:
                output += f"| {sector['sector']} | ${sector['value']:,.0f} | {sector['weight']:.1f}% |\n"

            # Recommendations
            output += f"\n**Recommendations:**\n"

            max_sector = sector_allocation[0] if sector_allocation else None
            if max_sector and max_sector['weight'] > 40:
                output += f"  **Note:** High concentration in {max_sector['sector']} ({max_sector['weight']:.1f}%)\n"
                output += f"     Consider reducing exposure or diversifying into other sectors\n"

            if len(sector_allocation) < 3:
                output += f"  **Note:** Only {len(sector_allocation)} sector(s) represented\n"
                output += f"     Consider adding positions in different sectors for better diversification\n"

            if diversification_score > 75:
                output += "  Portfolio is well-diversified across sectors\n"

            # Emit pie chart for sector allocation
            if sector_allocation:
                pie_data = [{"label": s["sector"], "value": round(s["weight"], 1)} for s in sector_allocation]
                chart_id = "portfolio_sector_allocation"
                chart_spec = json.dumps({
                    "id": chart_id,
                    "chart_type": "pie",
                    "title": "Portfolio Sector Allocation",
                    "subtitle": "% of total portfolio value",
                    "data": pie_data,
                })
                output += f"\n---CHART_DATA:{chart_id}---\n{chart_spec}\n---END_CHART_DATA:{chart_id}---"
                output += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss sector allocation. Do NOT reproduce the CHART_DATA block.]"

            return output

        except json.JSONDecodeError:
            return "Invalid portfolio JSON format"
        except Exception as e:
            logger.error(f"Error analyzing diversification: {e}")
            return f"Error analyzing diversification: {str(e)}"

    async def _arun(self, portfolio_json: str) -> str:
        return self._run(portfolio_json)


class IdentifyTaxLossHarvestingTool(BaseTool):
    """Identify tax loss harvesting opportunities"""

    name: str = "identify_tax_loss_harvesting"
    description: str = """Find tax loss harvesting opportunities in the portfolio.

    Identifies positions with unrealized losses that can be sold to offset capital gains.

    Use this when the user asks:
    - "What can I sell for tax losses?"
    - "Show me tax loss harvesting opportunities"
    - "Which positions are down?"
    """
    args_schema: type[BaseModel] = TaxLossHarvestInput

    def _run(self, portfolio_json: str, min_loss_threshold: float = 1000.0) -> str:
        """Identify tax loss harvesting opportunities"""
        try:
            import json
            from data.financial_data import FinancialDataFetcher

            # Parse portfolio
            holdings = json.loads(portfolio_json)
            if not holdings:
                return "Portfolio is empty"

            fetcher = FinancialDataFetcher()

            # Find loss positions
            loss_opportunities = []
            total_harvestable_loss = 0

            for holding in holdings:
                ticker = holding.get('ticker')
                shares = holding.get('shares')
                cost_basis = holding.get('cost_basis', 0)

                if not ticker or shares is None:
                    continue

                ticker = str(ticker).upper()
                try:
                    shares = float(shares)
                    cost_basis = float(cost_basis)
                except (ValueError, TypeError):
                    continue
                if shares <= 0 or cost_basis <= 0:
                    continue

                stock_info = fetcher.get_stock_info(ticker)
                current_price = stock_info.get('current_price', 0)

                if current_price == 0:
                    continue

                market_value = shares * current_price
                total_cost = shares * cost_basis
                unrealized_loss = market_value - total_cost

                if unrealized_loss < -min_loss_threshold:
                    loss_pct = (unrealized_loss / total_cost * 100)
                    loss_opportunities.append({
                        'ticker': ticker,
                        'shares': shares,
                        'cost_basis': cost_basis,
                        'current_price': current_price,
                        'unrealized_loss': unrealized_loss,
                        'loss_pct': loss_pct
                    })
                    total_harvestable_loss += unrealized_loss

            # Sort by largest loss
            loss_opportunities.sort(key=lambda x: x['unrealized_loss'])

            # Format output
            if not loss_opportunities:
                return f"No tax loss harvesting opportunities found (minimum loss threshold: ${min_loss_threshold:,.0f}). All positions are either profitable or have losses below the threshold."

            output = "## Tax Loss Harvesting Opportunities\n\n"
            output += f"**Summary:**\n"
            output += f"  • Total Harvestable Losses: ${abs(total_harvestable_loss):,.2f}\n"
            output += f"  • Number of Opportunities: {len(loss_opportunities)}\n"
            output += f"  • Minimum Loss Threshold: ${min_loss_threshold:,.0f}\n\n"

            output += "**Loss Positions:**\n\n"
            output += "| Ticker | Shares | Cost Basis | Current Price | Loss | Loss % |\n"
            output += "|--------|--------|------------|---------------|------|--------|\n"

            for opp in loss_opportunities:
                output += f"| **{opp['ticker']}** | {opp['shares']:,.0f} | ${opp['cost_basis']:.2f} | "
                output += f"${opp['current_price']:.2f} | ${opp['unrealized_loss']:,.0f} | {opp['loss_pct']:.1f}% |\n"

            output += f"\n**Important Notes:**\n"
            output += "  • **Wash Sale Rule:** Do not repurchase the same security within 30 days of the sale\n"
            output += f"  • Consider selling and buying a similar (but not identical) security\n"
            output += f"  • Losses can offset capital gains and up to $3,000 of ordinary income\n"
            output += f"  • Consult a tax professional before executing trades\n"

            return output

        except json.JSONDecodeError:
            return "Invalid portfolio JSON format"
        except Exception as e:
            logger.error(f"Error identifying tax loss harvesting: {e}")
            return f"Error: {str(e)}"

    async def _arun(self, portfolio_json: str, min_loss_threshold: float = 1000.0) -> str:
        return self._run(portfolio_json, min_loss_threshold)


# ============================================================================
# TOOL REGISTRY
# ============================================================================

def get_portfolio_tools() -> List[BaseTool]:
    """Get all portfolio analysis tools"""
    return [
        CalculatePortfolioMetricsTool(),
        AnalyzeDiversificationTool(),
        IdentifyTaxLossHarvestingTool(),
    ]
