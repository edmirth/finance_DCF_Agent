# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI-powered financial analysis system with two subsystems:

**Single-stock agents** (LangChain/LangGraph, CLI + web interface):
1. **DCF Agent** - Fast quantitative valuation using Discounted Cash Flow methodology
2. **LangGraph Equity Analyst** - Structured 10-step equity research workflow using LangGraph
3. **Research Assistant Agent** - Interactive conversational research tool with context memory
4. **Market Agent** - Market conditions, sentiment, regime classification, and sector analysis
5. **Portfolio Agent** - Portfolio analysis with performance metrics, diversification, and tax optimization
6. **Earnings Agent** - Comprehensive earnings analysis with quarterly trends, analyst estimates, surprises, and management commentary from earnings calls

**Finance Agent Arena** (`arena/`) — Multi-agent debate system:
- Five specialist agents (fundamental, risk, quant, macro, sentiment) debate investment theses
- PM node orchestrates debate rounds, computes consensus, and synthesises final investment memo
- Sequential LangGraph graph ensures each agent sees prior agents' full findings before reasoning
- Uses Anthropic SDK directly (not LangChain) with `claude-haiku-4-5-20251001` for all agent LLM calls

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
ANTHROPIC_API_KEY=your_anthropic_api_key_here
FINANCIAL_DATASETS_API_KEY=your_financial_datasets_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here
MASSIVE_API_KEY=your_massive_api_key_here  # Optional, for Market Agent
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here  # Optional, free tier (25 req/day) for earnings transcripts
```

API Sources:
- **Financial Datasets AI** - Historical financial data ([financialdatasets.ai](https://financialdatasets.ai))
- **Perplexity Sonar API** - Web search for current market data ([perplexity.ai/settings/api](https://www.perplexity.ai/settings/api))
- **Massive.com** - Real-time market data (optional for Market Agent)
- **Alpha Vantage** - Free earnings call transcripts and earnings history ([alphavantage.co](https://www.alphavantage.co/support/#api-key)) — 25 req/day free tier

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
python main.py --mode dcf --ticker GOOGL --model claude-haiku-4-5-20251001
```

### Equity Research Analysis (Comprehensive Report)
```bash
# Full equity research report (LangGraph 10-step workflow)
# --mode analyst and --mode graph are equivalent aliases
python main.py --mode graph --ticker AAPL
python main.py --mode analyst --ticker AAPL  # same as graph

# Interactive mode
python main.py --mode graph --interactive
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

### Portfolio Analysis (Performance & Optimization)
```bash
# Portfolio analysis mode (always interactive)
python main.py --mode portfolio

# Custom model
python main.py --mode portfolio --model claude-haiku-4-5-20251001
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
│   ├── equity_analyst_graph.py         # LangGraph equity analyst (structured 10-step workflow)
│   ├── earnings_agent.py               # Earnings-focused agent (LangGraph)
│   ├── finance_qa_agent.py     # Interactive conversational agent
│   ├── market_agent.py                 # Market analysis agent
│   └── portfolio_agent.py              # Portfolio analyzer agent
├── tools/               # LangChain tool implementations
│   ├── dcf_tools.py                    # Stock info, financials, DCF, web search
│   ├── equity_analyst_tools.py         # Industry, competitor, moat analysis
│   ├── research_assistant_tools.py     # Calculations, comparisons, news
│   ├── market_tools.py                 # Market data, indices, sectors, VIX
│   └── portfolio_tools.py              # Portfolio metrics, diversification, tax harvesting
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

**LangGraph Equity Analyst** (`agents/equity_analyst_graph.py`)
- Tools: DCF tools + `analyze_industry`, `analyze_competitors`, `analyze_moat`
- Focus: Comprehensive equity research with **structured, deterministic workflow**
- Pattern: LangGraph with 10 fixed steps (company info → financials → industry → competitors → moat → management → DCF → thesis → recommendation → report)
- Benefits: Reproducible, debuggable, predictable execution order, better progress visibility

**Research Assistant Agent** (`agents/finance_qa_agent.py`)
- Tools: Financial lookups, calculations, comparisons, news, deep-dive analysis triggers
- Focus: Interactive exploration with conversation memory
- Pattern: Conversational agent with context retention and proactive suggestions

**Market Agent** (`agents/market_agent.py`)
- Tools: `get_market_overview`, `analyze_sector`, `get_market_news`, `classify_market_regime`
- Focus: Macro market conditions, sentiment, and sector rotation
- Pattern: ReAct agent for market-level analysis

