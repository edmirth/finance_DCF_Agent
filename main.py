"""
Main entry point for DCF Analysis Agent, Equity Analyst Agent, and Financial Research Assistant
"""
import os
import sys
from dotenv import load_dotenv
from agents.dcf_agent import create_dcf_agent
from agents.equity_analyst_agent import create_equity_analyst_agent
from agents.research_assistant_agent import create_research_assistant, interactive_session
from agents.market_agent import create_market_agent
from agents.portfolio_agent import create_portfolio_agent
import argparse


def main():
    """Main function to run the DCF analysis agent"""

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="AI-powered Financial Analysis Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # DCF Analysis (quantitative valuation)
  python main.py --mode dcf --ticker AAPL
  python main.py --mode dcf --ticker MSFT --model gpt-4

  # Equity Research (comprehensive analysis)
  python main.py --mode analyst --ticker AAPL
  python main.py --mode analyst --ticker GOOGL --model gpt-4

  # Market Analysis (market conditions, sentiment, regime)
  python main.py --mode market
  python main.py --mode market --interactive

  # Financial Research Assistant (conversational, interactive)
  python main.py --mode research

  # Interactive mode (DCF and Analyst)
  python main.py --mode dcf --interactive
  python main.py --mode analyst --interactive

Modes:
  dcf       - DCF valuation analysis (intrinsic value calculation)
  analyst   - Comprehensive equity research report (industry, competitors, moat, valuation)
  market    - Market analysis (indices, sectors, news, sentiment, regime classification)
  research  - Conversational research assistant (ask questions, get suggestions, deep-dive)
  portfolio - Portfolio analysis (metrics, diversification, tax optimization)
        """
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["dcf", "analyst", "research", "market", "portfolio"],
        default="dcf",
        help="Agent mode: 'dcf', 'analyst', 'research', 'market', or 'portfolio' (default: dcf)"
    )

    parser.add_argument(
        "--ticker",
        type=str,
        help="Stock ticker symbol to analyze"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.2",
        help="OpenAI model to use (default: gpt-5.2)"
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode"
    )

    args = parser.parse_args()

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please create a .env file with your OpenAI API key.")
        print("See .env.example for reference.")
        sys.exit(1)

    # Research mode is always interactive and doesn't need ticker
    if args.mode == "research":
        print("Launching Financial Research Assistant...")
        try:
            interactive_session(model=args.model)
        except Exception as e:
            print(f"Error running research assistant: {e}")
            sys.exit(1)
        return

    # Market mode is always interactive and doesn't need ticker
    if args.mode == "market":
        print("Launching Market Analysis Agent...")
        try:
            agent = create_market_agent(model=args.model)
            print(f"Market Agent initialized with model: {args.model}\n")
            run_market_mode(agent)
        except Exception as e:
            print(f"Error running market agent: {e}")
            sys.exit(1)
        return

    # Portfolio mode is always interactive
    if args.mode == "portfolio":
        print("Launching Portfolio Analyzer Agent...")
        try:
            from agents.portfolio_agent import interactive_session as portfolio_session
            portfolio_session(model=args.model)
        except Exception as e:
            print(f"Error running portfolio agent: {e}")
            sys.exit(1)
        return

    # Create agent based on mode (dcf or analyst)
    if args.mode == "dcf":
        print("Initializing DCF Analysis Agent...")
        try:
            agent = create_dcf_agent(model=args.model)
            print(f"DCF Agent initialized with model: {args.model}\n")
        except Exception as e:
            print(f"Error initializing DCF agent: {e}")
            sys.exit(1)
    else:  # analyst mode
        print("Initializing Equity Analyst Agent...")
        try:
            agent = create_equity_analyst_agent(model=args.model)
            print(f"Equity Analyst Agent initialized with model: {args.model}\n")
        except Exception as e:
            print(f"Error initializing equity analyst agent: {e}")
            sys.exit(1)

    # Run based on mode
    if args.interactive:
        run_interactive_mode(agent, args.mode)
    elif args.ticker:
        run_ticker_analysis(agent, args.ticker, args.mode)
    else:
        parser.print_help()
        print("\nError: Please specify either --ticker or --interactive")
        sys.exit(1)


def run_ticker_analysis(agent, ticker: str, mode: str):
    """Run analysis on a specific ticker"""
    print(f"Analyzing {ticker.upper()}...")
    print("=" * 80)
    print()

    if mode == "dcf":
        result = agent.quick_dcf(ticker)
    else:  # analyst mode
        result = agent.research_report(ticker)

    print(result)


def run_interactive_mode(agent, mode: str):
    """Run agent in interactive mode"""
    print("=" * 80)
    if mode == "dcf":
        print("DCF Analysis Agent - Interactive Mode")
        print("=" * 80)
        print("\nAsk me to perform DCF analysis on any stock!")
        print("Examples:")
        print("  - 'Perform DCF analysis on AAPL'")
        print("  - 'What is the intrinsic value of TSLA?'")
        print("  - 'Analyze Microsoft using conservative assumptions'")
    else:  # analyst mode
        print("Equity Analyst Agent - Interactive Mode")
        print("=" * 80)
        print("\nAsk me to produce equity research reports!")
        print("Examples:")
        print("  - 'Produce an equity research report on AAPL'")
        print("  - 'Analyze Tesla's competitive position'")
        print("  - 'What is Microsoft's competitive moat?'")

    print("\nType 'exit' or 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break

            if not user_input:
                continue

            print("\nAgent: ")
            result = agent.analyze(user_input)
            print(result)
            print("\n" + "=" * 80 + "\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
            continue


def run_market_mode(agent):
    """Run market agent in interactive mode"""
    print("=" * 80)
    print("Market Analysis Agent - Interactive Mode")
    print("=" * 80)
    print("\nAsk me about market conditions, sentiment, sectors, and news!")
    print("\nQuick Commands:")
    print("  - 'overview'     - Get comprehensive market overview")
    print("  - 'briefing'     - Get daily market briefing")
    print("  - 'sectors'      - Analyze sector rotation")
    print("  - 'regime'       - Classify market regime")
    print("  - 'news'         - Get latest market news")
    print("\nCustom Questions:")
    print("  - 'What's the market sentiment today?'")
    print("  - 'Should I be risk-on or risk-off?'")
    print("  - 'Which sectors are hot right now?'")
    print("  - 'Is this a good time to buy stocks?'")
    print("\nType 'exit' or 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break

            if not user_input:
                continue

            # Handle quick commands
            print("\nAgent: ")
            if user_input.lower() == 'overview':
                result = agent.market_overview()
            elif user_input.lower() == 'briefing':
                result = agent.daily_briefing()
            elif user_input.lower() == 'sectors':
                result = agent.sector_analysis()
            elif user_input.lower() == 'regime':
                result = agent.market_regime_analysis()
            elif user_input.lower() == 'news':
                result = agent.news_analysis()
            else:
                result = agent.analyze(user_input)

            print(result)
            print("\n" + "=" * 80 + "\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
            continue


if __name__ == "__main__":
    main()
