"""
Comprehensive test suite for Earnings Call Insights Tool

Tests:
1. Tool exists and is properly registered
2. Tool works with multiple tickers (AAPL, TSLA, NVDA)
3. Tool handles specific queries
4. Tool integrates with Earnings Agent
5. Error handling for invalid inputs
"""

import os
from dotenv import load_dotenv
load_dotenv()

def test_tool_registration():
    """Test 1: Verify tool is registered"""
    print("TEST 1: Tool Registration")
    print("="*80)

    from tools.earnings_tools import get_earnings_tools, EarningsCallInsightsTool

    tools = get_earnings_tools()
    tool_names = [t.name for t in tools]

    print(f"Total tools: {len(tools)}")
    print(f"Tool names: {tool_names}")

    assert len(tools) == 7, f"Expected 7 tools, got {len(tools)}"
    assert "get_earnings_call_insights" in tool_names, "Earnings call insights tool not found"

    # Check tool properties
    insights_tool = next(t for t in tools if t.name == "get_earnings_call_insights")
    assert insights_tool.description != "", "Tool description is empty"
    assert "management" in insights_tool.description.lower(), "Description should mention management"
    assert "guidance" in insights_tool.description.lower(), "Description should mention guidance"

    print("✓ PASS: Tool properly registered with 7 total tools")
    print("✓ PASS: Tool has proper description")
    print()
    return True


def test_tool_with_aapl():
    """Test 2: Test with AAPL"""
    print("TEST 2: AAPL Analysis")
    print("="*80)

    from tools.earnings_tools import EarningsCallInsightsTool

    tool = EarningsCallInsightsTool()
    result = tool._run(ticker="AAPL", quarters=1)

    # Quality checks
    checks = {
        "Has header": "# Earnings Call Analysis" in result,
        "Has financial highlights": "financial" in result.lower() and ("revenue" in result.lower() or "earnings" in result.lower()),
        "Has guidance": "guidance" in result.lower() or "outlook" in result.lower(),
        "Has management content": "management" in result.lower() or "CEO" in result or "CFO" in result,
        "Has sentiment analysis": "tone" in result.lower() or "sentiment" in result.lower() or "confidence" in result.lower(),
        "No errors": not result.startswith("Error:"),
        "Reasonable length": len(result) > 1000
    }

    print(f"Result length: {len(result)} chars")
    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")

    all_passed = all(checks.values())
    if all_passed:
        print("\n✓ AAPL test PASSED")
    else:
        print("\n✗ AAPL test FAILED")

    print()
    return all_passed


def test_tool_with_tsla():
    """Test 3: Test with TSLA"""
    print("TEST 3: TSLA Analysis")
    print("="*80)

    from tools.earnings_tools import EarningsCallInsightsTool

    tool = EarningsCallInsightsTool()
    result = tool._run(ticker="TSLA", quarters=1)

    checks = {
        "No errors": not result.startswith("Error:"),
        "Has Tesla content": "tesla" in result.lower() or "TSLA" in result,
        "Reasonable length": len(result) > 1000
    }

    print(f"Result length: {len(result)} chars")
    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")

    all_passed = all(checks.values())
    if all_passed:
        print("\n✓ TSLA test PASSED")
    else:
        print("\n✗ TSLA test FAILED")

    print()
    return all_passed


def test_tool_with_nvda_query():
    """Test 4: Test with NVDA and specific query"""
    print("TEST 4: NVDA with Specific Query")
    print("="*80)

    from tools.earnings_tools import EarningsCallInsightsTool

    tool = EarningsCallInsightsTool()
    result = tool._run(ticker="NVDA", query="What did management say about AI chip demand?", quarters=1)

    checks = {
        "No errors": not result.startswith("Error:"),
        "Has NVDA content": "nvidia" in result.lower() or "NVDA" in result,
        "Addresses query topic": "AI" in result or "chip" in result.lower(),
        "Reasonable length": len(result) > 1000
    }

    print(f"Result length: {len(result)} chars")
    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")

    all_passed = all(checks.values())
    if all_passed:
        print("\n✓ NVDA query test PASSED")
    else:
        print("\n✗ NVDA query test FAILED")

    print()
    return all_passed


