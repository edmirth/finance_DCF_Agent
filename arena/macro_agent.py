"""
Arena Macro Analyst Agent

Purpose-built macro analyst for the Finance Agent Arena.
Answers: is the current macroeconomic environment a tailwind or headwind
for this specific stock?

Pillars:
  1. Interest Rate Regime   (Fed funds rate, 10Y yield, yield curve shape)
  2. Economic Cycle         (GDP, PMI, unemployment, recession probability)
  3. Inflation Regime       (CPI, core CPI, trend — cross with sector)
  4. Sector Rotation        (institutional positioning, regime mapping)

Macro data is 100% Tavily-sourced — real-time, never invented.
FinancialDataFetcher used only to fetch company sector/name.

Uses claude-haiku-4-5-20251001 for ALL LLM calls.
Never crashes the arena — all errors produce a fallback neutral signal.
"""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from arena.state import AgentSignal, ThesisState
from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)

VALID_VIEWS = {"bullish", "bearish", "neutral", "cautious"}
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Level 3: the agent this one questions when uncertain
QUESTION_TARGET = "fundamental"

# Sector macro regime mapping — baseline before Tavily confirms
_SECTOR_RISING_RATES_FAVOUR = {"Financials", "Energy", "Materials", "Finance"}
_SECTOR_RISING_RATES_AVOID = {"Technology", "Real Estate", "Utilities", "Communication Services"}
_SECTOR_LATE_CYCLE_FAVOUR = {"Healthcare", "Consumer Staples", "Utilities"}
_SECTOR_LATE_CYCLE_AVOID = {"Consumer Discretionary", "Industrials", "Technology"}
_SECTOR_EARLY_CYCLE_FAVOUR = {"Technology", "Consumer Discretionary", "Industrials", "Financials"}
_SECTOR_HIGH_INFLATION_FAVOUR = {"Energy", "Materials", "Real Estate"}
_SECTOR_HIGH_INFLATION_AVOID = {"Technology", "Communication Services"}
_SECTOR_DISINFLATION_FAVOUR = {"Technology", "Consumer Discretionary", "Communication Services"}


# ---------------------------------------------------------------------------
# Section 1 — Data fetching helpers
# ---------------------------------------------------------------------------

def fetch_company_sector(ticker: str) -> dict:
    """
    Fetch only company name, sector, and industry from FinancialDataFetcher.
    This is the only FinancialDataFetcher call in this agent.
    All macro data comes from Tavily.
    Never raises.
    """
    result = {
        "ticker": ticker,
        "company_name": ticker,
        "sector": "Unknown",
        "industry": "Unknown",
        "market_cap": None,
    }

    try:
        fetcher = FinancialDataFetcher()
        stock_info = fetcher.get_stock_info(ticker)
        if stock_info:
            result["company_name"] = stock_info.get("name") or stock_info.get("company_name") or ticker
            result["sector"] = stock_info.get("sector") or "Unknown"
            result["industry"] = stock_info.get("industry") or "Unknown"
            result["market_cap"] = stock_info.get("market_cap")
    except Exception as e:
        print(f"[Macro] fetch_company_sector failed for {ticker}: {e}")

    return result


