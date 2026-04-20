"""
Arena Quantitative Analyst Agent

Purpose-built quant analyst for the Finance Agent Arena.
Fetches real financial and price data, runs a 4-pillar quantitative analysis,
and returns a structured AgentSignal into the arena ThesisState whiteboard.

Pillars:
  1. Price Momentum         (12-1 momentum, 6m, 3m, relative vs S&P 500)
  2. Factor Scores          (value, quality, low-volatility factors)
  3. Volatility Regime      (annualised vol, VIX level)
  4. Earnings Revisions     (EPS estimate revisions, beats/misses streak)

Uses claude-haiku-4-5-20251001 for ALL LLM calls.
Never crashes the arena — all errors produce a fallback neutral signal.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from anthropic import Anthropic

from arena.state import AgentSignal, ThesisState
from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)

VALID_VIEWS = {"bullish", "bearish", "neutral", "cautious"}
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Level 3: the agent this one questions when uncertain
QUESTION_TARGET = "fundamental"


# ---------------------------------------------------------------------------
# Section 1 — Data fetching helpers
# ---------------------------------------------------------------------------

def fetch_financials(ticker: str) -> dict:
    """
    Fetch stock info, financial statements, and key metrics.
    Each call is independently wrapped — partial data is fine.
    Never raises.
    """
    result: dict = {"ticker": ticker, "_data_points_fetched": 0}
    fetcher = FinancialDataFetcher()

    try:
        stock_info = fetcher.get_stock_info(ticker)
        if stock_info:
            result.update(stock_info)
            result["_data_points_fetched"] += 1
    except Exception as e:
        print(f"[Quant] get_stock_info failed for {ticker}: {e}")

    try:
        statements = fetcher.get_financial_statements(ticker)
        if statements:
            result["income_statements"] = statements.get("income_statements", [])
            result["balance_sheets"] = statements.get("balance_sheets", [])
            result["cash_flow_statements"] = statements.get("cash_flow_statements", [])
            result["_data_points_fetched"] += 1
    except Exception as e:
        print(f"[Quant] get_financial_statements failed for {ticker}: {e}")

    try:
        metrics = fetcher.get_key_metrics(ticker)
        if metrics:
            result["key_metrics"] = metrics
            result["_data_points_fetched"] += 1
    except Exception as e:
        print(f"[Quant] get_key_metrics failed for {ticker}: {e}")

    return result


def fetch_price_and_market_data(ticker: str) -> dict:
    """
    Two Tavily searches combined into one Haiku extraction call.
    Search 1: price history (12m, 6m, 3m, current) and S&P 500 return.
    Search 2: EPS revisions, upgrades/downgrades, earnings surprises, VIX.
    Falls back to safe defaults on any error.
    """
    defaults = {
        "current_price": None,
        "price_12m_ago": None,
        "price_6m_ago": None,
        "price_3m_ago": None,
        "sp500_return_12m": 0.10,
        "annualised_vol_pct": 25.0,
        "earnings_revisions_direction": "stable",
        "earnings_surprises": [],
        "analyst_upgrades_90d": 0,
        "analyst_downgrades_90d": 0,
        "vix_level": 20.0,
    }

    try:
        tavily = get_tavily_client()

        # Search 1: price history and momentum
        price_result = tavily.search(
            query=f"{ticker} stock price 12 months ago 6 months ago 3 months ago current price total return vs S&P 500",
            topic="finance",
            search_depth="basic",
            max_results=5,
        )

        # Search 2: earnings revisions and sentiment
        revision_result = tavily.search(
            query=f"{ticker} analyst EPS estimate revisions upgrades downgrades earnings surprise beat miss current VIX level",
            topic="finance",
            search_depth="basic",
            max_results=5,
        )

        # Combine both searches into one context block
        def _extract_content(result: dict) -> str:
            parts = []
            if result.get("answer"):
                parts.append(result["answer"])
            for r in result.get("results", [])[:3]:
                if r.get("content"):
                    parts.append(r["content"][:400])
            return "\n\n".join(parts)

        combined_content = (
            "=== PRICE HISTORY SEARCH ===\n"
            + _extract_content(price_result)
            + "\n\n=== REVISIONS & SENTIMENT SEARCH ===\n"
            + _extract_content(revision_result)
        )[:3000]

        if not combined_content.strip():
            return defaults

        client = Anthropic()
        extraction_prompt = (
            f"Extract from these search results for {ticker}.\n"
            f"Respond ONLY with a JSON object with these exact fields. Use null if not found:\n"
            f"- current_price: current stock price (number)\n"
            f"- price_12m_ago: stock price ~12 months ago (number)\n"
            f"- price_6m_ago: stock price ~6 months ago (number)\n"
            f"- price_3m_ago: stock price ~3 months ago (number)\n"
            f"- sp500_return_12m: S&P 500 total return over last 12 months as decimal e.g. 0.15 (number)\n"
            f"- annualised_vol_pct: annualised stock volatility percentage e.g. 28.5 (number)\n"
            f"- earnings_revisions_direction: direction of recent EPS estimate revisions — 'up', 'down', or 'stable' (string)\n"
            f"- earnings_surprises: list of last 4 quarters beat/miss as strings e.g. ['beat', 'beat', 'miss', 'beat'] (array)\n"
            f"- analyst_upgrades_90d: number of analyst upgrades in last 90 days (number)\n"
            f"- analyst_downgrades_90d: number of analyst downgrades in last 90 days (number)\n"
            f"- vix_level: current VIX index level (number)\n\n"
            f"Search results:\n{combined_content}"
        )

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": extraction_prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)

        surprises_raw = parsed.get("earnings_surprises") or []
        if isinstance(surprises_raw, list):
            surprises = [str(s).lower() for s in surprises_raw[:4]]
        else:
            surprises = []

        return {
            "current_price": float(parsed["current_price"]) if parsed.get("current_price") else None,
            "price_12m_ago": float(parsed["price_12m_ago"]) if parsed.get("price_12m_ago") else None,
            "price_6m_ago": float(parsed["price_6m_ago"]) if parsed.get("price_6m_ago") else None,
            "price_3m_ago": float(parsed["price_3m_ago"]) if parsed.get("price_3m_ago") else None,
            "sp500_return_12m": float(parsed.get("sp500_return_12m") or 0.10),
            "annualised_vol_pct": float(parsed.get("annualised_vol_pct") or 25.0),
            "earnings_revisions_direction": str(parsed.get("earnings_revisions_direction") or "stable").lower(),
            "earnings_surprises": surprises,
            "analyst_upgrades_90d": int(parsed.get("analyst_upgrades_90d") or 0),
            "analyst_downgrades_90d": int(parsed.get("analyst_downgrades_90d") or 0),
            "vix_level": float(parsed.get("vix_level") or 20.0),
        }

    except Exception as e:
        print(f"[Quant] fetch_price_and_market_data failed for {ticker}: {e}")
        return defaults


# ---------------------------------------------------------------------------
# Section 2 — Calculation helpers
# ---------------------------------------------------------------------------

def calculate_momentum(price_data: dict) -> dict:
    """
    12-1 momentum (12-month return excluding last month), 6m, 3m returns,
    and return relative to S&P 500.
    Signal thresholds: >15% relative outperformance → bullish, <-15% → bearish.
    """
    result = {
        "return_12m": None,
        "return_6m": None,
        "return_3m": None,
        "relative_return_12m": None,
        "momentum_signal": "neutral",
    }

    current = price_data.get("current_price")
    p12 = price_data.get("price_12m_ago")
    p6 = price_data.get("price_6m_ago")
    p3 = price_data.get("price_3m_ago")
    sp500_12m = price_data.get("sp500_return_12m", 0.10)

    try:
        if current and p12 and float(p12) > 0:
            r12 = (float(current) - float(p12)) / float(p12)
            result["return_12m"] = round(r12 * 100, 1)
            result["relative_return_12m"] = round((r12 - float(sp500_12m)) * 100, 1)

        if current and p6 and float(p6) > 0:
            result["return_6m"] = round(((float(current) - float(p6)) / float(p6)) * 100, 1)

        if current and p3 and float(p3) > 0:
            result["return_3m"] = round(((float(current) - float(p3)) / float(p3)) * 100, 1)

        rel = result["relative_return_12m"]
        r3 = result["return_3m"]

        if rel is not None and r3 is not None:
            if rel > 15 and r3 > 5:
                result["momentum_signal"] = "bullish"
            elif rel < -15 and r3 < -5:
                result["momentum_signal"] = "bearish"
            elif rel > 15 or (r3 is not None and r3 > 8):
                result["momentum_signal"] = "bullish"
            elif rel < -15 or (r3 is not None and r3 < -8):
                result["momentum_signal"] = "bearish"
        elif rel is not None:
            if rel > 15:
                result["momentum_signal"] = "bullish"
            elif rel < -15:
                result["momentum_signal"] = "bearish"

    except Exception as e:
        print(f"[Quant] calculate_momentum error: {e}")

    return result


def calculate_factor_scores(financials: dict) -> dict:
    """
    Value, quality, and low-vol factor composite.
    Metrics: earnings yield, FCF yield, ROE, FCF conversion, asset turnover.
    Score: -3 to +3. >=+2 → bullish, <=-1 → bearish.
    """
    result = {
        "earnings_yield": None,
        "fcf_yield": None,
        "roe": None,
        "fcf_conversion": None,
        "asset_turnover": None,
        "factor_score": 0,
        "factor_signal": "neutral",
    }

    try:
        metrics = financials.get("key_metrics", {})
        cf_stmts = financials.get("cash_flow_statements", [])
        bs_stmts = financials.get("balance_sheets", [])
        income_stmts = financials.get("income_statements", [])

        market_cap = float(financials.get("market_cap") or 0)
        latest_cf = cf_stmts[0] if cf_stmts else {}
        latest_bs = bs_stmts[0] if bs_stmts else {}
        latest_is = income_stmts[0] if income_stmts else {}

        score = 0

        # Earnings yield = EPS / Price = Net Income / Market Cap
        net_income = float(metrics.get("latest_net_income") or
                           latest_is.get("net_income") or
                           latest_is.get("netIncome") or 0)
        if market_cap > 0 and net_income > 0:
            ey = net_income / market_cap
            result["earnings_yield"] = round(ey * 100, 2)
            if ey > 0.06:   # >6% earnings yield = cheap
                score += 1
            elif ey < 0.02:
                score -= 1

        # FCF yield = Free Cash Flow / Market Cap
        fcf = float(latest_cf.get("free_cash_flow") or 0)
        if not fcf:
            op = float(latest_cf.get("net_cash_flow_from_operations") or latest_cf.get("operating_cash_flow") or 0)
            capex = abs(float(latest_cf.get("capital_expenditure") or latest_cf.get("capital_expenditures") or 0))
            fcf = op - capex
        if market_cap > 0 and fcf > 0:
            fcf_y = fcf / market_cap
            result["fcf_yield"] = round(fcf_y * 100, 2)
            if fcf_y > 0.05:   # >5% FCF yield = quality value
                score += 1
            elif fcf_y < 0.01:
                score -= 1

        # ROE = Net Income / Shareholders Equity
        equity = float(latest_bs.get("shareholders_equity") or
                       latest_bs.get("total_stockholders_equity") or 0)
        if equity > 0 and net_income > 0:
            roe = net_income / equity
            result["roe"] = round(roe * 100, 1)
            if roe > 0.15:   # >15% ROE = high quality
                score += 1
            elif roe < 0.05:
                score -= 1

        # FCF conversion = FCF / Net Income (>100% = good cash quality)
        if net_income > 0:
            conv = fcf / net_income
            result["fcf_conversion"] = round(conv, 2)
            if conv > 1.0:
                score += 1
            elif conv < 0.5:
                score -= 1

        # Asset turnover = Revenue / Total Assets (efficiency)
        revenue = float(latest_is.get("revenue") or 0)
        total_assets = float(latest_bs.get("total_assets") or 0)
        if total_assets > 0 and revenue > 0:
            at = revenue / total_assets
            result["asset_turnover"] = round(at, 2)
            if at > 0.8:
                score += 1
            elif at < 0.3:
                score -= 1

        result["factor_score"] = score
        if score >= 2:
            result["factor_signal"] = "bullish"
        elif score <= -1:
            result["factor_signal"] = "bearish"
        else:
            result["factor_signal"] = "neutral"

    except Exception as e:
        print(f"[Quant] calculate_factor_scores error: {e}")

    return result


def calculate_volatility_regime(price_data: dict) -> dict:
    """
    Assess volatility regime from annualised vol and VIX.
    vol < 20% and VIX < 15 → low vol → bullish signal
    vol > 40% or VIX > 25 → high vol → cautious signal
    """
    annualised_vol = float(price_data.get("annualised_vol_pct") or 25.0)
    vix = float(price_data.get("vix_level") or 20.0)

    if annualised_vol < 20 and vix < 15:
        vol_regime = "low"
        vol_signal = "bullish"
    elif annualised_vol > 40 or vix > 25:
        vol_regime = "high"
        vol_signal = "cautious"
    else:
        vol_regime = "normal"
        vol_signal = "neutral"

    return {
        "annualised_vol_pct": round(annualised_vol, 1),
        "vix_level": round(vix, 1),
        "vol_regime": vol_regime,
        "vol_signal": vol_signal,
    }


def calculate_revision_momentum(price_data: dict) -> dict:
    """
    Assess earnings revision momentum from direction and recent surprises streak.
    Consecutive beats + upward revisions → bullish.
    Consecutive misses + downward revisions → bearish.
    """
    direction = price_data.get("earnings_revisions_direction", "stable")
    surprises = price_data.get("earnings_surprises", [])
    upgrades = int(price_data.get("analyst_upgrades_90d") or 0)
    downgrades = int(price_data.get("analyst_downgrades_90d") or 0)

    # Count consecutive beats/misses from most recent
    consecutive_beats = 0
    consecutive_misses = 0
    for s in surprises:
        if "beat" in str(s).lower():
            if consecutive_misses == 0:
                consecutive_beats += 1
        elif "miss" in str(s).lower():
            if consecutive_beats == 0:
                consecutive_misses += 1
            break
        else:
            break

    # Net analyst sentiment
    net_upgrades = upgrades - downgrades

    if consecutive_beats >= 2 and direction == "up":
        revision_signal = "bullish"
    elif consecutive_beats >= 2 or (direction == "up" and net_upgrades > 0):
        revision_signal = "bullish"
    elif consecutive_misses >= 2 and direction == "down":
        revision_signal = "bearish"
    elif consecutive_misses >= 2 or (direction == "down" and net_upgrades < 0):
        revision_signal = "bearish"
    else:
        revision_signal = "neutral"

    return {
        "revisions_direction": direction,
        "consecutive_beats": consecutive_beats,
        "consecutive_misses": consecutive_misses,
        "net_upgrades_90d": net_upgrades,
        "revision_signal": revision_signal,
    }


def score_pillars(financials: dict, price_data: dict) -> dict:
    """
    Evaluate all 4 quant pillars and compute overall_signal + data_quality.
    """
    data_points_available = 0
    data_points_total = 8

    # ── Pillar 1: Price Momentum ──────────────────────────────────────────────
    momentum = calculate_momentum(price_data)
    if momentum["return_12m"] is not None:
        data_points_available += 2
    elif momentum["return_3m"] is not None:
        data_points_available += 1
    momentum_signal = momentum["momentum_signal"]

    # ── Pillar 2: Factor Scores ───────────────────────────────────────────────
    factors = calculate_factor_scores(financials)
    if factors["factor_score"] != 0 or factors["earnings_yield"] is not None:
        data_points_available += 2
    factor_signal = factors["factor_signal"]

    # ── Pillar 3: Volatility Regime ───────────────────────────────────────────
    vol = calculate_volatility_regime(price_data)
    if price_data.get("annualised_vol_pct") or price_data.get("vix_level"):
        data_points_available += 2
    vol_signal = vol["vol_signal"]

    # ── Pillar 4: Earnings Revisions ──────────────────────────────────────────
    revisions = calculate_revision_momentum(price_data)
    if price_data.get("earnings_surprises") or price_data.get("earnings_revisions_direction") != "stable":
        data_points_available += 2
    revision_signal = revisions["revision_signal"]

    # ── Overall signal: majority vote, tie-break → neutral ───────────────────
    all_signals = [momentum_signal, factor_signal, vol_signal, revision_signal]
    counts: dict[str, int] = {}
    for s in all_signals:
        counts[s] = counts.get(s, 0) + 1

    max_count = max(counts.values())
    majority_candidates = [s for s, c in counts.items() if c == max_count]

    if len(majority_candidates) == 1:
        overall_signal = majority_candidates[0]
    elif "neutral" in majority_candidates:
        overall_signal = "neutral"
    else:
        overall_signal = majority_candidates[0]

    data_quality = round(data_points_available / data_points_total, 2)

    return {
        "momentum_signal": momentum_signal,
        "factor_signal": factor_signal,
        "vol_signal": vol_signal,
        "revision_signal": revision_signal,
        "overall_signal": overall_signal,
        # Momentum details
        "return_12m": momentum.get("return_12m"),
        "return_6m": momentum.get("return_6m"),
        "return_3m": momentum.get("return_3m"),
        "relative_return_12m": momentum.get("relative_return_12m"),
        # Factor details
        "factor_score": factors.get("factor_score", 0),
        "earnings_yield": factors.get("earnings_yield"),
        "fcf_yield": factors.get("fcf_yield"),
        "roe": factors.get("roe"),
        # Vol details
        "annualised_vol_pct": vol.get("annualised_vol_pct"),
        "vix_level": vol.get("vix_level"),
        "vol_regime": vol.get("vol_regime"),
        # Revision details
        "revisions_direction": revisions.get("revisions_direction"),
        "consecutive_beats": revisions.get("consecutive_beats", 0),
        "consecutive_misses": revisions.get("consecutive_misses", 0),
        "net_upgrades_90d": revisions.get("net_upgrades_90d", 0),
        "data_quality": data_quality,
    }


# ---------------------------------------------------------------------------
# Section 2b — Data-CoT: reason about what the quant data means
# ---------------------------------------------------------------------------

def run_data_cot(
    ticker: str,
    financials: dict,
    price_data: dict,
    pillar_scores: dict,
) -> str:
    """
    Step 1 of 3 in the CoT pipeline.
    Haiku thinks step-by-step through price, factor, and revision signals.
    Output feeds into run_concept_cot() as grounded observations.
    Never raises — falls back to a compact metrics string.
    """
    r12 = pillar_scores.get("return_12m")
    r6 = pillar_scores.get("return_6m")
    r3 = pillar_scores.get("return_3m")
    rel = pillar_scores.get("relative_return_12m")
    ey = pillar_scores.get("earnings_yield")
    roe = pillar_scores.get("roe")

    data_snapshot = (
        f"Ticker: {ticker}\n"
        f"Price momentum: 12m={f'{r12:.1f}%' if r12 is not None else 'N/A'} | "
        f"6m={f'{r6:.1f}%' if r6 is not None else 'N/A'} | "
        f"3m={f'{r3:.1f}%' if r3 is not None else 'N/A'} | "
        f"vs S&P 12m={f'{rel:+.1f}%' if rel is not None else 'N/A'}\n"
        f"Factor score: {pillar_scores.get('factor_score', 0):+d}/5 | "
        f"EY={f'{ey:.1f}%' if ey is not None else 'N/A'} | "
        f"ROE={f'{roe:.1f}%' if roe is not None else 'N/A'}\n"
        f"Vol: {pillar_scores.get('annualised_vol_pct', 25.0):.1f}% ann. | "
        f"VIX={pillar_scores.get('vix_level', 20.0):.1f} | "
        f"regime={pillar_scores.get('vol_regime', 'normal')}\n"
        f"Revisions: direction={pillar_scores.get('revisions_direction', 'stable')} | "
        f"beats streak={pillar_scores.get('consecutive_beats', 0)} | "
        f"net upgrades 90d={pillar_scores.get('net_upgrades_90d', 0):+d}\n"
        f"Pillar votes: Momentum={pillar_scores.get('momentum_signal')} | "
        f"Factors={pillar_scores.get('factor_signal')} | "
        f"Vol={pillar_scores.get('vol_signal')} | "
        f"Revisions={pillar_scores.get('revision_signal')}"
    )

    prompt = (
        f"You are a quantitative analyst looking at {ticker} for the first time.\n\n"
        f"Quant data:\n{data_snapshot}\n\n"
        f"Think step by step through this data:\n"
        f"1. What are the 2-3 most important quant signals here? "
        f"Are momentum and factor scores aligned or conflicting?\n"
        f"2. What does the volatility regime imply for position sizing and conviction?\n"
        f"3. What is the earnings revision story telling you — are analysts upgrading "
        f"or downgrading, and does that match the price action?\n\n"
        f"Write your observations in 150-200 words. Use specific numbers. "
        f"Do not give a final verdict yet — just analyze the signals."
    )

    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[Quant] run_data_cot failed: {e}")
        return (
            f"Momentum: 12m={f'{r12:.1f}%' if r12 is not None else 'N/A'} | "
            f"3m={f'{r3:.1f}%' if r3 is not None else 'N/A'}. "
            f"Factor score: {pillar_scores.get('factor_score', 0):+d}/5. "
            f"Vol regime: {pillar_scores.get('vol_regime', 'normal')}."
        )


# ---------------------------------------------------------------------------
# Section 3 — Concept-CoT + Signal (LLM reasoning)
# ---------------------------------------------------------------------------

def _build_peer_context(state: ThesisState) -> str:
    """
    Reads what other agents have already written to the whiteboard.
    Prioritises raw_outputs (full findings) over agent_signals (structured only).
    Quant should maintain data independence from fundamental narrative —
    use peers only to calibrate confidence, not to change pillar signals.
    """
    raw_outputs = state.get("raw_outputs", {})
    agent_signals = state.get("agent_signals", {})

    if not raw_outputs and not agent_signals:
        return ""

    lines = []

    # First pass — agents with full raw findings (richest context)
    for agent_name, findings_text in raw_outputs.items():
        if agent_name == "quant":
            continue
        lines.append(f"[{agent_name.upper()} — full findings]\n{findings_text}\n")

    # Second pass — agents with only structured signals (no raw yet)
    for agent_name, signal in agent_signals.items():
        if agent_name == "quant":
            continue
        if agent_name in raw_outputs:
            continue
        lines.append(
            f"[{agent_name.upper()} — signal only] "
            f"{signal['view']} ({signal['confidence']:.0%}) — {signal['reasoning']}"
        )

    if not lines:
        return ""

    return (
        "Other analysts have already written their findings on the whiteboard:\n\n"
        + "\n".join(lines)
        + "\nIMPORTANT: Your quant pillars are data-driven and independent. "
        "Use peer findings only to calibrate your CONFIDENCE — do not let narrative "
        "override your price/factor signals. If fundamental and quant disagree, "
        "hold your view but reduce confidence. If peers strongly corroborate, "
        "you may revise confidence upward."
    )


def run_concept_cot(
    ticker: str,
    pillar_scores: dict,
    conflicts: list,
    state: ThesisState,
    data_cot_text: str = "",
) -> tuple:
    """
    Step 2 of 3 in the CoT pipeline (Concept-CoT).
    Applies quant framework to data_cot_text observations.
    Returns (concept_analysis_text, AgentSignal).
    """
    conflict_context = ""
    if conflicts:
        desc_list = [c.get("description", "") for c in conflicts if "quant" in c.get("agents", [])]
        if desc_list:
            conflict_context = (
                "\nCommittee conflicts flagged:\n"
                + "\n".join(f"- {d}" for d in desc_list)
                + "\nRevise confidence downward if the conflict introduces genuine uncertainty."
            )

    peer_context = _build_peer_context(state)
    r12 = pillar_scores.get("return_12m")
    r3 = pillar_scores.get("return_3m")
    rel = pillar_scores.get("relative_return_12m")
    roe = pillar_scores.get("roe")

    prompt = f"""You are a Quantitative Analyst at a hedge fund investment committee presenting on {ticker}.

