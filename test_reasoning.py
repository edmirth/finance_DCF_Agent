"""
Test script for Research Assistant reasoning improvements
"""
import os
from dotenv import load_dotenv
from agents.research_assistant_agent import create_research_assistant

# Load environment variables
load_dotenv()

def test_reasoning():
    """Test reasoning improvements with a sample query"""

    print("=" * 80)
    print("TESTING RESEARCH ASSISTANT REASONING IMPROVEMENTS")
    print("=" * 80)
    print("\nTest Query: What's Apple's revenue growth over the last 3 years?")
    print("\nExpected:")
    print("  1. Should show PLAN with 3-4 numbered steps")
    print("  2. Should show REFLECTION after each tool call")
    print("  3. Should provide structured final answer")
    print("\n" + "=" * 80 + "\n")

    # Create research assistant with reasoning enabled
    assistant = create_research_assistant(model="gpt-5.2", show_reasoning=True)

    # Test query
    query = "What's Apple's revenue growth over the last 3 years?"

    # Run the query
    response = assistant.chat(query)

    print("\n" + "=" * 80)
    print("FINAL RESPONSE:")
    print("=" * 80)
    print(response)
    print("\n" + "=" * 80)

    return response

if __name__ == "__main__":
    test_reasoning()
