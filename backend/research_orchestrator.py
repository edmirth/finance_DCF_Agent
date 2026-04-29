"""
Research Workstation Orchestrator.
Runs selected specialist agents in parallel for a given ticker.
Emits structured events via emit_fn as each step completes.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Callable

from arena.data_fetch_node import data_fetch_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AgentSection:
    agent: str              # "dcf" | "fundamental" | "quant" | "risk" | "macro" | "sentiment"
    title: str
    sentiment: str          # "bullish" | "bearish" | "neutral"
    confidence: float       # 0.0 to 1.0
    content: str            # full markdown text (the raw_output from the agent)
    key_points: list        # 3-5 bullet strings extracted from content
    duration_seconds: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Static metadata
# ---------------------------------------------------------------------------

AGENT_META = {
    "dcf": {
        "title": "DCF Valuation",
        "role": "FMP DCF engine · Bull / Base / Bear · Levered + Unlevered",
        "tools": ["FMP Custom DCF", "Financial Datasets AI", "Macro rates"],
    },
    "fundamental": {
        "title": "Fundamental Analysis",
        "role": "Revenue, margins, moat, SEC filings",
        "tools": ["Financial Datasets AI", "SEC EDGAR", "Tavily search"],
    },
    "quant": {
        "title": "Quantitative Signals",
        "role": "Price momentum, volatility, relative performance",
        "tools": ["FMP price history", "SPY benchmark", "Analyst revisions"],
    },
    "risk": {
        "title": "Risk Assessment",
        "role": "Leverage, debt, dilution, stress testing",
        "tools": ["Financial Datasets AI", "FMP multiples", "SEC filings"],
    },
    "macro": {
        "title": "Macro Environment",
        "role": "Interest rates, GDP, inflation, sector cycle",
        "tools": ["Fed rates API", "Tavily macro search", "Sector analysis"],
    },
    "sentiment": {
        "title": "Market Sentiment",
        "role": "News flow, insider activity, institutional ownership",
        "tools": ["SEC Form 4", "Tavily news", "13F filings"],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_minimal_state(
    ticker: str,
    shared_data: dict,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> dict:
    """Creates a minimal ThesisState-compatible dict for running arena agents."""
    query_title = assignment_title.strip() or f"Analyze {ticker}"
    focus_text = assignment_focus.strip()
    query = query_title if not focus_text else f"{query_title}\n\nFocus: {focus_text}"
    return {
        "ticker": ticker,
        "query": query,
        "query_mode": "full",
        "raw_outputs": {},
        "agent_signals": {},
        "agent_questions": {},
        "agent_answers": {},
        "debate_log": [],
        "signal_history": [],
        "conflicts": [],
        "next_action": "",
        "round": 0,
        "active_agents": [],
        "shared_data": shared_data,
        "final_decision": None,
        "conviction_level": None,
        "investment_memo": None,
        # ThesisState extras that agents may read
        "thesis_summary": focus_text,
        "consensus_score": 0.0,
    }


def _extract_key_points(content: str) -> list:
    """
    Extract up to 5 key points from content.
    Looks for lines starting with bullet chars or numbered lists.
    Falls back to first 3 sentences if no lists found.
    """
    if not content:
        return []

    lines = content.split("\n")
    bullets = []
    for line in lines:
        stripped = line.strip()
        # Match bullet chars or numbered list items
        if stripped.startswith(("•", "-", "*", "–")) and len(stripped) > 2:
            text = stripped.lstrip("•-*– ").strip()
            if text:
                bullets.append(text)
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] in (". ", ") "):
            text = stripped[3:].strip() if len(stripped) > 3 else stripped[2:].strip()
            if text:
                bullets.append(text)
        if len(bullets) >= 5:
            break

    if bullets:
        return bullets[:5]

    # Fallback: first 3 sentences
    import re
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    result = []
    for s in sentences:
        s = s.strip()
        if len(s) > 20:
            result.append(s)
        if len(result) >= 3:
            break
    return result


def _signal_to_sentiment(view: str) -> str:
    """Convert agent signal view string to bullish | bearish | neutral."""
    v = view.upper().strip() if view else ""
    if v in ("BULLISH", "BUY"):
        return "bullish"
    if v in ("BEARISH", "SELL"):
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# Individual agent runner functions
# ---------------------------------------------------------------------------

def _run_fundamental(
    ticker: str,
    shared_data: dict,
    emit: Callable,
    start_time: float,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> AgentSection:
    from arena.fundamental_agent import run_fundamental_agent

    emit({"type": "agent_step", "agent": "fundamental", "step": "Fetching financial statements & SEC filings..."})
    state = _create_minimal_state(ticker, shared_data, assignment_title, assignment_focus)

    try:
        result = run_fundamental_agent(state)
        signal = result.get("agent_signals", {}).get("fundamental")
        content = result.get("raw_outputs", {}).get("fundamental", "No analysis available.")

        sentiment = _signal_to_sentiment(signal["view"] if signal else "NEUTRAL")
        confidence = float(signal["confidence"] if signal else 0.5)

        return AgentSection(
            agent="fundamental",
            title=AGENT_META["fundamental"]["title"],
            sentiment=sentiment,
            confidence=confidence,
            content=content,
            key_points=_extract_key_points(content),
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[Research] fundamental agent failed: {e}")
        return AgentSection(
            agent="fundamental",
            title=AGENT_META["fundamental"]["title"],
            sentiment="neutral",
            confidence=0.0,
            content="",
            key_points=[],
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


def _run_quant(
    ticker: str,
    shared_data: dict,
    emit: Callable,
    start_time: float,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> AgentSection:
    from arena.quant_agent import run_quant_agent

    emit({"type": "agent_step", "agent": "quant", "step": "Computing price momentum, factor scores & volatility..."})
    state = _create_minimal_state(ticker, shared_data, assignment_title, assignment_focus)

    try:
        result = run_quant_agent(state)
        signal = result.get("agent_signals", {}).get("quant")
        content = result.get("raw_outputs", {}).get("quant", "No analysis available.")

        sentiment = _signal_to_sentiment(signal["view"] if signal else "NEUTRAL")
        confidence = float(signal["confidence"] if signal else 0.5)

        return AgentSection(
            agent="quant",
            title=AGENT_META["quant"]["title"],
            sentiment=sentiment,
            confidence=confidence,
            content=content,
            key_points=_extract_key_points(content),
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[Research] quant agent failed: {e}")
        return AgentSection(
            agent="quant",
            title=AGENT_META["quant"]["title"],
            sentiment="neutral",
            confidence=0.0,
            content="",
            key_points=[],
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


def _run_risk(
    ticker: str,
    shared_data: dict,
    emit: Callable,
    start_time: float,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> AgentSection:
    from arena.risk_agent import run_risk_agent

    emit({"type": "agent_step", "agent": "risk", "step": "Evaluating leverage, liquidity & earnings stability..."})
    state = _create_minimal_state(ticker, shared_data, assignment_title, assignment_focus)

    try:
        result = run_risk_agent(state)
        signal = result.get("agent_signals", {}).get("risk")
        content = result.get("raw_outputs", {}).get("risk", "No analysis available.")

        sentiment = _signal_to_sentiment(signal["view"] if signal else "NEUTRAL")
        confidence = float(signal["confidence"] if signal else 0.5)

        return AgentSection(
            agent="risk",
            title=AGENT_META["risk"]["title"],
            sentiment=sentiment,
            confidence=confidence,
            content=content,
            key_points=_extract_key_points(content),
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[Research] risk agent failed: {e}")
        return AgentSection(
            agent="risk",
            title=AGENT_META["risk"]["title"],
            sentiment="neutral",
            confidence=0.0,
            content="",
            key_points=[],
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


def _run_macro(
    ticker: str,
    shared_data: dict,
    emit: Callable,
    start_time: float,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> AgentSection:
    from arena.macro_agent import run_macro_agent

    emit({"type": "agent_step", "agent": "macro", "step": "Analysing rates, GDP, inflation & sector cycle..."})
    state = _create_minimal_state(ticker, shared_data, assignment_title, assignment_focus)

    try:
        result = run_macro_agent(state)
        signal = result.get("agent_signals", {}).get("macro")
        content = result.get("raw_outputs", {}).get("macro", "No analysis available.")

        sentiment = _signal_to_sentiment(signal["view"] if signal else "NEUTRAL")
        confidence = float(signal["confidence"] if signal else 0.5)

        return AgentSection(
            agent="macro",
            title=AGENT_META["macro"]["title"],
            sentiment=sentiment,
            confidence=confidence,
            content=content,
            key_points=_extract_key_points(content),
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[Research] macro agent failed: {e}")
        return AgentSection(
            agent="macro",
            title=AGENT_META["macro"]["title"],
            sentiment="neutral",
            confidence=0.0,
            content="",
            key_points=[],
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


def _run_sentiment(
    ticker: str,
    shared_data: dict,
    emit: Callable,
    start_time: float,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> AgentSection:
    from arena.sentiment_agent import run_sentiment_agent

    emit({"type": "agent_step", "agent": "sentiment", "step": "Scanning news flow, insiders & analyst ratings..."})
    state = _create_minimal_state(ticker, shared_data, assignment_title, assignment_focus)

    try:
        result = run_sentiment_agent(state)
        signal = result.get("agent_signals", {}).get("sentiment")
        content = result.get("raw_outputs", {}).get("sentiment", "No analysis available.")

        sentiment = _signal_to_sentiment(signal["view"] if signal else "NEUTRAL")
        confidence = float(signal["confidence"] if signal else 0.5)

        return AgentSection(
            agent="sentiment",
            title=AGENT_META["sentiment"]["title"],
            sentiment=sentiment,
            confidence=confidence,
            content=content,
            key_points=_extract_key_points(content),
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[Research] sentiment agent failed: {e}")
        return AgentSection(
            agent="sentiment",
            title=AGENT_META["sentiment"]["title"],
            sentiment="neutral",
            confidence=0.0,
            content="",
            key_points=[],
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


def _run_dcf(
    ticker: str,
    shared_data: dict,
    emit: Callable,
    start_time: float,
    assignment_title: str = "",
    assignment_focus: str = "",
) -> AgentSection:
    from agents.dcf_agent import DCFAgent

    emit({"type": "agent_step", "agent": "dcf", "step": "Running FMP custom DCF — Bull / Base / Bear scenarios..."})

    try:
        agent = DCFAgent()
        result = agent.analyze(ticker)
        report = agent.format_report(result)

        # Determine sentiment from upside potential
        if result.upside_potential > 0.10:
            sentiment = "bullish"
        elif result.upside_potential < -0.10:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        confidence = min(float(result.confidence), 1.0)

        current = result.current_price if result.current_price else 1.0
        key_points = [
            f"Base case intrinsic value: ${result.intrinsic_value:,.2f} ({result.upside_potential * 100:+.1f}% vs current)",
            f"Bull case: ${result.bull_case_value:,.2f} ({(result.bull_case_value / current - 1) * 100:+.1f}%)",
            f"Bear case: ${result.bear_case_value:,.2f} ({(result.bear_case_value / current - 1) * 100:+.1f}%)",
            f"WACC: {result.wacc:.2%}",
            f"Revenue growth assumption: {result.revenue_growth_rate:.1%}",
        ]

        return AgentSection(
            agent="dcf",
            title=AGENT_META["dcf"]["title"],
            sentiment=sentiment,
            confidence=confidence,
            content=report,
            key_points=key_points,
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[Research] DCF agent failed: {e}")
        return AgentSection(
            agent="dcf",
            title=AGENT_META["dcf"]["title"],
            sentiment="neutral",
            confidence=0.0,
            content="",
            key_points=[],
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# PM synthesis
# ---------------------------------------------------------------------------

def _run_pm_synthesis(ticker: str, sections: list, mandate: dict | None = None) -> dict:
    """Uses Anthropic Haiku to synthesise an executive summary from all completed sections."""
    from anthropic import Anthropic

    sentiments = [s.sentiment for s in sections if not s.error]
    bullish = sentiments.count("bullish")
    bearish = sentiments.count("bearish")
    neutral = sentiments.count("neutral")

    # Overall: majority wins, ties go neutral
    if bullish > bearish and bullish > neutral:
        overall = "bullish"
    elif bearish > bullish and bearish > neutral:
        overall = "bearish"
    else:
        overall = "neutral"

    findings = "\n\n".join([
        f"## {s.title} ({s.sentiment.upper()})\n" + "\n".join(f"• {p}" for p in s.key_points)
        for s in sections if not s.error and s.key_points
    ])

    if not findings:
        return {
            "overall_sentiment": overall,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "summary": f"Analysis complete for {ticker}. {bullish} bullish, {bearish} bearish, {neutral} neutral signals.",
        }

    # Build mandate context block for the PM prompt
    mandate_block = ""
    if mandate:
        try:
            from backend.mandate import build_mandate_context
            mandate_block = build_mandate_context(mandate) + "\n"
        except Exception:
            pass

    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": (
                    f"{mandate_block}"
                    f"You are a portfolio manager at {mandate.get('firm_name', 'an investment firm') if mandate else 'an investment firm'} "
                    f"synthesising findings from specialist analysts on {ticker}.\n\n"
                    f"ANALYST FINDINGS:\n{findings}\n\n"
                    f"Write a 3-4 sentence executive summary that:\n"
                    f"1. States the overall signal ({overall})\n"
                    f"2. Highlights the 2-3 most important findings across all analysts\n"
                    f"3. Flags any concerns relative to the firm's mandate limits (position sizing, sector limits, risk)\n"
                    f"4. Ends with a concrete next step for the investor (e.g. "
                    f"\"monitor Q3 guidance\", \"watch macro rate path\")\n\n"
                    f"Be specific, cite numbers. No markdown headers. Plain prose."
                ),
            }],
        )
        summary = response.content[0].text.strip()
    except Exception as e:
        logger.error(f"[Research] PM synthesis LLM call failed: {e}")
        summary = (
            f"Overall signal is {overall} across {len(sentiments)} analysts "
            f"({bullish} bullish, {bearish} bearish, {neutral} neutral)."
        )

    return {
        "overall_sentiment": overall,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Runner dispatch table
# ---------------------------------------------------------------------------

AGENT_RUNNERS = {
    "dcf": _run_dcf,
    "fundamental": _run_fundamental,
    "quant": _run_quant,
    "risk": _run_risk,
    "macro": _run_macro,
    "sentiment": _run_sentiment,
}


# ---------------------------------------------------------------------------
# Orchestrator class
# ---------------------------------------------------------------------------

class ResearchOrchestrator:
    def __init__(
        self,
        run_id: str,
        ticker: str,
        selected_agents: list,
        emit_fn: Callable,
        task_id: Optional[str] = None,
        task_type: str = "ad_hoc",
        triggered_by: str = "manual",
        assignment_title: str = "",
        assignment_focus: str = "",
    ):
        self.run_id = run_id
        self.ticker = ticker.upper()
        self.selected_agents = selected_agents
        self.emit = emit_fn  # emit_fn(event_dict) — sync callable
        self.task_id = task_id
        self.task_type = task_type
        self.triggered_by = triggered_by
        self.assignment_title = assignment_title.strip()
        self.assignment_focus = assignment_focus.strip()

    # ---------- Task persistence helpers (Phase 2) ----------

    def _create_task_record(self) -> Optional[str]:
        """
        Create a research_tasks row at run-start. Idempotent — if task_id was
        passed in by the caller we just mark it 'running' instead of inserting.
        Returns the task_id (or None if persistence failed — runs continue).
        """
        try:
            import json as _json
            from datetime import datetime as _dt
            from backend.database import SyncSessionLocal
            from backend.models import ResearchTask

            with SyncSessionLocal() as db:
                if self.task_id:
                    task = db.query(ResearchTask).filter(ResearchTask.id == self.task_id).one_or_none()
                    if task:
                        task.status = "running"
                        task.started_at = task.started_at or _dt.utcnow()
                        task.run_id = self.run_id
                        if self.assignment_focus and not task.notes:
                            task.notes = self.assignment_focus
                        db.commit()
                        return task.id

                # Auto-create
                title = self.assignment_title or f"{self.task_type.replace('_', ' ').title()}: {self.ticker}"
                task = ResearchTask(
                    ticker=self.ticker,
                    task_type=self.task_type,
                    title=title,
                    status="running",
                    selected_agents=_json.dumps(self.selected_agents),
                    triggered_by=self.triggered_by,
                    run_id=self.run_id,
                    started_at=_dt.utcnow(),
                    notes=self.assignment_focus or None,
                )
                db.add(task)
                db.commit()
                db.refresh(task)
                self.task_id = task.id
                # Tell the frontend a task was opened
                try:
                    self.emit({"type": "task_created", "task_id": task.id})
                except Exception:
                    pass
                return task.id
        except Exception as e:
            logger.warning(f"[Research] Failed to create task record: {e}")
            return None

    def _append_finding(self, agent_name: str, section: "AgentSection") -> None:
        """Persist one agent's finding to the task as it completes."""
        if not self.task_id:
            return
        try:
            import json as _json
            from backend.database import SyncSessionLocal
            from backend.models import ResearchTask

            with SyncSessionLocal() as db:
                task = db.query(ResearchTask).filter(ResearchTask.id == self.task_id).one_or_none()
                if not task:
                    return
                try:
                    findings = _json.loads(task.findings or "{}")
                except Exception:
                    findings = {}
                findings[agent_name] = {
                    "title": section.title,
                    "sentiment": section.sentiment,
                    "confidence": section.confidence,
                    "key_points": section.key_points,
                    "duration_seconds": section.duration_seconds,
                    "error": section.error,
                }
                task.findings = _json.dumps(findings)

                try:
                    completed = _json.loads(task.completed_agents or "[]")
                except Exception:
                    completed = []
                if agent_name not in completed:
                    completed.append(agent_name)
                task.completed_agents = _json.dumps(completed)

                db.commit()
        except Exception as e:
            logger.warning(f"[Research] Failed to append finding for {agent_name}: {e}")

    def _finalize_task(
        self,
        synthesis: dict,
        status: str = "done",
        error_msg: Optional[str] = None,
    ) -> None:
        """Write final synthesis + status to the task row at end of run."""
        if not self.task_id:
            return
        try:
            import json as _json
            from datetime import datetime as _dt
            from backend.database import SyncSessionLocal
            from backend.models import ResearchTask

            with SyncSessionLocal() as db:
                task = db.query(ResearchTask).filter(ResearchTask.id == self.task_id).one_or_none()
                if not task:
                    return
                task.pm_synthesis = _json.dumps(synthesis) if synthesis else None
                task.overall_sentiment = (synthesis or {}).get("overall_sentiment")
                task.status = status
                task.completed_at = _dt.utcnow()
                task.mandate_check = "applied"
                if error_msg:
                    task.error = error_msg
                db.commit()
        except Exception as e:
            logger.warning(f"[Research] Failed to finalize task: {e}")

    def run(self) -> dict:
        """
        Full research run. Returns dict of all sections + synthesis.
        Calls emit_fn for each event so the frontend updates in real-time.
        Never raises — errors are captured per-agent.
        """
        results: dict = {}

        # 0. Open / mark a research_tasks row as running (Phase 2)
        self._create_task_record()

        # 1. Fetch shared data
        self.emit({"type": "fetch_start", "message": f"Fetching shared market data for {self.ticker}..."})
        try:
            minimal_state = _create_minimal_state(
                self.ticker,
                {},
                self.assignment_title,
                self.assignment_focus,
            )
            fetch_result = data_fetch_node(minimal_state)
            shared_data = fetch_result.get("shared_data", {})
        except Exception as e:
            logger.error(f"[Research] data_fetch_node failed: {e}")
            shared_data = {}
        self.emit({"type": "fetch_complete", "message": "Market data loaded."})

        # 2. Run selected agents in parallel
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {}
            for agent_name in self.selected_agents:
                runner = AGENT_RUNNERS.get(agent_name)
                if not runner:
                    continue
                start_time = time.time()
                self.emit({"type": "agent_start", "agent": agent_name})
                future = pool.submit(
                    runner,
                    self.ticker,
                    shared_data,
                    self.emit,
                    start_time,
                    self.assignment_title,
                    self.assignment_focus,
                )
                futures[future] = agent_name

            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    section = future.result()
                except Exception as e:
                    section = AgentSection(
                        agent=agent_name,
                        title=AGENT_META.get(agent_name, {}).get("title", agent_name),
                        sentiment="neutral",
                        confidence=0.0,
                        content="",
                        key_points=[],
                        error=str(e),
                    )

                results[agent_name] = section

                # Persist finding to task (Phase 2)
                self._append_finding(agent_name, section)

                # Emit completion event with full section data
                self.emit({
                    "type": "agent_complete",
                    "agent": agent_name,
                    "section": {
                        "agent": section.agent,
                        "title": section.title,
                        "sentiment": section.sentiment,
                        "confidence": section.confidence,
                        "content": section.content,
                        "key_points": section.key_points,
                        "duration_seconds": section.duration_seconds,
                        "error": section.error,
                    },
                })

        # 3. PM synthesis — load mandate from DB so PM knows the firm's rules
        self.emit({"type": "synthesis_start", "message": "Synthesising findings..."})
        sections_list = [results[a] for a in self.selected_agents if a in results]
        mandate: dict | None = None
        try:
            from backend.database import SyncSessionLocal
            from backend.mandate import get_mandate_sync
            with SyncSessionLocal() as _db:
                mandate = get_mandate_sync(_db)
        except Exception as _e:
            logger.warning(f"[Research] Could not load mandate for PM synthesis: {_e}")
        synthesis = _run_pm_synthesis(self.ticker, sections_list, mandate=mandate)
        self.emit({"type": "synthesis_complete", "synthesis": synthesis})

        # 4. Finalize task record (Phase 2)
        self._finalize_task(synthesis, status="done")
        if self.task_id:
            self.emit({"type": "task_completed", "task_id": self.task_id})

        return {
            "sections": {k: vars(v) for k, v in results.items()},
            "synthesis": synthesis,
            "task_id": self.task_id,
        }
