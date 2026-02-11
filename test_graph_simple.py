"""
Simple test for LangGraph equity analyst integration (no API calls)
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def test_integration():
    """Test that integration is complete"""
    print("=" * 80)
    print("LangGraph Integration - Simple Test")
    print("=" * 80)

    # Test 1: Import
    print("\n1. Testing import...")
    try:
        from agents.equity_analyst_graph import create_equity_analyst_graph
        print("   ✓ Import successful")
    except Exception as e:
        print(f"   ✗ Import failed: {e}")
        return False

    # Test 2: Agent creation
    print("\n2. Testing agent creation...")
    try:
        agent = create_equity_analyst_graph(model="claude-haiku-4-5-20251001")
        print("   ✓ Agent created")
    except Exception as e:
        print(f"   ✗ Creation failed: {e}")
        return False

    # Test 3: Check attributes
    print("\n3. Testing attributes...")
    has_analyze = hasattr(agent, 'analyze')
    has_executor = hasattr(agent, 'agent_executor')

    if has_analyze and has_executor:
        print("   ✓ Agent has analyze() method")
        print("   ✓ Agent has agent_executor (backend compatible)")
    else:
        if not has_analyze:
            print("   ✗ Missing analyze() method")
        if not has_executor:
            print("   ✗ Missing agent_executor")
        return False

    # Test 4: Check executor interface
    print("\n4. Testing executor interface...")
    try:
        if hasattr(agent.agent_executor, 'invoke'):
            print("   ✓ Executor has invoke() method")
        else:
            print("   ✗ Executor missing invoke() method")
            return False
    except Exception as e:
        print(f"   ✗ Executor check failed: {e}")
        return False

    print("\n" + "=" * 80)
    print("✓ All structure tests passed!")
    print("\nIntegration is complete. You can now use:")
    print("  CLI:     python main.py --mode graph --ticker AAPL")
    print("  CLI:     python main.py --mode graph --interactive")
    print("  Backend: Start web server and select 'graph' agent")
    print("=" * 80)

    return True

if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Warning: ANTHROPIC_API_KEY not set")
        print("Set it in .env to run actual analysis\n")

    success = test_integration()
    sys.exit(0 if success else 1)