def fetch_macro_data(ticker: str, sector: str) -> dict:
    """
    Four Tavily searches (one per pillar) combined into one Haiku extraction call.
    Each search uses search_depth='basic', max_results=5.
    Returns structured macro indicators — never invented, never hallucinated.
    Falls back to safe defaults if extraction fails.
    """
    defaults = {
        "fed_funds_rate": None,
        "rate_direction": "stable",
        "ten_year_yield": None,
        "yield_curve": "flat",
        "next_fed_move": "unknown",
        "gdp_growth_pct": None,
        "unemployment_rate": None,
        "manufacturing_pmi": None,
        "services_pmi": None,
        "recession_probability_pct": None,
        "cycle_phase": "mid",
        "cpi_yoy_pct": None,
        "core_cpi_pct": None,
        "inflation_trend": "stable",
        "above_target": False,
        "sector_macro_view": "neutral",
        "institutional_positioning": "neutral",
        "sector_tailwinds": None,
        "sector_headwinds": None,
    }

    try:
        tavily = get_tavily_client()

        def _search(query: str) -> str:
            try:
                result = tavily.search(
                    query=query,
                    topic="finance",
                    search_depth="basic",
                    max_results=5,
                )
                parts = []
                if result.get("answer"):
                    parts.append(result["answer"])
                for r in result.get("results", [])[:3]:
                    if r.get("content"):
                        parts.append(r["content"][:400])
                return "\n\n".join(parts)
            except Exception as e:
                print(f"[Macro] Tavily search failed: {e}")
                return ""

        # Pillar 1 — Interest rates
        rates_text = _search(
            "Federal Reserve interest rate current level direction next meeting "
            "expectations 10-year Treasury yield today yield curve 2-year vs 10-year spread"
        )

        # Pillar 2 — Economic cycle
        cycle_text = _search(
            "US GDP growth latest quarter unemployment rate PMI manufacturing services "
            "leading indicators recession probability current economic cycle"
        )

        # Pillar 3 — Inflation
        inflation_text = _search(
            "CPI inflation rate latest month core inflation PCE Federal Reserve "
            "inflation target trend rising falling disinflation"
        )

        # Pillar 4 — Sector rotation (ticker-specific)
        sector_text = _search(
            f"{ticker} sector {sector} performance outlook current macro environment "
            "sector rotation analyst view institutional positioning"
        )

        combined = (
            "=== INTEREST RATES SEARCH ===\n" + rates_text[:700]
            + "\n\n=== ECONOMIC CYCLE SEARCH ===\n" + cycle_text[:700]
            + "\n\n=== INFLATION SEARCH ===\n" + inflation_text[:700]
            + "\n\n=== SECTOR ROTATION SEARCH ===\n" + sector_text[:700]
        )

        if not combined.strip():
            print(f"[Macro] All Tavily searches returned empty for {ticker}")
            return defaults

        client = Anthropic()
        extraction_prompt = (
            f"Extract these macro indicators from the search results below.\n"
            f"Respond ONLY with a JSON object, no preamble, no markdown.\n\n"
            f"Required fields:\n"
            f"{{\n"
            f'  "fed_funds_rate": number or null,\n'
            f'  "rate_direction": "rising" | "falling" | "stable" | "cutting",\n'
            f'  "ten_year_yield": number or null,\n'
            f'  "yield_curve": "inverted" | "flat" | "normal" | "steepening",\n'
            f'  "next_fed_move": "hike" | "cut" | "hold" | "unknown",\n'
            f'  "gdp_growth_pct": number or null,\n'
            f'  "unemployment_rate": number or null,\n'
            f'  "manufacturing_pmi": number or null,\n'
            f'  "services_pmi": number or null,\n'
            f'  "recession_probability_pct": number or null,\n'
            f'  "cycle_phase": "early" | "mid" | "late" | "recession" | "recovery",\n'
            f'  "cpi_yoy_pct": number or null,\n'
            f'  "core_cpi_pct": number or null,\n'
            f'  "inflation_trend": "rising" | "falling" | "stable",\n'
            f'  "above_target": true or false,\n'
            f'  "sector_macro_view": "favoured" | "neutral" | "out-of-favour",\n'
            f'  "institutional_positioning": "overweight" | "neutral" | "underweight",\n'
            f'  "sector_tailwinds": "brief text or null",\n'
            f'  "sector_headwinds": "brief text or null"\n'
            f"}}\n\n"
            f"Search results:\n{combined}"
        )

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": extraction_prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)

        def _float(val, default=None):
            try:
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        def _str(val, default, valid_set=None):
            s = str(val).lower().strip() if val is not None else default
            if valid_set and s not in valid_set:
                return default
            return s

        return {
            "fed_funds_rate": _float(parsed.get("fed_funds_rate")),
            "rate_direction": _str(parsed.get("rate_direction"), "stable",
                                   {"rising", "falling", "stable", "cutting"}),
            "ten_year_yield": _float(parsed.get("ten_year_yield")),
            "yield_curve": _str(parsed.get("yield_curve"), "flat",
                                {"inverted", "flat", "normal", "steepening"}),
            "next_fed_move": _str(parsed.get("next_fed_move"), "unknown",
                                  {"hike", "cut", "hold", "unknown"}),
            "gdp_growth_pct": _float(parsed.get("gdp_growth_pct")),
            "unemployment_rate": _float(parsed.get("unemployment_rate")),
            "manufacturing_pmi": _float(parsed.get("manufacturing_pmi")),
            "services_pmi": _float(parsed.get("services_pmi")),
            "recession_probability_pct": _float(parsed.get("recession_probability_pct")),
            "cycle_phase": _str(parsed.get("cycle_phase"), "mid",
                                {"early", "mid", "late", "recession", "recovery"}),
            "cpi_yoy_pct": _float(parsed.get("cpi_yoy_pct")),
            "core_cpi_pct": _float(parsed.get("core_cpi_pct")),
            "inflation_trend": _str(parsed.get("inflation_trend"), "stable",
                                    {"rising", "falling", "stable"}),
            "above_target": bool(parsed.get("above_target", False)),
            "sector_macro_view": _str(parsed.get("sector_macro_view"), "neutral",
                                      {"favoured", "neutral", "out-of-favour"}),
            "institutional_positioning": _str(parsed.get("institutional_positioning"), "neutral",
                                              {"overweight", "neutral", "underweight"}),
            "sector_tailwinds": str(parsed.get("sector_tailwinds") or "") or None,
            "sector_headwinds": str(parsed.get("sector_headwinds") or "") or None,
        }

    except Exception as e:
        print(f"[Macro] fetch_macro_data failed for {ticker}: {e}")
        return defaults


