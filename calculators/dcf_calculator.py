"""
DCF (Discounted Cash Flow) Calculator with Scenario Analysis
"""
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DCFAssumptions:
    """
    Assumptions for DCF valuation

    IMPORTANT: All parameters are REQUIRED. No defaults are provided.
    This ensures DCF valuations are only performed with actual company-specific data,
    preventing catastrophic errors from using generic assumptions.
    """
    # Growth assumptions - REQUIRED
    revenue_growth_rate: float  # Annual revenue growth rate (e.g., 0.10 for 10%)
    terminal_growth_rate: float  # Perpetual growth rate (e.g., 0.025 for 2.5%)

    # Operating assumptions - REQUIRED
    ebit_margin: float  # EBIT as % of revenue (Operating margin)
    tax_rate: float  # Corporate tax rate (e.g., 0.21 for 21% US federal)

    # Capital intensity - REQUIRED
    capex_to_revenue: float  # CapEx as % of revenue
    depreciation_to_revenue: float  # D&A as % of revenue
    nwc_to_revenue: float  # Net Working Capital as % of revenue

    # Discount rate components (for Cost of Equity) - REQUIRED
    risk_free_rate: float  # Risk-free rate (e.g., 0.04 for 4%)
    market_risk_premium: float  # Equity risk premium (e.g., 0.08 for 8%)
    beta: float  # Stock beta coefficient

    # Debt parameters - REQUIRED
    cost_of_debt: float  # Interest rate on debt (e.g., 0.05 for 5%)
    debt_to_equity_ratio: float  # Target D/E ratio

    # Projection period - REQUIRED
    projection_years: int  # Number of years to project (typically 5)

    def calculate_cost_of_equity(self) -> float:
        """Calculate Cost of Equity using CAPM"""
        return self.risk_free_rate + (self.beta * self.market_risk_premium)

    def calculate_wacc(self, market_value_equity: float, market_value_debt: float) -> float:
        """
        Calculate Weighted Average Cost of Capital with proper debt component

        WACC = (E/V × Re) + (D/V × Rd × (1 - Tax Rate))

        Where:
        - E = Market value of equity
        - D = Market value of debt
        - V = E + D (Total firm value)
        - Re = Cost of equity (CAPM)
        - Rd = Cost of debt
        - Tax Rate = Corporate tax rate
        """
        # Calculate cost of equity
        cost_of_equity = self.calculate_cost_of_equity()

        # Calculate firm value
        total_value = market_value_equity + market_value_debt

        # Avoid division by zero
        if total_value == 0:
            return cost_of_equity

        # Calculate weights
        equity_weight = market_value_equity / total_value
        debt_weight = market_value_debt / total_value

        # Calculate WACC with tax shield on debt
        wacc = (equity_weight * cost_of_equity) + (debt_weight * self.cost_of_debt * (1 - self.tax_rate))

        return wacc


@dataclass
class DCFResult:
    """Results from DCF valuation"""
    intrinsic_value: float
    current_price: float
    upside_potential: float
    intrinsic_value_per_share: float
    enterprise_value: float
    equity_value: float
    terminal_value: float
    projected_fcf: List[float]
    discount_rate: float
    assumptions: DCFAssumptions
    scenario: str = "Base"


