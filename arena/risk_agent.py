"""
Arena Risk Analyst Agent

Purpose-built risk analyst for the Finance Agent Arena.
Fetches real financial data, runs a 4-pillar risk analysis, and returns
a structured AgentSignal into the arena ThesisState whiteboard.

Pillars:
  1. Leverage Risk      (D/E ratio, interest coverage)
  2. Liquidity Risk     (current ratio, FCF trend)
  3. Earnings Stability (earnings volatility, loss years)
  4. Market/Systematic  (beta, drawdown from 52-week high)

Uses claude-haiku-4-5-20251001 for ALL LLM calls.
Never crashes the arena — all errors produce a fallback neutral signal.
"""
from __future__ import annotations

import json
import logging
import statistics
from typing import Optional

from anthropic import Anthropic

from arena.state import AgentSignal, ThesisState

logger = logging.getLogger(__name__)

VALID_VIEWS = {"bullish", "bearish", "neutral", "cautious"}
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Level 3: the agent this one questions when uncertain
QUESTION_TARGET = "fundamental"


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
    Extract beta, 52w high/low, current price, analyst downside target from
    pre-fetched multiples_search_text. Haiku extraction logic unchanged.
    """
    defaults = {
        "beta": 1.0,
        "week_52_high": None,
        "week_52_low": None,
        "current_price": None,
        "analyst_downside_target": None,
    }

    raw_content = shared_data.get("multiples_search_text", "")[:2000]
    if not raw_content.strip():
        return defaults

    try:
        client = Anthropic()
        extraction_prompt = (
            f"Extract from these search results for {ticker}:\n"
            f"beta, week_52_high (52-week high price), week_52_low (52-week low price), "
            f"current_price, analyst_downside_target (lowest analyst price target).\n"
            f"Respond ONLY with a JSON object with those 5 fields. Use null if not found.\n\n"
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
            "beta":                   float(parsed.get("beta") or 1.0),
            "week_52_high":           float(parsed["week_52_high"]) if parsed.get("week_52_high") else None,
            "week_52_low":            float(parsed["week_52_low"]) if parsed.get("week_52_low") else None,
            "current_price":          float(parsed["current_price"]) if parsed.get("current_price") else None,
            "analyst_downside_target": float(parsed["analyst_downside_target"]) if parsed.get("analyst_downside_target") else None,
        }

    except Exception as e:
        print(f"[Risk] _market_context_from_shared failed for {ticker}: {e}")
        return defaults


# ---------------------------------------------------------------------------
# Section 2 — Risk metrics calculation
# ---------------------------------------------------------------------------

def calculate_risk_metrics(financials: dict, market_context: dict) -> dict:
    """
    Compute the core risk metrics across all 4 pillars.
    Returns a flat dict of numbers — never raises.
    """
    metrics = financials.get("key_metrics", {})
    income_stmts = financials.get("income_statements", [])
    balance_sheets = financials.get("balance_sheets", [])
    cf_statements = financials.get("cash_flow_statements", [])
    latest_bs = balance_sheets[0] if balance_sheets else {}

    result = {
        "de_ratio": 0.0,
        "interest_coverage": 999.0,
        "current_ratio": 1.0,
        "fcf_trend": "unknown",
        "earnings_volatility": 0.0,
        "beta": float(market_context.get("beta") or 1.0),
        "drawdown_from_high_pct": 0.0,
    }

    # ── Leverage: D/E and interest coverage ──────────────────────────────────
    try:
        total_debt = float(latest_bs.get("total_debt") or
                           latest_bs.get("long_term_debt") or 0)
        equity = float(latest_bs.get("shareholders_equity") or
                       latest_bs.get("total_stockholders_equity") or 1)
        if equity > 0:
            result["de_ratio"] = round(total_debt / equity, 2)

        ebit = float(metrics.get("latest_ebit") or 0)
        interest = float(metrics.get("latest_interest_expense") or 0)
        if interest and abs(interest) > 0:
            result["interest_coverage"] = round(ebit / abs(interest), 1)
    except Exception as e:
        print(f"[Risk] leverage metrics error: {e}")

    # ── Liquidity: current ratio and FCF trend ───────────────────────────────
    try:
        current_assets = float(latest_bs.get("total_current_assets") or
                               latest_bs.get("current_assets") or 0)
        current_liabilities = float(latest_bs.get("total_current_liabilities") or
                                    latest_bs.get("current_liabilities") or 1)
        if current_liabilities > 0:
            result["current_ratio"] = round(current_assets / current_liabilities, 2)

        # FCF trend: positive if last 2 years both positive
        fcf_vals = []
        for cf in cf_statements[:3]:
            fcf = cf.get("free_cash_flow") or 0
            if not fcf:
                op = cf.get("net_cash_flow_from_operations") or cf.get("operating_cash_flow") or 0
                capex = abs(cf.get("capital_expenditure") or cf.get("capital_expenditures") or 0)
                fcf = float(op) - float(capex)
            fcf_vals.append(float(fcf))

        if len(fcf_vals) >= 2:
            if all(v > 0 for v in fcf_vals[:2]):
                result["fcf_trend"] = "positive"
            elif all(v < 0 for v in fcf_vals[:2]):
                result["fcf_trend"] = "negative"
            else:
                result["fcf_trend"] = "mixed"
        elif fcf_vals:
            result["fcf_trend"] = "positive" if fcf_vals[0] > 0 else "negative"
    except Exception as e:
        print(f"[Risk] liquidity metrics error: {e}")

    # ── Earnings stability: volatility and loss years ────────────────────────
    try:
        net_incomes = []
        for stmt in income_stmts[:5]:
            ni = stmt.get("net_income") or stmt.get("netIncome")
            if ni is not None:
                net_incomes.append(float(ni))

        if len(net_incomes) >= 3:
            mean_ni = statistics.mean(net_incomes)
            stdev_ni = statistics.stdev(net_incomes)
            if mean_ni != 0:
                result["earnings_volatility"] = round(abs(stdev_ni / mean_ni), 2)
        elif len(net_incomes) == 2:
            # Simple relative change as proxy
            if net_incomes[1] != 0:
                result["earnings_volatility"] = round(
                    abs(net_incomes[0] - net_incomes[1]) / abs(net_incomes[1]), 2
                )
    except Exception as e:
        print(f"[Risk] stability metrics error: {e}")

    # ── Market risk: beta and drawdown from 52-week high ─────────────────────
    try:
        week_52_high = market_context.get("week_52_high")
        current_price = (
            market_context.get("current_price")
            or financials.get("current_price")
        )
        if week_52_high and current_price:
            high = float(week_52_high)
            price = float(current_price)
            if high > 0:
                result["drawdown_from_high_pct"] = round(
                    ((price - high) / high) * 100, 1
                )
    except Exception as e:
        print(f"[Risk] market risk metrics error: {e}")

    return result


# ---------------------------------------------------------------------------
# Section 3 — Pillar scoring
# ---------------------------------------------------------------------------

def score_pillars(financials: dict, market_context: dict, risk_metrics: dict) -> dict:
    """
    Evaluate all 4 risk pillars and compute overall_signal + data_quality.
    """
    income_stmts = financials.get("income_statements", [])
    data_points_available = 0
    data_points_total = 8

    # ── Pillar 1: Leverage Risk ───────────────────────────────────────────────
    leverage_signal = "neutral"
    de_ratio = risk_metrics["de_ratio"]
    interest_coverage = risk_metrics["interest_coverage"]

    if de_ratio > 0 or interest_coverage < 999.0:
        data_points_available += 1

    if de_ratio > 1.5 or interest_coverage < 2.0:
        leverage_signal = "cautious"
    elif de_ratio < 0.5 and interest_coverage > 5.0:
        leverage_signal = "bullish"
    else:
        leverage_signal = "neutral"

    # ── Pillar 2: Liquidity Risk ──────────────────────────────────────────────
    liquidity_signal = "neutral"
    current_ratio = risk_metrics["current_ratio"]
    fcf_trend = risk_metrics["fcf_trend"]

    if current_ratio != 1.0 or fcf_trend != "unknown":
        data_points_available += 1

    if current_ratio < 1.0 or fcf_trend == "negative":
        liquidity_signal = "bearish"
    elif current_ratio > 2.0 and fcf_trend == "positive":
        liquidity_signal = "bullish"
    elif fcf_trend == "negative":
        liquidity_signal = "cautious"
    else:
        liquidity_signal = "neutral"

    # ── Pillar 3: Earnings Stability ─────────────────────────────────────────
    stability_signal = "neutral"
    earnings_volatility = risk_metrics["earnings_volatility"]

    # Check for loss years in last 3
    loss_years = 0
    try:
        for stmt in income_stmts[:3]:
            ni = stmt.get("net_income") or stmt.get("netIncome") or 0
            if float(ni) < 0:
                loss_years += 1
        data_points_available += 1
    except Exception:
        pass

    if earnings_volatility > 0.50 or loss_years >= 2:
        stability_signal = "cautious"
    elif earnings_volatility < 0.15 and loss_years == 0:
        stability_signal = "bullish"
    else:
        stability_signal = "neutral"

    # ── Pillar 4: Market / Systematic Risk ───────────────────────────────────
    market_signal = "neutral"
    beta = risk_metrics["beta"]
    drawdown_pct = risk_metrics["drawdown_from_high_pct"]

    if beta != 1.0 or drawdown_pct != 0.0:
        data_points_available += 1

    if beta > 1.8:
        market_signal = "cautious"
    elif beta < 0.8:
        market_signal = "bullish"
    else:
        market_signal = "neutral"

    # Drawdown modifier: near 52-week low is a risk flag (unless fundamentals bullish)
    if drawdown_pct < -25:
        # Significant drawdown — cautious unless already bearish
        if market_signal == "bullish":
            market_signal = "neutral"
        elif market_signal == "neutral":
            market_signal = "cautious"

    # ── Overall signal: majority vote ────────────────────────────────────────
    all_signals = [leverage_signal, liquidity_signal, stability_signal, market_signal]
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
        "leverage_signal":    leverage_signal,
        "liquidity_signal":   liquidity_signal,
        "stability_signal":   stability_signal,
        "market_signal":      market_signal,
        "overall_signal":     overall_signal,
        "de_ratio":           de_ratio,
        "interest_coverage":  interest_coverage,
        "current_ratio":      current_ratio,
        "fcf_trend":          fcf_trend,
        "earnings_volatility": earnings_volatility,
        "beta":               beta,
        "drawdown_from_high_pct": drawdown_pct,
        "loss_years":         loss_years,
        "data_quality":       data_quality,
    }


# ---------------------------------------------------------------------------
# Section 3b — Data-CoT: reason about what the risk data actually means
# ---------------------------------------------------------------------------

def run_data_cot(
    ticker: str,
    financials: dict,
    market_context: dict,
    pillar_scores: dict,
) -> str:
    """
    Step 1 of 3 in the CoT pipeline.
    Haiku thinks step-by-step through the risk metrics before any framework is applied.
    Output feeds into run_concept_cot() as grounded observations.
    Never raises — falls back to a compact metrics string.
    """
    data_snapshot = (
        f"Ticker: {ticker} | Sector: {financials.get('sector', 'Unknown')}\n"
        f"Leverage: D/E={pillar_scores.get('de_ratio', 0):.2f} | "
        f"Interest coverage={pillar_scores.get('interest_coverage', 999):.1f}x\n"
        f"Liquidity: Current ratio={pillar_scores.get('current_ratio', 0):.2f} | "
        f"FCF trend={pillar_scores.get('fcf_trend', 'unknown')}\n"
        f"Earnings stability: Volatility={pillar_scores.get('earnings_volatility', 0):.0%} | "
        f"Loss years (last 3)={pillar_scores.get('loss_years', 0)}\n"
        f"Market risk: Beta={pillar_scores.get('beta', 1.0):.2f} | "
        f"Drawdown from 52w high={pillar_scores.get('drawdown_from_high_pct', 0):.1f}%\n"
        f"Pillar votes: Leverage={pillar_scores.get('leverage_signal')} | "
        f"Liquidity={pillar_scores.get('liquidity_signal')} | "
        f"Stability={pillar_scores.get('stability_signal')} | "
        f"Market={pillar_scores.get('market_signal')}"
    )

    prompt = (
        f"You are a risk manager looking at {ticker} for the first time.\n\n"
        f"Risk data:\n{data_snapshot}\n\n"
        f"Think step by step through this data:\n"
        f"1. What are the 2-3 most important risk signals here? Why does each matter?\n"
        f"2. What data is missing — where is your risk assessment weakest?\n"
        f"3. Is this risk profile normal for the sector, or genuinely elevated? "
        f"What's the key distinction?\n\n"
        f"Write your observations in 150-200 words. Use specific numbers. "
        f"Do not give a final verdict yet — just analyze what the risk data is telling you."
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
        print(f"[Risk] run_data_cot failed: {e}")
        return (
            f"D/E: {pillar_scores.get('de_ratio', 0):.2f} | "
            f"Coverage: {pillar_scores.get('interest_coverage', 999):.1f}x | "
            f"Current ratio: {pillar_scores.get('current_ratio', 0):.2f} | "
            f"FCF trend: {pillar_scores.get('fcf_trend', 'unknown')} | "
            f"Beta: {pillar_scores.get('beta', 1.0):.2f}."
        )


# ---------------------------------------------------------------------------
# Section 4 — Concept-CoT + Signal (LLM reasoning)
# ---------------------------------------------------------------------------

def _build_peer_context(state: ThesisState) -> str:
    """
    Reads what other agents have already written to the whiteboard.
    Prioritises raw_outputs (full findings) over agent_signals (structured only).
    Risk especially benefits from fundamental's intrinsic value findings —
    helps distinguish "cheap because distressed" vs "cheap because undervalued".
    """
    raw_outputs = state.get("raw_outputs", {})
    agent_signals = state.get("agent_signals", {})

    if not raw_outputs and not agent_signals:
        return ""

    lines = []

    # First pass — agents with full raw findings (richest context)
    for agent_name, findings_text in raw_outputs.items():
        if agent_name == "risk":
            continue
        lines.append(f"[{agent_name.upper()} — full findings]\n{findings_text}\n")

    # Second pass — agents with only structured signals (no raw yet)
    for agent_name, signal in agent_signals.items():
        if agent_name == "risk":
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
        + "\nCross-reference these findings with your risk assessment. "
        "If fundamental shows strong upside and your risk metrics are manageable, "
        "lean neutral rather than cautious — risk exists in every investment. "
        "Only flag bearish if the risk profile is genuinely severe (high leverage + negative FCF + deteriorating earnings). "
        "If peers broadly corroborate low risk, increase your confidence accordingly."
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
    Applies risk framework to data_cot_text observations.
    Returns (concept_analysis_text, AgentSignal).
    """
    conflict_context = ""
    if conflicts:
        desc_list = [c.get("description", "") for c in conflicts if "risk" in c.get("agents", [])]
        if desc_list:
            conflict_context = (
                "\nCommittee conflicts flagged:\n"
                + "\n".join(f"- {d}" for d in desc_list)
                + "\nRevise confidence downward if the conflict introduces genuine uncertainty."
            )

    peer_context = _build_peer_context(state)

    prompt = f"""You are a Risk Manager at a hedge fund investment committee presenting on {ticker}.

DATA OBSERVATIONS (from your step-1 analysis):
{data_cot_text}

Pillar results:
- Leverage risk:      {pillar_scores['leverage_signal']} (D/E: {pillar_scores['de_ratio']:.2f}, coverage: {pillar_scores['interest_coverage']:.1f}x)
- Liquidity risk:     {pillar_scores['liquidity_signal']} (current ratio: {pillar_scores['current_ratio']:.2f}, FCF trend: {pillar_scores['fcf_trend']})
- Earnings stability: {pillar_scores['stability_signal']} (volatility: {pillar_scores['earnings_volatility']:.0%}, loss years: {pillar_scores['loss_years']})
- Market/systematic:  {pillar_scores['market_signal']} (beta: {pillar_scores['beta']:.2f}, drawdown: {pillar_scores['drawdown_from_high_pct']:.1f}%)

Data quality: {pillar_scores['data_quality']:.0%}
{peer_context}
{conflict_context}

Apply your risk framework to these observations:
- Is this leverage level tolerable given the FCF profile and interest coverage?
- Does the liquidity position support the business through a downturn?
- Is the market risk (beta, drawdown) consistent with the fundamental picture?
- What is the single most dangerous risk factor — the one that could blow up the thesis?

Respond in exactly this format (SIGNAL first, then ANALYSIS):

SIGNAL:
{{"view": "bullish"|"bearish"|"neutral"|"cautious", "reasoning": "one sentence with the key risk number", "confidence": 0.0-1.0}}

ANALYSIS: [2-3 sentences applying risk framework. Reference specific numbers.]

Guidance: "bearish" requires multiple simultaneous red flags. "cautious" = elevated but manageable.
Use "bullish" only if risk is genuinely low (D/E <0.5, positive FCF, low beta)."""

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
                    "reasoning": str(parsed.get("reasoning", "Risk analysis complete.")),
                    "confidence": confidence,
                }
            except (json.JSONDecodeError, ValueError):
                print(f"[Risk] run_concept_cot: signal JSON parse failed, using pillar majority")

        return analysis_text, signal

    except Exception as e:
        print(f"[Risk] run_concept_cot failed: {e}")
        return "", fallback_signal


