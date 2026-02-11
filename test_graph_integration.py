"""
Test script for LangGraph equity analyst integration
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_graph_import():
    """Test that we can import the graph agent"""
    print("Testing LangGraph import...")
    try:
        from agents.equity_analyst_graph import create_equity_analyst_graph
        print("✓ Successfully imported create_equity_analyst_graph")
        return True
    except Exception as e:
        print(f"✗ Failed to import: {e}")
        return False

def test_graph_creation():
    """Test that we can create a graph agent"""
    print("\nTesting graph agent creation...")
    try:
        from agents.equity_analyst_graph import create_equity_analyst_graph
        agent = create_equity_analyst_graph(model="claude-haiku-4-5-20251001")  # Use cheaper model for testing
        print("✓ Successfully created graph agent")

        # Check that it has the required attributes
        if hasattr(agent, 'analyze'):
            print("✓ Agent has analyze() method")
        else:
            print("✗ Agent missing analyze() method")
            return False

        if hasattr(agent, 'agent_executor'):
            print("✓ Agent has agent_executor attribute (backend compatible)")
        else:
            print("✗ Agent missing agent_executor attribute")
            return False

        return True
    except Exception as e:
        print(f"✗ Failed to create agent: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_graph_adapter():
    """Test that the adapter works"""
    print("\nTesting adapter interface...")
    try:
        from agents.equity_analyst_graph import create_equity_analyst_graph
        agent = create_equity_analyst_graph(model="claude-haiku-4-5-20251001")

        # Test backend-style invocation
        result = agent.agent_executor.invoke(
            {"input": "Analyze AAPL"},
            config={}
        )

        if "output" in result:
            print("✓ Adapter invoke() returns correct format")
            print(f"  Output length: {len(result['output'])} characters")
            return True
        else:
            print("✗ Adapter invoke() missing 'output' key")
            return False

    except Exception as e:
        print(f"✗ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("=" * 80)
    print("LangGraph Integration Test Suite")
    print("=" * 80)

    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("✗ ANTHROPIC_API_KEY not set")
        print("Please set ANTHROPIC_API_KEY in .env file")
        sys.exit(1)

    print("✓ ANTHROPIC_API_KEY found\n")

    tests = [
        test_graph_import,
        test_graph_creation,
        test_graph_adapter,
    ]

    results = []
    for test in tests:
        results.append(test())
        print()

    print("=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"Test Results: {passed}/{total} passed")

    if passed == total:
        print("✓ All tests passed! LangGraph integration is working.")
        print("\nYou can now use:")
        print("  python main.py --mode graph --ticker AAPL")
        print("  python main.py --mode graph --interactive")
    else:
        print("✗ Some tests failed. Please check errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
