#!/usr/bin/env python3
"""
Full end-to-end test of EarningsAgent with EarningsCallInsightsTool
Tests the complete analysis for AAPL, TSLA, and NVDA
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from agents.earnings_agent import EarningsAgent

print("=" * 80)
print("Full Earnings Agent Analysis Test")
print("=" * 80)

test_tickers = ["AAPL", "TSLA", "NVDA"]

for ticker in test_tickers:
    print(f"\n{'='*80}")
    print(f"Testing: {ticker}")
    print(f"{'='*80}")

    try:
        agent = EarningsAgent()
        print(f"Analyzing {ticker} (this may take 30-60 seconds)...")

        # Run full analysis
        result = agent.analyze(ticker=ticker, quarters_back=8)

        # Validate result
        if result and len(result) > 2000:
            print(f"✓ Analysis completed successfully")
            print(f"✓ Report length: {len(result)} chars")

            # Check for key sections
            has_call_insights = "Earnings Call Analysis" in result or "MANAGEMENT COMMENTARY" in result.upper()
            has_guidance = "guidance" in result.lower() or "outlook" in result.lower()
            has_financial = "revenue" in result.lower() and "eps" in result.lower()

            print(f"✓ Contains call insights: {has_call_insights}")
            print(f"✓ Contains guidance: {has_guidance}")
            print(f"✓ Contains financials: {has_financial}")

            # Show snippet
            print(f"\nFirst 500 chars of report:")
            print("-" * 80)
            print(result[:500])
            print("...")

        else:
            print(f"✗ Analysis failed or returned insufficient data")
            print(f"Result: {str(result)[:500]}")

    except Exception as e:
        print(f"✗ Error analyzing {ticker}: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}")
print("Full Analysis Testing Complete")
print(f"{'='*80}")