**Portfolio Agent** (`agents/portfolio_agent.py`)
- Tools: `calculate_portfolio_metrics`, `analyze_diversification`, `identify_tax_loss_harvesting`
- Focus: Portfolio performance analysis, risk assessment, and tax optimization
- Pattern: ReAct agent with systematic portfolio analysis workflow

**Earnings Agent** (`agents/earnings_agent.py`)
- Tools: `get_quarterly_earnings`, `get_analyst_estimates`, `get_earnings_surprises`, `get_earnings_call_insights`, `compare_peer_earnings`, `get_price_targets`, `get_analyst_ratings`
- Focus: Comprehensive earnings analysis with management commentary from actual earnings call transcripts
- Pattern: 8-node LangGraph workflow (parallel data gathering → 1 analysis LLM call → 1 thesis LLM call → report)
- **Earnings Call Insights Tool** - Extracts primary source management quotes, guidance, and sentiment from earnings transcripts (Alpha Vantage → FMP → Perplexity fallback)

### Core Data Flow

All agents follow a similar pattern:

```
User Query → Agent (LLM) → Tool Selection → Tool Execution → Observation → Agent Reasoning → Response
```

**Key Components:**

1. **Agent Layer** (`agents/*.py`):
   - Creates LangChain ReAct agent with `create_react_agent()`
   - Defines systematic prompt templates with workflow instructions
   - Manages LLM (ChatAnthropic) and tool integration
   - Default model: `claude-sonnet-4-5-20250929` (configurable via `--model`)

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

**LangGraph Equity Analyst Workflow** (10-step, `agents/equity_analyst_graph.py`):
1. Company info (`get_stock_info`)
2. Financials (`get_financial_metrics`)
3. Industry analysis (`analyze_industry`)
4. Competitor analysis (`analyze_competitors`)
5. Moat evaluation (`analyze_moat`)
6. Management quality (`search_web`)
7. DCF valuation (`perform_dcf_analysis`)
8. Investment thesis
9. Recommendation (Buy/Hold/Sell)
10. Final report

**Research Assistant Features**:
- Maintains conversation context across queries
- Proactively suggests next analyses
- Can trigger deep-dive agents (DCF, industry, etc.) on demand
- Interactive loop with `interactive_session()` function

**Portfolio Agent Workflow** (encoded in `agents/portfolio_agent.py:64-137`):
1. Portfolio Overview - `calculate_portfolio_metrics` for overall performance, P&L, concentration risk
2. Diversification Assessment - `analyze_diversification` for sector exposure and diversification score
3. Tax Optimization - `identify_tax_loss_harvesting` for tax-saving opportunities
4. Final Recommendations - Synthesize findings into prioritized action items

**Earnings Agent Workflow** (8-node LangGraph, 2 LLM calls):
1. **Node 1**: Fetch company info (price, sector, market cap)
2. **Nodes 2-4 (Parallel Data Gathering)**:
   - Node 2: Fetch quarterly earnings history (revenue, EPS, margins, cash flow)
   - Node 3: Fetch analyst estimates (forward EPS and revenue forecasts)
   - Node 4: Fetch earnings surprises, **earnings call insights**, and peer comparison
3. **Node 5**: Aggregate (sync point — waits for all parallel nodes)
4. **Node 6**: Comprehensive analysis (1 LLM call — covers trends, quality, guidance, competition, valuation)
5. **Node 7**: Investment thesis + BUY/HOLD/SELL rating + price target (1 LLM call)
6. **Node 8**: Generate formatted report

**Earnings Call Insights Tool** (Node 4):
- Fetches earnings call transcripts with 3-tier fallback: Alpha Vantage (free) → FMP (premium) → Perplexity web search
- Extracts management quotes, forward guidance, Q&A themes, and sentiment
- Uses Perplexity Sonar Pro to analyze raw transcripts into structured insights

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
- Agent selection UI (DCF, Analyst, Research, Market, Portfolio)
- Message history and markdown rendering

**Communication Flow**:
1. User sends query from React UI
2. Frontend calls `/analyze` endpoint with POST request
3. Backend creates agent and attaches streaming callback
4. Agent executes, emitting events (thinking, thought, content, error, done)
5. SSE streams events back to frontend in real-time
6. React UI updates as each event arrives

### LangGraph Integration ✅

LangGraph is **fully integrated** and production-ready:

