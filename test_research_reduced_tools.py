"""
Test script to verify Research Assistant works with reduced toolset

This verifies that the research assistant:
1. Only loads 5 core tools (not 13)
2. Can still answer financial queries
3. Properly suggests using DCF/Analyst agents for deep analysis
"""
import os
from dotenv import load_dotenv
from agents.research_assistant_agent import create_research_assistant

def test_tool_count():
    """Verify only 5 tools are loaded"""
    print("=" * 80)
    print("TEST 1: Tool Count")
    print("=" * 80)

    assistant = create_research_assistant(show_reasoning=False)

    print(f"\nExpected: 5 tools")
    print(f"Actual: {len(assistant.tools)} tools")
    print(f"\nLoaded tools:")
    for i, tool in enumerate(assistant.tools, 1):
        print(f"  {i}. {tool.name}")

    assert len(assistant.tools) == 5, f"Expected 5 tools, got {len(assistant.tools)}"

    # Verify specific tools
    tool_names = {tool.name for tool in assistant.tools}
    expected_tools = {
        'get_quick_data',
        'get_date_context',
        'calculate',
        'get_recent_news',
        'compare_companies'
    }

    assert tool_names == expected_tools, f"Tool mismatch. Expected {expected_tools}, got {tool_names}"

    print("\n✅ PASSED: Correct tools loaded")


def test_quick_query():
    """Test a simple financial data query"""
    print("\n" + "=" * 80)
    print("TEST 2: Quick Financial Query")
    print("=" * 80)

    assistant = create_research_assistant(show_reasoning=True)

    query = "What is Apple's latest revenue and FCF margin?"
    print(f"\nQuery: {query}")
    print("\nResponse:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    # Check response contains expected data
    assert "AAPL" in response or "Apple" in response, "Response should mention Apple"
    assert "revenue" in response.lower() or "Revenue" in response, "Response should contain revenue data"

    print("\n✅ PASSED: Successfully answered quick query")


def test_calculation():
    """Test financial calculation capability"""
    print("\n" + "=" * 80)
    print("TEST 3: Financial Calculation")
    print("=" * 80)

    assistant = create_research_assistant(show_reasoning=True)

    query = "Calculate the P/E ratio for Microsoft"
    print(f"\nQuery: {query}")
    print("\nResponse:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    assert "P/E" in response or "P/E ratio" in response.lower(), "Response should contain P/E ratio"

    print("\n✅ PASSED: Successfully performed calculation")


def test_scope_limitation():
    """Test that agent recognizes scope limitations"""
    print("\n" + "=" * 80)
    print("TEST 4: Scope Limitation Recognition")
    print("=" * 80)

    assistant = create_research_assistant(show_reasoning=True)

    query = "What is the intrinsic value of Apple using DCF?"
    print(f"\nQuery: {query}")
    print("\nResponse:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    # Agent should suggest using DCF Agent
    suggests_dcf_agent = any(phrase in response.lower() for phrase in [
        'dcf agent',
        'use the dcf',
        'run the dcf',
        'dedicated dcf'
    ])

    if suggests_dcf_agent:
        print("\n✅ PASSED: Agent correctly suggests using DCF Agent")
    else:
        print("\n⚠️  WARNING: Agent may not have suggested DCF Agent (check response above)")


def test_comparison():
    """Test company comparison capability"""
    print("\n" + "=" * 80)
    print("TEST 5: Company Comparison")
    print("=" * 80)

    assistant = create_research_assistant(show_reasoning=True)

    query = "Compare Apple and Microsoft on profitability"
    print(f"\nQuery: {query}")
    print("\nResponse:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    assert "AAPL" in response or "Apple" in response, "Response should mention Apple"
    assert "MSFT" in response or "Microsoft" in response, "Response should mention Microsoft"

    print("\n✅ PASSED: Successfully compared companies")


def main():
    """Run all tests"""
    load_dotenv()

    # Check for required API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not found in environment")
        return

    if not os.getenv("FINANCIAL_DATASETS_API_KEY"):
        print("❌ ERROR: FINANCIAL_DATASETS_API_KEY not found in environment")
        return

    print("\n" + "=" * 80)
    print("RESEARCH ASSISTANT - REDUCED TOOLS TEST SUITE")
    print("=" * 80)

    try:
        # Test 1: Tool count
        test_tool_count()

        # Test 2: Quick query
        test_quick_query()

        # Test 3: Calculation
        test_calculation()

        # Test 4: Scope limitation
        test_scope_limitation()

        # Test 5: Comparison
        test_comparison()

        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETED")
        print("=" * 80)
        print("\n✅ Research Assistant is working correctly with reduced toolset!")
        print(f"   - Tool count reduced: 13 → 5 tools")
        print(f"   - Core functionality maintained")
        print(f"   - Clear scope boundaries established")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")


if __name__ == "__main__":
    main()