DATA OBSERVATIONS (from your step-1 analysis):
{data_cot_text}

Pillar results:
- Price momentum:     {pillar_scores['momentum_signal']} (12m={f'{r12:.1f}%' if r12 is not None else 'N/A'}, 3m={f'{r3:.1f}%' if r3 is not None else 'N/A'}, vs S&P={f'{rel:+.1f}%' if rel is not None else 'N/A'})
- Factor scores:      {pillar_scores['factor_signal']} (score: {pillar_scores.get('factor_score', 0):+d}/5, ROE: {f'{roe:.1f}%' if roe is not None else 'N/A'})
- Volatility regime:  {pillar_scores['vol_signal']} ({pillar_scores.get('annualised_vol_pct', 25.0):.1f}% ann. vol, VIX={pillar_scores.get('vix_level', 20.0):.1f}, {pillar_scores.get('vol_regime', 'normal')})
- Earnings revisions: {pillar_scores['revision_signal']} (direction: {pillar_scores.get('revisions_direction', 'stable')}, beats streak: {pillar_scores.get('consecutive_beats', 0)}, net upgrades 90d: {pillar_scores.get('net_upgrades_90d', 0):+d})

Data quality: {pillar_scores['data_quality']:.0%}
{peer_context}
{conflict_context}

Apply your quant framework to these observations:
- Do momentum and factor signals agree? If not, which is more reliable here?
- Does the volatility regime change how much weight to put on the directional signal?
- Are earnings revisions confirming or contradicting the price action?
- What is the overall quant verdict — and what one data point would change it?

