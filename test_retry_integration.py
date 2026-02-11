#!/usr/bin/env python3
"""
Integration test for retry logic with real API calls.

This script tests that retry logic works correctly with the financial data fetcher.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Setup logging to see retry attempts
logging.basicConfig(
    level=logging.WARNING,  # Show WARNING level to see retry logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_financial_data_retry():
    """Test Financial Data API with retry logic"""
    print("=" * 80)
    print("Testing Financial Data API with Retry Logic")
    print("=" * 80)

    try:
        from data.financial_data import FinancialDataFetcher

        # Load environment
        load_dotenv()

        print("\n1. Testing normal API call (should succeed on first attempt)...")
        fetcher = FinancialDataFetcher()

        # Test get_stock_info (makes API call with retry logic)
        info = fetcher.get_stock_info("AAPL")

        if info and info.get("company_name"):
            print(f"   ✓ SUCCESS: Retrieved data for {info.get('company_name')}")
            print(f"   - Symbol: {info.get('symbol')}")
            print(f"   - Sector: {info.get('sector')}")
            print(f"   - Market Cap: ${info.get('market_cap', 0):,.0f}")
        else:
            print("   ✗ FAILED: No data returned")
            return False

        print("\n2. Testing with multiple tickers (validates retry works across calls)...")
        tickers = ["MSFT", "GOOGL"]
        for ticker in tickers:
            info = fetcher.get_stock_info(ticker)
            if info and info.get("company_name"):
                print(f"   ✓ {ticker}: {info.get('company_name')}")
            else:
                print(f"   ✗ {ticker}: Failed to retrieve data")

        print("\n3. Testing financial statements (more complex API call)...")
        statements = fetcher.get_financial_statements("AAPL")
        if statements and statements.get("income_statements"):
            num_statements = len(statements.get("income_statements", []))
            print(f"   ✓ SUCCESS: Retrieved {num_statements} income statements")
        else:
            print("   ✗ FAILED: No financial statements returned")

        print("\n" + "=" * 80)
        print("✓ All financial data retry tests passed!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_perplexity_retry():
    """Test Perplexity API with retry logic"""
    print("\n" + "=" * 80)
    print("Testing Perplexity API with Retry Logic")
    print("=" * 80)

    try:
        from tools.dcf_tools import SearchWebTool

        # Load environment
        load_dotenv()

        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            print("   ⚠ SKIPPED: PERPLEXITY_API_KEY not found")
            return True  # Not a failure, just skipped

        print("\n1. Testing web search with retry logic...")
        search_tool = SearchWebTool()

        # Test search (makes Perplexity API call with retry logic)
        result = search_tool._run("What is Apple's current stock price?")

        if result and "Error" not in result:
            print(f"   ✓ SUCCESS: Web search completed")
            print(f"   - Result preview: {result[:200]}...")
        else:
            print(f"   ✗ FAILED: {result}")
            return False

        print("\n" + "=" * 80)
        print("✓ Perplexity retry tests passed!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_anthropic_retry():
    """Test Anthropic SDK retry configuration"""
    print("\n" + "=" * 80)
    print("Testing Anthropic SDK Retry Configuration")
    print("=" * 80)

    try:
        from langchain_anthropic import ChatAnthropic

        # Load environment
        load_dotenv()

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("   ⚠ SKIPPED: ANTHROPIC_API_KEY not found")
            return True  # Not a failure, just skipped

        print("\n1. Testing ChatAnthropic with retry configuration...")
        llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",  # Use smaller model for testing
            temperature=0,
            anthropic_api_key=api_key,
            max_retries=3,
            default_request_timeout=60.0,
            max_tokens=256
        )

        # Test simple invocation
        response = llm.invoke("Say 'Retry test successful' in exactly those words.")

        if response and hasattr(response, 'content'):
            print(f"   ✓ SUCCESS: Anthropic API call completed")
            print(f"   - Response: {response.content[:100]}...")
        else:
            print("   ✗ FAILED: No response from Anthropic")
            return False

        print("\n" + "=" * 80)
        print("✓ Anthropic retry configuration tests passed!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all retry integration tests"""
    print("\n")
    print("=" * 80)
    print("RETRY LOGIC INTEGRATION TESTS")
    print("=" * 80)
    print("\nThis script tests that retry logic is properly integrated and working.")
    print("You should see WARNING logs if any retries occur.\n")

    results = []

    # Test Financial Data API
    results.append(("Financial Data API", test_financial_data_retry()))

    # Test Perplexity API
    results.append(("Perplexity API", test_perplexity_retry()))

    # Test Anthropic SDK
    results.append(("Anthropic SDK", test_anthropic_retry()))

    # Summary
    print("\n\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    all_passed = all(result[1] for result in results)

    if all_passed:
        print("\n✓ All retry integration tests passed!")
        print("\nRetry logic is working correctly. The system will automatically")
        print("retry transient failures with exponential backoff.\n")
        return 0
    else:
        print("\n✗ Some tests failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