# ---------------------------------------------------------------------------
# Section 2 — Pillar scoring helpers
# ---------------------------------------------------------------------------

def score_rate_pillar(macro_data: dict, sector: str) -> dict:
    """Pillar 1: Interest rate regime signal."""
    yield_curve = macro_data.get("yield_curve", "flat")
    rate_direction = macro_data.get("rate_direction", "stable")
    next_fed_move = macro_data.get("next_fed_move", "unknown")
    fed_rate = macro_data.get("fed_funds_rate")
    ten_year = macro_data.get("ten_year_yield")

    # Inverted yield curve = recession warning → hard cautious floor
    if yield_curve == "inverted":
        rate_signal = "cautious"
    elif rate_direction in ("falling", "cutting") or next_fed_move == "cut":
        # Cutting cycle — tailwind for most equities
        if sector in _SECTOR_RISING_RATES_FAVOUR:
            # Financials hurt by falling rates on net interest margin
            rate_signal = "neutral"
        else:
            rate_signal = "bullish"
    elif rate_direction == "rising" or next_fed_move == "hike":
        if sector in _SECTOR_RISING_RATES_FAVOUR:
            rate_signal = "neutral"   # rising rates hurt them less / help financials
        elif sector in _SECTOR_RISING_RATES_AVOID:
            rate_signal = "bearish"
        else:
            rate_signal = "cautious"
    elif yield_curve == "steepening":
        # Steepening curve usually means recovery / early expansion
        rate_signal = "bullish"
    else:
        rate_signal = "neutral"

    return {
        "rate_signal": rate_signal,
        "yield_curve": yield_curve,
        "rate_direction": rate_direction,
        "fed_funds_rate": fed_rate,
        "ten_year_yield": ten_year,
        "next_fed_move": next_fed_move,
    }


