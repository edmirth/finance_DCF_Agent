"""
Visualize the LangGraph workflow
"""
from equity_analyst_graph import create_equity_analyst_graph
import os


def visualize_workflow():
    """Print the workflow structure"""

    print("=" * 80)
    print("EQUITY ANALYST LANGGRAPH WORKFLOW")
    print("=" * 80)
    print()

    workflow = """
    ┌─────────────────┐
    │   START         │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 1. Get Company  │  ← get_stock_info tool
    │    Info         │    (company name, sector, industry, price)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 2. Get Financial│  ← get_financial_metrics tool
    │    Metrics      │    (revenue, FCF, growth rates, debt)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 3. Analyze      │  ← analyze_industry tool
    │    Industry     │    (market size, Porter's 5 Forces, trends)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 4. Analyze      │  ← analyze_competitors tool
    │    Competitors  │    (market share, positioning, peer comparison)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 5. Analyze Moat │  ← analyze_moat tool
    │                 │    (brand, network effects, switching costs)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 6. Analyze      │  ← analyze_management tool
    │    Management   │    (CEO quality, capital allocation, ownership)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 7. Perform DCF  │  ← perform_dcf_analysis + search_web tools
    │    Valuation    │    (intrinsic value, upside potential)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 8. Develop      │  ← LLM synthesis
    │    Thesis       │    (bull case, bear case, base case)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 9. Make         │  ← Logic-based
    │    Recommendation│   (BUY/HOLD/SELL, price target, conviction)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │10. Format Report│  ← Template-based
    │                 │    (professional equity research report)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │      END        │
    └─────────────────┘
    """

    print(workflow)
    print()
    print("=" * 80)
    print("STATE TRACKING")
    print("=" * 80)
    print()

    state_info = """
The LangGraph maintains state across all steps:

COMPANY DATA:
  • ticker, company_name, sector, industry, current_price

ANALYSIS RESULTS:
  • company_info: Basic company information
  • financial_metrics: Historical financials
  • historical_growth: Revenue/FCF growth rates
  • industry_analysis: Market size, trends, structure
  • competitive_position: vs peers analysis
  • moat_strength: WIDE/NARROW/NONE
  • moat_sources: List of competitive advantages
  • management_quality: EXCELLENT/GOOD/FAIR/POOR
  • capital_allocation: M&A, buybacks, dividends assessment

VALUATION:
  • dcf_results: Full DCF output
  • intrinsic_value: Fair value per share
  • upside_potential: % upside/downside

INVESTMENT THESIS:
  • bull_case: List of 3+ bullish points
  • bear_case: List of 3+ bearish points
  • base_case: Most likely scenario

RECOMMENDATION:
  • rating: BUY/HOLD/SELL
  • price_target: 12-month target price
  • conviction: HIGH/MEDIUM/LOW

METADATA:
  • analysis_steps: List of completed steps
  • errors: Any errors encountered
  • current_step: Current workflow position
  • final_report: Formatted output
    """

    print(state_info)
    print()
    print("=" * 80)
    print("BENEFITS OF LANGGRAPH")
    print("=" * 80)
    print()

    benefits = """
1. STRUCTURED WORKFLOW
   ✓ Clear 10-step process (vs unstructured ReAct)
   ✓ Guaranteed execution order
   ✓ No missed steps

2. STATE MANAGEMENT
   ✓ Centralized state object tracks all data
   ✓ Easy to debug (inspect state at any step)
   ✓ Can save/resume analysis sessions

3. ERROR HANDLING
   ✓ Errors logged to state.errors[]
   ✓ Analysis continues even if one step fails
   ✓ Graceful degradation

4. OBSERVABILITY
   ✓ See exactly which step is running
   ✓ Track progress via state.analysis_steps[]
   ✓ View state.current_step in real-time

5. EXTENSIBILITY
   ✓ Easy to add new steps to workflow
   ✓ Can add conditional branching
   ✓ Can parallelize independent steps

6. REPRODUCIBILITY
   ✓ Deterministic workflow execution
   ✓ Same inputs → same state transitions
   ✓ Easy to unit test each step
    """

    print(benefits)
    print()
    print("=" * 80)
    print("USAGE")
    print("=" * 80)
    print()

    usage = """
# Use the LangGraph-based agent
python3 main.py --mode graph --ticker AAPL

# The agent will:
1. Execute each step sequentially
2. Print progress: [Step X/10] Description
3. Accumulate all analysis in state
4. Generate comprehensive report at the end

# You can inspect the state object to see:
- What data each tool returned
- Which steps completed successfully
- Any errors that occurred
- The full decision-making trail
    """

    print(usage)
    print()


if __name__ == "__main__":
    visualize_workflow()
