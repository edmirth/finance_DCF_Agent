"""
Arena Fundamental Analyst Agent

Purpose-built fundamental analyst for the Finance Agent Arena.
Fetches real financial data, runs a 4-pillar analysis, and returns
a structured AgentSignal into the arena ThesisState whiteboard.

Pillars:
  1. EV/EBITDA Multiples Valuation (vs. sector median)
  2. Earnings Quality & Growth
  3. P/E Relative Valuation (vs. sector)
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

logger = logging.getLogger(__name__)

VALID_VIEWS = {"bullish", "bearish", "neutral", "cautious"}
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Level 3: the agent this one questions when uncertain
QUESTION_TARGET = "risk"


# ---------------------------------------------------------------------------
# Section 1 — Data helpers (read from shared_data, no live fetching)
# ---------------------------------------------------------------------------

def _financials_from_shared(ticker: str, shared_data: dict) -> dict:
    """Build the financials dict from pre-fetched shared_data."""
    result: dict = {"ticker": ticker, "_data_points_fetched": 0}

    stock_info = shared_data.get("stock_info", {})
    if stock_info:
        result.update(stock_info)
        result["_data_points_fetched"] += 1

    stmts = shared_data.get("financial_statements", {})
    if stmts:
        result["income_statements"]    = stmts.get("income_statements", [])
        result["balance_sheets"]       = stmts.get("balance_sheets", [])
        result["cash_flow_statements"] = stmts.get("cash_flow_statements", [])
        result["_data_points_fetched"] += 1

    metrics = shared_data.get("key_metrics", {})
    if metrics:
        result["key_metrics"] = metrics
        result["_data_points_fetched"] += 1

    return result


def _market_context_from_shared(ticker: str, shared_data: dict) -> dict:
    """
    Extract structured market context from pre-fetched Tavily texts.
    Haiku extraction logic is identical to the old fetch_market_context —
    only the data source changes (shared texts vs. live Tavily searches).
    """
    defaults = {
        "current_price": None,
        "beta": 1.0,
        "sector_pe": 20.0,
        "sector_ev_ebitda": 12.0,
        "analyst_consensus": "neutral",
        "news_sentiment": "neutral",
        "company_context": "",
    }

    raw_content = shared_data.get("multiples_search_text", "")[:2000]
    company_context = shared_data.get("company_context_text", "")[:1500]

    if not raw_content.strip():
        return {**defaults, "company_context": company_context}

    try:
        client = Anthropic()
        extraction_prompt = (
            f"Extract from these search results for {ticker}:\n"
            f"current_price, beta, sector_pe (sector average P/E), "
            f"sector_ev_ebitda (sector average EV/EBITDA multiple), "
            f"analyst_consensus (buy/hold/sell), news_sentiment (positive/neutral/negative).\n"
            f"Respond ONLY with a JSON object with those 6 fields. Use null if not found.\n\n"
            f"Search results:\n{raw_content}"
        )
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": extraction_prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        return {
            "current_price":    parsed.get("current_price"),
            "beta":             float(parsed.get("beta") or 1.0),
            "sector_pe":        float(parsed.get("sector_pe") or 20.0),
            "sector_ev_ebitda": float(parsed.get("sector_ev_ebitda") or 12.0),
            "analyst_consensus": str(parsed.get("analyst_consensus") or "neutral").lower(),
            "news_sentiment":   str(parsed.get("news_sentiment") or "neutral").lower(),
            "company_context":  company_context,
        }

    except Exception as e:
        print(f"[Fundamental] _market_context_from_shared failed for {ticker}: {e}")
        return {**defaults, "company_context": company_context}


# ---------------------------------------------------------------------------
# Section 2 — EV/EBITDA Multiples Valuation (Pillar 1)
# ---------------------------------------------------------------------------

def calculate_multiples_valuation(financials: dict, market_context: dict) -> dict:
    """
    EV/EBITDA multiples-based valuation.
    Compares company EV/EBITDA to sector median and derives implied upside/downside.
    Returns valuation_signal, upside_pct, implied_price, ev_ebitda, sector_ev_ebitda.
    """
    fallback = {
        "implied_price": None,
        "current_price": None,
        "upside_pct": 0.0,
        "valuation_signal": "neutral",
        "ev_ebitda": None,
        "sector_ev_ebitda": 12.0,
    }

    try:
        metrics = financials.get("key_metrics", {})
        income_stmts = financials.get("income_statements", [])
        balance_sheets = financials.get("balance_sheets", [])

        if not income_stmts:
            return fallback

        latest_inc = income_stmts[0]

        # EBITDA = operating income + D&A (estimate D&A as 15% of operating income if unavailable)
        ebit = float(latest_inc.get("operating_income") or latest_inc.get("ebit") or 0)
        da = float(latest_inc.get("depreciation_and_amortization") or
                   latest_inc.get("depreciation") or 0)
        if da == 0:
            da = abs(ebit) * 0.15
        ebitda = ebit + da

        if ebitda <= 0:
            return fallback

        # Net debt
        latest_bs = (balance_sheets or [{}])[0]
        total_debt = float(latest_bs.get("total_debt") or latest_bs.get("long_term_debt") or 0)
        cash = float(latest_bs.get("cash_and_cash_equivalents") or
                     latest_bs.get("cash_and_short_term_investments") or 0)
        net_debt = total_debt - cash

        # Current EV/EBITDA
        market_cap = float(financials.get("market_cap") or 0)
        if market_cap <= 0:
            return fallback
        current_ev = market_cap + net_debt
        company_ev_ebitda = current_ev / ebitda

        # Sector EV/EBITDA median from market context (default 12x)
        sector_ev_ebitda = float(market_context.get("sector_ev_ebitda") or 12.0)

        # Implied price from sector multiple
        implied_ev = ebitda * sector_ev_ebitda
        implied_equity_value = implied_ev - net_debt
        shares = float(metrics.get("shares_outstanding") or
                       financials.get("weighted_average_shares") or 1)
        implied_price = implied_equity_value / shares if shares > 0 else None

        current_price = float(
            market_context.get("current_price") or financials.get("current_price") or 0
        )

        if implied_price and current_price > 0:
            upside_pct = ((implied_price - current_price) / current_price) * 100
        else:
            upside_pct = 0.0

        # Signal
        if upside_pct > 15:
            valuation_signal = "bullish"
        elif upside_pct < -10:
            valuation_signal = "bearish"
        else:
            valuation_signal = "neutral"

        return {
            "implied_price": round(implied_price, 2) if implied_price else None,
            "current_price": round(current_price, 2) if current_price else None,
            "upside_pct": round(upside_pct, 1),
            "valuation_signal": valuation_signal,
            "ev_ebitda": round(company_ev_ebitda, 1),
            "sector_ev_ebitda": round(sector_ev_ebitda, 1),
        }

    except Exception as e:
        print(f"[Fundamental] calculate_multiples_valuation error: {e}")
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

    # ── Pillar 1: EV/EBITDA Multiples Valuation ──────────────────────────────
    valuation_signal = valuation.get("valuation_signal", "neutral")
    if valuation.get("ev_ebitda") is not None:
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
            op = cf_latest.get("net_cash_flow_from_operations") or cf_latest.get("operating_cash_flow") or 0
            capex = abs(cf_latest.get("capital_expenditure") or cf_latest.get("capital_expenditures") or 0)
            fcf = float(op) - float(capex)
        fcf = float(fcf)
        if latest_revenue > 0:
            fcf_margin = fcf / latest_revenue
            data_points_available += 1

        # Quality: FCF > net income is good
        latest_ni = metrics.get("latest_net_income") or 0
        fcf_quality = fcf > float(latest_ni) * 0.8 if latest_ni else True

        if revenue_cagr > 0.12 and fcf_quality:
            growth_signal = "bullish"
        elif revenue_cagr < -0.05 or (fcf_margin < 0 and latest_revenue > 0):
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
        "ev_ebitda": valuation.get("ev_ebitda"),
        "sector_ev_ebitda": valuation.get("sector_ev_ebitda", 12.0),
        "fcf_margin": round(fcf_margin * 100, 1),
        "de_ratio": round(de_ratio, 2),
        "pe_vs_sector": pe_vs_sector,
        "revenue_cagr": round(revenue_cagr * 100, 1),
        "data_quality": round(data_quality, 2),
    }


# ---------------------------------------------------------------------------
# Section 3b — Data-CoT: reason about what the data actually means
# ---------------------------------------------------------------------------

def run_data_cot(
    ticker: str,
    financials: dict,
    market_context: dict,
    pillar_scores: dict,
) -> str:
    """
    Step 1 of 3 in the CoT pipeline.
    Haiku thinks step-by-step through the raw numbers before any framework is applied.
    Output feeds directly into run_concept_cot() as grounded observations.
    Never raises — falls back to a compact metrics string.
    """
    ev_ebitda = pillar_scores.get("ev_ebitda")
    sector_ev_ebitda = pillar_scores.get("sector_ev_ebitda", 12.0)
    premium_pct = (
        round((ev_ebitda / sector_ev_ebitda - 1) * 100, 1)
        if ev_ebitda and sector_ev_ebitda
        else None
    )

    data_snapshot = (
        f"Ticker: {ticker} | Sector: {financials.get('sector', 'Unknown')}\n"
        f"EV/EBITDA: {ev_ebitda}x vs sector {sector_ev_ebitda}x "
        f"({'premium' if premium_pct and premium_pct > 0 else 'discount'}: "
        f"{abs(premium_pct) if premium_pct is not None else 'N/A'}%)\n"
        f"Implied upside from sector multiple: {pillar_scores.get('upside_pct', 0):.1f}%\n"
        f"Revenue CAGR (3yr): {pillar_scores.get('revenue_cagr', 0):.1f}%\n"
        f"FCF margin: {pillar_scores.get('fcf_margin', 0):.1f}%\n"
        f"D/E ratio: {pillar_scores.get('de_ratio', 0):.2f}\n"
        f"P/E vs sector: {pillar_scores.get('pe_vs_sector', 'N/A')}\n"
        f"Analyst consensus: {market_context.get('analyst_consensus', 'N/A')}\n"
        f"Pillar votes: Valuation={pillar_scores.get('valuation_signal')} | "
        f"Growth={pillar_scores.get('growth_signal')} | "
        f"Multiples={pillar_scores.get('multiples_signal')} | "
        f"Balance={pillar_scores.get('balance_signal')}\n"
        f"Recent context: {market_context.get('company_context', 'N/A')}"
    )

    prompt = (
        f"You are a fundamental analyst looking at {ticker} for the first time.\n\n"
        f"Raw financial data:\n{data_snapshot}\n\n"
        f"Think step by step through this data:\n"
        f"1. What are the 2-3 most important signals here? Why does each matter?\n"
        f"2. What data is missing or uncertain — where are you flying blind?\n"
        f"3. What would a bull say about this data? What would a bear say?\n\n"
        f"Write your observations in 150-200 words. Use specific numbers. "
        f"Do not give a final verdict yet — just analyze what the data is telling you."
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
        print(f"[Fundamental] run_data_cot failed: {e}")
        ev_str = f"{ev_ebitda}x vs sector {sector_ev_ebitda}x" if ev_ebitda else "N/A"
        return (
            f"EV/EBITDA: {ev_str} (implied upside: {pillar_scores.get('upside_pct', 0):.1f}%). "
            f"Revenue CAGR: {pillar_scores.get('revenue_cagr', 0):.1f}%. "
            f"FCF margin: {pillar_scores.get('fcf_margin', 0):.1f}%. "
            f"D/E: {pillar_scores.get('de_ratio', 0):.2f}."
        )


# ---------------------------------------------------------------------------
# Section 4 — Concept-CoT + Signal (LLM reasoning)
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
        "If peers corroborate your analysis, revise your confidence upward. "
        "If peers contradict your pillars with strong evidence, note the tension but only revise downward "
        "if the contradiction is material — not just because views differ."
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
    Receives data_cot_text and applies the fundamental valuation framework to it.
    Returns (concept_analysis_text, AgentSignal) — the prose becomes part of raw_findings.
    Falls back to pillar majority signal on any error.
    """
    conflict_context = ""
    if conflicts:
        desc_list = [c.get("description", "") for c in conflicts if "fundamental" in c.get("agents", [])]
        if desc_list:
            conflict_context = (
                "\nCommittee conflicts flagged:\n"
                + "\n".join(f"- {d}" for d in desc_list)
                + "\nRevise confidence downward if the conflict introduces genuine uncertainty."
            )

    peer_context = _build_peer_context(state)

    prompt = f"""You are a fundamental analyst at a hedge fund investment committee presenting on {ticker}.

DATA OBSERVATIONS (from your step-1 analysis):
{data_cot_text}

Pillar results:
- EV/EBITDA valuation:       {pillar_scores['valuation_signal']} (implied upside: {pillar_scores['upside_pct']:.1f}%, {pillar_scores['ev_ebitda']}x vs sector {pillar_scores['sector_ev_ebitda']}x)
- Earnings quality & growth: {pillar_scores['growth_signal']} (Revenue CAGR: {pillar_scores['revenue_cagr']:.1f}%, FCF margin: {pillar_scores['fcf_margin']:.1f}%)
- Valuation multiples:       {pillar_scores['multiples_signal']} (P/E vs sector: {pillar_scores['pe_vs_sector']})
- Balance sheet quality:     {pillar_scores['balance_signal']} (D/E ratio: {pillar_scores['de_ratio']:.2f})

Data quality: {pillar_scores['data_quality']:.0%}
{peer_context}
{conflict_context}

Now apply your fundamental framework to these observations:
- Is the valuation premium/discount justified by the growth and FCF quality profile?
- Does the balance sheet support the investment case or introduce asymmetric downside?
- What is the single most important conclusion that should drive the investment decision?
- What one condition would materially change your view?

Respond in exactly this format (SIGNAL first, then ANALYSIS):

SIGNAL:
{{"view": "bullish"|"bearish"|"neutral"|"cautious", "reasoning": "one sentence with the key number driving the view", "confidence": 0.0-1.0}}

ANALYSIS: [2-3 sentences applying your framework to the data above. Reference specific numbers.]

Confidence calibration:
- 3-4 pillars agree AND data quality >80%  → 0.75–0.90
- 2 pillars agree OR data quality 50–80%   → 0.55–0.74
- Pillars conflict OR data quality <50%    → 0.35–0.54
- Use "cautious" only for specific material downside risk, not general uncertainty"""

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

        # SIGNAL comes first — extract it before ANALYSIS (truncation-safe)
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

        # Parse signal JSON
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
                confidence = float(parsed.get("confidence", 0.5))
                confidence = round(min(max(confidence, 0.0), 1.0), 2)
                signal = {
                    "view": view,
                    "reasoning": str(parsed.get("reasoning", "Fundamental analysis complete.")),
                    "confidence": confidence,
                }
            except (json.JSONDecodeError, ValueError):
                print(f"[Fundamental] run_concept_cot: signal JSON parse failed, using pillar majority")

        return analysis_text, signal

    except Exception as e:
        print(f"[Fundamental] run_concept_cot failed: {e}")
        return "", fallback_signal