def score_cycle_pillar(macro_data: dict) -> dict:
    """Pillar 2: Economic cycle signal."""
    mfg_pmi = macro_data.get("manufacturing_pmi")
    svc_pmi = macro_data.get("services_pmi")
    gdp = macro_data.get("gdp_growth_pct")
    unemp = macro_data.get("unemployment_rate")
    recession_prob = macro_data.get("recession_probability_pct")
    cycle_phase = macro_data.get("cycle_phase", "mid")

    # Use composite PMI as primary indicator
    composite_pmi = None
    if mfg_pmi is not None and svc_pmi is not None:
        composite_pmi = (mfg_pmi + svc_pmi) / 2
    elif mfg_pmi is not None:
        composite_pmi = mfg_pmi
    elif svc_pmi is not None:
        composite_pmi = svc_pmi

    if cycle_phase in ("recession",):
        cycle_signal = "bearish"
    elif cycle_phase == "recovery":
        cycle_signal = "bullish"
    elif composite_pmi is not None:
        if composite_pmi > 55 and (gdp is None or gdp > 2.5):
            cycle_signal = "bullish"
        elif composite_pmi >= 50:
            cycle_signal = "neutral"
        elif composite_pmi >= 48:
            cycle_signal = "cautious"
        else:
            # PMI < 48 — contraction territory
            if recession_prob is not None and recession_prob > 40:
                cycle_signal = "bearish"
            else:
                cycle_signal = "cautious"
    elif gdp is not None:
        if gdp > 3.0:
            cycle_signal = "bullish"
        elif gdp > 1.5:
            cycle_signal = "neutral"
        else:
            cycle_signal = "cautious"
    else:
        cycle_signal = "neutral"

    return {
        "cycle_signal": cycle_signal,
        "cycle_phase": cycle_phase,
        "gdp_growth_pct": gdp,
        "unemployment_rate": unemp,
        "manufacturing_pmi": mfg_pmi,
        "services_pmi": svc_pmi,
        "recession_probability_pct": recession_prob,
    }


def score_inflation_pillar(macro_data: dict, sector: str) -> dict:
    """Pillar 3: Inflation regime signal, cross-adjusted for sector."""
    cpi = macro_data.get("cpi_yoy_pct")
    core_cpi = macro_data.get("core_cpi_pct")
    trend = macro_data.get("inflation_trend", "stable")
    above_target = macro_data.get("above_target", False)

    # Use core CPI if available, otherwise headline
    primary_cpi = core_cpi if core_cpi is not None else cpi

    if primary_cpi is not None:
        if primary_cpi > 6:
            base_signal = "bearish"
        elif primary_cpi > 4 or (primary_cpi > 3 and trend == "rising"):
            base_signal = "cautious"
        elif trend == "falling" and (primary_cpi is None or primary_cpi < 3.5):
            base_signal = "bullish"
        elif not above_target or (primary_cpi <= 2.5 and trend == "stable"):
            base_signal = "bullish"
        else:
            base_signal = "neutral"
    elif trend == "falling":
        base_signal = "bullish"
    elif trend == "rising" and above_target:
        base_signal = "cautious"
    else:
        base_signal = "neutral"

    # Sector modifier
    final_signal = base_signal
    if base_signal in ("bearish", "cautious"):
        if sector in _SECTOR_HIGH_INFLATION_FAVOUR:
            # Energy/commodities benefit from high inflation
            final_signal = "neutral" if base_signal == "cautious" else "cautious"
    elif base_signal == "bullish":
        if sector in _SECTOR_HIGH_INFLATION_AVOID:
            # Tech hurt more by rising inflation even when not at extremes
            pass  # no override needed — Tavily sector pillar handles this
        if sector in _SECTOR_DISINFLATION_FAVOUR and trend == "falling":
            final_signal = "bullish"  # disinflation is extra good for tech/growth

    return {
        "inflation_signal": final_signal,
        "cpi_yoy_pct": cpi,
        "core_cpi_pct": core_cpi,
        "inflation_trend": trend,
        "above_target": above_target,
    }


def score_sector_pillar(macro_data: dict) -> dict:
    """Pillar 4: Sector rotation signal from Tavily-sourced positioning."""
    sector_view = macro_data.get("sector_macro_view", "neutral")
    positioning = macro_data.get("institutional_positioning", "neutral")

    if sector_view == "favoured" and positioning == "overweight":
        sector_signal = "bullish"
    elif sector_view == "favoured" or positioning == "overweight":
        sector_signal = "bullish"
    elif sector_view == "out-of-favour" and positioning == "underweight":
        sector_signal = "bearish"
    elif sector_view == "out-of-favour" or positioning == "underweight":
        sector_signal = "cautious"
    else:
        sector_signal = "neutral"

    return {
        "sector_signal": sector_signal,
        "sector_macro_view": sector_view,
        "institutional_positioning": positioning,
        "sector_tailwinds": macro_data.get("sector_tailwinds"),
        "sector_headwinds": macro_data.get("sector_headwinds"),
    }


