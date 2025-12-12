"""
Test the stock screener functionality
"""
from agents.market_agent import create_market_agent

def test_screener():
    print("Initializing Market Agent...")
    agent = create_market_agent(show_reasoning=True)

    query = "find me some good companies with profit margin of 20% and a P/E under 15x"

    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"{'='*80}\n")

    result = agent.analyze(query)

    print("\n" + "="*80)
    print("RESULT:")
    print("="*80)
    print(result)

if __name__ == "__main__":
    test_screener()
