"""
Agent Runner Service

Executes scheduled agent configurations against real financial data.
Supports 5 templates: earnings_watcher, market_pulse, thesis_guardian,
portfolio_heartbeat, firm_pipeline.

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
    "firm_pipeline":       "Firm Investment Pipeline",
    "fundamental_analyst": "Fundamental Analyst",
    "quant_analyst":       "Quant Analyst",
    "risk_analyst":        "Risk Analyst",
    "macro_analyst":       "Macro Analyst",
    "sentiment_analyst":   "Sentiment Analyst",
}

SCHEDULE_LABELS = {
    "daily_morning":       "Every day at 7am",
    "pre_market":          "Weekdays at 6:30am",
    "weekly_monday":       "Every Monday at 7am",
    "weekly_friday":       "Every Friday at 4pm",
    "monthly":             "1st of each month",
    # Phase 4 — finance-specific schedules
    "pre_market_brief":    "Weekdays at 6:30am — pre-market brief",
    "market_open":         "Weekdays at 9:30am — market open",
    "market_close":        "Weekdays at 4:00pm — market close",
    "weekly_friday_close": "Friday at 4:00pm — weekly IC prep",
    "monthly_first":       "1st of each month at 8am",
    "quarterly":           "1st of Jan/Apr/Jul/Oct at 8am",
}

SPECIALIST_TEMPLATE_TO_AGENT = {
    "fundamental_analyst": "fundamental",
    "quant_analyst": "quant",
    "risk_analyst": "risk",
    "macro_analyst": "macro",
    "sentiment_analyst": "sentiment",
}


def _statement_row_count(financials: dict, key: str) -> int:
    rows = (financials or {}).get(key) or []
    return len(rows) if isinstance(rows, list) else 0


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

            elif template == "firm_pipeline":
                raw_outputs, agents_used = self._run_firm_pipeline(
                    tickers, agent_config
                )

            elif template in SPECIALIST_TEMPLATE_TO_AGENT:
                raw_outputs, agents_used = self._run_instruction_driven_research(
                    tickers,
                    agent_config.instruction,
                    template,
                )

            elif template == "arena_analyst":
                return self._error_result(
                    "Template 'arena_analyst' has been removed"
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

    def _run_specialist_analyst(
        self,
        tickers: list[str],
        instruction: str,
        template: str,
    ) -> tuple[dict, list]:
        from backend.research_orchestrator import run_specialist_agent_once

        specialist = SPECIALIST_TEMPLATE_TO_AGENT[template]
        outputs: dict[str, str] = {}

        def _analyze(ticker: str) -> tuple[str, Optional[str]]:
            section = run_specialist_agent_once(
                specialist,
                ticker,
                assignment_title=f"{TEMPLATE_LABELS[template]} coverage for {ticker}",
                assignment_focus=instruction,
            )

            if section.error and not section.content and not section.key_points:
                logger.warning(
                    "Specialist analyst blocked for %s (%s): %s",
                    ticker,
                    template,
                    section.error,
                )
                return ticker, None

            sentiment = section.sentiment.upper()
            confidence = f"{section.confidence:.0%}"
            bullets = "\n".join(f"- {point}" for point in section.key_points[:5])
            body = section.content.strip()
            parts = [
                f"## {ticker} — {section.title} ({sentiment}, {confidence} confidence)",
            ]
            if bullets:
                parts.append(bullets)
            if body:
                parts.append(body)
            if section.error:
                parts.append(f"Warning: {section.error}")
            return ticker, "\n\n".join(parts)

        with ThreadPoolExecutor(max_workers=min(MAX_TICKER_WORKERS, len(tickers) or 1)) as ex:
            futures = {ex.submit(_analyze, t): t for t in tickers}
            for future in as_completed(futures):
                ticker_sym, result = future.result()
                if result:
                    outputs[ticker_sym] = result

        return outputs, [specialist] if outputs else []

    def _run_instruction_driven_research(
        self,
        tickers: list[str],
        instruction: str,
        template: str,
    ) -> tuple[dict, list]:
        """
        Instruction-driven analysis for hired agents.
        Fetches real financial data + current news per ticker, then runs a
        focused LLM call shaped by the agent's own instruction — not generic
        pillar math. This is what makes a hired analyst actually do its job.
        """
        from data.financial_data import FinancialDataFetcher
        from shared.tavily_client import get_tavily_client

        outputs: dict[str, str] = {}
        fetcher = FinancialDataFetcher()
        tavily = get_tavily_client()
        template_label = TEMPLATE_LABELS.get(template, template)

        def _validation_error(
            ticker_upper: str,
            stock_info: dict,
            financials: dict,
            key_metrics: dict,
        ) -> Optional[str]:
            missing: list[str] = []
            if not stock_info:
                missing.append("company profile")
            if _statement_row_count(financials, "income_statements") == 0:
                missing.append("income statements")
            if _statement_row_count(financials, "balance_sheets") == 0:
                missing.append("balance sheets")
            if _statement_row_count(financials, "cash_flow_statements") == 0:
                missing.append("cash flow statements")
            if not key_metrics:
                missing.append("key metrics")
            if missing:
                return (
                    f"Critical financial data is missing for {ticker_upper}: {', '.join(missing)}. "
                    "The analyst run was blocked instead of using incomplete data."
                )
            return None

        def _analyze(ticker: str) -> tuple[str, Optional[str]]:
            try:
                ticker_upper = ticker.strip().upper()
                stock_info = fetcher.get_stock_info(ticker_upper) or {}
                financials = fetcher.get_financial_statements(ticker_upper) or {}
                key_metrics = fetcher.get_key_metrics(ticker_upper) or {}
                validation_error = _validation_error(ticker_upper, stock_info, financials, key_metrics)
                if validation_error:
                    logger.warning("Instruction-driven research blocked for %s: %s", ticker_upper, validation_error)
                    return ticker_upper, None

                data_block = self._format_financial_data(ticker_upper, stock_info, financials, key_metrics)

                # Current news / analyst sentiment via Tavily
                news_block = ""
                try:
                    focus = instruction[:150] if instruction else "fundamentals and investment thesis"
                    news_block = tavily.search_text(
                        f"{ticker_upper} stock analysis {focus}",
                        topic="finance",
                        search_depth="advanced",
                        max_results=4,
                        time_range="month",
                    )
                except Exception as _e:
                    logger.warning(f"Tavily search failed for {ticker_upper}: {_e}")

                news_section = f"\nCURRENT CONTEXT:\n{news_block}" if news_block else ""

                prompt = f"""You are a {template_label}. Your assignment:

{instruction or f"Provide a comprehensive {template_label.lower()} analysis."}

TICKER: {ticker_upper}
COMPANY: {stock_info.get("company_name", ticker_upper)}
SECTOR: {stock_info.get("sector", "Unknown")}

HISTORICAL FINANCIALS:
{data_block}{news_section}

Write a focused research report that directly addresses the assignment above.
- Lead with your investment signal (BULLISH / BEARISH / NEUTRAL) and the single most important reason
- Support every claim with specific numbers from the data
- Focus on what matters most for the stated assignment
- Close with a concrete action or watch item

Markdown format. 400-600 words. No filler."""

                response = self._anthropic.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}],
                )
                return ticker_upper, response.content[0].text.strip()

            except Exception as exc:
                logger.error(f"Instruction-driven research failed for {ticker}: {exc}")
                return ticker.strip().upper(), None

        with ThreadPoolExecutor(max_workers=min(MAX_TICKER_WORKERS, len(tickers) or 1)) as ex:
            futures = {ex.submit(_analyze, t): t for t in tickers}
            for future in as_completed(futures):
                ticker_sym, result = future.result()
                if result:
                    outputs[ticker_sym] = result

        return outputs, [template] if outputs else []

    @staticmethod
    def _format_financial_data(ticker: str, stock_info: dict, financials: dict, key_metrics: Optional[dict] = None) -> str:
        """Format raw financial data into a compact LLM-readable block."""
        lines = []

        market_cap = stock_info.get("market_cap") or 0
        price = stock_info.get("current_price") or 0
        if market_cap:
            lines.append(f"Market Cap: ${market_cap / 1e9:.1f}B")
        if price:
            lines.append(f"Current Price: ${price:.2f}")

        key_metrics = key_metrics or {}
        if key_metrics:
            latest_revenue = key_metrics.get("latest_revenue") or 0
            latest_ebit = key_metrics.get("latest_ebit") or 0
            latest_net_income = key_metrics.get("latest_net_income") or 0
            shares = key_metrics.get("shares_outstanding") or 0
            tax_rate = key_metrics.get("effective_tax_rate")
            lines.append("\nKey Metrics:")
            if latest_revenue:
                lines.append(f"  Latest Revenue: ${latest_revenue / 1e9:.1f}B")
            if latest_ebit:
                lines.append(f"  Latest EBIT: ${latest_ebit / 1e9:.1f}B")
            if latest_net_income:
                lines.append(f"  Latest Net Income: ${latest_net_income / 1e9:.1f}B")
            if shares:
                lines.append(f"  Shares Outstanding: {shares / 1e9:.2f}B")
            if tax_rate is not None:
                lines.append(f"  Effective Tax Rate: {float(tax_rate) * 100:.1f}%")

        income = financials.get("income_statements", [])
        if income:
            lines.append("\nIncome Statement (annual, last 3 years):")
            for stmt in income[:3]:
                date = stmt.get("report_period") or stmt.get("date", "")
                rev = stmt.get("revenue") or 0
                gp = stmt.get("gross_profit") or 0
                oi = stmt.get("operating_income") or 0
                ni = stmt.get("net_income") or 0
                eps = stmt.get("earnings_per_share") or 0
                row = f"  {date}: Revenue ${rev / 1e9:.1f}B"
                if rev and gp:
                    row += f" | Gross Margin {gp / rev * 100:.0f}%"
                if oi:
                    row += f" | OpIncome ${oi / 1e9:.1f}B"
                if ni:
                    row += f" | Net Income ${ni / 1e9:.1f}B"
                if eps:
                    row += f" | EPS ${eps:.2f}"
                lines.append(row)

        balance = financials.get("balance_sheets", [])
        if balance:
            bs = balance[0]
            cash = bs.get("cash_and_equivalents") or 0
            debt = bs.get("total_debt") or 0
            equity = bs.get("total_equity") or 0
            lines.append("\nBalance Sheet (most recent):")
            if cash:
                lines.append(f"  Cash: ${cash / 1e9:.1f}B")
            if debt:
                lines.append(f"  Total Debt: ${debt / 1e9:.1f}B")
            if equity:
                lines.append(f"  Equity: ${equity / 1e9:.1f}B")

        cf = financials.get("cash_flow_statements", [])
        if cf:
            lines.append("\nCash Flow (last 3 years):")
            for stmt in cf[:3]:
                date = stmt.get("report_period") or stmt.get("date", "")
                ocf = stmt.get("operating_cash_flow") or 0
                capex = stmt.get("capital_expenditures") or 0
                fcf = stmt.get("free_cash_flow") or (ocf - abs(capex))
                if ocf or fcf:
                    lines.append(f"  {date}: OCF ${ocf / 1e9:.1f}B | FCF ${fcf / 1e9:.1f}B")

        return "\n".join(lines) if lines else "No financial data available."

    # ------------------------------------------------------------------
    # firm_pipeline (Phase 4) — runs the full InvestmentPipeline per ticker.
    # Each ticker becomes a tracked ResearchTask, gates are enforced, the
    # PM produces a structured BUY/HOLD/SELL with mandate-aware sizing.
    # ------------------------------------------------------------------

    def _run_firm_pipeline(
        self,
        tickers: list[str],
        agent_config,
    ) -> tuple[dict, list]:
        """
        For each ticker, create a ResearchTask + execute the InvestmentPipeline.
        Outputs the structured PM decision so the synthesis prompt can
        compose a coherent multi-ticker brief.
        """
        from backend.investment_pipeline import InvestmentPipeline
        from backend.database import SyncSessionLocal
        from backend.models import ResearchTask
        import uuid as _uuid

        if not tickers:
            return {}, []

        outputs: dict[str, str] = {}
        agents_used = ["fundamental", "quant", "risk", "macro", "sentiment", "dcf",
                       "risk_gate", "compliance_gate", "pm_decision"]

        for ticker in tickers:
            ticker_upper = ticker.strip().upper()
            if not ticker_upper:
                continue

            # 1. Open a ResearchTask seeded with the routine context
            task_id: Optional[str] = None
            try:
                with SyncSessionLocal() as db:
                    task = ResearchTask(
                        ticker=ticker_upper,
                        task_type="thesis_update",
                        title=f"Routine: {agent_config.name} — {ticker_upper}",
                        status="pending",
                        priority="medium",
                        selected_agents=json.dumps(
                            ["fundamental", "quant", "risk", "macro", "sentiment", "dcf"]
                        ),
                        triggered_by="routine",
                        notes=(agent_config.instruction or "")[:500] or None,
                    )
                    db.add(task)
                    db.commit()
                    db.refresh(task)
                    task_id = task.id
            except Exception as exc:
                logger.error(f"firm_pipeline: failed to create task for {ticker_upper}: {exc}")

            # 2. Run the pipeline — emits to /dev/null since this is a background
            #    routine, not a user-watched run.
            run_id = str(_uuid.uuid4())

            def _no_op_emit(_event: dict) -> None:
                return None

            try:
                pipeline = InvestmentPipeline(
                    run_id=run_id,
                    ticker=ticker_upper,
                    selected_agents=["fundamental", "quant", "risk", "macro", "sentiment", "dcf"],
                    emit_fn=_no_op_emit,
                    task_id=task_id,
                    task_type="thesis_update",
                    triggered_by="routine",
                )
                result = pipeline.run()

                pm = result.get("pm_decision") or {}
                action = pm.get("action", "HOLD")
                size = pm.get("suggested_size_pct", 0.0)
                conviction = pm.get("conviction", "MEDIUM")
                rationale = pm.get("rationale") or pm.get("summary") or ""
                blocked = pm.get("blocked", False)
                size_str = f" at {size:.1f}% NAV" if action == "BUY" and size > 0 else ""

                outputs[ticker_upper] = (
                    f"## {ticker_upper} — {action}{size_str} ({conviction} conviction)"
                    f"{' [BLOCKED]' if blocked else ''}\n\n{rationale}"
                )
            except Exception as exc:
                logger.exception(f"firm_pipeline failed for {ticker_upper}")
                outputs[ticker_upper] = f"Pipeline failed for {ticker_upper}: {exc}"

        return outputs, agents_used

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