def score_pillars(macro_data: dict, sector: str) -> dict:
    """
    Evaluate all 4 macro pillars and compute overall_signal + data_quality.
    Weight: cycle (2x) + rate (2x) + inflation (1x) + sector (1x) = 6 total votes.
    """
    rates = score_rate_pillar(macro_data, sector)
    cycle = score_cycle_pillar(macro_data)
    inflation = score_inflation_pillar(macro_data, sector)
    sector_rot = score_sector_pillar(macro_data)

    rate_signal = rates["rate_signal"]
    cycle_signal = cycle["cycle_signal"]
    inflation_signal = inflation["inflation_signal"]
    sector_signal = sector_rot["sector_signal"]

    # Weighted vote: cycle and rate count double
    weighted_signals = [
        rate_signal, rate_signal,       # 2x weight
        cycle_signal, cycle_signal,     # 2x weight
        inflation_signal,               # 1x weight
        sector_signal,                  # 1x weight
    ]

    counts: dict[str, int] = {}
    for s in weighted_signals:
        counts[s] = counts.get(s, 0) + 1

    max_count = max(counts.values())
    majority_candidates = [s for s, c in counts.items() if c == max_count]

    # Inverted yield curve hard-overrides to cautious minimum
    if macro_data.get("yield_curve") == "inverted":
        if majority_candidates == ["bullish"]:
            overall_signal = "neutral"
        elif "bearish" not in majority_candidates:
            overall_signal = "cautious"
        else:
            overall_signal = majority_candidates[0]
    elif len(majority_candidates) == 1:
        overall_signal = majority_candidates[0]
    elif "neutral" in majority_candidates:
        overall_signal = "neutral"
    else:
        overall_signal = majority_candidates[0]

    # Data quality: count how many indicators we actually got
    indicators = [
        macro_data.get("fed_funds_rate"),
        macro_data.get("ten_year_yield"),
        macro_data.get("manufacturing_pmi"),
        macro_data.get("services_pmi"),
        macro_data.get("gdp_growth_pct"),
        macro_data.get("unemployment_rate"),
        macro_data.get("cpi_yoy_pct"),
        macro_data.get("recession_probability_pct"),
    ]
    data_points_available = sum(1 for v in indicators if v is not None)
    data_quality = round(data_points_available / len(indicators), 2)

    return {
        # Signals
        "rate_signal": rate_signal,
        "cycle_signal": cycle_signal,
        "inflation_signal": inflation_signal,
        "sector_signal": sector_signal,
        "overall_signal": overall_signal,
        # Rate details
        "yield_curve": rates["yield_curve"],
        "rate_direction": rates["rate_direction"],
        "fed_funds_rate": rates["fed_funds_rate"],
        "ten_year_yield": rates["ten_year_yield"],
        "next_fed_move": rates["next_fed_move"],
        # Cycle details
        "cycle_phase": cycle["cycle_phase"],
        "gdp_growth_pct": cycle["gdp_growth_pct"],
        "unemployment_rate": cycle["unemployment_rate"],
        "manufacturing_pmi": cycle["manufacturing_pmi"],
        "services_pmi": cycle["services_pmi"],
        "recession_probability_pct": cycle["recession_probability_pct"],
        # Inflation details
        "cpi_yoy_pct": inflation["cpi_yoy_pct"],
        "core_cpi_pct": inflation["core_cpi_pct"],
        "inflation_trend": inflation["inflation_trend"],
        "above_target": inflation["above_target"],
        # Sector details
        "sector_macro_view": sector_rot["sector_macro_view"],
        "institutional_positioning": sector_rot["institutional_positioning"],
        "sector_tailwinds": sector_rot["sector_tailwinds"],
        "sector_headwinds": sector_rot["sector_headwinds"],
        "data_quality": data_quality,
    }


