from __future__ import annotations
import json
from anthropic import Anthropic
from arena.state import ThesisState

SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

_EMPTY_MEMO = {
    "thesis": None,
    "bear_case": None,
    "key_risks": None,
    "valuation_range": None,
    "what_would_make_this_wrong": None,
}


def extract_structured_memo(state: ThesisState) -> dict:
    """
    Post-processes a completed ThesisState into a structured memo dict.
    Called from the /memo/stream endpoint after run_arena() completes.
    Never raises — on any failure returns a dict with all 5 keys set to None.

    Returns:
        {
            "thesis": str | None,
            "bear_case": str | None,
            "key_risks": list[str] | None,
            "valuation_range": {"bear": str, "base": str, "bull": str} | None,
            "what_would_make_this_wrong": str | None,
        }
    """
    try:
        ticker = state.get("ticker", "UNKNOWN")
        signals = state.get("agent_signals", {})
        thesis_summary = state.get("thesis_summary", "") or ""
        conflicts = state.get("conflicts", []) or []
        raw_outputs = state.get("raw_outputs", {}) or {}

        signal_lines = "\n".join(
            f"  {name.upper()} ({sig.get('view', '?')}, {sig.get('confidence', 0):.0%}): {sig.get('reasoning', '')}"
            for name, sig in signals.items()
        )

        # Truncate raw_outputs to avoid exceeding context limits
        raw_summary = "\n\n".join(
            f"[{agent}]:\n{text[:800]}" for agent, text in list(raw_outputs.items())[:3]
        )

        conflict_text = (
            "\n".join(f"  - {c.get('description', '')}" for c in conflicts)
            if conflicts else "  None identified."
        )

        prompt = f"""You are a systematic portfolio manager. Extract a structured investment memo for {ticker} from the committee debate below.

ANALYST SIGNALS:
{signal_lines}

PM THESIS:
{thesis_summary}

CONFLICTS:
{conflict_text}

AGENT FINDINGS (excerpts):
{raw_summary}

Return ONLY a valid JSON object with these exact keys:
{{
  "thesis": "2-3 sentence bull thesis with specific numbers",
  "bear_case": "2-3 sentence bear case with specific numbers",
  "key_risks": ["risk 1 with metric", "risk 2 with metric", "risk 3 with metric"],
  "valuation_range": {{"bear": "$XX", "base": "$XX", "bull": "$XX"}},
  "what_would_make_this_wrong": "1-2 sentences on what would invalidate the thesis"
}}

Rules:
- Use actual numbers from the agent signals and findings
- Each key_risk must cite a specific metric or threshold
- valuation_range values must be dollar amounts or ranges (e.g. "$150-160")
- Return raw JSON only — no markdown fences, no preamble"""

        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)

        result = dict(_EMPTY_MEMO)
        for key in _EMPTY_MEMO:
            if key in parsed:
                result[key] = parsed[key]
        return result

    except Exception as e:
        print(f"[Output] extract_structured_memo failed: {e}")
        return dict(_EMPTY_MEMO)


def _write_memo_narrative(
    ticker: str,
    final_decision: str,
    conviction: str,
    consensus: float,
    rounds_run: int,
    signals: dict,
    thesis_summary: str,
    conflicts: list,
    agent_questions: dict,
    agent_answers: dict,
) -> str:
    """
    Uses Sonnet to write the narrative body of the investment memo.
    Returns the narrative string, or an empty string on failure (caller uses template fallback).
    """
    signal_lines = "\n".join(
        f"  {name.upper()} ({sig['view']}, {sig['confidence']:.0%}): {sig['reasoning']}"
        for name, sig in signals.items()
    )

    conflict_text = (
        "\n".join(f"  - {c['description']}" for c in conflicts)
        if conflicts else "  None identified."
    )

    qa_text = ""
    if agent_answers:
        parts = []
        for answering, askers in agent_answers.items():
            for asker, answer in askers.items():
                q = agent_questions.get(asker, {}).get(answering, "")
                if q:
                    parts.append(f"  {asker} asked {answering}: {q}\n  {answering} answered: {answer}")
        qa_text = "\n".join(parts) if parts else "  None."
    else:
        qa_text = "  None."

    prompt = f"""You are the CIO of a systematic hedge fund writing the final investment committee memo for {ticker}.

COMMITTEE OUTPUT:
Decision: {final_decision}
Consensus: {consensus:.0%} across {rounds_run} debate round(s)
Conviction: {conviction}

Analyst signals:
{signal_lines}

PM thesis synthesis:
{thesis_summary}

Conflicts identified:
{conflict_text}

Q&A exchanges:
{qa_text}

Write the narrative body of the investment memo in exactly four sections with these plain-text headers:

INVESTMENT THESIS
[2-3 sentences. State the core argument with the most important numbers. Be specific about what drives the view.]

KEY RISKS
[3 bullet points, each one sentence. Cite specific metrics where possible.]

WHAT THE DEBATE RESOLVED
[1-2 sentences. What did the Q&A or multi-round debate clarify? If no Q&A occurred, say what drove consensus.]

RECOMMENDATION
[1-2 sentences. State the position decision, sizing guidance (e.g. underweight, full position, no position), and the one condition that would cause a re-rating.]

Rules:
- Use actual numbers from the analyst signals and Q&A throughout
- No preamble, no closing remarks, no markdown formatting
- Write in the voice of a senior portfolio manager — direct, precise, professional
- Do not repeat the decision header — it will be prepended separately"""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[Output] _write_memo_narrative LLM call failed: {e}")
        return ""


