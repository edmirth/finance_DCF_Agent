# Quick Start Guide

## Running the Financial Analysis Agents

You have **three agents** available:

### 1. DCF Agent (Fast - Quantitative Valuation Only)
**What it does:** Calculates intrinsic value using DCF methodology with web-sourced parameters

**Run it:**
```bash
python3 main.py --ticker AAPL
# or explicitly
python3 main.py --mode dcf --ticker AAPL
```

**Output:**
- Bull/Base/Bear intrinsic value scenarios
- BUY/HOLD/SELL recommendation based on upside potential
- Takes ~30-60 seconds

---

### 2. Equity Analyst Agent (Comprehensive Research Report)
**What it does:** Full equity research analysis like a professional analyst

**Run it:**
```bash
python3 main.py --mode analyst --ticker AAPL
```

**Output:**
- Company overview and business model
- Industry analysis (market size, Porter's 5 Forces, trends)
- Competitive position vs peers (market share, strengths/weaknesses)
- Competitive moat assessment (brand, network effects, switching costs)
- Financial analysis + DCF valuation
- Management quality assessment
- Bull case / Bear case scenarios
- Investment recommendation with price target
- Takes ~2-5 minutes (comprehensive analysis)

---

### 3. Financial Research Assistant (Interactive Exploration) 🆕
**What it does:** Conversational AI assistant for exploring companies and answering questions

**Run it:**
```bash
python3 main.py --mode research
```

**Features:**
- Ask questions in natural language
- Get quick data lookups (revenue, margins, P/E ratios, etc.)
- Perform financial calculations (CAGR, ROE, comparisons)
- Fetch and explain recent news
- Compare companies side-by-side
- Deep-dive analysis on demand (DCF, industry, moat, etc.)
- **Maintains conversation context** - remembers what you're discussing
- **Proactive suggestions** - guides you toward important analyses
- Interactive, conversational flow

**Example conversation:**
```
You: What's Apple's revenue and profit margin?
Assistant: [Shows data + suggests comparisons]

You: Compare to Microsoft
Assistant: [Comparison + suggests next steps]

You: What's the latest news on Apple?
Assistant: [Recent news + suggests deeper analysis]
```

See [RESEARCH_ASSISTANT.md](RESEARCH_ASSISTANT.md) for detailed guide.

---

## Examples

### Quick DCF on Multiple Stocks
```bash
python3 main.py --ticker AAPL
python3 main.py --ticker MSFT
python3 main.py --ticker GOOGL
python3 main.py --ticker TSLA
```

### Full Equity Research Reports
```bash
python3 main.py --mode analyst --ticker AAPL
python3 main.py --mode analyst --ticker NVDA
```

### Interactive Mode
```bash
# DCF Interactive
python3 main.py --mode dcf --interactive

# Equity Analyst Interactive
python3 main.py --mode analyst --interactive
```

In interactive mode, you can ask questions like:
- "Perform DCF analysis on AAPL"
- "What is Apple's competitive moat?"
- "Compare Tesla's financials to competitors"
- "Analyze Microsoft's management quality"

---

## Which Agent Should I Use?

**Use DCF Agent when:**
- You just want a quick intrinsic value calculation
- You need to compare valuations across many stocks quickly
- You want web-sourced beta and growth rates in the DCF

**Use Equity Analyst Agent when:**
- You want a comprehensive understanding of the company
- You need industry and competitive context
- You want to assess competitive moat and management quality
- You're writing a full investment thesis
- You want both qualitative AND quantitative analysis

**Use Financial Research Assistant when:**
- You have specific questions about a company
- You want to explore a company interactively
- You need quick data lookups or calculations
- You want to compare companies
- You're researching and don't know exactly what you're looking for
- You want news and market context
- You want proactive suggestions on what to analyze next

---

## Troubleshooting

**If you get API errors:**
1. Check your `.env` file has all three API keys:
   - `OPENAI_API_KEY`
   - `FINANCIAL_DATASETS_API_KEY`
   - `PERPLEXITY_API_KEY`

2. Make sure you have credits/quota on each service

**If the agent runs but doesn't use tools:**
- Try using `gpt-4o` instead: `python3 main.py --mode analyst --ticker AAPL --model gpt-4o`
- This is a known issue with `gpt-4-turbo-preview` sometimes refusing to use tools

**If analysis takes too long:**
- The Equity Analyst Agent is comprehensive and can take 2-5 minutes
- Use DCF Agent for faster results
- Check your internet connection (it makes many API calls)

---

## Pro Tips

1. **Start with DCF for quick screening**, then use Equity Analyst for deep dives
2. **Compare both outputs** - DCF gives you the numbers, Analyst gives you the story
3. **Use interactive mode** to ask follow-up questions about specific aspects
4. **Export reports** by redirecting output:
   ```bash
   python3 main.py --mode analyst --ticker AAPL > reports/aapl_report.txt
   ```

---

## Example Workflow

```bash
# Step 1: Quick DCF screen on a watchlist
python3 main.py --ticker AAPL
python3 main.py --ticker MSFT
python3 main.py --ticker NVDA

# Step 2: Deep dive on the most interesting one
python3 main.py --mode analyst --ticker NVDA

# Step 3: Interactive follow-up questions
python3 main.py --mode analyst --interactive
# Then ask: "What are NVIDIA's competitive advantages in AI chips?"
```

Happy analyzing! 📊
