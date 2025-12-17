"""
Example usage of the DCF Analysis Agent

This script demonstrates various ways to use the agent programmatically.
"""
import os
from dotenv import load_dotenv
from agent import create_dcf_agent
from financial_data import FinancialDataFetcher
from dcf_calculator import DCFCalculator, DCFAssumptions

# Load environment variables
load_dotenv()


def example_1_quick_analysis():
    """Example 1: Quick DCF analysis on a single stock"""
    print("=" * 80)
    print("Example 1: Quick DCF Analysis")
    print("=" * 80)

    agent = create_dcf_agent()
    result = agent.quick_dcf("AAPL")
    print(result)


def example_2_custom_query():
    """Example 2: Custom analysis with specific requirements"""
    print("\n" + "=" * 80)
    print("Example 2: Custom Query")
    print("=" * 80)

    agent = create_dcf_agent()

    # Ask for analysis with conservative assumptions
    query = """
    Perform a DCF analysis on Microsoft (MSFT) using conservative assumptions.
    Use a revenue growth rate of 8% and FCF margin of 20%.
    """

    result = agent.analyze(query)
    print(result)


def example_3_compare_stocks():
    """Example 3: Compare multiple stocks"""
    print("\n" + "=" * 80)
    print("Example 3: Compare Multiple Stocks")
    print("=" * 80)

    agent = create_dcf_agent()
    tickers = ["AAPL", "MSFT", "GOOGL"]

    for ticker in tickers:
        print(f"\n--- Analyzing {ticker} ---\n")
        result = agent.quick_dcf(ticker)
        print(result)
        print("\n")


def example_4_direct_api_usage():
    """Example 4: Use the underlying APIs directly without agent"""
    print("\n" + "=" * 80)
    print("Example 4: Direct API Usage (Without Agent)")
    print("=" * 80)

    ticker = "TSLA"

    # Fetch data
    fetcher = FinancialDataFetcher()
    info = fetcher.get_stock_info(ticker)
    metrics = fetcher.get_key_metrics(ticker)

    print(f"\nCompany: {info.get('company_name')}")
    print(f"Current Price: ${info.get('current_price'):.2f}")
    print(f"Latest Revenue: ${metrics.get('latest_revenue'):,.0f}")
    print(f"Latest FCF: ${metrics.get('latest_fcf'):,.0f}")

    # Calculate historical growth
    revenue_growth = fetcher.calculate_historical_growth_rate(
        metrics.get('historical_revenue', [])
    )
    print(f"Historical Revenue Growth: {revenue_growth * 100:.2f}%")

    # Perform DCF with custom assumptions - ALL parameters required
    assumptions = DCFAssumptions(
        revenue_growth_rate=0.15,
        terminal_growth_rate=0.025,
        ebit_margin=0.20,  # 20% EBIT margin for tech company
        tax_rate=0.21,
        capex_to_revenue=0.03,
        depreciation_to_revenue=0.03,
        nwc_to_revenue=0.10,
        risk_free_rate=0.04,
        market_risk_premium=0.08,
        beta=metrics.get('beta', 1.0),
        cost_of_debt=0.05,
        debt_to_equity_ratio=0.3,
        projection_years=5
    )

    calculator = DCFCalculator()
    results = calculator.analyze_with_scenarios(
        ticker=ticker,
        current_revenue=metrics.get('latest_revenue', 0),
        current_price=info.get('current_price', 0),
        shares_outstanding=metrics.get('shares_outstanding', 0),
        total_debt=metrics.get('total_debt', 0),
        cash=metrics.get('cash_and_equivalents', 0),
        base_assumptions=assumptions
    )

    # Print results
    analysis = calculator.format_dcf_analysis(results)
    print(f"\n{analysis}")


