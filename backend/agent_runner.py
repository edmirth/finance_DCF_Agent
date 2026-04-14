"""
Agent Runner Service

Executes scheduled agent configurations against real financial data.
Supports 5 templates: earnings_watcher, market_pulse, thesis_guardian,
portfolio_heartbeat, arena_analyst.

Design goals:
  - Concurrent execution: multiple tickers run in parallel via ThreadPoolExecutor
  - Single synthesis LLM call (Haiku) per run to keep costs low
  - Never raises — errors produce a failed run record, not a crash
  - Stateless: each run creates fresh agent instances
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Max parallel ticker threads per run — keeps API rate limits safe
MAX_TICKER_WORKERS = 3

TEMPLATE_LABELS = {
    "earnings_watcher":    "Earnings Watcher",
    "market_pulse":        "Market Pulse",
    "thesis_guardian":     "Thesis Guardian",
    "portfolio_heartbeat": "Portfolio Heartbeat",
    "arena_analyst":       "Arena Analyst",
}

SCHEDULE_LABELS = {
    "daily_morning": "Every day at 7am",
    "pre_market": "Weekdays at 6:30am",
    "weekly_monday": "Every Monday at 7am",
    "weekly_friday": "Every Friday at 4pm",
    "monthly": "1st of each month",
}


class AgentRunnerService:
    """Executes a ScheduledAgent config and returns structured findings."""

    def __init__(self) -> None:
        self._anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, agent_config) -> dict:
        """
        Run the agent config synchronously.

        Returns:
            {
                "report":           str   — full markdown report
                "findings_summary": str   — 2-3 sentence digest
                "material_change":  bool  — whether something significant changed
                "alert_level":      str   — high | medium | low | none
                "tickers_analyzed": list
                "agents_used":      list
                "error":            str | None
            }
        """
        try:
            tickers = json.loads(agent_config.tickers or "[]")
            template = agent_config.template

            raw_outputs: dict[str, str] = {}
            agents_used: list[str] = []

            if template == "market_pulse":
                raw_outputs, agents_used = self._run_market_pulse(agent_config.instruction)

            elif template == "earnings_watcher":
                raw_outputs, agents_used = self._run_earnings_for_tickers(tickers)

            elif template == "thesis_guardian":
                raw_outputs, agents_used = self._run_thesis_guardian(
                    tickers, agent_config.instruction
                )

            elif template == "portfolio_heartbeat":
                raw_outputs, agents_used = self._run_portfolio_heartbeat(tickers)

            elif template == "arena_analyst":
                raw_outputs, agents_used = self._run_arena_analyst(
                    tickers, agent_config.instruction
                )

            else:
                return self._error_result(f"Unknown template: {template}")

            if not raw_outputs:
                return self._error_result("No agent outputs — all sub-agents failed")

            synthesis = self._synthesize(raw_outputs, agent_config)
            return {
                "report": synthesis.get("full_report", ""),
                "findings_summary": synthesis.get("summary", ""),
                "key_findings": synthesis.get("key_findings", []),
                "material_change": synthesis.get("material_change", False),
                "alert_level": synthesis.get("alert_level", "none"),
                "tickers_analyzed": tickers,
                "agents_used": agents_used,
                "error": None,
            }

        except Exception as exc:
            logger.exception("AgentRunnerService.execute failed")
            return self._error_result(str(exc))

    # ------------------------------------------------------------------
    # Template runners
    # ------------------------------------------------------------------

    def _run_market_pulse(self, instruction: str) -> tuple[dict, list]:
        from agents.market_agent import create_market_agent

        query = (
            "Give me a comprehensive market overview: major indices performance, "
            "sector rotation, VIX level and interpretation, macro conditions "
            "(rates, inflation, employment), and any notable market-moving events today."
        )
        if instruction:
            query += f"\n\nFocus especially on: {instruction}"

        try:
            agent = create_market_agent(show_reasoning=False)
            result = agent.analyze(query)
            return {"market_overview": result}, ["market"]
        except Exception as exc:
            logger.error(f"market_pulse sub-agent failed: {exc}")
            return {}, []

    def _run_earnings_for_tickers(self, tickers: list[str]) -> tuple[dict, list]:
        from agents.earnings_agent import create_earnings_agent

        outputs: dict[str, str] = {}

        def _analyze(ticker: str) -> tuple[str, str]:
            try:
                agent = create_earnings_agent()
                return ticker, agent.analyze(ticker)
            except Exception as exc:
                logger.error(f"Earnings agent failed for {ticker}: {exc}")
                return ticker, f"Error analyzing {ticker}: {exc}"

        with ThreadPoolExecutor(max_workers=min(MAX_TICKER_WORKERS, len(tickers) or 1)) as ex:
            futures = {ex.submit(_analyze, t): t for t in tickers}
            for future in as_completed(futures):
                ticker_sym, result = future.result()
                outputs[ticker_sym] = result

        return outputs, ["earnings"] if outputs else []

    def _run_thesis_guardian(self, tickers: list[str], instruction: str) -> tuple[dict, list]:
        """Run earnings agents for each ticker + market agent for macro context."""
        earnings_outputs, earnings_agents = self._run_earnings_for_tickers(tickers)

        from agents.market_agent import create_market_agent
        agents_used = list(earnings_agents)
        macro_result = ""
        try:
            agent = create_market_agent(show_reasoning=False)
            query = f"What are the current macro conditions relevant to: {instruction or ', '.join(tickers)}"
            macro_result = agent.analyze(query)
            agents_used.append("market")
        except Exception as exc:
            logger.error(f"thesis_guardian market agent failed: {exc}")

        outputs = dict(earnings_outputs)
        if macro_result:
            outputs["macro_context"] = macro_result
        return outputs, agents_used

    def _run_portfolio_heartbeat(self, tickers: list[str]) -> tuple[dict, list]:
        """Earnings analysis on each holding + sector diversification summary."""
        outputs, agents_used = self._run_earnings_for_tickers(tickers)
        return outputs, agents_used

    def _run_arena_analyst(self, tickers: list[str], instruction: str) -> tuple[dict, list]:
        from arena.run import run_arena

        outputs: dict[str, str] = {}
        # Limit arena runs to 2 tickers — each full IC run is expensive
        for ticker in tickers[:2]:
            try:
                query = instruction or f"Should we hold a long position in {ticker}?"
                state = run_arena(query=query, ticker=ticker, query_mode="full_ic")
                memo = state.get("investment_memo") or ""
                signals = state.get("agent_signals", {})
                consensus = state.get("consensus_score", 0)
                decision = state.get("final_decision", "")
                outputs[ticker] = (
                    f"**Decision:** {decision} | **Consensus:** {consensus:.0%}\n\n"
                    f"**Investment Memo:**\n{memo}\n\n"
                    f"**Agent Signals:**\n"
                    + "\n".join(
                        f"- {k}: {v.get('view', '')} ({v.get('confidence', 0):.0%} confidence)"
                        for k, v in signals.items()
                    )
                )
            except Exception as exc:
                logger.error(f"arena_analyst failed for {ticker}: {exc}")
                outputs[ticker] = f"Arena run failed for {ticker}: {exc}"

        return outputs, ["arena"] if outputs else []

    # ------------------------------------------------------------------
    # Synthesis — single Haiku call converts raw outputs to digest
    # ------------------------------------------------------------------

    def _synthesize(self, raw_outputs: dict[str, str], agent_config) -> dict:
        """Combine agent outputs into a structured digest using Haiku."""
        sections = "\n\n".join(
            f"### {key}\n{value[:3000]}"  # cap per section to keep prompt manageable
            for key, value in raw_outputs.items()
        )

        last_summary = agent_config.last_run_summary or ""
        instruction = agent_config.instruction or ""
        template_label = TEMPLATE_LABELS.get(agent_config.template, agent_config.template)
        topics = json.loads(agent_config.topics or "[]") if isinstance(agent_config.topics, str) else (agent_config.topics or [])
        topics_str = ", ".join(topics) if topics else ""

        prompt = f"""You are synthesizing investment research findings for a retail investor.

