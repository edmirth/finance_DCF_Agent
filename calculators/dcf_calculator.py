"""
DCF (Discounted Cash Flow) Calculator with Scenario Analysis

Professional-grade implementation using:
1. Industry-standard UFCF formula: NOPAT + D&A - CapEx - ΔNWC
2. Forward-looking growth projections (analyst consensus → industry average → terminal)
3. Normalized NWC as % of revenue (avoids volatility from raw balance sheet changes)
"""
import math
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DCFAssumptions:
    """
    Assumptions for DCF valuation using industry-standard methodology.

    Growth Projection Approach:
    - Years 1-2: Use near_term_growth_rate (from analyst consensus)
    - Years 3-5: Fade from near_term toward long_term_growth_rate
    - Terminal: Use terminal_growth_rate (GDP + inflation, ~2.5%)

    FCF Calculation (UFCF Method):
    UFCF = NOPAT + D&A - CapEx - ΔNWC
    Where NOPAT = EBIT × (1 - Tax Rate)
    """
    # === GROWTH ASSUMPTIONS (Forward-Looking) ===
    # Near-term growth should come from analyst consensus, NOT historical CAGR
    near_term_growth_rate: float  # Years 1-2: Analyst consensus (e.g., 0.20 for 20%)
    long_term_growth_rate: float  # Years 3-5 fade target: Industry average (e.g., 0.08 for 8%)
    terminal_growth_rate: float   # Perpetuity: GDP + inflation (e.g., 0.025 for 2.5%)

    # === OPERATING ASSUMPTIONS ===
    ebit_margin: float            # EBIT as % of revenue (Operating margin)
    tax_rate: float               # Effective tax rate (e.g., 0.21 for 21%)

    # === CAPITAL INTENSITY (as % of revenue, normalized) ===
    capex_to_revenue: float       # CapEx as % of revenue (e.g., 0.05 for 5%)
    depreciation_to_revenue: float  # D&A as % of revenue (e.g., 0.04 for 4%)
    nwc_to_revenue: float         # NWC as % of revenue, normalized (e.g., 0.10 for 10%)

    # === DISCOUNT RATE COMPONENTS ===
    risk_free_rate: float         # Current 10-year Treasury yield (e.g., 0.045 for 4.5%)
    market_risk_premium: float    # Equity risk premium (e.g., 0.055 for 5.5%)
    beta: float                   # Stock beta coefficient
    cost_of_debt: float           # Pre-tax cost of debt (e.g., 0.05 for 5%)

    # === PROJECTION PARAMETERS ===
    projection_years: int = 5     # Typically 5 years for DCF

    def __post_init__(self):
        """Validate assumption values after initialization."""
        # Bug #6 Fix: Validate tax rate bounds [0, 1]
        if self.tax_rate < 0:
            logger.warning(
                f"Tax rate ({self.tax_rate:.2%}) is negative. Clamping to 0%."
            )
            object.__setattr__(self, 'tax_rate', 0.0)
        elif self.tax_rate > 1:
            logger.warning(
                f"Tax rate ({self.tax_rate:.2%}) exceeds 100%. Clamping to 100%."
            )
            object.__setattr__(self, 'tax_rate', 1.0)

        # Validate projection_years
        if self.projection_years < 1:
            logger.warning(
                f"projection_years ({self.projection_years}) must be at least 1. Setting to 1."
            )
            object.__setattr__(self, 'projection_years', 1)

    def calculate_cost_of_equity(self) -> float:
        """Calculate Cost of Equity using CAPM: Re = Rf + β × MRP"""
        cost_of_equity = self.risk_free_rate + (self.beta * self.market_risk_premium)

        # Ensure cost of equity is at least the risk-free rate
        # Equity should always demand a premium over risk-free debt
        if cost_of_equity < self.risk_free_rate:
            logger.warning(
                f"Calculated Cost of Equity ({cost_of_equity:.2%}) is below risk-free rate "
                f"({self.risk_free_rate:.2%}) due to negative beta ({self.beta:.2f}). "
                f"Flooring at risk-free rate."
            )
            return self.risk_free_rate

        return cost_of_equity

    def calculate_wacc(self, market_value_equity: float, market_value_debt: float) -> float:
        """
        Calculate Weighted Average Cost of Capital.

        WACC = (E/V × Re) + (D/V × Rd × (1 - T))

        Where:
        - E/V = Equity weight
        - D/V = Debt weight
        - Re = Cost of equity (CAPM)
        - Rd = Cost of debt
        - T = Tax rate (provides tax shield on debt)
        """
        cost_of_equity = self.calculate_cost_of_equity()

        # Validate market value of equity
        if market_value_equity <= 0:
            logger.warning(
                f"Market value of equity ({market_value_equity:,.0f}) is zero or negative. "
                f"Using 100% equity WACC (Cost of Equity = {cost_of_equity:.2%})."
            )
            return cost_of_equity

        total_value = market_value_equity + market_value_debt

        if total_value <= 0:
            return cost_of_equity

        equity_weight = market_value_equity / total_value
        debt_weight = market_value_debt / total_value

        # WACC with tax shield on debt
        wacc = (equity_weight * cost_of_equity) + (debt_weight * self.cost_of_debt * (1 - self.tax_rate))

        return wacc

    def get_growth_rate_for_year(self, year: int) -> float:
        """
        Get the appropriate growth rate for a given projection year.

        Growth Rate Trajectory:
        - Year 1-2: near_term_growth_rate (analyst consensus)
        - Year 3-5: Linear fade from near_term to long_term

        This reflects reality: analyst estimates are reliable for 1-2 years,
        then growth fades toward industry average as competitive advantages normalize.
        """
        if year <= 2:
            # Years 1-2: Use analyst consensus
            return self.near_term_growth_rate
        else:
            # Years 3-5: Linear interpolation from near-term to long-term
            # Year 3: 67% near-term, 33% long-term
            # Year 4: 33% near-term, 67% long-term
            # Year 5: 100% long-term
            fade_years = self.projection_years - 2  # Number of years in fade period

            # Handle edge case where projection_years <= 2
            if fade_years <= 0:
                # If projection is 2 years or less, just use near-term rate
                return self.near_term_growth_rate

            year_in_fade = year - 2  # Which year of the fade (1, 2, or 3)
            fade_progress = year_in_fade / fade_years  # 0.33, 0.67, or 1.0

            growth_rate = (
                self.near_term_growth_rate * (1 - fade_progress) +
                self.long_term_growth_rate * fade_progress
            )
            return growth_rate