# ---------------------------------------------------------------------------
# Section 3 — LLM reasoning
# ---------------------------------------------------------------------------

def _build_peer_context(state: ThesisState) -> str:
    """
    Reads what other agents have already written to the whiteboard.
    Prioritises raw_outputs (full findings) over agent_signals (structured only).
    Macro stays in its lane — use peer context only to calibrate confidence,
    never to comment on DCF, balance sheet, or earnings.
    """
    raw_outputs = state.get("raw_outputs", {})
    agent_signals = state.get("agent_signals", {})

    if not raw_outputs and not agent_signals:
        return ""

    lines = []

    for agent_name, findings_text in raw_outputs.items():
        if agent_name == "macro":
            continue
        lines.append(f"[{agent_name.upper()} — full findings]\n{findings_text}\n")

    for agent_name, signal in agent_signals.items():
        if agent_name == "macro":
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
        + "\nIMPORTANT: Your view is about the MACRO ENVIRONMENT only. "
        "Do not comment on P/E, DCF, balance sheet, or earnings — that is "
        "other agents' domain. Use peer context only to assess whether the macro "
        "backdrop supports or contradicts the committee's emerging thesis. "
        "If fundamental shows strong buy and you see late-cycle headwinds, "
        "lean cautious and cite that explicitly."
    )