def example_5_custom_scenarios():
    """Example 5: Create and analyze custom scenarios"""
    print("\n" + "=" * 80)
    print("Example 5: Custom Scenarios")
    print("=" * 80)

    ticker = "NVDA"

    # Fetch data
    fetcher = FinancialDataFetcher()
    info = fetcher.get_stock_info(ticker)
    metrics = fetcher.get_key_metrics(ticker)

    # Define custom scenarios - ALL parameters required
    scenarios = {
        "Optimistic AI Boom": DCFAssumptions(
            revenue_growth_rate=0.30,
            terminal_growth_rate=0.04,
            ebit_margin=0.35,
            tax_rate=0.21,
            capex_to_revenue=0.05,
            depreciation_to_revenue=0.04,
            nwc_to_revenue=0.12,
            risk_free_rate=0.04,
            market_risk_premium=0.08,
            beta=metrics.get('beta', 1.0),
            cost_of_debt=0.04,
            debt_to_equity_ratio=0.2,
            projection_years=5
        ),
        "Moderate Growth": DCFAssumptions(
            revenue_growth_rate=0.15,
            terminal_growth_rate=0.03,
            ebit_margin=0.28,
            tax_rate=0.21,
            capex_to_revenue=0.04,
            depreciation_to_revenue=0.04,
            nwc_to_revenue=0.10,
            risk_free_rate=0.04,
            market_risk_premium=0.08,
            beta=metrics.get('beta', 1.0),
            cost_of_debt=0.05,
            debt_to_equity_ratio=0.3,
            projection_years=5
        ),
        "Market Saturation": DCFAssumptions(
            revenue_growth_rate=0.05,
            terminal_growth_rate=0.02,
            ebit_margin=0.20,
            tax_rate=0.21,
            capex_to_revenue=0.03,
            depreciation_to_revenue=0.03,
            nwc_to_revenue=0.08,
            risk_free_rate=0.04,
            market_risk_premium=0.08,
            beta=metrics.get('beta', 1.2),
            cost_of_debt=0.06,
            debt_to_equity_ratio=0.4,
            projection_years=5
        )
    }

    calculator = DCFCalculator()

    print(f"\nAnalyzing {ticker} - {info.get('company_name')}")
    print(f"Current Price: ${info.get('current_price'):.2f}\n")

    for scenario_name, assumptions in scenarios.items():
        result = calculator.perform_dcf(
            ticker=ticker,
            current_revenue=metrics.get('latest_revenue', 0),
            current_price=info.get('current_price', 0),
            shares_outstanding=metrics.get('shares_outstanding', 0),
            total_debt=metrics.get('total_debt', 0),
            cash=metrics.get('cash_and_equivalents', 0),
            assumptions=assumptions,
            scenario_name=scenario_name
        )

        print(f"{scenario_name}:")
        print(f"  Intrinsic Value: ${result.intrinsic_value_per_share:.2f}")
        print(f"  Upside Potential: {result.upside_potential:.2f}%")
        print(f"  WACC: {result.discount_rate * 100:.2f}%")
        print()


def example_6_sector_analysis():
    """Example 6: Analyze multiple stocks in a sector"""
    print("\n" + "=" * 80)
    print("Example 6: Tech Sector Analysis")
    print("=" * 80)

    tech_stocks = {
        "AAPL": "Apple",
        "MSFT": "Microsoft",
        "GOOGL": "Google",
        "META": "Meta",
        "AMZN": "Amazon"
    }

    agent = create_dcf_agent()

    results = []

    for ticker, name in tech_stocks.items():
        print(f"\nAnalyzing {name} ({ticker})...")
        try:
            # Use agent to get quick analysis
            query = f"Provide a brief DCF analysis summary for {ticker}, focusing on the base case intrinsic value and upside potential."
            result = agent.analyze(query)
            results.append((ticker, name, result))
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")

    print("\n" + "=" * 80)
    print("SECTOR SUMMARY")
    print("=" * 80)
    for ticker, name, result in results:
        print(f"\n{name} ({ticker}):")
        print(result[:500])  # Print first 500 chars


if __name__ == "__main__":
    # Run examples
    print("DCF Analysis Agent - Example Usage\n")

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment variables.")
        print("Please create a .env file with your OpenAI API key.")
        exit(1)

    # Choose which examples to run
    print("Choose example to run:")
    print("1. Quick DCF Analysis")
    print("2. Custom Query")
    print("3. Compare Multiple Stocks")
    print("4. Direct API Usage")
    print("5. Custom Scenarios")
    print("6. Sector Analysis")
    print("7. Run All Examples")

    choice = input("\nEnter choice (1-7): ").strip()

    examples = {
        "1": example_1_quick_analysis,
        "2": example_2_custom_query,
        "3": example_3_compare_stocks,
        "4": example_4_direct_api_usage,
        "5": example_5_custom_scenarios,
        "6": example_6_sector_analysis,
    }

    if choice in examples:
        examples[choice]()
    elif choice == "7":
        for func in examples.values():
            func()
    else:
        print("Invalid choice")