- **Earnings Agent**: 8-node LangGraph workflow (parallel data gathering → 2 LLM calls → report)
- **LangGraph Equity Analyst**: 10-step structured workflow (available via `--mode graph`)

Current versions are compatible:
- `langchain`: 0.3.27
- `langgraph`: 0.6.11

#### `--mode analyst` vs `--mode graph`

Both flags are equivalent aliases — both run the LangGraph 10-step equity analyst workflow. `--mode analyst` is kept for backwards compatibility.

### Finance Agent Arena Architecture

The Arena (`arena/`) is a separate multi-agent debate system that runs independently from the single-stock agents.

**Entry point**: `arena/run.py:run_arena(query, ticker, query_mode)`

**Graph structure** (`arena/graph.py`):
```
START → pm → sequence_start → <agent_node> → sequence_advance → sequence_start (loop)
                            → sequence_done → pm (next round)
         → output → END
```

Each agent runs in its own LangGraph super-step, so agent N+1 reads agent N's committed `raw_outputs` — this is the "peer context" guarantee.

**Shared state** (`arena/state.py:ThesisState`): All nodes read/write a single `TypedDict`. Key fields:
- `raw_outputs` — `{agent_name: full findings text}`, last-write-wins, read by subsequent agents
- `agent_signals` — `{agent_name: AgentSignal}` with `view`, `reasoning`, `confidence`
- `agent_questions/agent_answers` — cross-agent Q&A dicts
- `debate_log`, `signal_history`, `conflicts` — append-only via `operator.add`

**PM node** (`arena/pm.py`): On first pass sets `active_agents` from `ARENA_CONFIG["query_modes"]`. On subsequent passes computes `consensus_score = alignment_ratio × avg_confidence`, detects conflicts, synthesises thesis via Haiku LLM call, and sets `next_action` ("debate" | "finalise" | "escalate_to_human").

**Agent nodes** (`arena/fundamental_agent.py`, `quant_agent.py`, etc.): Each fetches real financial data (FinancialDataFetcher + Tavily web search), runs analysis, and returns an `AgentSignal`. Never raises — errors produce a neutral fallback signal.

**Config** (`arena/config.py:ARENA_CONFIG`):
- `consensus_threshold: 0.7` — stops debate early when reached
- `max_rounds: 2` — hard cap on debate rounds
- `query_modes` — maps mode names to ordered agent lists
- `recursion_limit: 100` set at invoke time (default 25 is too low for full IC run)

**Progress events** (`arena/progress.py`): `emit_arena_event()` emits SSE-style events (`arena_dispatch`, `arena_signal`, `arena_conflict`, `arena_synthesis`) consumed by the frontend Arena page.

### SEC EDGAR Integration

**Client**: `data/sec_edgar.py` — `SECEdgarClient` singleton, no API key required, sets `User-Agent` header per SEC requirements. Use `www.sec.gov/files/company_tickers.json` (not `data.sec.gov`) for CIK lookup.

**Tools** (`tools/sec_tools.py`): `GetSECFilingsTool`, `AnalyzeSECFilingTool`, `GetSECFinancialsTool`
- Revenue concept: use `RevenueFromContractWithCustomerExcludingAssessedTax` (ASC 606), fallback to `Revenues`
- Available in: Equity Analyst (13 tools total), Finance Q&A (7 tools total), Earnings Agent (parallel node 5)

### Database Persistence Layer

**Engine**: SQLite (`finance_agent.db` in project root). Set `DATABASE_URL` env var to use Postgres.

**New files**: `backend/database.py` (engine + `init_db()`), `backend/models.py` (5 ORM tables: `sessions`, `messages`, `analyses`, `watchlists`, `watchlist_tickers`)

**REST endpoints** in `api_server.py`: `/sessions`, `/analyses`, `/watchlists` + sub-resources. DCF/analyst/earnings/graph responses are auto-saved to the `analyses` table.

**Frontend**: `frontend/src/pages/LibraryPage.tsx` at `/library` route. Session URL synced to `?session=<uuid>` query param for bookmark/restore. Sidebar shows last 10 sessions.

**Python 3.9 compat**: use `Optional[str]` not `str | None`; add `from __future__ import annotations` at top of file.

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
python main.py --mode graph --ticker AAPL

# Interactive research
python main.py --mode research

# Market analysis
python main.py --mode market

# Portfolio analysis
python main.py --mode portfolio
```

### Testing and Validation
```bash
# Validate all dependencies and API access
python test_setup.py

