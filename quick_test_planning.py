"""Quick test to verify planning works"""
from dotenv import load_dotenv
from agents.research_assistant_agent import create_research_assistant

load_dotenv()

print("Creating assistant with gpt-4o...")
assistant = create_research_assistant(model='gpt-4o', show_reasoning=False)

print("\nAsking: What is Apple's revenue?")
response = assistant.chat('What is Apple revenue?')

print("\nResponse:")
print(response)

if 'revenue' in response.lower():
    print("\n✅ SUCCESS - Planning works!")
else:
    print("\n❌ FAILED")