def run_llm_reasoning(
    ticker: str,
    pillar_scores: dict,
    conflicts: list,
    state: ThesisState,
    data_cot_text: str = "",
) -> AgentSignal:
    """Backward-compatible wrapper — returns only AgentSignal."""
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

def run_risk_agent(state: ThesisState) -> dict:
    """
    Main entry point called by arena/agents.py.
    Fetches data, runs 4-pillar risk analysis, returns AgentSignal.
    Always returns — never crashes the arena.
    """
    ticker = state.get("ticker", "")
    conflicts = state.get("conflicts", [])

    print(f"[Risk] Starting analysis for {ticker}")

    from arena.progress import emit_arena_event as _emit
    _emit({"type": "arena_agent_start", "agent": "risk", "round": state.get("round", 0) + 1})

    try:
        shared_data = state.get("shared_data", {})
        financials = _financials_from_shared(ticker, shared_data)
        market_context = _market_context_from_shared(ticker, shared_data)
        risk_metrics = calculate_risk_metrics(financials, market_context)
        pillar_scores = score_pillars(financials, market_context, risk_metrics)

        print(
            f"[Risk] Pillars: leverage={pillar_scores['leverage_signal']} "
            f"liquidity={pillar_scores['liquidity_signal']} "
            f"stability={pillar_scores['stability_signal']} "
            f"market={pillar_scores['market_signal']} "
            f"→ overall={pillar_scores['overall_signal']} "
            f"data_quality={pillar_scores['data_quality']:.0%}"
        )

        # Stage 1 — Data-CoT: reason about what the risk data means
        data_cot_text = run_data_cot(ticker, financials, market_context, pillar_scores)

        # Stage 2 — Concept-CoT: apply risk framework, produce signal
        concept_text, signal = run_concept_cot(ticker, pillar_scores, conflicts, state, data_cot_text)

        # Level 3: Q&A
        incoming_questions = _read_questions("risk", state)
        updated_questions = _generate_question("risk", pillar_scores, signal, state)
        updated_answers = _extract_answers("risk", incoming_questions, signal, pillar_scores, state)

        raw_findings = (
            f"RISK ANALYSIS — {ticker}\n\n"
            f"DATA OBSERVATIONS:\n{data_cot_text}\n\n"
            f"FRAMEWORK APPLICATION:\n{concept_text}\n\n"
            f"SIGNAL: {signal['view'].upper()} ({signal['confidence']:.0%} confidence)\n"
            f"REASONING: {signal['reasoning']}\n\n"
            f"METRICS: D/E={risk_metrics.get('de_ratio', 0):.2f} | "
            f"Coverage={risk_metrics.get('interest_coverage', 0):.1f}x | "
            f"Current ratio={risk_metrics.get('current_ratio', 0):.2f} | "
            f"FCF trend={risk_metrics.get('fcf_trend', 'N/A')} | "
            f"Beta={risk_metrics.get('beta', 1.0):.2f} | "
            f"Drawdown={risk_metrics.get('drawdown_from_high_pct', 0):.1f}%"
        )

        if incoming_questions:
            qa_lines = ["\nQUESTIONS ANSWERED:"]
            my_answers = updated_answers.get("risk", {})
            for asker, q in incoming_questions.items():
                qa_lines.append(f"  [{asker.upper()} asked]: {q}")
                qa_lines.append(f"  [Answer]: {my_answers.get(asker, 'No answer generated.')}")
            raw_findings += "\n".join(qa_lines)

        if "risk" in updated_questions:
            tgt = list(updated_questions["risk"].keys())[0]
            q_text = updated_questions["risk"][tgt]
            raw_findings += f"\nOPEN QUESTION TO {tgt.upper()}: {q_text}"
            from arena.progress import emit_arena_event as _emit_q
            _emit_q({"type": "arena_question", "from_agent": "risk", "to_agent": tgt, "question": q_text})

        if incoming_questions:
            my_answers = updated_answers.get("risk", {})
            from arena.progress import emit_arena_event as _emit_a
            for asker, q in incoming_questions.items():
                ans = my_answers.get(asker, "")
                if ans:
                    _emit_a({"type": "arena_answer", "from_agent": "risk", "to_agent": asker, "question": q, "answer": ans})

    except Exception as e:
        print(f"[Risk] Unhandled error for {ticker}: {e}")
        signal = {
            "view": "neutral",
            "reasoning": f"Analysis incomplete — data error: {str(e)[:80]}",
            "confidence": 0.30,
        }
        raw_findings = f"RISK ANALYSIS — {ticker}\nError: {str(e)[:120]}"
        updated_questions = dict(state.get("agent_questions", {}))
        updated_answers = dict(state.get("agent_answers", {}))

    print(f"[Risk] Signal: view={signal['view']} confidence={signal['confidence']}")

    from arena.progress import emit_arena_event
    emit_arena_event({
        "type": "arena_agent_done",
        "agent": "risk",
        "view": signal["view"],
        "confidence": signal["confidence"],
        "reasoning": signal["reasoning"],
    })

    existing_raw = dict(state.get("raw_outputs", {}))
    existing_raw["risk"] = raw_findings

    return {
        "agent_signals":   {"risk": signal},
        "raw_outputs":     existing_raw,
        "agent_questions": updated_questions,
        "agent_answers":   updated_answers,
    }