# Test Financial Datasets API responses
python test_api.py

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_arena_level2_sequential.py -v

# Run a specific test
pytest tests/test_arena_level1_peer_context.py::test_peer_context_injected -v
```

### Terminal Data Monitor
```bash
# Interactive terminal monitor for data flow and API health
venv/bin/python eval_monitor.py health
venv/bin/python eval_monitor.py flow --agent dcf
venv/bin/python eval_monitor.py eval AAPL
venv/bin/python eval_monitor.py monitor AAPL --agent dcf
```

### Using Different Models
```bash
# Default model (claude-sonnet-4-5-20250929)
python main.py --mode graph --ticker AAPL

# Use a faster/cheaper model
python main.py --mode graph --ticker AAPL --model claude-haiku-4-5-20251001

# Use Opus for deeper reasoning
python main.py --mode dcf --ticker MSFT --model claude-opus-4-6
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

### Earnings Call Insights Tool Parameters

The `get_earnings_call_insights` tool accepts (`tools/earnings_tools.py`):
- `ticker` (str, required): Stock ticker symbol
- `query` (Optional[str], default=None): Specific focus area (e.g., "AI strategy", "margins", "iPhone demand")
- `quarters` (int, default=1): Number of recent quarters to analyze (1-8)

**Data Sources (3-tier automatic fallback)**:
1. **Primary (Free): Alpha Vantage** earnings call transcripts
   - Endpoint: `https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT`
   - **Free tier**: 25 requests/day (get a key at [alphavantage.co](https://www.alphavantage.co/support/#api-key))
   - 15+ years of transcripts (back to 2010) with speaker attribution
   - Client: `data/alpha_vantage.py` with singleton, caching, and rate limiting
   - If rate limited or unavailable, automatically falls back to FMP

2. **Secondary (Premium FMP users)**: FMP earnings call transcripts
   - Endpoint: `https://financialmodelingprep.com/stable/earning-call-transcript`
   - **Note**: Requires FMP premium subscription (as of August 2025)
   - Provides full verbatim transcripts with speaker attribution
   - If unavailable (402/403 error), automatically falls back to Perplexity

3. **Fallback (Always available)**: Perplexity web search
   - Searches authoritative financial sources (news, analyst reports, earnings summaries)
   - Still provides comprehensive structured analysis
   - Includes management commentary, guidance, Q&A themes, and sentiment
   - **Analysis quality remains high** using web-based sources

**Analysis Engine**: Perplexity Sonar Pro with structured prompts
- 5-part analysis framework: Financial Highlights, Management Commentary, Forward Guidance, Analyst Q&A, Tone & Sentiment
- Outputs markdown-formatted report (800-1200 words typically)
- Includes specific numbers, quotes (when available), and sentiment assessment

**Example Usage**:
```python
# General comprehensive analysis
tool.run(ticker="AAPL", quarters=1)

# Focused query on specific topic
tool.run(ticker="TSLA", query="What did management say about Full Self-Driving?", quarters=2)

# Multi-quarter analysis
tool.run(ticker="NVDA", quarters=4)
```

**Data Source Notes**:
- **Recommended**: Set `ALPHA_VANTAGE_API_KEY` for free primary-source transcripts (25 req/day)
- If you also have FMP premium access, FMP serves as a secondary transcript source
- For users without either key, Perplexity fallback provides excellent analysis quality
- No code changes needed — cascade is automatic and seamless
- Alpha Vantage EARNINGS endpoint also provides earnings surprise history (1 call = full history)

### Portfolio Tool Input Format

The Portfolio Agent expects portfolio data as a JSON string with the following structure (`tools/portfolio_tools.py`):
```json
[
  {
    "ticker": "AAPL",
    "shares": 100,
    "cost_basis": 150.00
  },
  {
    "ticker": "MSFT",
    "shares": 50,
    "cost_basis": 250.00
  }
]
```

**Key fields:**
- `ticker` (str): Stock ticker symbol (required)
- `shares` (float): Number of shares owned (required)
- `cost_basis` (float): Original purchase price per share (required for P&L and tax calculations)

The `identify_tax_loss_harvesting` tool also accepts:
- `min_loss_threshold` (float, default=1000.0): Minimum unrealized loss to flag for harvesting

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
- **Tool usage issues**: Some models may refuse to use tools; try `claude-sonnet-4-5-20250929` or `claude-opus-4-6` if issues occur
- **Reasoning callback**: `agents/reasoning_callback.py` provides friendly tool descriptions for CLI output
- **Streaming callback**: `backend/api_server.py` has `StreamingCallbackHandler` for web interface SSE
- **Portfolio Agent**: Always runs in interactive mode, requires portfolio JSON input format

### LangGraph Status (Updated 2026-02-02)
✅ **FULLY INTEGRATED** - No version conflicts
- Earnings Agent: 8-node LangGraph workflow (2 LLM calls)
- Equity Analyst Graph: 10-step structured workflow (`--mode graph`)

### Retry Logic and Resilience
- **All external API calls** implement exponential backoff retry logic for transient failures
- **Retryable errors**: Network timeouts, connection errors, HTTP 429 (rate limit), HTTP 5xx (server errors)
- **Non-retryable errors**: HTTP 400, 401, 403, 404 (client errors fail immediately)
- **Exponential backoff**: Wait times increase exponentially (1s → 2s → 4s) with random jitter to prevent thundering herd
- **Configurable policies**: Each API has tuned retry settings (max attempts, base delay, max delay)

## API Retry Strategy

All external API calls implement production-grade retry logic to handle transient failures gracefully.

### Retry Policies by API

**Financial Datasets API** (`data/financial_data.py`):
- Max attempts: 3
- Base delay: 1.0s
- Max delay: 30s
- Rationale: Fast API, usually reliable

**Perplexity API** (`tools/*.py`):
- Max attempts: 3
- Base delay: 1.5s
- Max delay: 45s
- Rationale: Search can be slow, more tolerance needed

**FMP API** (optional, `data/financial_data.py`):
- Max attempts: 3
- Base delay: 2.0s
- Max delay: 60s
- Rationale: Secondary data source, can be slower

**OpenAI API** (all agents):
- Built-in SDK retry: `max_retries=3`
- Timeout: 60s per request
- Rationale: SDK handles retries automatically

### Retryable vs Non-Retryable Errors

**Retryable (will retry with exponential backoff):**
- Network timeouts (`requests.exceptions.Timeout`)
- Connection errors (`requests.exceptions.ConnectionError`)
- HTTP 429 (Rate Limit)
- HTTP 5xx (Server errors: 500, 502, 503, 504)
- OpenAI API errors (`APIError`, `RateLimitError`)

**Non-Retryable (fail immediately):**
- HTTP 400 (Bad Request)
- HTTP 401 (Unauthorized - invalid API key)
- HTTP 403 (Forbidden)
- HTTP 404 (Not Found)

### Exponential Backoff Algorithm

```
wait_time = base_delay * (2 ^ attempt) + jitter
```

Example with base_delay=1s:
- Attempt 1: Wait 1s (2^0 = 1)
- Attempt 2: Wait 2s (2^1 = 2)
- Attempt 3: Wait 4s (2^2 = 4)
- Capped at max_delay

**Jitter**: Random ±25% variation prevents thundering herd when multiple clients retry simultaneously.

### Monitoring Retry Attempts

Retry attempts are logged at WARNING level:
```
WARNING: _make_request: Attempt 1/3 failed with Timeout: Connection timeout. Retrying in 1.23s...
```

Final failures are logged at ERROR level:
```
ERROR: _make_request: Failed after 3 attempts. Last error: Timeout: Connection timeout
```

### Customizing Retry Behavior

To customize retry settings for specific use cases:

```python
from shared.retry_utils import retry_with_backoff, RetryConfig

# More aggressive retry for critical operations
@retry_with_backoff(RetryConfig(
    max_attempts=5,
    base_delay=2.0,
    max_delay=120.0
))
def critical_api_call():
    # Your API call here
    pass
```

### Implementation Details

- **Location**: `shared/retry_utils.py` contains the retry decorator and configuration
- **Decorator pattern**: Uses `@retry_with_backoff()` decorator on API call functions
- **Thread-safe**: No shared state, safe for concurrent use
- **Transparent**: Existing error handling preserved, retry logic wraps cleanly
- **Zero overhead**: When no failures occur, decorator adds no latency

## Troubleshooting

### "Could not fetch data for ticker"
- Verify ticker symbol is correct
- Check internet connection and API quotas
- Try different ticker to test if API is working

### Agent doesn't use tools / just responds without calling tools
- Try using `--model claude-haiku-4-5-20251001` for a faster, lighter model
- Check that ANTHROPIC_API_KEY has sufficient credits
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

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
