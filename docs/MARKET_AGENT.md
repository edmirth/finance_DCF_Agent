# Market Analysis Agent

The Market Analysis Agent is a specialized AI agent designed to analyze market conditions, sentiment, sector rotation, and news to provide investors with actionable market intelligence.

## Overview

The Market Agent provides comprehensive analysis of:
- **Market Indices** - S&P 500, Nasdaq, Dow Jones, Russell 2000 performance
- **Market Breadth** - Advance/decline ratios, new highs/lows
- **Volatility** - VIX levels, put/call ratios
- **Sector Rotation** - Leading and lagging sectors, defensive vs cyclical rotation
- **Market Regime** - BULL/BEAR/NEUTRAL classification with RISK_ON/RISK_OFF modes
- **Market News** - Latest market-moving developments and sentiment

## Quick Start

### Basic Usage

```bash
# Launch Market Agent in interactive mode
python main.py --mode market

# Use specific model
python main.py --mode market --model gpt-4
```

### Interactive Commands

Once in the Market Agent, you can use quick commands or ask custom questions:

**Quick Commands:**
- `overview` - Get comprehensive market overview
- `briefing` - Get daily market briefing
- `sectors` - Analyze sector rotation
- `regime` - Classify market regime
- `news` - Get latest market news

**Custom Questions:**
- "What's the market sentiment today?"
- "Should I be risk-on or risk-off?"
- "Which sectors are hot right now?"
- "Is this a good time to buy stocks?"
- "What's moving the market today?"

## Architecture

### Components

The Market Agent is built on three layers:

1. **Data Layer** (`data/market_data.py`)
   - Abstract base class for extensibility
   - Placeholder data with structure ready for massive.com API
   - Market regime classification logic

2. **Tools Layer** (`tools/market_tools.py`)
   - `GetMarketOverviewTool` - Comprehensive market snapshot
   - `GetSectorRotationTool` - Sector performance and rotation analysis
   - `GetMarketNewsTool` - Latest market news via Perplexity AI
   - `ClassifyMarketRegimeTool` - BULL/BEAR/NEUTRAL classification

3. **Agent Layer** (`agents/market_agent.py`)
   - LangChain ReAct agent orchestrating market tools
   - Professional analysis prompts
   - Helper methods for common queries

### Data Flow

```
User Query
    ↓
Market Agent (ReAct Loop)
    ↓
Market Tools (LangChain BaseTool)
    ↓
Market Data Fetcher
    ↓
Market Data Provider (Abstract)
    ↓
massive.com API (future) / Placeholder Data (current)
```

## Market Regime Classification

The Market Agent classifies market regime based on multiple factors:

### Regime Types
- **BULL** - Uptrend with positive breadth and low volatility
- **BEAR** - Downtrend with negative breadth and high volatility
- **NEUTRAL** - Mixed signals, choppy market

### Risk Modes
- **RISK_ON** - Low VIX (<20), low put/call ratio (<0.85), risk appetite
- **RISK_OFF** - High VIX, high put/call ratio, defensive positioning

### Signals Analyzed
1. **Trend** - Index price action (S&P 500)
2. **Breadth** - Advance/decline ratios (>1.5 = positive)
3. **Volatility** - VIX levels (LOW/NORMAL/ELEVATED/HIGH)
4. **High/Low Ratio** - New 52-week highs vs lows (>2.0 = bullish)

### Confidence Scoring
- **4/4 signals aligned** → 100% confidence
- **3/4 signals aligned** → 75% confidence
- **2/4 signals mixed** → 50% confidence (NEUTRAL)

## Agent Methods

### Core Methods

#### `analyze(query: str)`
General-purpose market analysis. Agent decides which tools to use based on query.

```python
agent = create_market_agent()
result = agent.analyze("What's the market sentiment today?")
```

#### `market_overview()`
Quick snapshot of current market conditions.

```python
result = agent.market_overview()
# Returns: indices, breadth, volatility, regime
```

#### `sector_analysis(timeframe: str = "1M")`
Analyze sector rotation over specified timeframe.

```python
result = agent.sector_analysis(timeframe="1M")
# Timeframes: '1D', '5D', '1M', '3M', 'YTD'
```

