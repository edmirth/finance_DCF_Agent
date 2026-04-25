"""
Arena shared data fetch node.

Runs once before any specialist agent, fetching all financial data that
agents share. All fetches run in parallel via ThreadPoolExecutor.

Data fetched:
  FinancialDataFetcher: stock_info (sequential, first), financial_statements,
                        key_metrics, price_history (ticker + SPY)
  Tavily (7 general):   multiples, company_context, revisions, news, analyst,
                        guidance, insider
  Tavily (4 macro):     macro_rates, macro_cycle, macro_inflation, macro_sector
  SEC EDGAR:            Form 4 insider filings

stock_info is fetched first (synchronous) because macro_sector_text is
parameterised with the company's sector. All remaining 15 fetches run in
parallel via ThreadPoolExecutor(max_workers=16).

Agents read from state["shared_data"] instead of fetching independently,
ensuring all five specialists reason from the same numbers.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from data.financial_data import FinancialDataFetcher
from data.sec_edgar import SECEdgarClient
from arena.state import ThesisState
from arena.progress import emit_arena_event
from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)


def _tavily_text(
    query: str,
    topic: str = "finance",
    search_depth: str = "basic",
    max_results: int = 5,
) -> str:
    """Execute a Tavily search and return answer + top results as a single string."""
    try:
        tavily = get_tavily_client()
        result = tavily.search(
            query=query,
            topic=topic,
            search_depth=search_depth,
            max_results=max_results,
        )
        content_limit = 600 if search_depth == "advanced" else 400
        parts = []
        if result.get("answer"):
            parts.append(result["answer"])
        for r in result.get("results", [])[:max_results]:
            if r.get("content"):
                parts.append(r["content"][:content_limit])
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"[DataFetch] Tavily search failed: {e}")
        return ""


def data_fetch_node(state: ThesisState) -> dict:
    """
    Fetch all shared financial data before specialist agents run.
    Stores results in state["shared_data"] which all agents read from.
    Never raises — partial data is better than no data.
    """
    ticker = state["ticker"]

    emit_arena_event({"type": "arena_agent_start", "agent": "data_fetch", "round": 0})
    print(f"[DataFetch] Fetching shared data for {ticker}")

    shared: dict[str, Any] = {}
    fetcher = FinancialDataFetcher()

    # ── Step 1: stock_info first (sector needed for macro_sector_text query) ──
    try:
        shared["stock_info"] = fetcher.get_stock_info(ticker) or {}
    except Exception as e:
        shared["stock_info"] = {}
        logger.warning(f"[DataFetch] get_stock_info failed: {e}")

    sector = shared["stock_info"].get("sector") or "Unknown"

    # ── Step 2: all remaining fetches in parallel ─────────────────────────────

    def _safe(key: str, fn, fallback: Any) -> tuple[str, Any]:
        try:
            result = fn()
            return key, result if result is not None else fallback
        except Exception as e:
            logger.warning(f"[DataFetch] {key} failed: {e}")
            return key, fallback

    tasks: dict[str, tuple] = {
        # ── FinancialDataFetcher ──────────────────────────────────────────────
        "financial_statements": (
            lambda: fetcher.get_financial_statements(ticker),
            {},
        ),
        "key_metrics": (
            lambda: fetcher.get_key_metrics(ticker),
            {},
        ),
        "price_history": (
            lambda: fetcher.get_price_history(ticker, days=400),
            [],
        ),
        "spy_price_history": (
            lambda: fetcher.get_price_history("SPY", days=400),
            [],
        ),
        # ── General Tavily searches ───────────────────────────────────────────
        # multiples_search_text — beta, P/E, EV/EBITDA, 52w high/low,
        #   analyst consensus, price targets. Used by: fundamental + risk agents.
        "multiples_search_text": (
            lambda: _tavily_text(
                f"{ticker} stock current price beta 52-week high low P/E ratio EV/EBITDA "
                f"sector average multiples analyst consensus price target downside risk",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # company_context_text — recent earnings, growth, guidance, competitive
        #   position. Used by: fundamental agent.
        "company_context_text": (
            lambda: _tavily_text(
                f"{ticker} recent earnings results revenue growth guidance 2025 2026 "
                f"competitive position growth drivers",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # revisions_search_text — EPS estimate revisions, analyst
        #   upgrades/downgrades, earnings surprises, VIX. Used by: quant agent.
        "revisions_search_text": (
            lambda: _tavily_text(
                f"{ticker} analyst EPS estimate revisions upgrades downgrades earnings "
                f"surprise beat miss current VIX level",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # news_search_text — recent news, catalysts, analyst reactions.
        #   Used by: sentiment agent (Pillar 1).
        "news_search_text": (
            lambda: _tavily_text(
                f"{ticker} stock news recent weeks major catalyst product launch "
                f"lawsuit regulatory issue earnings miss beat analyst reaction",
                topic="news", search_depth="advanced", max_results=7,
            ),
            "",
        ),
        # analyst_search_text — analyst ratings, price targets,
        #   upgrades/downgrades. Used by: sentiment agent (Pillar 2).
        "analyst_search_text": (
            lambda: _tavily_text(
                f"{ticker} analyst price target consensus rating buy sell hold "
                f"upgrades downgrades 2024 2025 Wall Street forecast",
                topic="finance", search_depth="advanced", max_results=7,
            ),
            "",
        ),
        # guidance_search_text — earnings call, management guidance, buybacks.
        #   Used by: sentiment agent (Pillar 3).
        "guidance_search_text": (
            lambda: _tavily_text(
                f"{ticker} earnings call guidance raised lowered maintained CEO CFO "
                f"outlook forward guidance buyback share repurchase dividend 2024 2025",
                topic="finance", search_depth="advanced", max_results=7,
            ),
            "",
        ),
        # insider_search_text — insider filings, institutional holdings, short
        #   interest. Used by: sentiment agent (Pillar 4).
        "insider_search_text": (
            lambda: _tavily_text(
                f"{ticker} insider buying selling Form 4 SEC filing institutional "
                f"holdings 13F short interest float hedge fund position 2024 2025",
                topic="finance", search_depth="advanced", max_results=7,
            ),
            "",
        ),
        # ── Macro Tavily searches (read by macro_agent, not fetched there) ────
        # macro_rates_text — Fed funds rate, 10Y yield, yield curve.
        "macro_rates_text": (
            lambda: _tavily_text(
                "Federal Reserve interest rate current level direction next meeting "
                "expectations 10-year Treasury yield today yield curve 2-year vs 10-year spread",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # macro_cycle_text — GDP, PMI, unemployment, recession probability.
        "macro_cycle_text": (
            lambda: _tavily_text(
                "US GDP growth latest quarter unemployment rate PMI manufacturing services "
                "leading indicators recession probability current economic cycle",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # macro_inflation_text — CPI, core CPI, PCE, inflation trend.
        "macro_inflation_text": (
            lambda: _tavily_text(
                "CPI inflation rate latest month core inflation PCE Federal Reserve "
                "inflation target trend rising falling disinflation",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # macro_sector_text — sector rotation, institutional positioning.
        #   Uses sector extracted from stock_info above.
        "macro_sector_text": (
            lambda: _tavily_text(
                f"{ticker} sector {sector} performance outlook current macro environment "
                "sector rotation analyst view institutional positioning",
                topic="finance", search_depth="basic", max_results=5,
            ),
            "",
        ),
        # ── SEC EDGAR Form 4 insider filings ─────────────────────────────────
        "sec_insider_filings": (
            lambda: SECEdgarClient().get_recent_filings(ticker, filing_type="4", limit=30),
            [],
        ),
    }

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {
            pool.submit(_safe, key, fn, fallback): key
            for key, (fn, fallback) in tasks.items()
        }
        for future in as_completed(futures):
            key, value = future.result()
            shared[key] = value

    # Normalise financial_statements shape (agents expect nested keys)
    stmts = shared.get("financial_statements") or {}
    shared["financial_statements"] = {
        "income_statements":    stmts.get("income_statements", []),
        "balance_sheets":       stmts.get("balance_sheets", []),
        "cash_flow_statements": stmts.get("cash_flow_statements", []),
    }

    print(
        f"[DataFetch] Done — "
        f"income={len(shared['financial_statements']['income_statements'])} stmts, "
        f"price={len(shared.get('price_history', []))} days, "
        f"spy={len(shared.get('spy_price_history', []))} days, "
        f"sec={len(shared.get('sec_insider_filings', []))} filings, "
        f"macro_texts={'yes' if shared.get('macro_rates_text') else 'empty'}"
    )

    emit_arena_event({
        "type": "arena_agent_done",
        "agent": "data_fetch",
        "view": "complete",
        "confidence": 1.0,
        "reasoning": "Shared financial data loaded",
    })

    return {"shared_data": shared}