def output_node(state: ThesisState) -> dict:
    """
    Reads the final agent signals and consensus score.
    Writes final_decision, conviction_level, and investment_memo.
    """
    signals = state.get("agent_signals", {})
    consensus = state.get("consensus_score", 0.0)
    ticker = state.get("ticker", "UNKNOWN")
    rounds_run = state.get("round", 0)

    # Determine final view from majority
    if signals:
        views = [s["view"] for s in signals.values()]
        final_view = max(set(views), key=views.count)
    else:
        final_view = "neutral"

    # Conviction from consensus score
    if consensus >= 0.80:
        conviction = "high"
    elif consensus >= 0.60:
        conviction = "medium"
    else:
        conviction = "low"

    # Map view to decision language
    decision_map = {
        "bullish":  f"LONG {ticker}",
        "bearish":  f"AVOID / SHORT {ticker}",
        "neutral":  f"MONITOR {ticker}",
        "cautious": f"UNDERWEIGHT {ticker}",
    }
    final_decision = (
        f"{decision_map.get(final_view, f'MONITOR {ticker}')} — {conviction} conviction"
    )

    agent_questions = state.get("agent_questions", {})
    agent_answers   = state.get("agent_answers", {})

    # Structured header — always present regardless of LLM outcome
    signal_lines = "\n".join(
        f"  {name.upper():15} {sig['view'].upper():8} "
        f"conf:{sig['confidence']:.0%}  {sig['reasoning'][:120]}"
        for name, sig in signals.items()
    )

    header = (
        f"INVESTMENT COMMITTEE MEMO — {ticker}\n"
        f"{'='*52}\n"
        f"DECISION: {final_decision}\n"
        f"CONSENSUS: {consensus:.0%} after {rounds_run} round(s)\n\n"
        f"ANALYST SIGNALS:\n{signal_lines}\n"
    )

    # LLM-written narrative body
    narrative = _write_memo_narrative(
        ticker, final_decision, conviction, consensus, rounds_run,
        signals,
        state.get("thesis_summary", ""),
        state.get("conflicts", []),
        agent_questions,
        agent_answers,
    )

    if narrative:
        body = f"\n{narrative}\n"
    else:
        # Fallback: template body if Sonnet call failed
        body = f"\nTHESIS:\n{state.get('thesis_summary', 'No summary available.')}\n"
        if state.get("conflicts"):
            conflict_lines = "\n".join(
                f"  Round {c['round']}: {c['description']}"
                for c in state["conflicts"]
            )
            body += f"\nCONFLICTS IDENTIFIED:\n{conflict_lines}\n"

    # Q&A always appended in structured form — primary source data
    qa_section = ""
    if agent_answers:
        qa_lines = []
        for answering_agent, askers in agent_answers.items():
            for asking_agent, answer in askers.items():
                question = agent_questions.get(asking_agent, {}).get(answering_agent, "")
                if question and answer:
                    qa_lines.append(f"  [{asking_agent} → {answering_agent}]: {question}")
                    qa_lines.append(f"  [{answering_agent} answered]: {answer}")
        if qa_lines:
            qa_section = "\nQUESTIONS ASKED & ANSWERED:\n" + "\n".join(qa_lines) + "\n"

    memo = header + body + qa_section + f"{'='*52}\n"

    return {
        "final_decision": final_decision,
        "conviction_level": conviction,
        "investment_memo": memo,
    }
