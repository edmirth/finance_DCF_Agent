"""
Test script to validate DCF Agent setup

Run this script to verify that all dependencies are installed correctly
and the agent can access required APIs.
"""
import sys


def test_imports():
    """Test that all required packages can be imported"""
    print("Testing imports...")

    try:
        import langchain
        print("✓ langchain")
    except ImportError as e:
        print(f"✗ langchain - {e}")
        return False

    try:
        import langchain_openai
        print("✓ langchain_openai")
    except ImportError as e:
        print(f"✗ langchain_openai - {e}")
        return False

    try:
        import openai
        print("✓ openai")
    except ImportError as e:
        print(f"✗ openai - {e}")
        return False

    try:
        import yfinance
        print("✓ yfinance")
    except ImportError as e:
        print(f"✗ yfinance - {e}")
        return False

    try:
        import pandas
        print("✓ pandas")
    except ImportError as e:
        print(f"✗ pandas - {e}")
        return False

    try:
        import numpy
        print("✓ numpy")
    except ImportError as e:
        print(f"✗ numpy - {e}")
        return False

    try:
        from dotenv import load_dotenv
        print("✓ python-dotenv")
    except ImportError as e:
        print(f"✗ python-dotenv - {e}")
        return False

    return True


def test_environment():
    """Test environment variables"""
    print("\nTesting environment...")

    import os
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("✓ OPENAI_API_KEY is set")
        return True
    else:
        print("✗ OPENAI_API_KEY not found in environment")
        print("  Please create a .env file with your OpenAI API key")
        return False


def test_financial_data():
    """Test financial data fetching"""
    print("\nTesting financial data API...")

    try:
        from financial_data import FinancialDataFetcher

        fetcher = FinancialDataFetcher()
        info = fetcher.get_stock_info("AAPL")

        if info and info.get("company_name"):
            print(f"✓ Successfully fetched data for {info.get('company_name')}")
            print(f"  Current Price: ${info.get('current_price', 0):.2f}")
            return True
        else:
            print("✗ Failed to fetch stock info")
            return False

    except Exception as e:
        print(f"✗ Error fetching financial data: {e}")
        return False


def test_dcf_calculator():
    """Test DCF calculator"""
    print("\nTesting DCF calculator...")

    try:
        from dcf_calculator import DCFCalculator, DCFAssumptions

        calculator = DCFCalculator()
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            fcf_margin=0.15,
            terminal_growth_rate=0.025
        )

        wacc = assumptions.calculate_wacc()
        print(f"✓ DCF calculator working")
        print(f"  Calculated WACC: {wacc * 100:.2f}%")
        return True

    except Exception as e:
        print(f"✗ Error in DCF calculator: {e}")
        return False


def test_tools():
    """Test LangChain tools"""
    print("\nTesting LangChain tools...")

    try:
        from tools import get_dcf_tools

        tools = get_dcf_tools()
        print(f"✓ Created {len(tools)} LangChain tools:")
        for tool in tools:
            print(f"  - {tool.name}")
        return True

    except Exception as e:
        print(f"✗ Error creating tools: {e}")
        return False


def test_agent_creation():
    """Test agent creation (requires API key)"""
    print("\nTesting agent creation...")

    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("⊘ Skipping agent test (no API key)")
        return True

    try:
        from agent import create_dcf_agent

        agent = create_dcf_agent()
        print("✓ Agent created successfully")
        return True

    except Exception as e:
        print(f"✗ Error creating agent: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 80)
    print("DCF Analysis Agent - Setup Test")
    print("=" * 80)
    print()

    tests = [
        ("Imports", test_imports),
        ("Environment", test_environment),
        ("Financial Data API", test_financial_data),
        ("DCF Calculator", test_dcf_calculator),
        ("LangChain Tools", test_tools),
        ("Agent Creation", test_agent_creation),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} failed with error: {e}")
            results.append((test_name, False))
        print()

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed! Your DCF Agent is ready to use.")
        print("\nTry running:")
        print("  python main.py --ticker AAPL")
        print("  python main.py --interactive")
        return 0
    else:
        print("\n✗ Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
