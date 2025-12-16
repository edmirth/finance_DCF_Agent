"""Test to verify JSON formatting fix"""
from dotenv import load_dotenv
from agents.research_assistant_agent import create_research_assistant

load_dotenv()

print("Testing JSON formatting fix...")
print("=" * 80)

# Use gpt-4o since it works better with ReAct
assistant = create_research_assistant(model='gpt-4o', show_reasoning=False)

print("\n1. Testing comparison (the problematic case):")
print("Query: Compare Apple and Microsoft on profitability")
print("-" * 80)

try:
    response = assistant.chat('Compare Apple and Microsoft on profitability')
    print("\n✅ SUCCESS - No JSON parsing error!")
    print("\nResponse preview:")
    print(response[:300] + "..." if len(response) > 300 else response)
except Exception as e:
    print(f"\n❌ FAILED: {e}")

print("\n" + "=" * 80)
print("\n2. Testing quick data lookup:")
print("Query: What is Apple's revenue?")
print("-" * 80)

try:
    response = assistant.chat("What is Apple's revenue?")
    print("\n✅ SUCCESS!")
    print("\nResponse preview:")
    print(response[:200] + "..." if len(response) > 200 else response)
except Exception as e:
    print(f"\n❌ FAILED: {e}")