AGENT TYPE: {template_label}
INVESTOR INSTRUCTION / THESIS:
{instruction or "No specific instruction — provide general findings."}
{f"FOCUS TOPICS: {topics_str}" if topics_str else ""}

PREVIOUS RUN SUMMARY (for detecting material changes):
{last_summary or "No previous run — this is the first run."}

AGENT RESEARCH OUTPUTS:
{sections}

Produce a JSON object with these exact keys:
{{
  "summary": "2-3 sentence plain-English digest of the most important findings",
  "key_findings": ["3-5 concrete, specific findings with numbers where available"],
  "material_change": true or false (true if something significant changed vs previous run, or first run with notable findings),
  "alert_level": "high" | "medium" | "low" | "none",
  "full_report": "A well-structured markdown report (400-700 words). Include: ## Summary, ## Key Findings, ## What This Means For Your Thesis, ## Action Items. Use real numbers. No emojis. No ASCII borders."
}}

Return ONLY the JSON object — no preamble, no explanation."""

        try:
            response = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as exc:
            logger.error(f"Synthesis Haiku call failed: {exc}")
            # Fallback: return raw concatenation
            fallback_report = "\n\n".join(
                f"## {k}\n{v}" for k, v in raw_outputs.items()
            )
            return {
                "summary": "Research completed. See full report for details.",
                "key_findings": [],
                "material_change": True,
                "alert_level": "low",
                "full_report": fallback_report,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error_result(error: str) -> dict:
        return {
            "report": "",
            "findings_summary": "",
            "key_findings": [],
            "material_change": False,
            "alert_level": "none",
            "tickers_analyzed": [],
            "agents_used": [],
            "error": error,
        }


# Singleton
_runner: Optional[AgentRunnerService] = None


def get_runner() -> AgentRunnerService:
    global _runner
    if _runner is None:
        _runner = AgentRunnerService()
    return _runner
