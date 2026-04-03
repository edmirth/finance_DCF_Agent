"""
Arena Fundamental Analyst Agent

Purpose-built fundamental analyst for the Finance Agent Arena.
Fetches real financial data, runs a 4-pillar analysis, and returns
a structured AgentSignal into the arena ThesisState whiteboard.

Pillars:
  1. Intrinsic Value (FCF-based)
  2. Earnings Quality & Growth
  3. Valuation Multiples (vs. sector)
  4. Balance Sheet Quality

Uses claude-haiku-4-5-20251001 for ALL LLM calls.
Never crashes the arena — all errors produce a fallback neutral signal.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from anthropic import Anthropic

from arena.state import AgentSignal, ThesisState
from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)

VALID_VIEWS = {"bullish", "bearish", "neutral", "cautious"}
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Level 3: the agent this one questions when uncertain
QUESTION_TARGET = "risk"


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
        print(f"[Fundamental] get_stock_info failed for {ticker}: {e}")

    try:
        statements = fetcher.get_financial_statements(ticker)
        if statements:
            result["income_statements"] = statements.get("income_statements", [])
            result["balance_sheets"] = statements.get("balance_sheets", [])
            result["cash_flow_statements"] = statements.get("cash_flow_statements", [])
            result["_data_points_fetched"] += 1
    except Exception as e:
        print(f"[Fundamental] get_financial_statements failed for {ticker}: {e}")

    try:
        metrics = fetcher.get_key_metrics(ticker)
        if metrics:
            result["key_metrics"] = metrics
            result["_data_points_fetched"] += 1
    except Exception as e:
        print(f"[Fundamental] get_key_metrics failed for {ticker}: {e}")

    return result


def fetch_market_context(ticker: str) -> dict:
    """
    One Tavily search for current beta, sector P/E, analyst consensus.
    Haiku extracts structured numbers from raw search content.
    Falls back to safe defaults on any error.
    """
    defaults = {
        "current_price": None,
        "beta": 1.0,
        "sector_pe": 20.0,
        "analyst_consensus": "neutral",
        "news_sentiment": "neutral",
    }

    try:
        tavily = get_tavily_client()
        search_result = tavily.search(
            query=f"{ticker} stock current price beta P/E ratio sector average P/E analyst consensus",
            topic="finance",
            search_depth="basic",
            max_results=5,
        )

        # Combine answer + top result snippets into one context block
        content_parts = []
        if search_result.get("answer"):
            content_parts.append(search_result["answer"])
        for r in search_result.get("results", [])[:3]:
            if r.get("content"):
                content_parts.append(r["content"][:400])
        raw_content = "\n\n".join(content_parts)[:2000]

        if not raw_content.strip():
            return defaults

        # Haiku extraction call
        client = Anthropic()
        extraction_prompt = (
            f"Extract from these search results for {ticker}:\n"
            f"current_price, beta, sector_pe (sector average P/E), "
            f"analyst_consensus (buy/hold/sell), news_sentiment (positive/neutral/negative).\n"
            f"Respond ONLY with a JSON object with those 5 fields. Use null if not found.\n\n"
            f"Search results:\n{raw_content}"
        )
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": extraction_prompt}],
        )
        text = response.content[0].text.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        return {
            "current_price": parsed.get("current_price"),
            "beta": float(parsed.get("beta") or 1.0),
            "sector_pe": float(parsed.get("sector_pe") or 20.0),
            "analyst_consensus": str(parsed.get("analyst_consensus") or "neutral").lower(),
            "news_sentiment": str(parsed.get("news_sentiment") or "neutral").lower(),
        }

    except Exception as e:
        print(f"[Fundamental] fetch_market_context failed for {ticker}: {e}")
        return defaults


# ---------------------------------------------------------------------------
# Section 2 — Intrinsic Value calculation (Pillar 1)
# ---------------------------------------------------------------------------

def calculate_intrinsic_value(financials: dict, market_context: dict) -> dict:
    """
    Simplified 5-year FCF intrinsic value model.
    Returns valuation_signal, upside_pct, intrinsic_value_per_share, fcf_cagr, wacc.
    """
    fallback = {
        "intrinsic_value_per_share": None,
        "current_price": None,
        "upside_pct": 0.0,
        "valuation_signal": "neutral",
        "fcf_cagr": 0.0,
        "wacc": 0.10,
    }

    try:
        metrics = financials.get("key_metrics", {})
        cf_statements = financials.get("cash_flow_statements", [])
        if not cf_statements or len(cf_statements) < 2:
            return fallback

        # Extract FCF from cash flow statements (most recent first)
        fcf_values = []
        for cf in cf_statements[:5]:
            fcf = cf.get("free_cash_flow") or cf.get("freeCashFlow")
            if fcf is None:
                op = cf.get("operating_cash_flow") or cf.get("net_cash_provided_by_operating_activities") or 0
                capex = abs(cf.get("capital_expenditures") or cf.get("capitalExpenditures") or 0)
                fcf = op - capex
            fcf_values.append(float(fcf))

        if not fcf_values or fcf_values[0] <= 0:
            return fallback

        latest_fcf = fcf_values[0]

        # FCF CAGR (most recent vs oldest available)
        if len(fcf_values) >= 2 and fcf_values[-1] > 0:
            n = len(fcf_values) - 1
            fcf_cagr = (latest_fcf / fcf_values[-1]) ** (1 / n) - 1
        else:
            fcf_cagr = 0.05  # default

        # Clamp to reasonable range
        fcf_cagr = max(min(fcf_cagr, 0.40), -0.20)

        # WACC = risk_free_rate + beta * 0.07
        beta = float(market_context.get("beta") or 1.0)
        risk_free_rate = 0.045  # approximate current 10Y Treasury
        wacc = risk_free_rate + beta * 0.07
        wacc = max(min(wacc, 0.20), 0.06)

        terminal_growth = 0.025

        # Project 5-year FCF with 0.95 decay on growth rate
        pv_sum = 0.0
        projected_fcf = latest_fcf
        growth = fcf_cagr
        for year in range(1, 6):
            projected_fcf = projected_fcf * (1 + growth)
            growth = growth * 0.95
            pv_sum += projected_fcf / ((1 + wacc) ** year)

        # Terminal value
        terminal_value = (projected_fcf * (1 + terminal_growth)) / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** 5)

        enterprise_value = pv_sum + pv_terminal

        # Equity value adjustments
        latest_bs = (financials.get("balance_sheets") or [{}])[0]
        cash = float(latest_bs.get("cash_and_cash_equivalents") or
                     latest_bs.get("cash_and_short_term_investments") or 0)
        debt = float(latest_bs.get("total_debt") or
                     latest_bs.get("long_term_debt") or 0)
        shares = float(metrics.get("shares_outstanding") or
                       financials.get("weighted_average_shares") or 1)

        equity_value = enterprise_value + cash - debt
        intrinsic_per_share = equity_value / shares if shares > 0 else None

        # Current price
        current_price = (
            market_context.get("current_price")
            or financials.get("current_price")
            or None
        )
        if current_price:
            current_price = float(current_price)

        if intrinsic_per_share and current_price and current_price > 0:
            upside_pct = ((intrinsic_per_share - current_price) / current_price) * 100
        else:
            upside_pct = 0.0

        # Valuation signal
        if upside_pct > 20:
            valuation_signal = "bullish"
        elif upside_pct < 0:
            valuation_signal = "bearish"
        else:
            valuation_signal = "neutral"

        return {
            "intrinsic_value_per_share": round(intrinsic_per_share, 2) if intrinsic_per_share else None,
            "current_price": round(current_price, 2) if current_price else None,
            "upside_pct": round(upside_pct, 1),
            "valuation_signal": valuation_signal,
            "fcf_cagr": round(fcf_cagr * 100, 1),  # as percentage
            "wacc": round(wacc * 100, 1),            # as percentage
        }

    except Exception as e:
        print(f"[Fundamental] calculate_intrinsic_value error: {e}")
        return fallback


# ---------------------------------------------------------------------------
# Section 3 — Pillar scoring
# ---------------------------------------------------------------------------

def score_pillars(financials: dict, market_context: dict, valuation: dict) -> dict:
    """
    Evaluate all 4 pillars and compute overall_signal + data_quality.
    """
    metrics = financials.get("key_metrics", {})
    income_stmts = financials.get("income_statements", [])
    balance_sheets = financials.get("balance_sheets", [])
    cf_statements = financials.get("cash_flow_statements", [])
    data_points_available = 0
    data_points_total = 8

    # ── Pillar 1: Intrinsic Value ─────────────────────────────────────────────
    valuation_signal = valuation.get("valuation_signal", "neutral")
    if valuation.get("upside_pct") is not None:
        data_points_available += 1

    # ── Pillar 2: Earnings Quality & Growth ──────────────────────────────────
    growth_signal = "neutral"
    fcf_margin = 0.0
    revenue_cagr = 0.0

    try:
        revenues = metrics.get("historical_revenue", [])
        if len(revenues) >= 2 and revenues[-1] > 0:
            n = len(revenues) - 1
            revenue_cagr = (revenues[0] / revenues[-1]) ** (1 / n) - 1
            data_points_available += 1

        # FCF margin
        latest_revenue = metrics.get("latest_revenue") or (revenues[0] if revenues else 0)
        cf_latest = cf_statements[0] if cf_statements else {}
        fcf = cf_latest.get("free_cash_flow") or 0
        if not fcf:
            op = cf_latest.get("operating_cash_flow") or 0
            capex = abs(cf_latest.get("capital_expenditures") or 0)
            fcf = op - capex
        fcf = float(fcf)
        if latest_revenue > 0:
            fcf_margin = fcf / latest_revenue
            data_points_available += 1

        # Quality: FCF > net income is good
        latest_ni = metrics.get("latest_net_income") or 0
        fcf_quality = fcf > float(latest_ni) * 0.8 if latest_ni else True

        if revenue_cagr > 0.12 and fcf_quality:
            growth_signal = "bullish"
        elif revenue_cagr < 0 or (fcf_margin < 0.03 and latest_revenue > 0):
            growth_signal = "cautious"
        else:
            growth_signal = "neutral"
    except Exception as e:
        print(f"[Fundamental] Pillar 2 error: {e}")

    # ── Pillar 3: Valuation Multiples ─────────────────────────────────────────
    multiples_signal = "neutral"
    pe_vs_sector = "N/A"

    try:
        market_cap = float(financials.get("market_cap") or 0)
        latest_ni = float(metrics.get("latest_net_income") or 0)
        sector_pe = float(market_context.get("sector_pe") or 20.0)

        if market_cap > 0 and latest_ni > 0:
            company_pe = market_cap / latest_ni
            pe_premium = (company_pe - sector_pe) / sector_pe
            pe_vs_sector = f"{pe_premium:+.0%}"
            data_points_available += 1

            if pe_premium < -0.10:
                multiples_signal = "bullish"
            elif pe_premium > 0.30:
                multiples_signal = "cautious"
            else:
                multiples_signal = "neutral"
    except Exception as e:
        print(f"[Fundamental] Pillar 3 error: {e}")

    # ── Pillar 4: Balance Sheet Quality ──────────────────────────────────────
    balance_signal = "neutral"
    de_ratio = 0.0

    try:
        latest_bs = balance_sheets[0] if balance_sheets else {}
        total_debt = float(latest_bs.get("total_debt") or
                           latest_bs.get("long_term_debt") or 0)
        equity = float(latest_bs.get("shareholders_equity") or
                       latest_bs.get("total_stockholders_equity") or 1)
        cash = float(latest_bs.get("cash_and_cash_equivalents") or
                     latest_bs.get("cash_and_short_term_investments") or 0)

        if equity > 0:
            de_ratio = total_debt / equity
            data_points_available += 1

        ebit = float(metrics.get("latest_ebit") or 0)
        interest = float(metrics.get("latest_interest_expense") or 0)
        interest_coverage = (ebit / abs(interest)) if interest else 999.0

        net_debt = total_debt - cash

        if de_ratio < 0.3 and net_debt < 0:      # net cash position
            balance_signal = "bullish"
        elif de_ratio > 1.5 or interest_coverage < 2.0:
            balance_signal = "cautious"
        else:
            balance_signal = "neutral"
    except Exception as e:
        print(f"[Fundamental] Pillar 4 error: {e}")

    # ── Overall signal: majority vote across 4 pillars ────────────────────────
    all_signals = [valuation_signal, growth_signal, multiples_signal, balance_signal]
    counts: dict[str, int] = {}
    for s in all_signals:
        counts[s] = counts.get(s, 0) + 1

    max_count = max(counts.values())
    majority_candidates = [s for s, c in counts.items() if c == max_count]

    # Tie-break: prefer "neutral" for safety
    if len(majority_candidates) == 1:
        overall_signal = majority_candidates[0]
    elif "neutral" in majority_candidates:
        overall_signal = "neutral"
    else:
        overall_signal = majority_candidates[0]

    data_quality = data_points_available / data_points_total

    return {
        "valuation_signal": valuation_signal,
        "growth_signal": growth_signal,
        "multiples_signal": multiples_signal,
        "balance_signal": balance_signal,
        "overall_signal": overall_signal,
        "upside_pct": valuation.get("upside_pct", 0.0),
        "fcf_cagr": valuation.get("fcf_cagr", 0.0),
        "fcf_margin": round(fcf_margin * 100, 1),
        "de_ratio": round(de_ratio, 2),
        "pe_vs_sector": pe_vs_sector,
        "revenue_cagr": round(revenue_cagr * 100, 1),
        "data_quality": round(data_quality, 2),
    }


# ---------------------------------------------------------------------------
# Section 4 — LLM reasoning
# ---------------------------------------------------------------------------

def _build_peer_context(state: ThesisState) -> str:
    """
    Reads what other agents have already written to the whiteboard.
    Prioritises raw_outputs (full findings) over agent_signals (structured only).
    Returns formatted string to inject into the LLM prompt.
    """
    raw_outputs = state.get("raw_outputs", {})
    agent_signals = state.get("agent_signals", {})

    if not raw_outputs and not agent_signals:
        return ""

    lines = []

    # First pass — agents with full raw findings (richest context)
    for agent_name, findings_text in raw_outputs.items():
        if agent_name == "fundamental":
            continue
        lines.append(f"[{agent_name.upper()} — full findings]\n{findings_text}\n")

    # Second pass — agents with only structured signals (no raw yet)
    for agent_name, signal in agent_signals.items():
        if agent_name == "fundamental":
            continue
        if agent_name in raw_outputs:
            continue  # already included above
        lines.append(
            f"[{agent_name.upper()} — signal only] "
            f"{signal['view']} ({signal['confidence']:.0%}) — {signal['reasoning']}"
        )

    if not lines:
        return ""

    return (
        "Other analysts have already written their findings on the whiteboard:\n\n"
        + "\n".join(lines)
        + "\nUse this context to calibrate your confidence. "
        "If peers with high-confidence findings contradict your pillars, "
        "revise your confidence downward and consider 'cautious'. "
        "If peers strongly corroborate your analysis, revise upward."
    )


def run_llm_reasoning(
    ticker: str,
    pillar_scores: dict,
    conflicts: list,
    state: ThesisState,
) -> AgentSignal:
    """
    Single Haiku call to reason over pillar results and produce AgentSignal.
    Falls back to pillar majority on any error.
    """
    # Build conflict context
    conflict_context = ""
    if conflicts:
        desc_list = [c.get("description", "") for c in conflicts if "fundamental" in c.get("agents", [])]
        if desc_list:
            conflict_context = (
                "\nThe investment committee has flagged these conflicts from other analysts:\n"
                + "\n".join(f"- {d}" for d in desc_list)
                + "\nFactor this into your confidence — revise downward if it introduces genuine uncertainty."
            )

    peer_context = _build_peer_context(state)

    prompt = f"""You are a fundamental analyst at a hedge fund investment committee.