def test_error_handling():
    """Test 5: Error handling"""
    print("TEST 5: Error Handling")
    print("="*80)

    from tools.earnings_tools import EarningsCallInsightsTool

    tool = EarningsCallInsightsTool()

    # Test invalid ticker
    result1 = tool._run(ticker="INVALIDTICKER123", quarters=1)

    # Test invalid quarters
    result2 = tool._run(ticker="AAPL", quarters=10)

    checks = {
        "Handles invalid ticker gracefully": "Error" in result1 or len(result1) > 0,
        "Handles invalid quarters": "Error" in result2 and "1-4" in result2
    }

    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")

    all_passed = all(checks.values())
    if all_passed:
        print("\n✓ Error handling test PASSED")
    else:
        print("\n✗ Error handling test FAILED")

    print()
    return all_passed


def test_earnings_agent_integration():
    """Test 6: Integration with Earnings Agent"""
    print("TEST 6: Earnings Agent Integration")
    print("="*80)

    from agents.earnings_agent import EarningsAgent

    # Test Node 4 directly
    agent = EarningsAgent()

    state = {
        'ticker': 'AAPL',
        'quarters_back': 4,
        'errors': []
    }

    result_state = agent.fetch_guidance_and_news(state)

    earnings_guidance = result_state.get('earnings_guidance', '')

    checks = {
        "Node 4 executed": 'earnings_guidance' in result_state,
        "Has earnings call data": len(earnings_guidance) > 1000,
        "Has analysis header": "# Earnings Call Analysis" in earnings_guidance,
        "No errors in state": len(result_state.get('errors', [])) == 0 or not any('guidance' in e.lower() for e in result_state.get('errors', []))
    }

    print(f"Earnings guidance length: {len(earnings_guidance)} chars")
    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")

    all_passed = all(checks.values())
    if all_passed:
        print("\n✓ Earnings Agent integration test PASSED")
    else:
        print("\n✗ Earnings Agent integration test FAILED")

    print()
    return all_passed


def main():
    """Run all tests"""
    print("COMPREHENSIVE EARNINGS CALL INSIGHTS TOOL TEST SUITE")
    print("="*80)
    print()

    # Check API keys
    fmp_key = os.getenv("FMP_API_KEY")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    print("API Key Check:")
    print(f"  FMP_API_KEY: {'✓ Found' if fmp_key else '✗ Missing'}")
    print(f"  PERPLEXITY_API_KEY: {'✓ Found' if perplexity_key else '✗ Missing'}")
    print(f"  ANTHROPIC_API_KEY: {'✓ Found' if anthropic_key else '✗ Missing'}")
    print()

    if not all([fmp_key, perplexity_key, anthropic_key]):
        print("⚠ WARNING: Missing required API keys. Some tests may fail.")
        print()

    # Run tests
    results = []

    try:
        results.append(("Tool Registration", test_tool_registration()))
    except Exception as e:
        print(f"✗ EXCEPTION in Tool Registration: {e}")
        results.append(("Tool Registration", False))

    try:
        results.append(("AAPL Analysis", test_tool_with_aapl()))
    except Exception as e:
        print(f"✗ EXCEPTION in AAPL test: {e}")
        results.append(("AAPL Analysis", False))

    try:
        results.append(("TSLA Analysis", test_tool_with_tsla()))
    except Exception as e:
        print(f"✗ EXCEPTION in TSLA test: {e}")
        results.append(("TSLA Analysis", False))

    try:
        results.append(("NVDA Query", test_tool_with_nvda_query()))
    except Exception as e:
        print(f"✗ EXCEPTION in NVDA test: {e}")
        results.append(("NVDA Query", False))

    try:
        results.append(("Error Handling", test_error_handling()))
    except Exception as e:
        print(f"✗ EXCEPTION in error handling test: {e}")
        results.append(("Error Handling", False))

    try:
        results.append(("Agent Integration", test_earnings_agent_integration()))
    except Exception as e:
        print(f"✗ EXCEPTION in agent integration test: {e}")
        results.append(("Agent Integration", False))

    # Summary
    print()
    print("="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print()
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print()
        print("🎉 ALL TESTS PASSED! 🎉")
        print()
        print("The Earnings Call Insights Tool is working correctly and integrated with the Earnings Agent.")
        return True
    else:
        print()
        print(f"⚠ {total - passed} test(s) failed. Review output above for details.")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