#### `market_regime_analysis()`
Deep-dive market regime classification.

```python
result = agent.market_regime_analysis()
# Returns: BULL/BEAR/NEUTRAL, RISK_ON/RISK_OFF, signals, confidence
```

#### `news_analysis(topic: Optional[str] = None)`
Latest market news and developments.

```python
result = agent.news_analysis()  # General news
result = agent.news_analysis(topic="Fed")  # Specific topic
```

#### `daily_briefing()`
Comprehensive daily market briefing combining all analyses.

```python
result = agent.daily_briefing()
# Returns: overview + sectors + regime + news + recommendations
```

## Use Cases

### Morning Market Briefing

```python
from agents.market_agent import create_market_agent

agent = create_market_agent()
briefing = agent.daily_briefing()
print(briefing)
```

### Sector Rotation Analysis

```python
# Find hot sectors this month
sectors = agent.sector_analysis(timeframe="1M")

# Compare different timeframes
short_term = agent.sector_analysis(timeframe="5D")
long_term = agent.sector_analysis(timeframe="3M")
```

### Market Regime Check

```python
# Before making investment decisions
regime = agent.market_regime_analysis()

# Adjust portfolio based on regime
if "BULL" in regime and "RISK_ON" in regime:
    # Favor growth, cyclicals
    pass
elif "BEAR" in regime and "RISK_OFF" in regime:
    # Favor cash, bonds, defensives
    pass
```

### News-Driven Analysis

```python
# General market news
news = agent.news_analysis()

# Specific topics
fed_news = agent.news_analysis(topic="Fed")
earnings_news = agent.news_analysis(topic="earnings")
inflation_news = agent.news_analysis(topic="inflation")
```

## Integration with massive.com API

The Market Agent now has **full integration** with the massive.com API (formerly Polygon.io) for real-time market data!

### Implementation Status

✅ **Fully Implemented:**
- **Indices Data** - Real-time S&P 500, Nasdaq, Dow Jones, Russell 2000
- **Sector ETFs** - Live performance for all 11 sector SPDR ETFs
- **VIX Data** - Real-time volatility index with classification
- **Smart Fallback** - Automatically uses placeholder data if API unavailable

⚠️ **Partially Implemented:**
- **Market Breadth** - Estimated from index performance (fetching all stocks would exceed rate limits)
- **Sector Timeframes** - 1D performance is real-time, longer timeframes use aggregate bars (optional enhancement)

### Setup Instructions