class DCFCalculator:
    """Performs DCF valuation with multiple scenarios"""

    def __init__(self):
        pass

    def create_scenarios(self, base_assumptions: DCFAssumptions) -> Dict[str, DCFAssumptions]:
        """Create bull, base, and bear scenarios"""
        scenarios = {}

        # Base case
        scenarios["base"] = base_assumptions

        # Bull case: Higher growth, better margins, lower discount rate
        bull = DCFAssumptions(
            revenue_growth_rate=base_assumptions.revenue_growth_rate * 1.5,
            terminal_growth_rate=base_assumptions.terminal_growth_rate * 1.2,
            ebit_margin=base_assumptions.ebit_margin * 1.2,
            tax_rate=base_assumptions.tax_rate,
            capex_to_revenue=base_assumptions.capex_to_revenue * 0.9,
            depreciation_to_revenue=base_assumptions.depreciation_to_revenue,
            nwc_to_revenue=base_assumptions.nwc_to_revenue * 0.9,
            risk_free_rate=base_assumptions.risk_free_rate,
            market_risk_premium=base_assumptions.market_risk_premium * 0.9,
            beta=base_assumptions.beta * 0.9,
            cost_of_debt=base_assumptions.cost_of_debt,
            debt_to_equity_ratio=base_assumptions.debt_to_equity_ratio,
            projection_years=base_assumptions.projection_years
        )
        scenarios["bull"] = bull

        # Bear case: Lower growth, worse margins, higher discount rate
        bear = DCFAssumptions(
            revenue_growth_rate=base_assumptions.revenue_growth_rate * 0.5,
            terminal_growth_rate=base_assumptions.terminal_growth_rate * 0.6,
            ebit_margin=base_assumptions.ebit_margin * 0.8,
            tax_rate=base_assumptions.tax_rate,
            capex_to_revenue=base_assumptions.capex_to_revenue * 1.1,
            depreciation_to_revenue=base_assumptions.depreciation_to_revenue,
            nwc_to_revenue=base_assumptions.nwc_to_revenue * 1.1,
            risk_free_rate=base_assumptions.risk_free_rate,
            market_risk_premium=base_assumptions.market_risk_premium * 1.1,
            beta=base_assumptions.beta * 1.1,
            cost_of_debt=base_assumptions.cost_of_debt * 1.2,
            debt_to_equity_ratio=base_assumptions.debt_to_equity_ratio,
            projection_years=base_assumptions.projection_years
        )
        scenarios["bear"] = bear

        return scenarios

    def project_free_cash_flows(
        self,
        current_revenue: float,
        assumptions: DCFAssumptions
    ) -> List[float]:
        """
        Project Unlevered Free Cash Flows (UFCF) using proper operating drivers

        UFCF = NOPAT + D&A - CapEx - ΔWC

        Where:
        - NOPAT = EBIT × (1 - Tax Rate)
        - D&A = Depreciation & Amortization (non-cash, add back)
        - CapEx = Capital Expenditures (cash outflow)
        - ΔWC = Change in Net Working Capital (cash impact)
        """
        projected_fcf = []
        revenue = current_revenue
        previous_nwc = current_revenue * assumptions.nwc_to_revenue

        for year in range(1, assumptions.projection_years + 1):
            # Project revenue with declining growth rate (realistic fade)
            growth_rate = assumptions.revenue_growth_rate * (0.95 ** (year - 1))
            revenue = revenue * (1 + growth_rate)

            # Calculate EBIT (Operating Income)
            ebit = revenue * assumptions.ebit_margin

            # Calculate NOPAT (Net Operating Profit After Tax)
            nopat = ebit * (1 - assumptions.tax_rate)

            # Calculate D&A (non-cash expense, add back)
            depreciation = revenue * assumptions.depreciation_to_revenue

            # Calculate CapEx (investment in fixed assets)
            capex = revenue * assumptions.capex_to_revenue

            # Calculate change in Net Working Capital
            current_nwc = revenue * assumptions.nwc_to_revenue
            delta_nwc = current_nwc - previous_nwc
            previous_nwc = current_nwc

            # Calculate Unlevered Free Cash Flow
            ufcf = nopat + depreciation - capex - delta_nwc

            projected_fcf.append(ufcf)

        return projected_fcf

    def calculate_terminal_value(
        self,
        final_fcf: float,
        wacc: float,
        assumptions: DCFAssumptions
    ) -> float:
        """Calculate terminal value using perpetuity growth method"""
        # Terminal FCF
        terminal_fcf = final_fcf * (1 + assumptions.terminal_growth_rate)

        # Terminal value = Terminal FCF / (WACC - Terminal Growth Rate)
        terminal_value = terminal_fcf / (wacc - assumptions.terminal_growth_rate)

        return terminal_value

    def calculate_present_value(
        self,
        cash_flows: List[float],
        discount_rate: float
    ) -> float:
        """Calculate present value of cash flows"""
        pv = 0
        for year, cf in enumerate(cash_flows, start=1):
            pv += cf / ((1 + discount_rate) ** year)
        return pv

    def perform_dcf(
        self,
        ticker: str,
        current_revenue: float,
        current_price: float,
        shares_outstanding: float,
        total_debt: float,
        cash: float,
        assumptions: DCFAssumptions,
        scenario_name: str = "Base"
    ) -> DCFResult:
        """Perform complete DCF valuation"""

        # Calculate market value of equity (for WACC calculation)
        market_value_equity = current_price * shares_outstanding if shares_outstanding > 0 else 0

        # Use book value of debt as proxy for market value
        market_value_debt = total_debt

        # Calculate WACC using proper formula with debt component
        wacc = assumptions.calculate_wacc(market_value_equity, market_value_debt)

        # Project Unlevered Free Cash Flows
        projected_fcf = self.project_free_cash_flows(current_revenue, assumptions)

        # Calculate terminal value
        terminal_value = self.calculate_terminal_value(projected_fcf[-1], wacc, assumptions)

        # Discount projected FCF to present value
        pv_fcf = self.calculate_present_value(projected_fcf, wacc)

        # Discount terminal value to present value
        pv_terminal = terminal_value / ((1 + wacc) ** assumptions.projection_years)

        # Calculate Enterprise Value (present value of all cash flows)
        enterprise_value = pv_fcf + pv_terminal

        # Bridge to Equity Value: EV + Cash - Debt
        equity_value = enterprise_value + cash - total_debt

        # Calculate intrinsic value per share
        intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        # Calculate upside potential
        upside_potential = ((intrinsic_value_per_share - current_price) / current_price * 100) if current_price > 0 else 0

        return DCFResult(
            intrinsic_value=intrinsic_value_per_share,
            current_price=current_price,
            upside_potential=upside_potential,
            intrinsic_value_per_share=intrinsic_value_per_share,
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            terminal_value=terminal_value,
            projected_fcf=projected_fcf,
            discount_rate=wacc,
            assumptions=assumptions,
            scenario=scenario_name
        )

    def analyze_with_scenarios(
        self,
        ticker: str,
        current_revenue: float,
        current_price: float,
        shares_outstanding: float,
        total_debt: float,
        cash: float,
        base_assumptions: DCFAssumptions
    ) -> Dict[str, DCFResult]:
        """Perform DCF analysis with multiple scenarios"""

        scenarios = self.create_scenarios(base_assumptions)
        results = {}

        for scenario_name, assumptions in scenarios.items():
            result = self.perform_dcf(
                ticker=ticker,
                current_revenue=current_revenue,
                current_price=current_price,
                shares_outstanding=shares_outstanding,
                total_debt=total_debt,
                cash=cash,
                assumptions=assumptions,
                scenario_name=scenario_name.capitalize()
            )
            results[scenario_name] = result

        return results

    def format_dcf_analysis(self, results: Dict[str, DCFResult]) -> str:
        """Format DCF results into a readable analysis"""
        output = []
        output.append("=" * 80)
        output.append("DCF VALUATION ANALYSIS")
        output.append("=" * 80)
        output.append("")

        for scenario_name, result in results.items():
            output.append(f"\n{scenario_name.upper()} SCENARIO")
            output.append("-" * 80)
            output.append(f"Current Stock Price: ${result.current_price:,.2f}")
            output.append(f"Intrinsic Value per Share: ${result.intrinsic_value_per_share:,.2f}")
            output.append(f"Upside Potential: {result.upside_potential:.2f}%")
            output.append(f"")
            output.append(f"Enterprise Value: ${result.enterprise_value:,.0f}")
            output.append(f"Equity Value: ${result.equity_value:,.0f}")
            output.append(f"Terminal Value: ${result.terminal_value:,.0f}")
            output.append(f"Discount Rate (WACC): {result.discount_rate * 100:.2f}%")
            output.append(f"")
            output.append(f"Key Assumptions:")
            output.append(f"  Growth & Operations:")
            output.append(f"    - Revenue Growth Rate: {result.assumptions.revenue_growth_rate * 100:.1f}%")
            output.append(f"    - EBIT Margin: {result.assumptions.ebit_margin * 100:.1f}%")
            output.append(f"    - Tax Rate: {result.assumptions.tax_rate * 100:.1f}%")
            output.append(f"  Capital Intensity:")
            output.append(f"    - CapEx/Revenue: {result.assumptions.capex_to_revenue * 100:.1f}%")
            output.append(f"    - D&A/Revenue: {result.assumptions.depreciation_to_revenue * 100:.1f}%")
            output.append(f"    - NWC/Revenue: {result.assumptions.nwc_to_revenue * 100:.1f}%")
            output.append(f"  Discount Rate (WACC):")
            output.append(f"    - Cost of Equity: {result.assumptions.calculate_cost_of_equity() * 100:.2f}%")
            output.append(f"    - Cost of Debt: {result.assumptions.cost_of_debt * 100:.2f}%")
            output.append(f"    - Beta: {result.assumptions.beta:.2f}")
            output.append(f"  Terminal Value:")
            output.append(f"    - Terminal Growth Rate: {result.assumptions.terminal_growth_rate * 100:.1f}%")
            output.append("")

        output.append("=" * 80)

        # Investment recommendation
        base_result = results.get("base")
        if base_result:
            output.append("\nINVESTMENT RECOMMENDATION")
            output.append("-" * 80)
            if base_result.upside_potential > 20:
                output.append("BUY: Stock appears significantly undervalued")
            elif base_result.upside_potential > 0:
                output.append("HOLD: Stock appears fairly valued to slightly undervalued")
            else:
                output.append("SELL: Stock appears overvalued")
            output.append(f"Base case upside potential: {base_result.upside_potential:.2f}%")
            output.append("")

        return "\n".join(output)
