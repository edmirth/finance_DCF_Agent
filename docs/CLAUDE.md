# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI-powered financial analysis system with two specialized agents:

1. **DCF Analysis Agent** - Quantitative valuation using Discounted Cash Flow methodology
2. **Equity Analyst Agent** - Comprehensive equity research reports (industry, competitors, moat, valuation)

Both agents use the ReAct pattern to autonomously gather data, perform analysis, and provide investment recommendations.

## Setup and Environment

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Environment Configuration
Create `.env` file with:
```
OPENAI_API_KEY=your_openai_api_key_here
FINANCIAL_DATASETS_API_KEY=your_financial_datasets_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here
```

The agent uses:
- **Financial Datasets AI** for historical financial data. Get a free API key at [financialdatasets.ai](https://financialdatasets.ai)
- **Perplexity Sonar API** for web search to find current market data (beta values, analyst estimates, etc.). Get your API key at [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api)

## Running the Application

### DCF Analysis (Quantitative Valuation)
```bash
# Single ticker DCF analysis
python main.py --mode dcf --ticker AAPL

# Interactive DCF mode
python main.py --mode dcf --interactive

# Custom model
python main.py --mode dcf --ticker GOOGL --model gpt-4
```

### Equity Research Analysis (Comprehensive Report)
```bash
# Full equity research report
python main.py --mode analyst --ticker AAPL

# Interactive equity analyst mode
python main.py --mode analyst --interactive

# Custom model
python main.py --mode analyst --ticker MSFT --model gpt-4
```

### Default Mode
If `--mode` is not specified, defaults to `dcf`:
```bash
python main.py --ticker AAPL  # Same as --mode dcf --ticker AAPL
```

## Architecture

### Core Components and Data Flow

The system follows a **LangChain ReAct Agent** pattern where the LLM autonomously decides which tools to use and in what order:

1. **agent.py**: DCFAnalysisAgent class
   - Creates LangChain ReAct agent with custom prompt template
   - Agent uses iterative Thought/Action/Observation loop
   - Default model: `gpt-4-turbo-preview`
   - Max iterations: 10
   - Tools are invoked dynamically based on agent reasoning

2. **tools.py**: LangChain Tool implementations
   - `GetStockInfoTool`: Fetches company information (name, sector, industry, market cap, price)
   - `GetFinancialMetricsTool`: Retrieves financial data (revenue, FCF, debt, cash, beta, historical growth rates)
   - `SearchWebTool`: Searches the web via Perplexity Sonar API for current market data (beta values, analyst estimates, risk-free rates, industry trends, company news)
   - `PerformDCFAnalysisTool`: Executes complete DCF valuation with scenarios
     - **Enhanced with web-sourced parameters**: Accepts beta, risk_free_rate, market_risk_premium, revenue_growth_rate, fcf_margin, terminal_growth_rate, and projection_years
     - **Parameter precedence for beta**: 1) Explicit parameter (web-sourced), 2) Financial data, 3) Default 1.0
   - All tools inherit from LangChain's `BaseTool` with Pydantic schemas

3. **financial_data.py**: FinancialDataFetcher class
   - Uses Financial Datasets AI API for data retrieval
   - Fetches company facts via `/company/facts` endpoint
   - Retrieves financial statements via `/financials` endpoint (income statements, balance sheets, cash flow statements)
   - Calculates historical CAGR from time series data
   - Key method: `get_key_metrics()` returns all DCF inputs
   - Requires `FINANCIAL_DATASETS_API_KEY` environment variable

4. **dcf_calculator.py**: DCFCalculator class
   - `DCFAssumptions` dataclass: revenue growth, FCF margin, terminal growth, WACC components
   - `DCFResult` dataclass: intrinsic value, upside potential, enterprise/equity value
   - `create_scenarios()`: Generates Bull (+50% growth, -10% risk), Base, Bear (-50% growth, +10% risk)
   - `project_free_cash_flows()`: Projects 5-year FCF with declining growth (0.95 decay factor)
   - `calculate_terminal_value()`: Perpetuity growth method
   - WACC calculation: Uses CAPM (risk-free rate + beta × market risk premium)

5. **main.py**: CLI interface
   - Argparse-based command line handling
   - Supports `--ticker`, `--model`, `--interactive` flags
   - Interactive mode runs agent in loop with user input

### Agent Workflow

The agent follows this systematic approach (encoded in the agent prompt in agent.py:46-102):

1. Gather company context via `get_stock_info`
2. Retrieve historical financials via `get_financial_metrics`
3. **Search the web** via `search_web` to find:
   - Current beta coefficient from financial websites
   - Analyst consensus on revenue/earnings growth
   - Current risk-free rate (10-year Treasury yield)
   - Industry-specific information and recent company guidance
4. Analyze both historical data AND current market information to determine assumptions
5. **Execute `perform_dcf_analysis` with web-sourced parameters**:
   - **beta**: Current beta from web search (e.g., 1.22)
   - **revenue_growth_rate**: Analyst consensus growth rate as decimal
   - **risk_free_rate**: Current 10-year Treasury yield
   - **fcf_margin**: Calculated from historical FCF/Revenue ratio
   - **terminal_growth_rate**: Typically 2.5% for mature companies
   - **market_risk_premium**: Typically 6-8%