# Keep backward-compatible alias
def run_llm_reasoning(
    ticker: str,
    pillar_scores: dict,
    conflicts: list,
    state: ThesisState,
    data_cot_text: str = "",
) -> AgentSignal:
    """Backward-compatible wrapper — returns only AgentSignal (drops concept prose)."""
    _, signal = run_concept_cot(ticker, pillar_scores, conflicts, state, data_cot_text)
    return signal


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
        shared_data = state.get("shared_data", {})
        financials = _financials_from_shared(ticker, shared_data)
        market_context = _market_context_from_shared(ticker, shared_data)
        valuation = calculate_multiples_valuation(financials, market_context)
        pillar_scores = score_pillars(financials, market_context, valuation)

        print(
            f"[Fundamental] Pillars: valuation={pillar_scores['valuation_signal']} "
            f"growth={pillar_scores['growth_signal']} "
            f"multiples={pillar_scores['multiples_signal']} "
            f"balance={pillar_scores['balance_signal']} "
            f"→ overall={pillar_scores['overall_signal']} "
            f"data_quality={pillar_scores['data_quality']:.0%}"
        )

        # Stage 1 — Data-CoT: reason about what the data means
        data_cot_text = run_data_cot(ticker, financials, market_context, pillar_scores)

        # Stage 2 — Concept-CoT: apply valuation framework, produce signal
        concept_text, signal = run_concept_cot(ticker, pillar_scores, conflicts, state, data_cot_text)

        # Level 3: Q&A
        incoming_questions = _read_questions("fundamental", state)
        updated_questions = _generate_question("fundamental", pillar_scores, signal, state)
        updated_answers = _extract_answers("fundamental", incoming_questions, signal, pillar_scores, state)

        # Build explicit price target line for memo extraction — grounded in computed numbers
        implied_price = valuation.get("implied_price")
        current_price_val = valuation.get("current_price")
        price_target_line = ""
        if implied_price and current_price_val:
            upside = pillar_scores.get("upside_pct", 0)
            bear_price = round(implied_price * 0.75, 2)
            bull_price = round(implied_price * 1.20, 2)
            price_target_line = (
                f"\nPRICE TARGETS (EV/EBITDA implied): "
                f"bear=${bear_price} | base=${implied_price} | bull=${bull_price} "
                f"(current=${current_price_val}, implied upside={upside:+.1f}%)"
            )

        # Rich findings: full CoT chain for peer agents to reason from
        raw_findings = (
            f"FUNDAMENTAL ANALYSIS — {ticker}\n\n"
            f"DATA OBSERVATIONS:\n{data_cot_text}\n\n"
            f"FRAMEWORK APPLICATION:\n{concept_text}\n\n"
            f"SIGNAL: {signal['view'].upper()} ({signal['confidence']:.0%} confidence)\n"
            f"REASONING: {signal['reasoning']}\n\n"
            f"METRICS: EV/EBITDA={pillar_scores.get('ev_ebitda')}x vs {pillar_scores.get('sector_ev_ebitda')}x sector | "
            f"Upside={pillar_scores.get('upside_pct', 0):.1f}% | FCF={pillar_scores.get('fcf_margin', 0):.1f}% | "
            f"RevCAGR={pillar_scores.get('revenue_cagr', 0):.1f}% | D/E={pillar_scores.get('de_ratio', 0):.2f} | "
            f"P/E vs sector={pillar_scores.get('pe_vs_sector', 'N/A')}"
            f"{price_target_line}"
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