def run_llm_reasoning(
    ticker: str,
    sector: str,
    pillar_scores: dict,
    macro_data: dict,
    conflicts: list,
    state: ThesisState,
) -> AgentSignal:
    """
    Single Haiku call to reason over macro pillar results and produce AgentSignal.
    Falls back to pillar majority on any error.
    """
    conflict_context = ""
    if conflicts:
        desc_list = [c.get("description", "") for c in conflicts if "macro" in c.get("agents", [])]
        if desc_list:
            conflict_context = (
                "\nThe investment committee has flagged these conflicts:\n"
                + "\n".join(f"- {d}" for d in desc_list)
                + "\nFactor this into your confidence."
            )

    peer_context = _build_peer_context(state)

    def _fmt(val, suffix="", precision=2, fallback="N/A"):
        if val is None:
            return fallback
        try:
            if precision == 0:
                return f"{val:.0f}{suffix}"
            elif precision == 1:
                return f"{val:.1f}{suffix}"
            else:
                return f"{val:.2f}{suffix}"
        except (TypeError, ValueError):
            return fallback

    prompt = f"""You are a Macro Analyst at a hedge fund investment committee.
Your job is to assess whether the macroeconomic environment is a
tailwind, headwind, or neutral for {ticker} ({sector} sector).
You do NOT analyse the company itself — only the world around it.
Never comment on P/E, DCF, balance sheet, or earnings.

4-pillar macro analysis:

- Interest rate regime:   {pillar_scores['rate_signal']}
  (Fed funds: {_fmt(pillar_scores.get('fed_funds_rate'), '%', 2)}, 10Y yield: {_fmt(pillar_scores.get('ten_year_yield'), '%', 2)},
   Curve: {pillar_scores.get('yield_curve', 'N/A')}, Next Fed move: {pillar_scores.get('next_fed_move', 'N/A')},
   Direction: {pillar_scores.get('rate_direction', 'N/A')})

- Economic cycle:         {pillar_scores['cycle_signal']} — {pillar_scores.get('cycle_phase', 'N/A')} cycle
  (GDP: {_fmt(pillar_scores.get('gdp_growth_pct'), '%', 1)}, Unemployment: {_fmt(pillar_scores.get('unemployment_rate'), '%', 1)},
   Mfg PMI: {_fmt(pillar_scores.get('manufacturing_pmi'), '', 1)}, Services PMI: {_fmt(pillar_scores.get('services_pmi'), '', 1)},
   Recession probability: {_fmt(pillar_scores.get('recession_probability_pct'), '%', 0)})

- Inflation regime:       {pillar_scores['inflation_signal']}
  (CPI: {_fmt(pillar_scores.get('cpi_yoy_pct'), '% YoY', 1)}, Core: {_fmt(pillar_scores.get('core_cpi_pct'), '%', 1)},
   Trend: {pillar_scores.get('inflation_trend', 'N/A')}, Above target: {pillar_scores.get('above_target', False)})

- Sector positioning:     {pillar_scores['sector_signal']}
  ({sector} — institutional: {pillar_scores.get('institutional_positioning', 'N/A')},
   macro view: {pillar_scores.get('sector_macro_view', 'N/A')})
  Tailwinds: {pillar_scores.get('sector_tailwinds') or 'N/A'}
  Headwinds: {pillar_scores.get('sector_headwinds') or 'N/A'}

Data quality: {pillar_scores['data_quality']:.0%} of macro indicators available.
{peer_context}
{conflict_context}

Key principle: your view is whether MACRO is for or against this stock.
A great company in a terrible macro environment still faces headwinds.

Respond with ONLY a JSON object — no preamble, no markdown:
{{
  "view": "bullish" | "bearish" | "neutral" | "cautious",
  "reasoning": "one sentence citing the dominant macro factor with real data",
  "confidence": 0.0 to 1.0
}}

Macro-specific guidance:
- "bullish" = macro is a clear tailwind for this sector/stock
- "bearish" = macro is a clear headwind (inverted curve + recession risk + sector out-of-favour)
- "cautious" = macro is mixed, some headwinds emerging but not recessionary
- "neutral" = stable macro, no strong directional view
- Inverted yield curve is a hard cautious/bearish override — lean cautious minimum
- Late cycle + rising rates for tech = bearish to cautious
- Falling rates + early/mid cycle = bullish for most sectors

Confidence calibration:
- 3 or 4 pillars agree AND data quality > 80%  → 0.72–0.88
- 2 pillars agree OR data quality 50–80%        → 0.50–0.71
- Pillars conflict OR data quality < 50%        → 0.35–0.50
- Always cite the real data point that drives your view (e.g. PMI, yield curve, CPI)"""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        view = str(parsed.get("view", "")).lower().strip()
        if view not in VALID_VIEWS:
            view = pillar_scores["overall_signal"]

        confidence = float(parsed.get("confidence", 0.5))
        confidence = round(min(max(confidence, 0.0), 1.0), 2)

        return {
            "view": view,
            "reasoning": str(parsed.get("reasoning", "Macro analysis complete.")),
            "confidence": confidence,
        }

    except Exception as e:
        print(f"[Macro] run_llm_reasoning failed: {e}")
        return {
            "view": pillar_scores["overall_signal"],
            "reasoning": f"LLM parse failed — pillar majority: {pillar_scores['overall_signal']}",
            "confidence": 0.45,
        }


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

