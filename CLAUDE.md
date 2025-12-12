# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI-powered financial analysis system with four specialized agents built using LangChain and LangGraph:

1. **DCF Agent** - Fast quantitative valuation using Discounted Cash Flow methodology
2. **Equity Analyst Agent** - Comprehensive equity research reports (industry, competitors, moat, valuation)
3. **Research Assistant Agent** - Interactive conversational research tool with context memory
4. **Market Agent** - Market conditions, sentiment, regime classification, and sector analysis

All agents use the ReAct pattern for autonomous decision-making and tool selection.

## Setup and Environment

### Install Dependencies

**Core Dependencies** (required for CLI agents):
```bash
pip install -r requirements.txt
```

**Backend Dependencies** (additional, required for web interface):
```bash
pip install -r backend/requirements.txt
```

**Frontend Dependencies** (required for web interface):
```bash
cd frontend
npm install
```

### Environment Configuration
Create `.env` file with:
```
OPENAI_API_KEY=your_openai_api_key_here
FINANCIAL_DATASETS_API_KEY=your_financial_datasets_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here
MASSIVE_API_KEY=your_massive_api_key_here  # Optional, for Market Agent
```

API Sources:
- **Financial Datasets AI** - Historical financial data ([financialdatasets.ai](https://financialdatasets.ai))
- **Perplexity Sonar API** - Web search for current market data ([perplexity.ai/settings/api](https://www.perplexity.ai/settings/api))
- **Massive.com** - Real-time market data (optional for Market Agent)

### Verify Setup
```bash
python test_setup.py
```

## Running the Application

### Web Interface (Recommended)

A modern web-based chat interface is available for all agents:

```bash
# Quick start (starts both backend and frontend)
./start_web.sh         # On macOS/Linux
start_web.bat          # On Windows

# Or manually:
# Terminal 1 - Backend
cd backend && python api_server.py

# Terminal 2 - Frontend
cd frontend && npm install && npm run dev
```

Then open `http://localhost:3000` in your browser.

See `WEB_SETUP.md` for detailed instructions.

### Command Line Interface

### DCF Analysis (Fast Quantitative Valuation)
```bash
# Single ticker DCF analysis
python main.py --mode dcf --ticker AAPL

# Interactive DCF mode
python main.py --mode dcf --interactive

# Custom model
python main.py --mode dcf --ticker GOOGL --model gpt-4o
```

### Equity Research Analysis (Comprehensive Report)
```bash
# Full equity research report
python main.py --mode analyst --ticker AAPL

# Interactive equity analyst mode
python main.py --mode analyst --interactive
```

### Research Assistant (Interactive Exploration)
```bash
# Conversational research mode (always interactive)
python main.py --mode research
```

### Market Analysis (Market Conditions & Sentiment)
```bash
# Market analysis mode
python main.py --mode market

# Market analysis with interactions
python main.py --mode market --interactive
```

### Default Mode
If `--mode` is not specified, defaults to `dcf`:
```bash
python main.py --ticker AAPL  # Same as --mode dcf --ticker AAPL
```

## Architecture

### Repository Structure

```
finance_dcf_agent/
├── backend/             # FastAPI web server
│   ├── api_server.py               # REST API + SSE streaming
│   └── requirements.txt            # Backend-specific dependencies
├── frontend/            # React web interface
│   ├── src/
│   │   ├── components/             # React components
│   │   ├── api.ts                  # API client
│   │   ├── types.ts                # TypeScript types
│   │   └── App.tsx                 # Main app
│   ├── package.json                # Frontend dependencies
│   └── vite.config.ts              # Vite configuration
├── agents/              # Agent implementations
│   ├── dcf_agent.py                    # DCF valuation agent (ReAct)
│   ├── equity_analyst_agent.py         # Comprehensive research agent (ReAct)
│   ├── equity_analyst_graph.py         # LangGraph implementation (not integrated)
│   ├── research_assistant_agent.py     # Interactive conversational agent
│   └── market_agent.py                 # Market analysis agent
├── tools/               # LangChain tool implementations
│   ├── dcf_tools.py                    # Stock info, financials, DCF, web search
│   ├── equity_analyst_tools.py         # Industry, competitor, moat analysis
│   ├── research_assistant_tools.py     # Calculations, comparisons, news
│   └── market_tools.py                 # Market data, indices, sectors, VIX
├── calculators/         # Core calculation engines
│   └── dcf_calculator.py               # DCF valuation engine with scenarios
├── data/                # Data layer
│   └── financial_data.py               # Financial data fetcher (Financial Datasets API)
├── main.py             # CLI entry point with argparse
├── example_usage.py    # Programmatic usage examples
├── test_setup.py       # Setup validation script
├── test_api.py         # API debugging script
├── start_web.sh        # Web interface startup script (macOS/Linux)
└── start_web.bat       # Web interface startup script (Windows)
```

### Multi-Agent Architecture

The system uses **specialized agents** that share common infrastructure but have different tool sets and prompts:

**DCF Agent** (`agents/dcf_agent.py`)
- Tools: `get_stock_info`, `get_financial_metrics`, `search_web`, `perform_dcf_analysis`
- Focus: Fast intrinsic value calculation with web-sourced parameters
- Pattern: ReAct agent with 10 max iterations

**Equity Analyst Agent** (`agents/equity_analyst_agent.py`)
- Tools: All DCF tools + `analyze_industry`, `analyze_competitors`, `analyze_moat`
- Focus: Comprehensive equity research like a professional analyst
- Pattern: ReAct agent with extended workflow (industry → competitors → moat → valuation)

**Research Assistant Agent** (`agents/research_assistant_agent.py`)
- Tools: Financial lookups, calculations, comparisons, news, deep-dive analysis triggers
- Focus: Interactive exploration with conversation memory
- Pattern: Conversational agent with context retention and proactive suggestions

**Market Agent** (`agents/market_agent.py`)
- Tools: `get_market_overview`, `analyze_sector`, `get_market_news`, `classify_market_regime`
- Focus: Macro market conditions, sentiment, and sector rotation
- Pattern: ReAct agent for market-level analysis

### Core Data Flow

All agents follow a similar pattern:

```
User Query → Agent (LLM) → Tool Selection → Tool Execution → Observation → Agent Reasoning → Response
```

**Key Components:**

1. **Agent Layer** (`agents/*.py`):
   - Creates LangChain ReAct agent with `create_react_agent()`
   - Defines systematic prompt templates with workflow instructions
   - Manages LLM (ChatOpenAI) and tool integration
   - Default model: `gpt-4-turbo-preview` (configurable via `--model`)

2. **Tools Layer** (`tools/*.py`):
   - All tools inherit from LangChain's `BaseTool`
   - Use Pydantic schemas for input validation
   - Implement `_run()` method for execution
   - Return formatted strings (not exceptions) for better LLM handling

3. **Data Layer** (`data/financial_data.py`, API calls in tools):
   - Financial Datasets AI API for historical financials
   - Perplexity Sonar API for web search
   - Massive.com API for real-time market data

4. **Calculation Layer** (`calculators/dcf_calculator.py`):
   - Pure DCF logic separated from agent/tool layers
   - Generates Bull/Base/Bear scenarios
   - Projects 5-year FCF with declining growth (0.95 decay)
   - Terminal value using perpetuity growth method

### Agent Workflow Deep Dive

**DCF Agent Systematic Approach** (encoded in `agents/dcf_agent.py:46-102`):
1. `get_stock_info` - Company context
2. `get_financial_metrics` - Historical financials
3. `search_web` - Current beta, analyst estimates, risk-free rate, industry trends
4. Analyze data to determine assumptions
5. `perform_dcf_analysis` - **Pass web-sourced parameters** (beta, growth rates, risk-free rate)
6. Present Bull/Base/Bear scenarios
7. Investment recommendation (Buy >20% upside, Hold 0-20%, Sell <0%)

**Equity Analyst Agent Workflow** (encoded in `agents/equity_analyst_agent.py:48-120`):
1. Company overview and business model (`get_stock_info` + `search_web`)
2. `analyze_industry` - Market size, Porter's 5 Forces, trends, benchmarks
3. `analyze_competitors` - Top competitors, market share, positioning
4. `analyze_moat` - Brand, network effects, switching costs, pricing power
5. Financial analysis (`get_financial_metrics` + `perform_dcf_analysis`)
6. Management quality assessment (`search_web`)
7. Bull/Bear case scenarios and investment recommendation

**Research Assistant Features**:
- Maintains conversation context across queries
- Proactively suggests next analyses
- Can trigger deep-dive agents (DCF, industry, etc.) on demand
- Interactive loop with `interactive_session()` function

### DCF Methodology Details

**Valuation Formula**:
```
Enterprise Value = PV(5-year FCF) + PV(Terminal Value)
Equity Value = Enterprise Value + Cash - Debt
Intrinsic Value per Share = Equity Value / Shares Outstanding
```

**Key Calculations** (`calculators/dcf_calculator.py`):
- Revenue growth declines geometrically each year: `growth_rate * (0.95 ** year)`
- WACC = Risk-free rate + Beta × Market risk premium (equity-only CAPM)
- Terminal value = FCF_final × (1 + terminal_growth) / (WACC - terminal_growth)
- NPV using discount factors: `1 / ((1 + WACC) ** year)`

**Scenario Generation** (`dcf_calculator.py:57-88`):
- **Bull**: 1.5× growth, 1.2× margins, 0.9× beta (lower risk)
- **Base**: Historical assumptions
- **Bear**: 0.5× growth, 0.8× margins, 1.1× beta (higher risk)

**Parameter Sources**:
- Beta: Web search → Financial Datasets → Default 1.0 (3-tier precedence)
- Growth rates: Analyst consensus (web) + historical CAGR
- FCF margin: Calculated as `latest_fcf / latest_revenue`
- Risk-free rate: Current 10-year Treasury yield (web search)
- Market risk premium: Typically 6-8%

### Web Interface Architecture

The web interface uses a modern client-server architecture:

**Backend (`backend/api_server.py`)**:
- FastAPI server exposing REST endpoints
- Server-Sent Events (SSE) for streaming agent responses
- Custom `StreamingCallbackHandler` to capture agent thinking process
- CORS enabled for React dev servers (localhost:3000, localhost:5173)
- Endpoints: `/analyze` (stream), `/quick-query` (non-stream)
- Auto-generated API docs at `/docs`

**Frontend (`frontend/`)**:
- React 18 + TypeScript + Vite for fast dev experience
- TailwindCSS for styling
- Axios for HTTP client with SSE support
- Real-time streaming of agent thoughts and final responses
- Agent selection UI (DCF, Analyst, Research, Market)
- Message history and markdown rendering

**Communication Flow**:
1. User sends query from React UI
2. Frontend calls `/analyze` endpoint with POST request
3. Backend creates agent and attaches streaming callback
4. Agent executes, emitting events (thinking, thought, content, error, done)
5. SSE streams events back to frontend in real-time
6. React UI updates as each event arrives

### LangGraph Implementation Note

There is a LangGraph implementation in `agents/equity_analyst_graph.py` but it's **not currently integrated** due to version conflicts (see `requirements.txt:10-12`). The active equity analyst uses standard LangChain ReAct pattern.

## Development Commands

### Backend Development
```bash
# Install backend dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Start backend API server (for web interface)
cd backend
python api_server.py
# Server runs on http://localhost:8000
# API docs available at http://localhost:8000/docs

# Test API connectivity and data sources
python test_api.py
```

### Frontend Development
```bash
# Install frontend dependencies
cd frontend
npm install

# Start development server
npm run dev
# Frontend runs on http://localhost:3000

# Build for production
npm run build

# Preview production build
npm run preview

# Run linter
npm run lint
```

### Running CLI Agents
```bash
# Quick DCF screening
python main.py --ticker AAPL

# Deep equity research
python main.py --mode analyst --ticker AAPL

# Interactive research
python main.py --mode research

# Market analysis
python main.py --mode market
```

### Testing and Validation
```bash
# Validate all dependencies and API access
python test_setup.py

# Test Financial Datasets API responses
python test_api.py
```

### Using Different Models
```bash
# gpt-4o (recommended for better tool usage)
python main.py --mode analyst --ticker AAPL --model gpt-4o

# gpt-4 (more expensive but reliable)
python main.py --mode dcf --ticker MSFT --model gpt-4
```

### Programmatic Usage
See `example_usage.py` for examples of:
- Direct API usage without agents
- Custom DCF scenarios
- Batch analysis across multiple tickers
- Sector-wide comparisons

## Working with the Codebase

### Adding New Tools

1. Create Pydantic input schema:
```python
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    param: float = Field(description="Parameter description")
```

2. Implement BaseTool subclass:
```python
from langchain.tools import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does and when to use it"
    args_schema = MyToolInput

    def _run(self, ticker: str, param: float) -> str:
        # Tool logic here
        return "Formatted result string"
```

3. Add to appropriate `get_*_tools()` function in `tools/*.py`

4. Agent will automatically discover and use new tools based on description

### Modifying Agent Behavior

Agent reasoning is controlled by prompt templates in `agents/*.py`:
- System role and guidelines
- Tool usage workflow instructions
- Output format specifications

To change agent behavior, edit the `template` string in `_create_agent()` method.

### Changing DCF Assumptions

Default assumptions in `calculators/dcf_calculator.py` (`DCFAssumptions` dataclass):
```python
@dataclass
class DCFAssumptions:
    revenue_growth_rate: float = 0.10      # 10% base growth
    fcf_margin: float = 0.15               # 15% FCF margin
    terminal_growth_rate: float = 0.025    # 2.5% perpetual growth
    risk_free_rate: float = 0.04           # 4% risk-free rate
    market_risk_premium: float = 0.08      # 8% equity risk premium
    beta: Optional[float] = None           # Stock beta (calculated if None)
    projection_years: int = 5              # 5-year projection
```

### Switching Data Sources

To use different financial data APIs:
1. Modify `FinancialDataFetcher` class methods in `data/financial_data.py`
2. Maintain same output dictionary structure expected by agents
3. Update API key configuration in `.env` file

### DCF Tool Parameters

The `perform_dcf_analysis` tool accepts (`tools/dcf_tools.py:28-64`):
- `ticker` (str): Stock ticker symbol
- `revenue_growth_rate` (float, default=0.10): Annual revenue growth rate
- `fcf_margin` (float, default=0.15): Free cash flow as % of revenue
- `terminal_growth_rate` (float, default=0.025): Perpetual growth rate
- `beta` (float, default=None): Stock beta coefficient (web-sourced)
- `risk_free_rate` (float, default=0.04): 10-year Treasury yield
- `market_risk_premium` (float, default=0.08): Equity risk premium
- `projection_years` (int, default=5): Cash flow projection period

Agents are instructed to pass web-researched values for beta, risk_free_rate, and revenue_growth_rate.

## Important Implementation Notes

### Data & APIs
- **Financial data API**: Uses `X-API-KEY` header for Financial Datasets AI authentication
- **Perplexity API**: Uses OpenAI SDK client with custom `base_url` for web search
- **Massive API**: Optional for Market Agent real-time data
- **Data caching**: FinancialDataFetcher has `self.cache` dict but not currently utilized
- **Current price calculation**: `market_cap / shares_outstanding` when not directly available

### DCF Calculations
- **WACC simplification**: Equity-only WACC via CAPM (no debt cost or tax shield)
- **Growth decay**: Revenue growth declines by 0.95 each year to model maturation
- **Beta precedence**: 1) Explicit parameter (web-sourced) → 2) Financial Datasets → 3) Default 1.0
- **Scenario sensitivity**: DCF highly sensitive to assumptions (especially terminal growth and WACC)

### Agent Behavior
- **Error handling**: Tools return error strings rather than raising exceptions
- **Async methods**: All tools implement `_arun()` but delegate to `_run()` (not truly async)
- **Max iterations**: ReAct agents limited to 10 iterations by default
- **Tool usage issues**: `gpt-4-turbo-preview` sometimes refuses to use tools; try `gpt-4o` or `gpt-4`
- **Reasoning callback**: `agents/reasoning_callback.py` provides friendly tool descriptions for CLI output
- **Streaming callback**: `backend/api_server.py` has `StreamingCallbackHandler` for web interface SSE

### LangGraph Status
- LangGraph implementation exists but has version conflicts with current langchain versions
- See `docs/LANGGRAPH_GUIDE.md` for details on the graph-based equity analyst
- Current production agents use standard LangChain ReAct pattern

## Troubleshooting

### "Could not fetch data for ticker"
- Verify ticker symbol is correct
- Check internet connection and API quotas
- Try different ticker to test if API is working

### Agent doesn't use tools / just responds without calling tools
- Try using `--model gpt-4o` instead of `gpt-4-turbo-preview`
- Check that OPENAI_API_KEY has sufficient credits
- Verify prompt includes tool descriptions and usage instructions

### "API key not found"
- Ensure `.env` file exists with all required keys
- Check you're in correct directory when running
- Verify no typos in environment variable names

### Analysis takes too long
- Equity Analyst is comprehensive and can take 2-5 minutes
- Use DCF Agent for faster results (~30-60 seconds)
- Check internet connection (agents make many API calls)

### Financial data incomplete
- Some companies (especially small/new ones) lack complete historical data
- Try larger, established companies first
- Check Financial Datasets AI API quota and access

## Dependencies

**Core packages** (`requirements.txt`):
- `langchain>=0.3.0` - Agent framework
- `langchain-openai>=0.3.0` - OpenAI LLM integration
- `langchain-community>=0.3.0` - Community tools
- `langchain-core>=0.3.0` - Core abstractions
- `openai>=1.7.1` - OpenAI API client
- `requests==2.31.0` - HTTP client for API calls
- `numpy==1.26.2` - Numerical operations
- `python-dotenv==1.0.0` - Environment variable management

**Backend packages** (`backend/requirements.txt`):
- `fastapi==0.104.1` - Web framework
- `uvicorn[standard]==0.24.0` - ASGI server
- `pydantic==2.5.0` - Data validation

**Frontend packages** (`frontend/package.json`):
- React 18 + TypeScript - UI framework
- Vite 5 - Build tool and dev server
- TailwindCSS 3 - Styling
- Axios - HTTP client with SSE support

**Note**: LangGraph has version conflicts with current LangChain versions (see `requirements.txt:10-12`)

## Known Limitations

### DCF Analysis
- Highly sensitive to assumptions (terminal growth, WACC, growth rates)
- Simplified WACC calculation (equity-only, no tax shield for debt)
- Historical growth may not reflect future performance
- No Monte Carlo simulation or probabilistic modeling
- No consideration of qualitative factors beyond moat analysis

### Data Quality
- Relies on publicly available financial data
- Data completeness varies by ticker and company size
- Current price calculated from market cap (not real-time quotes)
- Web search results depend on Perplexity API availability

### Agent Limitations
- LLM must correctly parse and pass parameters (relies on reasoning)
- Web search accuracy depends on source quality
- No consideration of macroeconomic scenarios in DCF
- ReAct agents can hit max iteration limits on complex queries
