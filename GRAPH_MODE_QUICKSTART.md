# LangGraph Equity Analyst - Quick Start Guide

## Try It Now

The LangGraph equity analyst is ready to use! Here's how to get started:

### 1. Quick Test (2 minutes)

```bash
# Verify integration
python3 test_graph_simple.py
```

Should output:
```
✓ All structure tests passed!
Integration is complete.
```

### 2. Run Your First Analysis

```bash
# Analyze Apple
python3 main.py --mode graph --ticker AAPL
```

You'll see:
```
Initializing LangGraph Equity Analyst Agent...
Using structured 10-step workflow

Analyzing AAPL...
[Step 1/9] Getting company info for AAPL
[Step 2/9] Getting financial metrics
[Step 3/9] Analyzing industry
[Step 4/9] Analyzing competitors
[Step 5/9] Analyzing competitive moat
[Step 6/9] Analyzing management quality
[Step 7/9] Performing DCF analysis
[Step 8/9] Developing investment thesis
[Step 9/9] Making recommendation

================================================================================
EQUITY RESEARCH REPORT: Apple Inc (AAPL)
Analyst: AI Equity Analyst (LangGraph) | Date: 2026-02-02
================================================================================

INVESTMENT RATING: HOLD
Price Target (12M): $245.00 (Current: $277.55)
Upside Potential: -11.7%
Conviction: MEDIUM

[... detailed analysis ...]
```

### 3. Try Interactive Mode

```bash
python3 main.py --mode graph --interactive
```

Then type:
```
You: Analyze Tesla
You: Research Microsoft
You: Full analysis on NVDA
You: exit
```

## What You Get

Every analysis includes:

✅ **Company Overview** - Name, sector, industry, current price
✅ **Financial Analysis** - Revenue, FCF, growth rates, debt
✅ **Industry Analysis** - Market size, Porter's 5 Forces, trends
✅ **Competitive Analysis** - Market share, positioning, peers
✅ **Moat Analysis** - Brand strength, network effects, pricing power
✅ **Management Analysis** - CEO quality, capital allocation
✅ **DCF Valuation** - Intrinsic value, upside potential
✅ **Investment Thesis** - Bull case (3 points), bear case (3 points)
✅ **Recommendation** - BUY/HOLD/SELL + price target + conviction
✅ **Professional Report** - Formatted equity research output

## Command Options

```bash
# Basic usage
python main.py --mode graph --ticker <TICKER>

# Different model
python main.py --mode graph --ticker AAPL --model gpt-4o

# Interactive mode
python main.py --mode graph --interactive
```

## Web Interface

```bash
# Start servers
./start_web.sh

# Or manually:
cd backend && python api_server.py &
cd frontend && npm run dev
```

Open `http://localhost:3000`, select "graph" agent, type: "Analyze AAPL"

## Comparison with Other Modes

### vs DCF Mode (`--mode dcf`)
- DCF: Fast quantitative valuation only (~1 min)
- Graph: Full equity research with qualitative analysis (~5-10 min)

### vs Analyst Mode (`--mode analyst`)
- Analyst: Flexible ReAct agent, variable execution
- Graph: **Structured 10-step workflow, deterministic**
- Graph: **Better progress visibility** ("[Step 3/10] Industry Analysis")
- Graph: **More reproducible** (same inputs → same workflow)

Both analyst and graph produce similar depth of analysis.

### vs Earnings Mode (`--mode earnings`)
- Earnings: Fast earnings-focused report (~15 min)
- Graph: Comprehensive equity research with valuation (~5-10 min)

## Tips

1. **Model Selection**: Use `gpt-4o` or `gpt-5.2` for best results
2. **API Keys**: Ensure `OPENAI_API_KEY`, `FINANCIAL_DATASETS_API_KEY`, and `PERPLEXITY_API_KEY` are set
3. **Retry Logic**: System automatically retries failed API calls
4. **Progress**: Watch for "[Step X/9]" messages to track progress
5. **Errors**: If a step fails, the analysis continues with graceful degradation

## Example Tickers to Try

```bash
# Large cap tech
python main.py --mode graph --ticker AAPL
python main.py --mode graph --ticker MSFT
python main.py --mode graph --ticker GOOGL

# Other sectors
python main.py --mode graph --ticker JPM    # Finance
python main.py --mode graph --ticker JNJ    # Healthcare
python main.py --mode graph --ticker XOM    # Energy
```

## Troubleshooting

**"Module not found: langgraph"**
```bash
pip install langgraph>=0.2.0
```

**"OPENAI_API_KEY not set"**
```bash
# Add to .env file
echo "OPENAI_API_KEY=your_key_here" >> .env
```

**"API quota exceeded"**
- Use a cheaper model: `--model gpt-4o-mini`
- Check your OpenAI billing

## Next Steps

- ✅ Run your first analysis
- ✅ Try interactive mode
- ✅ Compare with `--mode analyst`
- ✅ Integrate into your workflow
- 📖 Read `LANGGRAPH_INTEGRATION_COMPLETE.md` for architecture details

## Questions?

- Architecture: See `LANGGRAPH_INTEGRATION_COMPLETE.md`
- Code: See `agents/equity_analyst_graph.py`
- Workflow: See `docs/LANGGRAPH_GUIDE.md`
- Issues: Check logs for "[ERROR]" messages

---

**Ready to go! 🚀**

```bash
python3 main.py --mode graph --ticker AAPL
```
