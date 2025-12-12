# Financial Research Assistant

## Overview

The Financial Research Assistant is an **interactive, conversational AI agent** that helps you explore companies, analyze financial data, and make informed investment decisions. Unlike the one-shot DCF and Equity Analyst agents, the Research Assistant maintains conversation memory and enables deep-dive exploration through follow-up questions.

## Key Features

### 💬 Conversational Interface
- Ask questions in natural language
- Maintains context across the conversation
- Remembers what company you're analyzing
- Supports follow-up questions and clarifications

### 🎯 Proactive Suggestions
- After each answer, suggests relevant follow-up analyses
- Guides you toward important insights
- Helps you discover what you didn't know to ask

### 🔍 Quick Data Lookups
- Get specific metrics instantly (revenue, P/E, margins, etc.)
- No need to run full reports for simple questions
- Fast responses for exploratory analysis

### 🧮 Financial Calculations
- Perform ratio analysis (P/E, ROE, debt/equity)
- Calculate CAGR and growth rates
- Custom arithmetic calculations

### 📰 News & Market Context
- Fetch recent news and developments
- Explain earnings reports and announcements
- Understand market reactions

### 📊 Company Comparisons
- Compare two companies side-by-side
- Benchmark against competitors
- Understand relative positioning

### 🏗️ Deep Analysis
- Full DCF valuation on demand
- Industry analysis (Porter's 5 Forces)
- Competitive moat assessment
- Management quality evaluation

## How to Use

### Launch the Research Assistant

```bash
python main.py --mode research
```

This launches an interactive session where you can have a conversation with the assistant.

### Example Conversation Flow

```
💬 You: Tell me about Apple's revenue and profit margins

🤖 Assistant: [Retrieves data using get_quick_data tool]
📊 **Apple Inc (AAPL)**

**Revenue (TTM):** $383.9B
**Net Income:** $97.0B
**Net Margin:** 25.3%
**FCF Margin:** 26.2%

Suggestions:
• Want me to compare AAPL's margins to MSFT or GOOGL?
• Should I pull recent news to see if margins are expanding?
• I can calculate the historical CAGR to see revenue growth trends

💬 You: Yes, compare to Microsoft

🤖 Assistant: [Uses compare_companies tool]
📊 **Company Comparison: Apple Inc vs Microsoft Corporation**

**PROFITABILITY:**
- Net Margin: 25.3% vs 36.7%
- FCF Margin: 26.2% vs 32.1%

Microsoft has higher margins, driven by cloud/software business...

Suggestions:
• Should I analyze both companies' competitive moats?
• Want to see revenue growth rates to understand momentum?

💬 You: What's the latest news on Apple?

🤖 Assistant: [Uses get_recent_news tool]
📰 **Recent News for Apple Inc (AAPL)**

Recent developments include:
1. Vision Pro headset launch in international markets
2. Services revenue growth acceleration to 18% YoY
3. iPhone 15 strong demand in China despite competition...
```

### Commands

During a session, you can use these commands:

- **Type your question** - Get analysis and suggestions
- **reset** - Clear conversation memory and start fresh
- **context** - View current conversation context (ticker focus, message count)
- **quit** or **exit** - End the session

## Use Cases

### 1. Quick Data Lookups

Perfect for when you need specific metrics without running a full analysis:

```
💬 You: What's Tesla's P/E ratio and debt level?

🤖 Assistant: [Quick response with specific data]
```

### 2. Deep-Dive Exploration

Start with a question and go down the rabbit hole:

```
💬 You: Why is Nvidia growing so fast?

🤖 Assistant: [Explains AI chip demand, data center growth]
  Suggestion: Want me to analyze the semiconductor industry structure?

💬 You: Yes

🤖 Assistant: [Industry analysis using analyze_industry tool]
  Suggestion: Should I compare NVDA to AMD and INTC?

💬 You: Yes, and also run a DCF on Nvidia

🤖 Assistant: [Comparison + DCF valuation]
```

### 3. Company Comparisons

```
💬 You: Compare Coca-Cola and PepsiCo on profitability and growth

🤖 Assistant: [Side-by-side comparison]
  Suggestion: Want me to analyze their competitive moats?
```

### 4. Investment Research

```
💬 You: I'm considering investing in Microsoft. What should I look at?

🤖 Assistant: Let me help you evaluate MSFT comprehensively.
  First, here are the key metrics... [data]

  Suggestions:
  • Analyze cloud computing industry dynamics
  • Assess Microsoft's competitive moat (Azure, Office, Windows)
  • Review recent earnings and guidance
  • Perform DCF valuation
  • Compare to competitors (GOOGL, AMZN)

  Which would you like me to start with?
```

### 5. News Explanation

```
💬 You: Apple just reported earnings. What happened?

🤖 Assistant: [Fetches and explains recent earnings report]
  Suggestion: Want me to calculate the revenue growth acceleration?
```

## Available Tools

The Research Assistant has access to these tools:

### Quick Data & Calculations
- **get_quick_data** - Retrieve specific financial metrics
- **calculate** - Perform financial calculations and ratios

### News & Context
- **get_recent_news** - Fetch recent news and developments
- **search_web** - Search for current market data and trends

### Deep Analysis
- **get_stock_info** - Basic company information
- **get_financial_metrics** - Historical financials
- **perform_dcf_analysis** - DCF valuation (Bull/Base/Bear)
- **analyze_industry** - Industry structure and dynamics
- **analyze_competitors** - Competitive positioning
- **analyze_moat** - Competitive advantages
- **analyze_management** - Management quality

### Comparisons
- **compare_companies** - Side-by-side company comparison

## Tips for Best Results

### 1. Start Broad, Then Narrow
```
✓ "Tell me about Apple's business"
  → "What's their revenue growth rate?"
  → "How does that compare to Microsoft?"
  → "Perform a DCF on Apple"
```

### 2. Use Follow-Up Questions
The assistant maintains context, so you don't need to repeat the company name:
```
💬 You: Tell me about Tesla
🤖 Assistant: [Information about TSLA]

💬 You: What's their P/E ratio?  ← No need to say "Tesla's P/E ratio"
🤖 Assistant: [Calculates P/E for TSLA]
```

### 3. Let the Assistant Guide You
Pay attention to the suggestions - they help you discover important analyses you might have missed.

### 4. Combine Multiple Analyses
```
💬 You: Compare Google and Meta, then analyze the digital advertising industry
```

### 5. Use 'reset' for New Topics
If you switch from analyzing one company to another, use `reset` to clear context:
```
💬 You: reset
🤖 Assistant: ✓ Conversation memory cleared. Starting fresh!

💬 You: Tell me about Amazon
```

## Differences from Other Agents

| Feature | DCF Agent | Equity Analyst | Research Assistant |
|---------|-----------|----------------|-------------------|
| **Mode** | One-shot | One-shot | Conversational |
| **Output** | DCF valuation | Full research report | Interactive Q&A |
| **Memory** | None | None | ✓ Maintains context |
| **Suggestions** | No | No | ✓ Proactive guidance |
| **Follow-ups** | No | No | ✓ Supports deep-dive |
| **Quick Data** | No | No | ✓ Fast lookups |
| **Use Case** | Valuation only | Comprehensive report | Exploratory research |

## When to Use Each Agent

### Use Research Assistant when:
- You have questions about specific data points
- You want to explore a company interactively
- You need quick calculations or comparisons
- You're researching and don't know exactly what you're looking for
- You want to follow interesting threads of analysis
- You need news and market context

### Use DCF Agent when:
- You want a quick intrinsic value estimate
- You need Bull/Base/Bear scenarios
- Valuation is your primary focus

### Use Equity Analyst when:
- You want a comprehensive research report
- You need industry + competitive + moat + valuation analysis
- You want a structured BUY/HOLD/SELL recommendation

## Example Session

```bash
$ python main.py --mode research

================================================================================
FINANCIAL RESEARCH ASSISTANT
================================================================================

An AI-powered research assistant for exploring companies and making
informed investment decisions.

Features:
  • Answer questions about financial data
  • Perform quick calculations
  • Explain recent news and developments
  • Compare companies
  • Deep-dive analysis with DCF valuation
  • Proactive suggestions on what to explore next

Commands:
  • Type your question to get started
  • Type 'reset' to clear conversation memory
  • Type 'context' to see conversation context
  • Type 'quit' or 'exit' to end session
================================================================================

💬 You: What's Nvidia's current revenue and growth rate?

🤖 Assistant:
📊 **NVIDIA Corporation (NVDA)**

**Revenue (TTM):** $60.9B
**Revenue Growth (Historical):** 61.4%

NVIDIA is experiencing explosive growth, primarily driven by AI accelerator
demand from data centers and cloud providers.

**Suggestions:**
• Want me to compare NVDA to AMD and INTC on revenue growth?
• Should I analyze the semiconductor industry to understand TAM?
• I can perform a DCF to see if the stock is fairly valued at this growth rate

💬 You: Yes, compare to AMD

🤖 Assistant:
📊 **Company Comparison: NVIDIA Corporation vs Advanced Micro Devices**

**SIZE:**
- Market Cap: $2.2T vs $234.5B
- Revenue: $60.9B vs $22.7B

**GROWTH (Historical):**
- Revenue Growth: 61.4% vs 15.2%
- FCF Growth: 78.3% vs 28.1%

NVIDIA is significantly larger and growing much faster...

💬 You: quit

Goodbye!
```

## API Requirements

The Research Assistant requires:
- **OPENAI_API_KEY** - For LLM reasoning
- **FINANCIAL_DATASETS_API_KEY** - For financial data
- **PERPLEXITY_API_KEY** - For web search and news

Make sure all three are set in your `.env` file.

---

**Happy researching! The Financial Research Assistant is your AI partner for exploring the markets.** 🚀