6. Present results from all three scenarios (Bull, Base, Bear)
7. Provide investment recommendation (Buy >20% upside, Hold 0-20%, Sell <0%)

### DCF Methodology Details

**Valuation Formula**:
- Enterprise Value = PV(5-year FCF) + PV(Terminal Value)
- Equity Value = Enterprise Value + Cash - Debt
- Intrinsic Value per Share = Equity Value / Shares Outstanding

**Key Assumptions** (in dcf_calculator.py:13-26):
- Projection period: 5 years
- Revenue growth: Declines each year by factor of 0.95 (line 101)
- Terminal growth: 2.5% (base case)
- Risk-free rate: 4%
- Market risk premium: 8%
- WACC: Simplified equity-only CAPM model

**Scenario Generation** (in dcf_calculator.py:57-88):
- Bull: 1.5x growth, 1.2x margins, 0.9x beta
- Base: Historical assumptions
- Bear: 0.5x growth, 0.8x margins, 1.1x beta

## Working with the Codebase

### Modifying DCF Assumptions

Default assumptions are in `dcf_calculator.py` DCFAssumptions dataclass. To change defaults, edit:
- Line 16: `revenue_growth_rate`
- Line 17: `fcf_margin`
- Line 18: `terminal_growth_rate`
- Lines 21-23: WACC components

### Changing Data Sources

The application currently uses Financial Datasets AI. To use a different data source:
1. Modify `financial_data.py` FinancialDataFetcher class
2. Replace API calls in methods: `get_stock_info()`, `get_financial_statements()`, `get_key_metrics()`
3. Ensure output dictionaries maintain same key structure expected by tools.py
4. Update environment variable requirements in `.env.example`

### Modifying Agent Behavior

Agent reasoning is controlled by the prompt template in `agent.py:46-85`. Key sections:
- System role and guidelines (lines 46-69)
- ReAct format specification (lines 71-80)
- Tool usage workflow instructions

### Adding New Tools

1. Create Pydantic input schema (see `tools.py:16-65`)
2. Implement BaseTool subclass with `name`, `description`, `args_schema`, `_run()` method
3. Add to `get_dcf_tools()` list (line 327)
4. Agent will automatically discover and use new tools

### DCF Analysis Tool Parameters

The `PerformDCFAnalysisTool` accepts the following parameters (tools.py:28-64):

**Growth & Margin Assumptions**:
- `revenue_growth_rate` (float, default=0.10): Annual revenue growth rate
- `fcf_margin` (float, default=0.15): Free cash flow as % of revenue
- `terminal_growth_rate` (float, default=0.025): Perpetual growth rate

**WACC Components** (sourced from web search):
- `beta` (float, default=None): Stock beta coefficient. If None, uses financial data or 1.0
- `risk_free_rate` (float, default=0.04): Risk-free rate (10-year Treasury)
- `market_risk_premium` (float, default=0.08): Equity risk premium

**Projection Settings**:
- `projection_years` (int, default=5): Cash flow projection period

The agent is instructed to pass web-researched values for these parameters to improve valuation accuracy.

## Important Implementation Notes

- **Financial data caching**: FinancialDataFetcher has `self.cache` dict but it's not currently utilized
- **API authentication**: Uses `X-API-KEY` header for Financial Datasets AI authentication; Perplexity uses OpenAI SDK client with custom base_url
- **WACC simplification**: Current implementation uses equity-only WACC via CAPM. Does not account for debt cost or capital structure
- **Growth decay**: Revenue growth declines geometrically (0.95^year factor) to model maturation
- **Error handling**: Tools return error strings rather than raising exceptions for better LLM handling
- **Async methods**: All tools implement `_arun()` but just delegate to `_run()` (not truly async)
- **JSON data extraction**: Financial statements are returned as JSON arrays from the API
- **Beta enhancement**: Beta uses 3-tier precedence: 1) Explicit parameter from agent (web-sourced), 2) Financial Datasets AI value, 3) Default 1.0. Agent is instructed to always pass web-sourced beta values.
- **Current price calculation**: Calculated as market_cap / shares_outstanding when not directly available
- **Web search integration**: Perplexity Sonar API uses `sonar-pro` model for real-time web searches with cited sources

## Dependencies

Key packages (from requirements.txt):
- `langchain==0.1.0` - Agent framework
- `langchain-openai==0.0.2` - OpenAI LLM integration
- `requests==2.31.0` - HTTP client for API calls
- `numpy==1.26.2` - Numerical operations
- `python-dotenv==1.0.0` - Environment variable management

## Limitations to Be Aware Of

- DCF calculations are highly sensitive to assumptions (especially terminal growth and WACC)
- **Beta**: Now enhanced with web search capability. Agent automatically searches for and uses current beta values from financial websites, significantly improving WACC accuracy.
- **Risk-free rate**: Can be customized via web search for current Treasury yields, but defaults to 4%
- Current stock price is calculated from market cap / shares, not real-time quotes
- Data quality varies by ticker and can be incomplete for small/new companies
- No consideration of qualitative factors, management quality, or competitive moats
- Simplified WACC calculation (equity-only, no tax shield for debt)
- Historical growth may not reflect future performance
- No Monte Carlo simulation or probabilistic modeling
- Web search results depend on Perplexity API availability and accuracy of sources
- Agent must correctly parse and pass web-sourced parameters to DCF tool (relies on LLM reasoning)
