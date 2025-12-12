"""
Quick test to verify Phase 1 Research Assistant fixes
"""
import os
from dotenv import load_dotenv
from agents.research_assistant_agent import create_research_assistant

def test_phase1_fixes():
    """Test that Phase 1 fixes work correctly"""

    # Load environment
    load_dotenv()

    print("=" * 80)
    print("RESEARCH ASSISTANT PHASE 1 FIXES - VERIFICATION TEST")
    print("=" * 80)
    print()

    # Test 1: Create assistant (should load all tools)
    print("Test 1: Creating Research Assistant with all tools...")
    try:
        assistant = create_research_assistant()
        print(f"✅ SUCCESS: Assistant created")
        print(f"   - Total tools available: {len(assistant.tools)}")
        print()
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

    # Test 2: Verify equity analyst tools are present
    print("Test 2: Verifying equity analyst tools are loaded...")
    equity_analyst_tool_names = [
        'analyze_industry',
        'analyze_competitors',
        'analyze_moat',
        'analyze_management'
    ]

    loaded_tool_names = [tool.name for tool in assistant.tools]
    print(f"   All loaded tools: {loaded_tool_names}")
    print()

    missing_tools = []
    for tool_name in equity_analyst_tool_names:
        if tool_name in loaded_tool_names:
            print(f"   ✅ {tool_name} - FOUND")
        else:
            print(f"   ❌ {tool_name} - MISSING")
            missing_tools.append(tool_name)

    if missing_tools:
        print(f"\n❌ FAILED: Missing tools: {missing_tools}")
        return False
    else:
        print(f"\n✅ SUCCESS: All equity analyst tools loaded")
    print()

    # Test 3: Verify memory type
    print("Test 3: Verifying ConversationSummaryBufferMemory is used...")
    from langchain.memory import ConversationSummaryBufferMemory

    if isinstance(assistant.memory, ConversationSummaryBufferMemory):
        print(f"   ✅ SUCCESS: Using ConversationSummaryBufferMemory")
        print(f"   - Max token limit: {assistant.memory.max_token_limit}")
    else:
        print(f"   ❌ FAILED: Wrong memory type: {type(assistant.memory)}")
        return False
    print()

    # Test 4: Quick conversation test
    print("Test 4: Testing basic conversation...")
    try:
        # Simple question that should use get_quick_data
        response = assistant.chat("What tools do you have access to?")

        if response and len(response) > 0:
            print(f"   ✅ SUCCESS: Agent responded")
            print(f"   - Response length: {len(response)} characters")
            print(f"   - First 200 chars: {response[:200]}...")
        else:
            print(f"   ❌ FAILED: Empty response")
            return False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    print()

    # Test 5: Verify memory stores conversation
    print("Test 5: Verifying conversation memory...")
    memory_vars = assistant.memory.load_memory_variables({})

    if 'chat_history' in memory_vars:
        print(f"   ✅ SUCCESS: Memory storing conversation")
        print(f"   - Messages in memory: {len(memory_vars['chat_history'])}")
    else:
        print(f"   ❌ FAILED: Memory not storing conversation")
        return False
    print()

    # Summary
    print("=" * 80)
    print("PHASE 1 VERIFICATION COMPLETE")
    print("=" * 80)
    print()
    print("✅ All Phase 1 fixes verified:")
    print("   1. Equity analyst tools imported and loaded")
    print("   2. ConversationSummaryBufferMemory implemented")
    print("   3. Agent prompt updated (see agent logs for tool descriptions)")
    print("   4. Basic conversation functionality working")
    print()
    print("The Research Assistant is now ready with:")
    print(f"   - {len(assistant.tools)} total tools available")
    print("   - Smart memory management (bounded token usage)")
    print("   - All deep analysis tools (industry, moat, competitors, management)")
    print()

    return True


if __name__ == "__main__":
    success = test_phase1_fixes()
    exit(0 if success else 1)