@dataclass
class DCFResult:
    """Results from DCF valuation"""
    intrinsic_value_per_share: float
    current_price: float
    upside_potential: float
    enterprise_value: float
    equity_value: float
    terminal_value: float
    projected_revenues: List[float]
    projected_fcf: List[float]
    growth_rates_used: List[float]
    discount_rate: float
    assumptions: DCFAssumptions
    scenario: str = "Base"


class DCFCalculator:
    """
    Professional DCF Calculator using industry-standard methodology.

    Key Features:
    1. Forward-looking growth (analyst consensus → industry average → terminal)
    2. UFCF calculation: NOPAT + D&A - CapEx - ΔNWC
    3. Normalized NWC (% of revenue) to avoid balance sheet volatility
    4. Comprehensive validation and error handling
    """

    def __init__(self):
        pass

    def create_scenarios(self, base_assumptions: DCFAssumptions) -> Dict[str, DCFAssumptions]:
        """
        Create bull, base, and bear scenarios with appropriate adjustments.

        Scenario adjustments reflect different views on:
        - Growth trajectory (near-term and long-term)
        - Margin evolution
        - Risk profile (beta, cost of capital)
        """
        scenarios = {}
        scenarios["base"] = base_assumptions

        # === SCENARIO BOUNDS ===
        MAX_TERMINAL_GROWTH = 0.035  # 3.5% max (long-term GDP growth)
        MIN_TERMINAL_GROWTH = 0.01   # 1.0% min (inflation floor)

        # === BULL CASE ===
        # Higher growth, better margins, lower risk
        bull_terminal = min(base_assumptions.terminal_growth_rate * 1.2, MAX_TERMINAL_GROWTH)
        bull = DCFAssumptions(
            # Growth: More optimistic trajectory
            near_term_growth_rate=base_assumptions.near_term_growth_rate * 1.25,
            long_term_growth_rate=base_assumptions.long_term_growth_rate * 1.2,
            terminal_growth_rate=bull_terminal,
            # Margins: Expansion
            ebit_margin=base_assumptions.ebit_margin * 1.15,
            tax_rate=base_assumptions.tax_rate,
            # Capital intensity: More efficient
            capex_to_revenue=base_assumptions.capex_to_revenue * 0.9,
            depreciation_to_revenue=base_assumptions.depreciation_to_revenue,
            nwc_to_revenue=base_assumptions.nwc_to_revenue * 0.9,
            # Risk: Lower
            risk_free_rate=base_assumptions.risk_free_rate,
            market_risk_premium=base_assumptions.market_risk_premium * 0.9,
            beta=base_assumptions.beta * 0.9,
            cost_of_debt=base_assumptions.cost_of_debt,
            projection_years=base_assumptions.projection_years
        )
        scenarios["bull"] = bull

        # === BEAR CASE ===
        # Lower growth, margin compression, higher risk
        bear_terminal = max(base_assumptions.terminal_growth_rate * 0.7, MIN_TERMINAL_GROWTH)
        bear = DCFAssumptions(
            # Growth: More conservative trajectory
            near_term_growth_rate=base_assumptions.near_term_growth_rate * 0.7,
            long_term_growth_rate=base_assumptions.long_term_growth_rate * 0.6,
            terminal_growth_rate=bear_terminal,
            # Margins: Compression
            ebit_margin=base_assumptions.ebit_margin * 0.85,
            tax_rate=base_assumptions.tax_rate,
            # Capital intensity: Less efficient
            capex_to_revenue=base_assumptions.capex_to_revenue * 1.1,
            depreciation_to_revenue=base_assumptions.depreciation_to_revenue,
            nwc_to_revenue=base_assumptions.nwc_to_revenue * 1.1,
            # Risk: Higher
            risk_free_rate=base_assumptions.risk_free_rate,
            market_risk_premium=base_assumptions.market_risk_premium * 1.1,
            beta=base_assumptions.beta * 1.15,
            cost_of_debt=base_assumptions.cost_of_debt * 1.1,
            projection_years=base_assumptions.projection_years
        )
        scenarios["bear"] = bear

        return scenarios

    def project_revenues(
        self,
        current_revenue: float,
        assumptions: DCFAssumptions
    ) -> tuple[List[float], List[float]]:
        """
        Project revenues using forward-looking growth rates.

        Returns:
            Tuple of (projected_revenues, growth_rates_used)
        """
        revenues = []
        growth_rates = []
        revenue = current_revenue

        for year in range(1, assumptions.projection_years + 1):
            growth_rate = assumptions.get_growth_rate_for_year(year)
            growth_rates.append(growth_rate)
            revenue = revenue * (1 + growth_rate)
            revenues.append(revenue)

        logger.info(
            f"Revenue projection: Year 1-2 growth={assumptions.near_term_growth_rate:.1%}, "
            f"fading to {assumptions.long_term_growth_rate:.1%} by Year {assumptions.projection_years}"
        )

        return revenues, growth_rates

    def calculate_ufcf(
        self,
        revenues: List[float],
        current_revenue: float,
        assumptions: DCFAssumptions
    ) -> List[float]:
        """
        Calculate Unlevered Free Cash Flow using industry-standard formula.

        UFCF = NOPAT + D&A - CapEx - ΔNWC

        Where:
        - NOPAT = EBIT × (1 - Tax Rate)
        - D&A = Depreciation & Amortization
        - CapEx = Capital Expenditures
        - ΔNWC = Change in Net Working Capital

        NWC is calculated as % of revenue (normalized) to avoid volatility
        from raw balance sheet changes.
        """
        projected_fcf = []

        # Initialize previous NWC for ΔNWC calculation
        previous_nwc = current_revenue * assumptions.nwc_to_revenue

        for i, revenue in enumerate(revenues):
            # Calculate EBIT (Operating Income)
            ebit = revenue * assumptions.ebit_margin

            # Calculate NOPAT (Net Operating Profit After Tax)
            nopat = ebit * (1 - assumptions.tax_rate)

            # Calculate D&A (non-cash expense, add back)
            depreciation = revenue * assumptions.depreciation_to_revenue

            # Calculate CapEx (deduct as cash outflow)
            capex = revenue * assumptions.capex_to_revenue

            # Calculate ΔNWC (change in working capital)
            # Using normalized NWC as % of revenue avoids balance sheet volatility
            current_nwc = revenue * assumptions.nwc_to_revenue
            delta_nwc = current_nwc - previous_nwc
            previous_nwc = current_nwc

            # Calculate UFCF
            ufcf = nopat + depreciation - capex - delta_nwc
            projected_fcf.append(ufcf)

            logger.debug(
                f"Year {i+1}: Revenue=${revenue:,.0f}, NOPAT=${nopat:,.0f}, "
                f"D&A=${depreciation:,.0f}, CapEx=${capex:,.0f}, "
                f"ΔNWC=${delta_nwc:,.0f}, UFCF=${ufcf:,.0f}"
            )

        return projected_fcf

    def calculate_terminal_value(
        self,
        final_fcf: float,
        wacc: float,
        terminal_growth_rate: float,
        min_spread: float = 0.01
    ) -> float:
        """
        Calculate terminal value using Gordon Growth Model (Perpetuity Method).

        Terminal Value = FCF_final × (1 + g) / (WACC - g)

        Validates the mathematical constraint: WACC > g + min_spread

        Args:
            final_fcf: Final year free cash flow
            wacc: Weighted average cost of capital (or cost of equity for levered DCF)
            terminal_growth_rate: Perpetual growth rate
            min_spread: Minimum spread between WACC and terminal growth (default 1%)
        """
        # Validate Gordon Growth Model constraint
        if wacc <= terminal_growth_rate:
            raise ValueError(
                f"WACC ({wacc:.2%}) must exceed terminal growth rate ({terminal_growth_rate:.2%}). "
                f"This violates the Gordon Growth Model. Adjust assumptions."
            )

        # Bug #2 Fix: Validate minimum spread to prevent extreme terminal values
        spread = wacc - terminal_growth_rate
        if spread < min_spread:
            logger.warning(
                f"Spread between WACC ({wacc:.2%}) and terminal growth ({terminal_growth_rate:.2%}) "
                f"is only {spread:.2%}, below minimum {min_spread:.2%}. "
                f"This may produce unreliably high terminal values. "
                f"Adjusting spread to minimum {min_spread:.2%}."
            )
            # Adjust wacc to enforce minimum spread
            wacc = terminal_growth_rate + min_spread

        # Warn if final FCF is negative
        if final_fcf < 0:
            logger.warning(
                f"Final year FCF is negative (${final_fcf:,.0f}). "
                "Company may not be suitable for DCF valuation."
            )

        # Terminal value calculation
        terminal_fcf = final_fcf * (1 + terminal_growth_rate)
        terminal_value = terminal_fcf / (wacc - terminal_growth_rate)

        return terminal_value

    def calculate_present_value(
        self,
        cash_flows: List[float],
        discount_rate: float,
        max_discount_rate: float = 1.0
    ) -> float:
        """
        Calculate present value of cash flows.

        Args:
            cash_flows: List of future cash flows
            discount_rate: Discount rate to apply
            max_discount_rate: Maximum allowed discount rate (default 100%)
        """
        # Bug #7 Fix: Bounds checking on discount_rate to prevent overflow
        if discount_rate < 0:
            logger.warning(
                f"Discount rate ({discount_rate:.2%}) is negative. Using 0%."
            )
            discount_rate = 0.0
        elif discount_rate > max_discount_rate:
            logger.warning(
                f"Discount rate ({discount_rate:.2%}) exceeds maximum ({max_discount_rate:.2%}). "
                f"Capping at {max_discount_rate:.2%}."
            )
            discount_rate = max_discount_rate

        # Bug #8 partial fix: Handle empty cash flows list
        if not cash_flows:
            logger.warning("Empty cash flows list provided to calculate_present_value.")
            return 0.0

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
        """
        Perform complete DCF valuation.

        Steps:
        1. Project revenues using forward-looking growth rates
        2. Calculate UFCF for each projection year
        3. Calculate terminal value
        4. Discount all cash flows to present value
        5. Calculate equity value and intrinsic value per share
        """
        # === INPUT VALIDATION ===
        if current_revenue <= 0:
            raise ValueError(f"current_revenue must be positive, got {current_revenue}")
        if current_price <= 0:
            raise ValueError(f"current_price must be positive, got {current_price}")
        if shares_outstanding <= 0:
            raise ValueError(f"shares_outstanding must be positive, got {shares_outstanding}")
        if assumptions.projection_years < 1:
            raise ValueError(f"projection_years must be at least 1, got {assumptions.projection_years}")

        # Data quality warnings
        if cash < 0:
            logger.warning(f"{ticker}: Negative cash value (${cash:,.0f}). Verify data quality.")
        if total_debt < 0:
            logger.warning(f"{ticker}: Negative debt value (${total_debt:,.0f}). Verify data quality.")

        logger.info(f"Performing DCF valuation for {ticker} ({scenario_name} scenario)")

        # === CALCULATE WACC ===
        market_value_equity = current_price * shares_outstanding
        market_value_debt = total_debt
        wacc = assumptions.calculate_wacc(market_value_equity, market_value_debt)

        if wacc <= 0:
            raise ValueError(f"Calculated WACC ({wacc:.4f}) must be positive. Check inputs.")

        logger.info(f"WACC: {wacc:.2%} (Cost of Equity: {assumptions.calculate_cost_of_equity():.2%})")

        # === PROJECT REVENUES ===
        projected_revenues, growth_rates_used = self.project_revenues(current_revenue, assumptions)

        # === CALCULATE UFCF ===
        projected_fcf = self.calculate_ufcf(projected_revenues, current_revenue, assumptions)

        # Bug #8 Fix: Defensive check for empty FCF list
        if not projected_fcf:
            raise ValueError(
                f"Failed to generate projected FCF for {ticker}. "
                "Check revenue projections and assumptions."
            )

        # === CALCULATE TERMINAL VALUE ===
        terminal_value = self.calculate_terminal_value(
            projected_fcf[-1], wacc, assumptions.terminal_growth_rate
        )

        # === DISCOUNT CASH FLOWS ===
        pv_fcf = self.calculate_present_value(projected_fcf, wacc)
        pv_terminal = terminal_value / ((1 + wacc) ** assumptions.projection_years)

        # === CALCULATE VALUES ===
        enterprise_value = pv_fcf + pv_terminal
        equity_value = enterprise_value + cash - total_debt

        # Warn if equity value is negative
        if equity_value < 0:
            logger.warning(
                f"{ticker}: Negative equity value (${equity_value:,.0f}). "
                f"Debt exceeds EV + Cash. May indicate distressed company."
            )

        intrinsic_value_per_share = equity_value / shares_outstanding
        upside_potential = ((intrinsic_value_per_share - current_price) / current_price) * 100

        # === OUTPUT VALIDATION ===
        if math.isinf(intrinsic_value_per_share) or math.isnan(intrinsic_value_per_share):
            raise ValueError("DCF produced invalid result (inf/nan). Check assumptions.")

        return DCFResult(
            intrinsic_value_per_share=intrinsic_value_per_share,
            current_price=current_price,
            upside_potential=upside_potential,
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            terminal_value=terminal_value,
            projected_revenues=projected_revenues,
            projected_fcf=projected_fcf,
            growth_rates_used=growth_rates_used,
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
        """Perform DCF analysis with bull, base, and bear scenarios."""
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
        """Format DCF results into a readable analysis."""
        output = []
        output.append("=" * 80)
        output.append("DCF VALUATION ANALYSIS")
        output.append("=" * 80)

        for scenario_name, result in results.items():
            output.append(f"\n{scenario_name.upper()} SCENARIO")
            output.append("-" * 80)
            output.append(f"Current Stock Price: ${result.current_price:,.2f}")
            output.append(f"Intrinsic Value per Share: ${result.intrinsic_value_per_share:,.2f}")
            output.append(f"Upside Potential: {result.upside_potential:.2f}%")
            output.append("")
            output.append(f"Enterprise Value: ${result.enterprise_value:,.0f}")
            output.append(f"Equity Value: ${result.equity_value:,.0f}")
            output.append(f"Terminal Value: ${result.terminal_value:,.0f}")
            output.append(f"Discount Rate (WACC): {result.discount_rate * 100:.2f}%")
            output.append("")

            # Growth assumptions
            output.append("Growth Assumptions (Forward-Looking):")
            output.append(f"  - Near-term (Yr 1-2): {result.assumptions.near_term_growth_rate * 100:.1f}% (analyst consensus)")
            output.append(f"  - Long-term (Yr 3-5): fading to {result.assumptions.long_term_growth_rate * 100:.1f}% (industry avg)")
            output.append(f"  - Terminal: {result.assumptions.terminal_growth_rate * 100:.1f}% (GDP growth)")
            output.append(f"  - Actual rates used: {[f'{r*100:.1f}%' for r in result.growth_rates_used]}")
            output.append("")

            # Operating assumptions
            output.append("Operating Assumptions:")
            output.append(f"  - EBIT Margin: {result.assumptions.ebit_margin * 100:.1f}%")
            output.append(f"  - Tax Rate: {result.assumptions.tax_rate * 100:.1f}%")
            output.append(f"  - CapEx/Revenue: {result.assumptions.capex_to_revenue * 100:.1f}%")
            output.append(f"  - D&A/Revenue: {result.assumptions.depreciation_to_revenue * 100:.1f}%")
            output.append(f"  - NWC/Revenue: {result.assumptions.nwc_to_revenue * 100:.1f}%")
            output.append("")

            # Discount rate components
            output.append("Discount Rate Components:")
            output.append(f"  - Risk-free Rate: {result.assumptions.risk_free_rate * 100:.2f}%")
            output.append(f"  - Market Risk Premium: {result.assumptions.market_risk_premium * 100:.2f}%")
            output.append(f"  - Beta: {result.assumptions.beta:.2f}")
            output.append(f"  - Cost of Equity: {result.assumptions.calculate_cost_of_equity() * 100:.2f}%")
            output.append(f"  - Cost of Debt: {result.assumptions.cost_of_debt * 100:.2f}%")
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

    # =========================================================================
    # Levered DCF Methods (FCFE-based, for high-leverage companies)
    # =========================================================================

    def calculate_fcfe(
        self,
        ufcf: float,
        interest_expense: float,
        tax_rate: float,
        net_debt_change: float = 0
    ) -> float:
        """
        Calculate Free Cash Flow to Equity from UFCF.

        FCFE = UFCF - Interest(1-T) + Net Borrowing

        Where:
        - UFCF = Unlevered Free Cash Flow (NOPAT + D&A - CapEx - ΔNWC)
        - Interest(1-T) = After-tax interest expense (cash outflow to debt holders)
        - Net Borrowing = New debt issued - Debt repaid (can be positive or negative)

        Args:
            ufcf: Unlevered Free Cash Flow
            interest_expense: Annual interest expense
            tax_rate: Effective tax rate
            net_debt_change: Net new borrowing (positive) or repayment (negative)

        Returns:
            Free Cash Flow to Equity
        """
        after_tax_interest = interest_expense * (1 - tax_rate)
        fcfe = ufcf - after_tax_interest + net_debt_change
        return fcfe

    def perform_levered_dcf(
        self,
        ticker: str,
        current_revenue: float,
        current_price: float,
        shares_outstanding: float,
        total_debt: float,
        cash: float,
        interest_expense: float,
        assumptions: DCFAssumptions,
        scenario_name: str = "Base"
    ) -> DCFResult:
        """
        Perform Levered DCF valuation (FCFE method).

        Key Differences from Unlevered DCF:
        1. Uses FCFE (after debt service) instead of UFCF
        2. Discounts at Cost of Equity (not WACC)
        3. No need to subtract debt from EV (already valued equity directly)

        Use this for:
        - Highly leveraged companies (D/E > 1.0)
        - Financial institutions
        - Companies with significant debt changes

        Args:
            ticker: Stock ticker symbol
            current_revenue: Current annual revenue
            current_price: Current stock price
            shares_outstanding: Number of shares
            total_debt: Total debt
            cash: Cash and equivalents
            interest_expense: Annual interest expense
            assumptions: DCF assumptions
            scenario_name: Scenario name for labeling

        Returns:
            DCFResult with levered valuation
        """
        # === INPUT VALIDATION ===
        if current_revenue <= 0:
            raise ValueError(f"current_revenue must be positive, got {current_revenue}")
        if current_price <= 0:
            raise ValueError(f"current_price must be positive, got {current_price}")
        if shares_outstanding <= 0:
            raise ValueError(f"shares_outstanding must be positive, got {shares_outstanding}")

        # Bug #5 Fix: Warn about unnecessary Levered DCF for zero-debt companies
        if total_debt <= 0:
            logger.warning(
                f"{ticker}: Levered DCF called on company with zero/no debt. "
                "Results will be identical to Unlevered DCF. "
                "Consider using perform_dcf() instead for efficiency."
            )

        logger.info(f"Performing Levered DCF for {ticker} ({scenario_name} scenario)")

        # === CALCULATE COST OF EQUITY (discount rate for FCFE) ===
        cost_of_equity = assumptions.calculate_cost_of_equity()

        if cost_of_equity <= 0:
            raise ValueError(f"Cost of Equity ({cost_of_equity:.4f}) must be positive")

        # Validate Gordon Growth Model constraint
        if cost_of_equity <= assumptions.terminal_growth_rate:
            raise ValueError(
                f"Cost of Equity ({cost_of_equity:.2%}) must exceed terminal growth rate "
                f"({assumptions.terminal_growth_rate:.2%}). Adjust assumptions."
            )

        logger.info(f"Levered DCF using Cost of Equity: {cost_of_equity:.2%}")

        # === PROJECT REVENUES ===
        projected_revenues, growth_rates_used = self.project_revenues(current_revenue, assumptions)

        # === CALCULATE UFCF (intermediate step) ===
        projected_ufcf = self.calculate_ufcf(projected_revenues, current_revenue, assumptions)

        # === CONVERT UFCF TO FCFE ===
        # Assume interest expense scales with debt, and debt scales with revenue
        # This is a simplification - in practice, debt schedule would be modeled explicitly
        debt_to_revenue = total_debt / current_revenue if current_revenue > 0 else 0
        interest_rate = interest_expense / total_debt if total_debt > 0 else assumptions.cost_of_debt

        projected_fcfe = []
        for i, (revenue, ufcf) in enumerate(zip(projected_revenues, projected_ufcf)):
            # Estimate debt and interest for this year
            projected_debt = revenue * debt_to_revenue
            projected_interest = projected_debt * interest_rate

            # Assume debt grows proportionally with revenue (net borrowing)
            if i == 0:
                prev_debt = total_debt
            else:
                prev_debt = projected_revenues[i-1] * debt_to_revenue
            net_debt_change = projected_debt - prev_debt

            # Calculate FCFE
            fcfe = self.calculate_fcfe(
                ufcf=ufcf,
                interest_expense=projected_interest,
                tax_rate=assumptions.tax_rate,
                net_debt_change=net_debt_change
            )
            projected_fcfe.append(fcfe)

            logger.debug(
                f"Year {i+1}: UFCF=${ufcf:,.0f}, Interest=${projected_interest:,.0f}, "
                f"Net Borrow=${net_debt_change:,.0f}, FCFE=${fcfe:,.0f}"
            )

        # Bug #8 Fix: Defensive check for empty FCFE list
        if not projected_fcfe:
            raise ValueError(
                f"Failed to generate projected FCFE for {ticker}. "
                "Check revenue projections and assumptions."
            )

        # === CALCULATE TERMINAL VALUE (using FCFE and Cost of Equity) ===
        terminal_fcfe = projected_fcfe[-1] * (1 + assumptions.terminal_growth_rate)
        terminal_value = terminal_fcfe / (cost_of_equity - assumptions.terminal_growth_rate)

        # Warn if terminal FCFE is negative
        if projected_fcfe[-1] < 0:
            logger.warning(
                f"{ticker}: Final year FCFE is negative (${projected_fcfe[-1]:,.0f}). "
                "Levered DCF may not be appropriate for this company."
            )

        # === DISCOUNT CASH FLOWS (at Cost of Equity) ===
        pv_fcfe = self.calculate_present_value(projected_fcfe, cost_of_equity)
        pv_terminal = terminal_value / ((1 + cost_of_equity) ** assumptions.projection_years)

        # === CALCULATE EQUITY VALUE (direct, no debt subtraction needed) ===
        equity_value = pv_fcfe + pv_terminal

        # Add excess cash (cash above operating needs)
        # Typically assume ~2% of revenue is operating cash
        operating_cash = current_revenue * 0.02
        excess_cash = max(0, cash - operating_cash)
        equity_value += excess_cash

        # Warn if equity value is negative
        if equity_value < 0:
            logger.warning(
                f"{ticker}: Negative equity value (${equity_value:,.0f}) in Levered DCF. "
                "Interest burden may exceed cash generation."
            )

        intrinsic_value_per_share = equity_value / shares_outstanding
        upside_potential = ((intrinsic_value_per_share - current_price) / current_price) * 100

        # Enterprise value for comparison (back-calculate from equity value)
        enterprise_value = equity_value + total_debt - cash

        return DCFResult(
            intrinsic_value_per_share=intrinsic_value_per_share,
            current_price=current_price,
            upside_potential=upside_potential,
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            terminal_value=terminal_value,
            projected_revenues=projected_revenues,
            projected_fcf=projected_fcfe,  # Note: This is FCFE, not UFCF
            growth_rates_used=growth_rates_used,
            discount_rate=cost_of_equity,  # Cost of Equity, not WACC
            assumptions=assumptions,
            scenario=f"{scenario_name} (Levered)"
        )

    def analyze_with_levered_scenarios(
        self,
        ticker: str,
        current_revenue: float,
        current_price: float,
        shares_outstanding: float,
        total_debt: float,
        cash: float,
        interest_expense: float,
        base_assumptions: DCFAssumptions
    ) -> Dict[str, DCFResult]:
        """Perform Levered DCF analysis with bull, base, and bear scenarios."""
        scenarios = self.create_scenarios(base_assumptions)
        results = {}

        for scenario_name, assumptions in scenarios.items():
            result = self.perform_levered_dcf(
                ticker=ticker,
                current_revenue=current_revenue,
                current_price=current_price,
                shares_outstanding=shares_outstanding,
                total_debt=total_debt,
                cash=cash,
                interest_expense=interest_expense,
                assumptions=assumptions,
                scenario_name=scenario_name.capitalize()
            )
            results[scenario_name] = result

        return results