def run_macro_agent(state: ThesisState) -> dict:
    """
    Main entry point called by arena/agents.py.
    Fetches sector, fetches real macro data, runs 4-pillar analysis, returns AgentSignal.
    Always returns — never crashes the arena.
    """
    ticker = state.get("ticker", "")
    conflicts = state.get("conflicts", [])

    print(f"[Macro] Starting analysis for {ticker}")

    from arena.progress import emit_arena_event as _emit
    _emit({"type": "arena_agent_start", "agent": "macro", "round": state.get("round", 0) + 1})

    try:
        company_info = fetch_company_sector(ticker)
        sector = company_info.get("sector") or "Unknown"

        print(f"[Macro] Fetching macro data for {ticker} (sector: {sector})")
        macro_data = fetch_macro_data(ticker, sector)

        pillar_scores = score_pillars(macro_data, sector)

        print(
            f"[Macro] Pillars: rates={pillar_scores['rate_signal']} "
            f"cycle={pillar_scores['cycle_signal']} "
            f"inflation={pillar_scores['inflation_signal']} "
            f"sector={pillar_scores['sector_signal']} "
            f"→ overall={pillar_scores['overall_signal']} "
            f"data_quality={pillar_scores['data_quality']:.0%}"
        )

        signal: AgentSignal = run_llm_reasoning(
            ticker, sector, pillar_scores, macro_data, conflicts, state
        )

        # Level 3: Q&A
        incoming_questions = _read_questions("macro", state)
        updated_questions = _generate_question("macro", pillar_scores, signal, state)
        updated_answers = _extract_answers("macro", incoming_questions, signal, pillar_scores, state)

        def _fmtv(val, suffix="", precision=1):
            if val is None:
                return "N/A"
            try:
                return f"{val:.{precision}f}{suffix}"
            except (TypeError, ValueError):
                return "N/A"

        raw_findings = (
            f"MACRO ANALYSIS — {ticker} ({sector} sector)\n"
            f"Rate regime: {pillar_scores.get('rate_signal')} | "
            f"Fed funds={_fmtv(macro_data.get('fed_funds_rate'), '%')} | "
            f"10Y={_fmtv(macro_data.get('ten_year_yield'), '%')} | "
            f"Curve={macro_data.get('yield_curve', 'N/A')} | "
            f"Next move={macro_data.get('next_fed_move', 'N/A')}\n"
            f"Cycle: {pillar_scores.get('cycle_signal')} — "
            f"{macro_data.get('cycle_phase', 'N/A')} | "
            f"GDP={_fmtv(macro_data.get('gdp_growth_pct'), '%')} | "
            f"PMI(mfg)={_fmtv(macro_data.get('manufacturing_pmi'))} | "
            f"Recession prob={_fmtv(macro_data.get('recession_probability_pct'), '%', 0)}\n"
            f"Inflation: {pillar_scores.get('inflation_signal')} | "
            f"CPI={_fmtv(macro_data.get('cpi_yoy_pct'), '%')} | "
            f"Trend={macro_data.get('inflation_trend', 'N/A')}\n"
            f"Sector: {pillar_scores.get('sector_signal')} | "
            f"{sector} — {macro_data.get('institutional_positioning', 'N/A')} | "
            f"View={macro_data.get('sector_macro_view', 'N/A')}\n"
            f"Tailwinds: {macro_data.get('sector_tailwinds') or 'N/A'}\n"
            f"Headwinds: {macro_data.get('sector_headwinds') or 'N/A'}\n"
            f"Final view: {signal['view']} ({signal['confidence']:.0%} confidence)\n"
            f"Reasoning: {signal['reasoning']}"
        )

        if incoming_questions:
            qa_lines = ["\nQUESTIONS ANSWERED:"]
            my_answers = updated_answers.get("macro", {})
            for asker, q in incoming_questions.items():
                qa_lines.append(f"  [{asker.upper()} asked]: {q}")
                qa_lines.append(f"  [Answer]: {my_answers.get(asker, 'No answer generated.')}")
            raw_findings += "\n".join(qa_lines)

        if "macro" in updated_questions:
            tgt = list(updated_questions["macro"].keys())[0]
            raw_findings += f"\nOPEN QUESTION TO {tgt.upper()}: {updated_questions['macro'][tgt]}"

    except Exception as e:
        print(f"[Macro] Unhandled error for {ticker}: {e}")
        signal = {
            "view": "neutral",
            "reasoning": f"Analysis incomplete — data error: {str(e)[:80]}",
            "confidence": 0.30,
        }
        raw_findings = f"MACRO ANALYSIS — {ticker}\nError: {str(e)[:120]}"
        updated_questions = dict(state.get("agent_questions", {}))
        updated_answers = dict(state.get("agent_answers", {}))

    print(f"[Macro] Signal: view={signal['view']} confidence={signal['confidence']}")

    from arena.progress import emit_arena_event
    emit_arena_event({
        "type": "arena_agent_done",
        "agent": "macro",
        "view": signal["view"],
        "confidence": signal["confidence"],
        "reasoning": signal["reasoning"],
    })

    existing_raw = dict(state.get("raw_outputs", {}))
    existing_raw["macro"] = raw_findings

    return {
        "agent_signals":   {"macro": signal},
        "raw_outputs":     existing_raw,
        "agent_questions": updated_questions,
        "agent_answers":   updated_answers,
    }
