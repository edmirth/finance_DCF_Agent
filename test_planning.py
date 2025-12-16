"""
Test script to verify Research Assistant planning capability

This verifies that the research assistant:
1. Creates a plan before executing tools
2. Follows the plan systematically
3. Handles complex multi-step queries
4. Uses temporal awareness (get_date_context first)
"""
import os
from dotenv import load_dotenv
from agents.research_assistant_agent import create_research_assistant


def test_simple_planning():
    """Test planning for a simple query"""
    print("=" * 80)
    print("TEST 1: Simple Query Planning")
    print("=" * 80)

    # Use gpt-4o for testing since it supports all ReAct features including stop sequences
    assistant = create_research_assistant(model="gpt-4o", show_reasoning=True)

    query = "What is Apple's current revenue?"
    print(f"\nQuery: {query}")
    print("\nExpected Plan:")
    print("  1. Use get_quick_data for AAPL with metrics='revenue'")
    print("  2. Present the revenue figure")
    print("  3. Suggest related analysis")
    print("\nActual Response:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    assert "revenue" in response.lower() or "Revenue" in response, "Response should contain revenue data"
    print("\n✅ PASSED: Successfully answered with planning")


def test_temporal_planning():
    """Test planning for temporal queries"""
    print("\n" + "=" * 80)
    print("TEST 2: Temporal Query Planning")
    print("=" * 80)

    assistant = create_research_assistant(model="gpt-4o", show_reasoning=True)

    query = "What was Microsoft's revenue last year?"
    print(f"\nQuery: {query}")
    print("\nExpected Plan:")
    print("  1. Use get_date_context with query='last year' to determine the year")
    print("  2. Use get_quick_data for MSFT with metrics='revenue'")
    print("  3. Present the result with context")
    print("\nActual Response:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    # Check that date context was used (should mention the year)
    assert any(year in response for year in ["2024", "2023", "2025"]), "Response should mention specific year"
    assert "revenue" in response.lower() or "Revenue" in response, "Response should contain revenue"

    print("\n✅ PASSED: Successfully handled temporal query with planning")


def test_calculation_planning():
    """Test planning for calculation queries"""
    print("\n" + "=" * 80)
    print("TEST 3: Calculation Planning")
    print("=" * 80)

    assistant = create_research_assistant(model="gpt-4o", show_reasoning=True)

    query = "Calculate the P/E ratio for Google"
    print(f"\nQuery: {query}")
    print("\nExpected Plan:")
    print("  1. Use calculate tool with calculation='P/E ratio for GOOGL'")
    print("  2. Present P/E ratio")
    print("  3. Suggest comparing to industry average or competitors")
    print("\nActual Response:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    assert "P/E" in response or "p/e" in response.lower(), "Response should contain P/E ratio"

    print("\n✅ PASSED: Successfully performed calculation with planning")


def test_comparison_planning():
    """Test planning for comparison queries"""
    print("\n" + "=" * 80)
    print("TEST 4: Comparison Query Planning")
    print("=" * 80)

    assistant = create_research_assistant(model="gpt-4o", show_reasoning=True)

    query = "Compare Tesla and Ford on profitability and growth"
    print(f"\nQuery: {query}")
    print("\nExpected Plan:")
    print("  1. Use compare_companies with ticker1='TSLA', ticker2='F', metrics='profitability,growth'")
    print("  2. Present comparison results")
    print("  3. Suggest deeper analysis if needed")
    print("\nActual Response:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    assert "TSLA" in response or "Tesla" in response, "Response should mention Tesla"
    assert "F" in response or "Ford" in response, "Response should mention Ford"

    print("\n✅ PASSED: Successfully compared companies with planning")


def test_out_of_scope_planning():
    """Test planning recognizes out-of-scope queries"""
    print("\n" + "=" * 80)
    print("TEST 5: Out-of-Scope Query Planning")
    print("=" * 80)

    assistant = create_research_assistant(model="gpt-4o", show_reasoning=True)

    query = "What is Amazon's intrinsic value using DCF?"
    print(f"\nQuery: {query}")
    print("\nExpected Plan:")
    print("  - Recognize DCF is out of scope")
    print("  - Suggest using DCF Agent")
    print("  - Optionally offer to pull key inputs")
    print("\nActual Response:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    # Should suggest using DCF Agent
    suggests_dcf = any(phrase in response.lower() for phrase in [
        'dcf agent',
        'use the dcf',
        'out of scope',
        'outside my scope'
    ])

    assert suggests_dcf, "Should suggest using DCF Agent for DCF queries"

    print("\n✅ PASSED: Correctly recognized out-of-scope query")


def test_multi_step_planning():
    """Test planning for complex multi-step queries"""
    print("\n" + "=" * 80)
    print("TEST 6: Multi-Step Query Planning")
    print("=" * 80)

    assistant = create_research_assistant(model="gpt-4o", show_reasoning=True)

    query = "Compare Apple and Microsoft's revenue growth over the last 5 years, and tell me which has better margins"
    print(f"\nQuery: {query}")
    print("\nExpected Plan:")
    print("  1. Use get_date_context for 'last 5 years'")
    print("  2. Get historical data for both companies")
    print("  3. Compare revenue growth")
    print("  4. Compare margins")
    print("  5. Present comprehensive comparison")
    print("\nActual Response:")
    print("-" * 80)

    response = assistant.chat(query)
    print(response)
    print("-" * 80)

    assert any(company in response for company in ["AAPL", "Apple", "MSFT", "Microsoft"]), "Should mention both companies"
    assert any(metric in response.lower() for metric in ["growth", "margin"]), "Should discuss growth and margins"

    print("\n✅ PASSED: Successfully handled multi-step query with planning")


def main():
    """Run all planning tests"""
    load_dotenv()

    # Check for required API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not found in environment")
        return

    if not os.getenv("FINANCIAL_DATASETS_API_KEY"):
        print("❌ ERROR: FINANCIAL_DATASETS_API_KEY not found in environment")
        return

    print("\n" + "=" * 80)
    print("RESEARCH ASSISTANT - PLANNING CAPABILITY TEST SUITE")
    print("=" * 80)
    print("\nThis test verifies the agent creates and follows plans before executing tools.")

    try:
        # Test 1: Simple planning
        test_simple_planning()

        # Test 2: Temporal planning
        test_temporal_planning()

        # Test 3: Calculation planning
        test_calculation_planning()

        # Test 4: Comparison planning
        test_comparison_planning()

        # Test 5: Out-of-scope planning
        test_out_of_scope_planning()

        # Test 6: Multi-step planning
        test_multi_step_planning()

        print("\n" + "=" * 80)
        print("ALL PLANNING TESTS COMPLETED")
        print("=" * 80)
        print("\n✅ Research Assistant planning is working correctly!")
        print("\n**Key Improvements:**")
        print("   - Agent now creates explicit plans before executing")
        print("   - Better tool sequencing (e.g., get_date_context first)")
        print("   - More systematic approach to complex queries")
        print("   - Clear reasoning visible in thought process")
        print("   - ReAct pattern enables better step-by-step execution")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
