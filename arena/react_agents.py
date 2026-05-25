"""
ReAct (tool-calling) specialist agents for the research orchestrator.

Each specialist gets its own curated toolset and a focused system prompt.
The agent runs a multi-step tool-calling loop (up to max_iterations) then
returns a structured dict that maps to AgentSection in the orchestrator.

Output contract
---------------
Every run_react_* function returns:
  {
    "view":        "BULLISH" | "BEARISH" | "NEUTRAL",
    "confidence":  float 0.0–1.0,
    "content":     str   (full markdown findings),
    "key_points":  list[str]  (3-5 bullets),
  }
Errors surface as exceptions; callers wrap in try/except.
"""
from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_SIGNAL_FOOTER = textwrap.dedent("""
    When you have gathered enough information, end your response with a JSON
    block (fenced with ```json) in exactly this format:

    ```json
    {
      "view":       "BULLISH" | "BEARISH" | "NEUTRAL",
      "confidence": <float 0.0–1.0>,
      "key_points": ["point 1", "point 2", "point 3"]
    }
    ```

    Before the JSON, write your full analysis in plain markdown paragraphs.
    Do NOT include the JSON block mid-response — only at the very end.
""").strip()


def _make_prompt(system: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", system + "\n\n" + _SIGNAL_FOOTER),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

def _parse_output(raw: str) -> dict[str, Any]:
    """Extract the terminal JSON block from an agent's final message."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            view = str(parsed.get("view", "NEUTRAL")).upper()
            if view not in ("BULLISH", "BEARISH", "NEUTRAL"):
                view = "NEUTRAL"
            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            key_points = [str(p) for p in parsed.get("key_points", [])][:5]
            content = raw[: match.start()].strip()
            return {
                "view": view,
                "confidence": confidence,
                "content": content,
                "key_points": key_points,
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: no parseable JSON — return full text as neutral
    logger.warning("react_agents: could not parse terminal JSON from agent output")
    return {
        "view": "NEUTRAL",
        "confidence": 0.4,
        "content": raw,
        "key_points": [],
    }


# ---------------------------------------------------------------------------
# Generic runner
# ---------------------------------------------------------------------------

def _run(
    tools: list,
    system_prompt: str,
    human_message: str,
    max_iterations: int = 8,
    use_sonnet: bool = False,
) -> dict[str, Any]:
    model = _SONNET if use_sonnet else _MODEL
    llm = ChatAnthropic(model=model, max_tokens=4096, timeout=120.0)
    prompt = _make_prompt(system_prompt)
    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=max_iterations,
        max_execution_time=180,
        return_intermediate_steps=False,
    )
    result = executor.invoke({"input": human_message})
    raw = result.get("output", "")
    return _parse_output(raw)


# ---------------------------------------------------------------------------
# Fundamental analyst
# ---------------------------------------------------------------------------

_FUNDAMENTAL_SYSTEM = textwrap.dedent("""
    You are a sell-side fundamental equity analyst. Your job is to assess the
    business quality, earnings power, and long-term competitive position of a
    single stock.

    Workflow (use tools in this order, only call what you need):
    1. get_stock_info         — confirm sector, market cap, current price
    2. get_financial_metrics  — revenue trend, margins, FCF, balance sheet
    3. analyze_industry       — market size, growth, key threats
    4. analyze_moat           — sustainable competitive advantages
    5. analyze_management     — capital allocation, track record
    6. get_sec_filings        — list recent 10-K / 10-Q
    7. analyze_sec_filing     — deep-dive one key filing (10-K) for risks and MD&A
    8. search_web             — any missing data points (recent news, guidance)

    Focus on: earnings quality, FCF generation, ROIC, balance sheet health,
    and whether the moat is durable. Skip steps that add no marginal value.
""").strip()


def run_react_fundamental(ticker: str, query: str) -> dict[str, Any]:
    from tools.stock_tools import GetStockInfoTool, GetFinancialMetricsTool, SearchWebTool
    from tools.equity_analyst_tools import (
        IndustryAnalysisTool, MoatAnalysisTool, ManagementAnalysisTool,
    )
    from tools.sec_tools import GetSECFilingsTool, AnalyzeSECFilingTool

    tools = [
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        IndustryAnalysisTool(),
        MoatAnalysisTool(),
        ManagementAnalysisTool(),
        GetSECFilingsTool(),
        AnalyzeSECFilingTool(),
        SearchWebTool(),
    ]
    human = (
        f"Perform a comprehensive fundamental analysis of {ticker}.\n"
        f"Research context: {query}"
    )
    return _run(tools, _FUNDAMENTAL_SYSTEM, human, max_iterations=10, use_sonnet=True)


# ---------------------------------------------------------------------------
# Quantitative analyst
# ---------------------------------------------------------------------------

_QUANT_SYSTEM = textwrap.dedent("""
    You are a quantitative equity analyst. Your job is to assess price
    momentum, factor signals, volatility, and analyst revision trends for a
    single stock.

    Workflow:
    1. get_stock_info         — confirm current price, market cap
    2. get_financial_metrics  — EPS trend, P/E, revenue growth (factor inputs)
    3. search_web             — recent analyst estimate revisions, price target
                                changes, short interest, relative performance
                                vs index (last 1M, 3M, 6M)
    4. calculate              — compute any ratios or momentum scores you need

    Focus on: price vs 52-week range, momentum vs SPY, analyst revision
    direction, short float, earnings estimate trend (up/down/flat).
    Express conviction numerically where possible.
""").strip()


def run_react_quant(ticker: str, query: str) -> dict[str, Any]:
    from tools.stock_tools import GetStockInfoTool, GetFinancialMetricsTool, SearchWebTool
    from tools.research_assistant_tools import FinancialCalculatorTool

    tools = [
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        SearchWebTool(),
        FinancialCalculatorTool(),
    ]
    human = (
        f"Perform a quantitative signal analysis of {ticker}.\n"
        f"Research context: {query}"
    )
    return _run(tools, _QUANT_SYSTEM, human, max_iterations=6)


# ---------------------------------------------------------------------------
# Risk analyst
# ---------------------------------------------------------------------------

_RISK_SYSTEM = textwrap.dedent("""
    You are a credit and risk analyst. Your job is to stress-test the balance
    sheet, identify downside scenarios, and flag tail risks for a single stock.

    Workflow:
    1. get_stock_info         — sector context, market cap
    2. get_financial_metrics  — debt/equity, interest coverage, current ratio,
                                cash burn, FCF vs capex
    3. get_sec_filings        — list 10-K and any 8-K risk disclosures
    4. analyze_sec_filing     — extract risk factors and debt covenant language
                                from the most recent 10-K
    5. search_web             — credit rating, recent downgrades, litigation,
                                regulatory risk, macro sensitivity

    Focus on: leverage, liquidity runway, refinancing risk, earnings stability,
    concentration risk, and any binary event risks (lawsuits, regulation).
    Rate each risk as LOW / MEDIUM / HIGH and size its potential impact.
""").strip()


def run_react_risk(ticker: str, query: str) -> dict[str, Any]:
    from tools.stock_tools import GetStockInfoTool, GetFinancialMetricsTool, SearchWebTool
    from tools.sec_tools import GetSECFilingsTool, AnalyzeSECFilingTool

    tools = [
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        GetSECFilingsTool(),
        AnalyzeSECFilingTool(),
        SearchWebTool(),
    ]
    human = (
        f"Perform a comprehensive risk assessment of {ticker}.\n"
        f"Research context: {query}"
    )
    return _run(tools, _RISK_SYSTEM, human, max_iterations=8, use_sonnet=True)


# ---------------------------------------------------------------------------
# Macro analyst
# ---------------------------------------------------------------------------

_MACRO_SYSTEM = textwrap.dedent("""
    You are a macro strategist. Your job is to assess how the current macro
    environment — interest rates, inflation, GDP growth, sector cycle — affects
    a specific stock's near-term prospects.

    Workflow:
    1. get_market_overview    — indices, VIX, market breadth
    2. get_macro_context      — Fed policy, rates, inflation, GDP
    3. get_sector_rotation    — which sectors are leading / lagging
    4. get_market_news        — key macro headlines
    5. search_web             — company-specific macro sensitivity (e.g. rate
                                sensitivity, FX exposure, commodity input costs)

    Focus on: macro tailwinds vs headwinds for this specific company, sector
    positioning relative to the current regime, and the 12-month macro outlook.
""").strip()


def run_react_macro(ticker: str, query: str) -> dict[str, Any]:
    from tools.market_tools import (
        GetMarketOverviewTool, GetMacroContextTool,
        GetSectorRotationTool, GetMarketNewsTool,
    )
    from tools.stock_tools import SearchWebTool

    tools = [
        GetMarketOverviewTool(),
        GetMacroContextTool(),
        GetSectorRotationTool(),
        GetMarketNewsTool(),
        SearchWebTool(),
    ]
    human = (
        f"Assess the macro environment and its impact on {ticker}.\n"
        f"Research context: {query}"
    )
    return _run(tools, _MACRO_SYSTEM, human, max_iterations=6)


# ---------------------------------------------------------------------------
# Sentiment analyst
# ---------------------------------------------------------------------------

_SENTIMENT_SYSTEM = textwrap.dedent("""
    You are a market sentiment analyst. Your job is to read the room —
    news flow, insider activity, institutional positioning, and social/analyst
    sentiment — for a single stock.

    Workflow:
    1. get_recent_news        — latest news headlines and narrative
    2. get_sentiment_score    — quantitative sentiment score
    3. get_sec_filings        — list recent Form 4 (insider transactions)
    4. search_web             — institutional ownership changes, short interest
                                trend, options positioning (put/call ratio),
                                social media sentiment (Reddit, Twitter)

    Focus on: is sentiment turning positive or negative? Are insiders buying or
    selling? Is institutional ownership rising or falling? Is there a narrative
    shift in media coverage? Rate overall sentiment as BULLISH / BEARISH /
    NEUTRAL with confidence.
""").strip()


def run_react_sentiment(ticker: str, query: str) -> dict[str, Any]:
    from tools.market_tools import GetSentimentScoreTool
    from tools.research_assistant_tools import RecentNewsTool
    from tools.sec_tools import GetSECFilingsTool
    from tools.stock_tools import SearchWebTool

    tools = [
        RecentNewsTool(),
        GetSentimentScoreTool(),
        GetSECFilingsTool(),
        SearchWebTool(),
    ]
    human = (
        f"Perform a sentiment analysis of {ticker}.\n"
        f"Research context: {query}"
    )
    return _run(tools, _SENTIMENT_SYSTEM, human, max_iterations=6)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

REACT_RUNNERS = {
    "fundamental": run_react_fundamental,
    "quant":       run_react_quant,
    "risk":        run_react_risk,
    "macro":       run_react_macro,
    "sentiment":   run_react_sentiment,
}
