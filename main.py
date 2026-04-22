"""
Main entry point for Financial Analysis Agents
"""
import os
import sys
from dotenv import load_dotenv
from agents.finance_qa_agent import create_finance_qa_agent, interactive_session
from agents.market_agent import create_market_agent
from agents.portfolio_agent import create_portfolio_agent
from agents.earnings_agent import create_earnings_agent
from agents.dcf_agent import DCFAgent
import argparse


def main():
    """Main function to run the financial analysis agents"""

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="AI-powered Financial Analysis Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Equity Research (comprehensive analysis)
  python main.py --mode analyst --ticker AAPL
  python main.py --mode analyst --ticker GOOGL --model claude-haiku-4-5-20251001

  # Equity Research - LangGraph (structured workflow)
  python main.py --mode graph --ticker AAPL
  python main.py --mode graph --ticker MSFT --model claude-haiku-4-5-20251001

  # Market Analysis (market conditions, sentiment, regime)
  python main.py --mode market
  python main.py --mode market --interactive

  # Finance Q&A (conversational, interactive)
  python main.py --mode research

  # Earnings Analysis (fast earnings-focused research)
  python main.py --mode earnings --ticker NVDA
  python main.py --mode earnings --ticker AAPL --model claude-haiku-4-5-20251001

  # Interactive mode
  python main.py --mode analyst --interactive

Modes:
  analyst   - Comprehensive equity research report (industry, competitors, moat, valuation)
  graph     - Equity research using LangGraph (structured 10-step workflow)
  market    - Market analysis (indices, sectors, news, sentiment, regime classification)
  research  - Finance Q&A: quick data lookups, calculations, comparisons, and news (conversational)
  portfolio - Portfolio analysis (metrics, diversification, tax optimization)
  earnings  - Earnings-focused equity research with quarterly trends and estimates
  dcf       - DCF valuation with two-stage pipeline (data fetch → analysis)
        """
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["research", "market", "portfolio", "earnings", "arena", "dcf"],
        default="research",
        help="Agent mode (default: research)"
    )

    parser.add_argument(
        "--ticker",
        type=str,
        help="Stock ticker symbol to analyze"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-5-20250929",
        help="Anthropic model to use (default: claude-sonnet-4-5-20250929)"
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode"
    )

    parser.add_argument(
        "--query-mode",
        choices=["full_ic", "quick_screen", "risk_check", "macro_view", "valuation"],
        default="full_ic",
        dest="query_mode",
        help="Arena query mode — controls which agents activate (default: full_ic)"
    )

    args = parser.parse_args()

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Please create a .env file with your Anthropic API key.")
        print("See .env.example for reference.")
        sys.exit(1)

    # Research mode is always interactive and doesn't need ticker
    if args.mode == "research":
        print("Launching Finance Q&A...")
        try:
            interactive_session(model=args.model)
        except Exception as e:
            print(f"Error running Finance Q&A: {e}")
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

    # Create agent based on mode
    if args.mode == "earnings":
        print("Initializing Earnings Analyst Agent...")
        try:
            agent = create_earnings_agent(model=args.model)
            print(f"Earnings Agent initialized with model: {args.model}\n")
        except Exception as e:
            print(f"Error initializing earnings agent: {e}")
            sys.exit(1)
    elif args.mode == "dcf":
        # DCF mode - two-stage pipeline
        if not args.ticker:
            print("DCF mode requires --ticker")
            sys.exit(1)
        
        print(f"Initializing DCF Agent (two-stage pipeline)...")
        try:
            agent = DCFAgent(model=args.model)
            print(f"DCF Agent initialized with model: {args.model}\n")
            result = agent.analyze(args.ticker)
            print(agent.format_report(result))
        except Exception as e:
            print(f"Error running DCF agent: {e}")
            sys.exit(1)
        return

    elif args.mode == "arena":
        import re
        from arena.run import run_arena

        if args.ticker:
            ticker = args.ticker.upper()
            query = f"Should we open a position on {ticker} this quarter?"
        elif args.interactive:
            query = input("\nArena query: ").strip()
            match = re.search(r'\b([A-Z]{2,5})\b', query)
            ticker = match.group(1) if match else input("Ticker symbol: ").strip().upper()
        else:
            print("Arena mode requires --ticker or --interactive")
            sys.exit(1)

        query_mode = getattr(args, "query_mode", "full_ic")

        print(f"{'='*60}")
        print(f"  FINANCE AGENT ARENA")
        print(f"  Query:  {query}")
        print(f"  Ticker: {ticker}")
        print(f"  Mode:   {query_mode}")
        print(f"{'='*60}\n")

        result = run_arena(query=query, ticker=ticker, query_mode=query_mode)

        print(result["investment_memo"])

        print("\nDEBATE LOG:")
        for e in result["debate_log"]:
            print(f"  R{e['round']} | {e['agent']:15} | {e['action']:20} | {e['content'][:75]}")
        return
    else:
        print(f"Error: Unknown mode '{args.mode}'")
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

    result = agent.analyze(ticker)
    print(result)


def run_interactive_mode(agent, mode: str):
    """Run agent in interactive mode"""
    print("=" * 80)
    if mode == "earnings":
        print("Earnings Analyst Agent - Interactive Mode")
        print("=" * 80)
        print("\nAsk me to analyze earnings for any stock!")
        print("Examples:")
        print("  - 'Analyze NVDA's latest earnings'")
        print("  - 'What's Apple's earnings trend?'")
        print("  - 'Evaluate Microsoft's forward earnings outlook'")

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


_MARKET_SHORTCUT_QUERIES = {
    "overview": (
        "Provide a comprehensive market overview: major index performance, market breadth "
        "(advance/decline ratios, new highs/lows), VIX level and interpretation, and market "
        "regime classification (BULL/BEAR/NEUTRAL, RISK_ON/RISK_OFF). Highlight the key "
        "takeaways for portfolio positioning."
    ),
    "briefing": (
        "Provide a comprehensive daily market briefing. Call these tools in order: "
        "get_sentiment_score (lead with Fear & Greed score), get_market_overview (indices, VIX, regime), "
        "get_historical_context (52-week percentile for VIX and indices), get_sector_rotation (leaders/laggards), "
        "get_macro_context (yield curve, Fed rate, inflation), get_market_news (key catalysts). "
        "Structure output as: Sentiment → Market Overview → Historical Context → Sector Rotation → "
        "Macro Context → News & Catalysts → Investor Takeaways. Every number needs context."
    ),
    "sectors": (
        "Analyze current sector rotation over the past month: which sectors are leading and lagging, "
        "what the rotation signals about market positioning, whether money is flowing into cyclicals "
        "or defensives, and which sectors investors should focus on. Provide specific, actionable recommendations."
    ),
    "regime": (
        "Classify the current market regime with investment implications: BULL/BEAR/NEUTRAL, "
        "RISK_ON/RISK_OFF, supporting signals, confidence level, and specific portfolio actions "
        "investors should take based on this regime."
    ),
    "news": (
        "Analyze the most important market news today: major market-moving stories, how markets "
        "are reacting, what investors need to know, and any actionable portfolio implications."
    ),
}


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
            query = _MARKET_SHORTCUT_QUERIES.get(user_input.lower(), user_input)
            result = agent.analyze(query)

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
