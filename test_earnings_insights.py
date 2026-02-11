#!/usr/bin/env python3
"""
Test script for EarningsCallInsightsTool integration with EarningsAgent
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 80)
print("Testing EarningsCallInsightsTool Integration")
print("=" * 80)

# Test 1: Tool availability
print("\n1. Testing tool availability...")
from tools.earnings_tools import get_earnings_tools

tools = get_earnings_tools()
print(f"   Total tools: {len(tools)}")

tool_names = [tool.name for tool in tools]
if 'get_earnings_call_insights' in tool_names:
    print("   ✓ EarningsCallInsightsTool found in registry")
else:
    print("   ✗ EarningsCallInsightsTool NOT in registry")
    exit(1)

# Test 2: Tool instantiation
print("\n2. Testing tool instantiation...")
from tools.earnings_tools import EarningsCallInsightsTool

tool = EarningsCallInsightsTool()
print(f"   ✓ Tool name: {tool.name}")
print(f"   ✓ Description length: {len(tool.description)} chars")

# Test 3: Direct tool execution
print("\n3. Testing direct tool execution (AAPL)...")
result = tool._run(ticker="AAPL", quarters=1)

if "Error:" not in result and len(result) > 500:
    print(f"   ✓ Tool executed successfully")
    print(f"   ✓ Result length: {len(result)} chars")
    print(f"   ✓ Contains analysis: {'Earnings Call Analysis' in result}")
else:
    print(f"   ✗ Tool execution failed or returned error")
    print(f"   Result: {result[:200]}")

# Test 4: EarningsAgent integration
print("\n4. Testing EarningsAgent integration...")
try:
    from agents.earnings_agent import EarningsAgent

    agent = EarningsAgent()
    print(f"   ✓ EarningsAgent initialized")
    print(f"   ✓ Agent has {len(agent.tools)} tools")

    # Check our tool is available
    agent_tool_names = [t.name for t in agent.tools]
    if 'get_earnings_call_insights' in agent_tool_names:
        print(f"   ✓ EarningsCallInsightsTool available to agent")
    else:
        print(f"   ✗ EarningsCallInsightsTool NOT available to agent")
        print(f"   Available tools: {agent_tool_names}")

except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 5: Node 4 execution test
print("\n5. Testing Node 4 (fetch_guidance_and_news) modification...")
try:
    from agents.earnings_agent import EarningsAgent

    agent = EarningsAgent()

    # Create a minimal state
    state = {
        "ticker": "AAPL",
        "quarters_back": 8,
        "errors": []
    }

    # Test Node 4 execution
    result_state = agent.fetch_guidance_and_news(state)

    if "earnings_guidance" in result_state and len(str(result_state["earnings_guidance"])) > 500:
        print(f"   ✓ Node 4 executed successfully")
        print(f"   ✓ Guidance data length: {len(str(result_state['earnings_guidance']))} chars")
        print(f"   ✓ Contains insights: {'Earnings Call Analysis' in str(result_state['earnings_guidance'])}")
    else:
        print(f"   ✗ Node 4 failed or returned insufficient data")
        print(f"   Guidance: {str(result_state.get('earnings_guidance', 'MISSING'))[:200]}")

except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("Integration Testing Complete")
print("=" * 80)