1. **Get API Key**
   - Sign up at [massive.com](https://massive.com)
   - Navigate to Dashboard → API Keys
   - Copy your API key

2. **Configure Environment**
   Add to your `.env` file:
   ```bash
   MASSIVE_API_KEY=your_actual_api_key_here
   ```

3. **Verify Integration**
   ```bash
   python main.py --mode market
   # You should see "Massive.com API initialized with key" in logs
   # Try 'overview' command to see real data
   ```

### How It Works

The system automatically detects your API key and switches between real data and placeholder data:

**Without API Key:**
```
WARNING: MASSIVE_API_KEY not found - using placeholder data
INFO: Using placeholder indices data
```

**With API Key:**
```
INFO: Massive.com API initialized with key
INFO: Fetching indices from massive.com: I:SPX,I:COMP,I:DJI,I:RUT
INFO: Successfully fetched 4 indices from massive.com
```

### API Endpoints Used

The implementation uses these massive.com REST API endpoints:

1. **Indices Snapshot** (`/v3/snapshot/indices`)
   - Fetches S&P 500 (I:SPX), Nasdaq (I:COMP), Dow (I:DJI), Russell 2000 (I:RUT)
   - Returns: current value, change, change %, session data
   - [Documentation](https://massive.com/docs/rest/indices/snapshots/indices-snapshot)

2. **Stocks Snapshot** (`/v2/snapshot/locale/us/markets/stocks/tickers`)
   - Fetches all 11 sector SPDR ETFs (XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLRE, XLC, XLU)
   - Returns: todaysChangePerc for 1D performance
   - [Documentation](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)

3. **VIX Snapshot** (`/v3/snapshot/indices?ticker=I:VIX`)
   - Fetches CBOE Volatility Index
   - Automatically classifies as LOW (<15), NORMAL (15-20), ELEVATED (20-30), HIGH (>30)
   - [Documentation](https://massive.com/indices)

4. **Aggregate Bars** (`/v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}`) - Optional
   - Used to enhance sector performance with accurate 5D, 1M, 3M, YTD data
   - [Documentation](https://massive.com/docs/rest/stocks/aggregates/custom-bars)

### Data Structure

The API responses are mapped to our standardized format:

**Indices:**
```python
{
    "SPX": {
        "name": "S&P 500",
        "price": 4783.45,
        "change": 35.67,
        "change_pct": 0.75,
        "52w_high": 4800.00,
        "52w_low": 4100.00,
        "volume": 3.2e9
    },
    # ... other indices
}
```

**Sector Performance:**
```python
{
    "XLK": {
        "name": "Technology",
        "1D": 1.5,
        "5D": 3.2,
        "1M": 8.5,
        "3M": 15.2,
        "YTD": 42.3
    },
    # ... other sectors
}
```

See `data/market_data.py` for complete structure.

## Environment Variables

Required environment variables in `.env`:

```bash
# OpenAI API (required)
OPENAI_API_KEY=your_openai_key

# Perplexity AI for news (required for news tool)
PERPLEXITY_API_KEY=your_perplexity_key

# massive.com API (optional - uses placeholder data if not set)
MASSIVE_API_KEY=your_massive_key
```

## Advanced Usage

### Programmatic Access

```python
from agents.market_agent import create_market_agent

# Initialize agent
agent = create_market_agent(model="gpt-4-turbo-preview")

# Custom analysis
result = agent.analyze("""
    Analyze current market conditions and tell me:
    1. Is this a good time to add equity exposure?
    2. Which sectors should I focus on?
    3. What are the key risks to monitor?
""")

print(result)
```

### Combining with Other Agents

The Market Agent is designed to work in multi-agent workflows:

```python
# Future workflow example
market_agent = create_market_agent()
equity_agent = create_equity_analyst_agent()

# Get market context
market_regime = market_agent.market_regime_analysis()

# Use market context for stock analysis
if "BULL" in market_regime:
    # Analyze growth stocks
    analysis = equity_agent.research_report("NVDA")
else:
    # Analyze defensive stocks
    analysis = equity_agent.research_report("JNJ")
```

## Limitations

### Current Limitations
- **Placeholder Data** - Using simulated data until massive.com API integrated
- **No Historical Analysis** - Only current market snapshot
- **No Technical Analysis** - Focus on regime/sentiment, not chart patterns
- **Limited News Sources** - Relies on Perplexity AI aggregation

### Future Enhancements
- Real-time data integration with massive.com
- Historical regime backtesting
- Technical indicator analysis (RSI, MACD, moving averages)
- Economic calendar integration
- Correlation analysis with bonds, commodities, currencies
- Earnings season tracking
- Automated daily briefing reports saved to files

## Troubleshooting

### "PERPLEXITY_API_KEY not found"
The news tool requires Perplexity API. Get a key at [perplexity.ai](https://perplexity.ai) or skip news analysis.

### "MASSIVE_API_KEY not found - using placeholder data"
This is a warning, not an error. The agent works with placeholder data. Add the API key when ready.

### Agent gives generic responses
- Ensure OPENAI_API_KEY is valid
- Try using GPT-4 instead of GPT-3.5: `--model gpt-4`
- Check that tools are being invoked (verbose=True shows tool calls)

### Import errors
Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

## Contributing

To extend the Market Agent:

1. **Add new tools** in `tools/market_tools.py`
2. **Add new data sources** in `data/market_data.py`
3. **Add new agent methods** in `agents/market_agent.py`
4. **Update tests** (future)

## Related Documentation

- [QUICKSTART.md](QUICKSTART.md) - General system overview
- [RESEARCH_ASSISTANT.md](RESEARCH_ASSISTANT.md) - Research Assistant Agent
- [LANGGRAPH_GUIDE.md](LANGGRAPH_GUIDE.md) - LangGraph implementation
- [CLAUDE.md](CLAUDE.md) - System architecture

## License

Part of the finance_dcf_agent project.