You have completed a 4-pillar fundamental analysis of {ticker}.
Your job is to give a structured investment signal.

Pillar results:
- Intrinsic value:             {pillar_scores['valuation_signal']} (upside: {pillar_scores['upside_pct']:.1f}%)
- Earnings quality & growth:   {pillar_scores['growth_signal']} (FCF CAGR: {pillar_scores['fcf_cagr']:.1f}%, FCF margin: {pillar_scores['fcf_margin']:.1f}%)
- Valuation multiples:         {pillar_scores['multiples_signal']} (P/E vs sector: {pillar_scores['pe_vs_sector']})
- Balance sheet quality:       {pillar_scores['balance_signal']} (D/E ratio: {pillar_scores['de_ratio']:.2f})

Data quality: {pillar_scores['data_quality']:.0%} of expected data was available.
{peer_context}
{conflict_context}

Respond with ONLY a JSON object — no preamble, no markdown:
{{
  "view": "bullish" | "bearish" | "neutral" | "cautious",
  "reasoning": "one sentence with specific numbers",
  "confidence": 0.0 to 1.0
}}

Confidence calibration:
- 3 or 4 pillars agree AND data quality > 80%  → 0.75–0.90
- 2 pillars agree OR data quality 50–80%        → 0.55–0.74
- Pillars conflict OR data quality < 50%        → 0.35–0.54
- Use "cautious" when signals conflict but downside risk is skewed negative"""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Strip markdown fences if present
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
            "reasoning": str(parsed.get("reasoning", "Fundamental analysis complete.")),
            "confidence": confidence,
        }

    except Exception as e:
        print(f"[Fundamental] run_llm_reasoning failed: {e}")
        return {
            "view": pillar_scores["overall_signal"],
            "reasoning": f"LLM parse failed — pillar majority: {pillar_scores['overall_signal']}",
            "confidence": 0.45,
        }


# ---------------------------------------------------------------------------
# Section 5 — Level 3: Agent-to-agent Q&A helpers
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
# Section 6 — Main entry point
# ---------------------------------------------------------------------------

def run_fundamental_agent(state: ThesisState) -> dict:
    """
    Main entry point called by arena/agents.py.
    Fetches data, runs 4-pillar analysis, returns AgentSignal.
    Always returns — never crashes the arena.
    """
    ticker = state.get("ticker", "")
    conflicts = state.get("conflicts", [])

    print(f"[Fundamental] Starting analysis for {ticker}")

    from arena.progress import emit_arena_event as _emit
    _emit({"type": "arena_agent_start", "agent": "fundamental", "round": state.get("round", 0) + 1})

    try:
        financials = fetch_financials(ticker)
        market_context = fetch_market_context(ticker)
        valuation = calculate_intrinsic_value(financials, market_context)
        pillar_scores = score_pillars(financials, market_context, valuation)

        print(
            f"[Fundamental] Pillars: valuation={pillar_scores['valuation_signal']} "
            f"growth={pillar_scores['growth_signal']} "
            f"multiples={pillar_scores['multiples_signal']} "
            f"balance={pillar_scores['balance_signal']} "
            f"→ overall={pillar_scores['overall_signal']} "
            f"data_quality={pillar_scores['data_quality']:.0%}"
        )

        signal: AgentSignal = run_llm_reasoning(ticker, pillar_scores, conflicts, state)

        # Level 3: Q&A
        incoming_questions = _read_questions("fundamental", state)
        updated_questions = _generate_question("fundamental", pillar_scores, signal, state)
        updated_answers = _extract_answers("fundamental", incoming_questions, signal, pillar_scores, state)

        raw_findings = (
            f"FUNDAMENTAL ANALYSIS — {ticker}\n"
            f"Intrinsic value upside: {pillar_scores.get('upside_pct', 0):.1f}% | "
            f"WACC: {valuation.get('wacc', 0):.1f}%\n"
            f"FCF CAGR: {pillar_scores.get('fcf_cagr', 0):.1f}% | "
            f"FCF margin: {pillar_scores.get('fcf_margin', 0):.1f}%\n"
            f"P/E vs sector: {pillar_scores.get('pe_vs_sector', 'N/A')}\n"
            f"D/E ratio: {pillar_scores.get('de_ratio', 0):.2f}\n"
            f"Pillar signals: Valuation={pillar_scores.get('valuation_signal')} | "
            f"Growth={pillar_scores.get('growth_signal')} | "
            f"Multiples={pillar_scores.get('multiples_signal')} | "
            f"Balance={pillar_scores.get('balance_signal')}\n"
            f"Final view: {signal['view']} ({signal['confidence']:.0%} confidence)\n"
            f"Reasoning: {signal['reasoning']}"
        )

        if incoming_questions:
            qa_lines = ["\nQUESTIONS ANSWERED:"]
            my_answers = updated_answers.get("fundamental", {})
            for asker, q in incoming_questions.items():
                qa_lines.append(f"  [{asker.upper()} asked]: {q}")
                qa_lines.append(f"  [Answer]: {my_answers.get(asker, 'No answer generated.')}")
            raw_findings += "\n".join(qa_lines)

        if "fundamental" in updated_questions:
            tgt = list(updated_questions["fundamental"].keys())[0]
            q_text = updated_questions["fundamental"][tgt]
            raw_findings += f"\nOPEN QUESTION TO {tgt.upper()}: {q_text}"
            from arena.progress import emit_arena_event as _emit_q
            _emit_q({"type": "arena_question", "from_agent": "fundamental", "to_agent": tgt, "question": q_text})

        if incoming_questions:
            my_answers = updated_answers.get("fundamental", {})
            from arena.progress import emit_arena_event as _emit_a
            for asker, q in incoming_questions.items():
                ans = my_answers.get(asker, "")
                if ans:
                    _emit_a({"type": "arena_answer", "from_agent": "fundamental", "to_agent": asker, "question": q, "answer": ans})

    except Exception as e:
        print(f"[Fundamental] Unhandled error for {ticker}: {e}")
        signal = {
            "view": "neutral",
            "reasoning": f"Analysis incomplete — data error: {str(e)[:80]}",
            "confidence": 0.30,
        }
        raw_findings = f"FUNDAMENTAL ANALYSIS — {ticker}\nError: {str(e)[:120]}"
        updated_questions = dict(state.get("agent_questions", {}))
        updated_answers = dict(state.get("agent_answers", {}))

    print(f"[Fundamental] Signal: view={signal['view']} confidence={signal['confidence']}")

    from arena.progress import emit_arena_event
    emit_arena_event({
        "type": "arena_agent_done",
        "agent": "fundamental",
        "view": signal["view"],
        "confidence": signal["confidence"],
        "reasoning": signal["reasoning"],
    })

    # Merge into existing raw_outputs — do not overwrite other agents' findings
    existing_raw = dict(state.get("raw_outputs", {}))
    existing_raw["fundamental"] = raw_findings

    return {
        "agent_signals":   {"fundamental": signal},
        "raw_outputs":     existing_raw,
        "agent_questions": updated_questions,
        "agent_answers":   updated_answers,
    }