Respond in exactly this format (SIGNAL first, then ANALYSIS):

SIGNAL:
{{"view": "bullish"|"bearish"|"neutral"|"cautious", "reasoning": "one sentence with the key quant number", "confidence": 0.0-1.0}}

ANALYSIS: [2-3 sentences applying quant framework. Reference specific numbers.]

Note: Reduce confidence by 0.10 in high-vol regime (VIX >25). Maintain independence from fundamental narrative."""

    fallback_signal: AgentSignal = {
        "view": pillar_scores["overall_signal"],
        "reasoning": f"Pillar majority: {pillar_scores['overall_signal']}",
        "confidence": 0.45,
    }

    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # SIGNAL comes first — truncation-safe extraction
        analysis_text = ""
        signal_text = ""
        if "SIGNAL:" in text:
            parts = text.split("SIGNAL:", 1)
            after_signal = parts[1].strip()
            if "ANALYSIS:" in after_signal:
                signal_parts = after_signal.split("ANALYSIS:", 1)
                signal_text = signal_parts[0].strip()
                analysis_text = signal_parts[1].strip()
            else:
                signal_text = after_signal
        else:
            analysis_text = text

        signal = fallback_signal
        if signal_text:
            clean = signal_text
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            clean = clean.strip()
            try:
                parsed = json.loads(clean)
                view = str(parsed.get("view", "")).lower().strip()
                if view not in VALID_VIEWS:
                    view = pillar_scores["overall_signal"]
                confidence = round(min(max(float(parsed.get("confidence", 0.5)), 0.0), 1.0), 2)
                signal = {
                    "view": view,
                    "reasoning": str(parsed.get("reasoning", "Quantitative analysis complete.")),
                    "confidence": confidence,
                }
            except (json.JSONDecodeError, ValueError):
                print(f"[Quant] run_concept_cot: signal JSON parse failed, using pillar majority")

        return analysis_text, signal

    except Exception as e:
        print(f"[Quant] run_concept_cot failed: {e}")
        return "", fallback_signal


def run_llm_reasoning(
    ticker: str,
    pillar_scores: dict,
    conflicts: list,
    state: ThesisState,
    data_cot_text: str = "",
) -> AgentSignal:
    """Backward-compatible wrapper."""
    _, signal = run_concept_cot(ticker, pillar_scores, conflicts, state, data_cot_text)
    return signal


# ---------------------------------------------------------------------------
# Section 4 — Level 3: Agent-to-agent Q&A helpers
# ---------------------------------------------------------------------------

def _read_questions(agent_name: str, state: ThesisState) -> dict:
    """Returns {asking_agent: question_text} for questions addressed to agent_name."""
    all_questions = state.get("agent_questions", {})
    return {
        asker: targets[agent_name]
        for asker, targets in all_questions.items()
        if agent_name in targets
    }


def _build_answer_context(questions: dict) -> str:
    """Formats incoming questions for injection into the LLM prompt. Returns '' if none."""
    if not questions:
        return ""
    lines = ["DIRECT QUESTIONS FROM COMMITTEE MEMBERS — answer these in your reasoning:"]
    for asker, question in questions.items():
        lines.append(f"  [{asker.upper()} asks]: {question}")
    return "\n".join(lines)


def _extract_answers(
    agent_name: str,
    questions: dict,
    signal: AgentSignal,
    pillar_scores: dict,
    state: ThesisState,
) -> dict:
    """
    For each incoming question, makes a Haiku call to produce a grounded answer.
    Returns the full updated agent_answers dict (carry-forward pattern).
    """
    existing_answers = dict(state.get("agent_answers", {}))
    if not questions:
        return existing_answers

    answers_for_this_agent = {}
    client = Anthropic()

    for asking_agent, question in questions.items():
        prompt = (
            f"You are the {agent_name} analyst. A colleague ({asking_agent}) asked:\n"
            f'"{question}"\n\n'
            f"Your signal: {signal['view']} ({signal['confidence']:.0%} confidence)\n"
            f"Your findings: {json.dumps(pillar_scores, default=str)}\n\n"
            f"Answer in 1-2 sentences using specific numbers. Be direct."
        )
        try:
            response = client.messages.create(
                model=HAIKU_MODEL, max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            answers_for_this_agent[asking_agent] = response.content[0].text.strip()
        except Exception as e:
            print(f"[{agent_name.capitalize()}] _extract_answers error: {e}")
            answers_for_this_agent[asking_agent] = "Answer unavailable — see full findings."

    existing_answers[agent_name] = answers_for_this_agent
    return existing_answers


def _generate_question(
    agent_name: str,
    pillar_scores: dict,
    signal: AgentSignal,
    state: ThesisState,
) -> dict:
    """
    If confidence < 0.70 and conditions allow, asks QUESTION_TARGET one question.
    Returns the full updated agent_questions dict (carry-forward pattern).

    Guards (all must pass):
      1. confidence < 0.70
      2. agent_name not already in agent_questions (no repeat questions)
      3. QUESTION_TARGET has produced raw_outputs
    """
    existing_questions = dict(state.get("agent_questions", {}))

    if signal.get("confidence", 1.0) >= 0.70:
        return existing_questions
    if agent_name in existing_questions:
        return existing_questions
    if QUESTION_TARGET not in state.get("raw_outputs", {}):
        return existing_questions

    prompt = (
        f"You are the {agent_name} analyst with a {signal['view']} view at "
        f"{signal['confidence']:.0%} confidence — below your comfort threshold.\n"
        f"Write ONE specific question (1 sentence) for the {QUESTION_TARGET} analyst "
        f"that would most reduce your uncertainty. Cite exact metrics you need.\n"
        f"Your findings: {json.dumps(pillar_scores, default=str)}\n\n"
        f"If you have no genuinely useful question, respond exactly: NO_QUESTION"
    )
    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        question_text = response.content[0].text.strip()
        if question_text != "NO_QUESTION" and len(question_text) >= 10:
            existing_questions[agent_name] = {QUESTION_TARGET: question_text}
    except Exception as e:
        print(f"[{agent_name.capitalize()}] _generate_question error: {e}")

    return existing_questions


# ---------------------------------------------------------------------------
# Section 5 — Main entry point
# ---------------------------------------------------------------------------

def run_quant_agent(state: ThesisState) -> dict:
    """
    Main entry point called by arena/agents.py.
    Fetches data, runs 4-pillar quant analysis, returns AgentSignal.
    Always returns — never crashes the arena.
    """
    ticker = state.get("ticker", "")
    conflicts = state.get("conflicts", [])

    print(f"[Quant] Starting analysis for {ticker}")

    from arena.progress import emit_arena_event as _emit
    _emit({"type": "arena_agent_start", "agent": "quant", "round": state.get("round", 0) + 1})

    try:
        financials = fetch_financials(ticker)
        price_data = fetch_price_and_market_data(ticker)
        pillar_scores = score_pillars(financials, price_data)

        print(
            f"[Quant] Pillars: momentum={pillar_scores['momentum_signal']} "
            f"factors={pillar_scores['factor_signal']} "
            f"vol={pillar_scores['vol_signal']} "
            f"revisions={pillar_scores['revision_signal']} "
            f"→ overall={pillar_scores['overall_signal']} "
            f"data_quality={pillar_scores['data_quality']:.0%}"
        )

        # Stage 1 — Data-CoT: reason about what the quant signals mean
        data_cot_text = run_data_cot(ticker, financials, price_data, pillar_scores)

        # Stage 2 — Concept-CoT: apply quant framework, produce signal
        concept_text, signal = run_concept_cot(ticker, pillar_scores, conflicts, state, data_cot_text)

        # Level 3: Q&A
        incoming_questions = _read_questions("quant", state)
        updated_questions = _generate_question("quant", pillar_scores, signal, state)
        updated_answers = _extract_answers("quant", incoming_questions, signal, pillar_scores, state)

        r12 = pillar_scores.get("return_12m")
        r3 = pillar_scores.get("return_3m")
        rel = pillar_scores.get("relative_return_12m")
        ey = pillar_scores.get("earnings_yield")
        roe = pillar_scores.get("roe")

        raw_findings = (
            f"QUANT ANALYSIS — {ticker}\n\n"
            f"DATA OBSERVATIONS:\n{data_cot_text}\n\n"
            f"FRAMEWORK APPLICATION:\n{concept_text}\n\n"
            f"SIGNAL: {signal['view'].upper()} ({signal['confidence']:.0%} confidence)\n"
            f"REASONING: {signal['reasoning']}\n\n"
            f"METRICS: 12m={f'{r12:.1f}%' if r12 is not None else 'N/A'} | "
            f"3m={f'{r3:.1f}%' if r3 is not None else 'N/A'} | "
            f"vs S&P={f'{rel:+.1f}%' if rel is not None else 'N/A'} | "
            f"factors={pillar_scores.get('factor_score', 0):+d}/5 | "
            f"vol={pillar_scores.get('annualised_vol_pct', 25.0):.1f}% | "
            f"VIX={pillar_scores.get('vix_level', 20.0):.1f}"
        )

        if incoming_questions:
            qa_lines = ["\nQUESTIONS ANSWERED:"]
            my_answers = updated_answers.get("quant", {})
            for asker, q in incoming_questions.items():
                qa_lines.append(f"  [{asker.upper()} asked]: {q}")
                qa_lines.append(f"  [Answer]: {my_answers.get(asker, 'No answer generated.')}")
            raw_findings += "\n".join(qa_lines)

        if "quant" in updated_questions:
            tgt = list(updated_questions["quant"].keys())[0]
            raw_findings += f"\nOPEN QUESTION TO {tgt.upper()}: {updated_questions['quant'][tgt]}"

    except Exception as e:
        print(f"[Quant] Unhandled error for {ticker}: {e}")
        signal = {
            "view": "neutral",
            "reasoning": f"Analysis incomplete — data error: {str(e)[:80]}",
            "confidence": 0.30,
        }
        raw_findings = f"QUANT ANALYSIS — {ticker}\nError: {str(e)[:120]}"
        updated_questions = dict(state.get("agent_questions", {}))
        updated_answers = dict(state.get("agent_answers", {}))

    print(f"[Quant] Signal: view={signal['view']} confidence={signal['confidence']}")

    from arena.progress import emit_arena_event
    emit_arena_event({
        "type": "arena_agent_done",
        "agent": "quant",
        "view": signal["view"],
        "confidence": signal["confidence"],
        "reasoning": signal["reasoning"],
    })

    # Merge into existing raw_outputs — do not overwrite other agents' findings
    existing_raw = dict(state.get("raw_outputs", {}))
    existing_raw["quant"] = raw_findings

    return {
        "agent_signals":   {"quant": signal},
        "raw_outputs":     existing_raw,
        "agent_questions": updated_questions,
        "agent_answers":   updated_answers,
    }
