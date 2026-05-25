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
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Optional

from anthropic import Anthropic

from backend.agent_prompt_profiles import (
    format_bullets,
    format_required_sections,
    infer_research_intent,
    resolve_role_prompt_profile,
)

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


def _strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
    return cleaned.strip()


def _extract_json_object(text: str) -> Optional[dict]:
    cleaned = _strip_markdown_fences(text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return None


def _dedupe_preserve_order(values: list[str], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= limit:
            break
    return deduped


def _clean_report_for_display(text: str, section_key: str) -> str:
    lines = [line.rstrip() for line in (text or "").strip().splitlines()]
    if len(lines) >= 2 and lines[0].strip().upper() == section_key.upper():
        second = lines[1].strip()
        if second.startswith("#") or second.upper().startswith(section_key.upper()):
            lines = lines[1:]

    cleaned_lines: list[str] = []
    skip_internal_block = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            skip_internal_block = False
            cleaned_lines.append("")
            continue

        upper = line.upper()
        if re.match(r"^(CURRENT ISSUE|ASSIGNMENT|USER REQUEST|ISSUE METADATA|TASK METADATA):?\s*$", upper):
            skip_internal_block = True
            continue
        if skip_internal_block and re.match(r"^(TITLE|OBJECTIVE|TASK TYPE|PRIORITY|RESOLVED SCOPE|REQUIRED DELIVERABLE):\s+", upper):
            continue
        if re.match(r"^(TASK TYPE|PRIORITY):\s+", upper):
            continue

        heading_match = re.match(r"^([A-Z][A-Z /&()\-]{4,}):\s*$", line)
        inline_label_match = re.match(r"^([A-Z][A-Z /&()\-]{2,}):\s+(.+)$", line)
        if heading_match:
            cleaned_lines.append(f"### {heading_match.group(1).title()}")
            continue
        if " — " in line and upper == line and len(line) <= 90:
            cleaned_lines.append(f"## {line.title()}")
            continue
        if inline_label_match:
            label = inline_label_match.group(1).title()
            value = inline_label_match.group(2).strip()
            cleaned_lines.append(f"**{label}:** {value}")
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _extract_summary_from_report(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    lines = [line.strip() for line in cleaned.splitlines()]
    for line in lines:
        if not line or line.startswith("#") or line.startswith("- ") or re.match(r"^\d+[.)]\s", line):
            continue
        if len(line) < 25:
            continue
        return line
    compact = re.sub(r"\s+", " ", cleaned)
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) >= 25:
            return sentence
    return compact[:220].strip()


def _extract_key_findings_from_report(text: str) -> list[str]:
    lines = [line.strip() for line in (text or "").splitlines()]
    findings: list[str] = []
    for line in lines:
        if not line:
            continue
        if line.startswith(("- ", "* ", "• ")):
            findings.append(line[2:].strip())
        elif re.match(r"^\d+[.)]\s+", line):
            findings.append(re.sub(r"^\d+[.)]\s+", "", line).strip())
        if len(findings) >= 5:
            break
    if findings:
        return _dedupe_preserve_order(findings, limit=5)

    compact = re.sub(r"\s+", " ", (text or "").strip())
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    extracted = [sentence.strip() for sentence in sentences if len(sentence.strip()) >= 30]
    return _dedupe_preserve_order(extracted, limit=4)


def _extract_suggestions_from_report(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    section_match = re.search(
        r"(?:^|\n)##\s*(?:Agent Suggestions|Next Steps|Action Items|Risks And Watch Items|What This Means For Your Thesis)\s*\n(?P<body>.*?)(?=\n##\s+|\Z)",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    source = section_match.group("body") if section_match else cleaned

    suggestions: list[str] = []
    for line in source.splitlines():
        item = line.strip()
        if not item:
            continue
        if item.startswith(("- ", "* ", "• ")):
            suggestions.append(item[2:].strip())
        elif re.match(r"^\d+[.)]\s+", item):
            suggestions.append(re.sub(r"^\d+[.)]\s+", "", item).strip())
        if len(suggestions) >= 4:
            break

    if suggestions:
        return _dedupe_preserve_order(suggestions, limit=4)

    compact = re.sub(r"\s+", " ", source)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", compact)
        if any(keyword in sentence.lower() for keyword in ["watch", "track", "compare", "review", "stress", "monitor", "next"])
    ]
    return _dedupe_preserve_order(sentences, limit=3)


def _render_structured_fallback_report(
    *,
    summary: str,
    key_findings: list[str],
    suggestions: list[str],
    cleaned_sections: list[tuple[str, str]],
) -> str:
    findings_block = "\n".join(f"- {item}" for item in key_findings if item) or "- None recorded"
    suggestions_block = "\n".join(f"- {item}" for item in suggestions if item) or "- Review the detailed analysis and decide whether the issue needs a follow-up run."
    section_blocks: list[str] = []
    for key, section in cleaned_sections:
        label = key.strip().upper()
        if len(cleaned_sections) == 1:
            label = "Company analysis"
        section_blocks.append(f"### {label.title()}\n\n{section.strip()}")

    detail_block = "\n\n".join(block for block in section_blocks if block.strip())
    parts = [
        "## Executive Summary",
        summary.strip() or "Research completed. Review the detailed analysis.",
        "",
        "## Key Findings",
        findings_block,
        "",
        "## Agent Suggestions",
        suggestions_block,
    ]
    if detail_block:
        parts.extend(["", "## Detailed Analysis", detail_block])
    return "\n".join(parts).strip()


def _statement_row_count(financials: dict, key: str) -> int:
    rows = (financials or {}).get(key) or []
    return len(rows) if isinstance(rows, list) else 0


def _agent_config_attr(agent_config: Any, name: str, default: Any = None) -> Any:
    return getattr(agent_config, name, default)


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
                    role_key=_agent_config_attr(agent_config, "role_key"),
                    role_title=(
                        _agent_config_attr(agent_config, "role_title")
                        or _agent_config_attr(agent_config, "name")
                    ),
                    role_family=_agent_config_attr(agent_config, "role_family"),
                    description=_agent_config_attr(agent_config, "description"),
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
        *,
        role_key: Optional[str] = None,
        role_title: Optional[str] = None,
        role_family: Optional[str] = None,
        description: Optional[str] = None,
    ) -> tuple[dict, list]:
        """
        Instruction-driven analysis for hired agents.
        Fetches real financial data + current news per ticker, then runs a
        focused LLM call shaped by the agent's own instruction — not generic
        pillar math. This is what makes a hired analyst actually do its job.
        """
        from data.financial_data import FinancialDataFetcher
        from shared.web_research import WebResearchService

        outputs: dict[str, str] = {}
        fetcher = FinancialDataFetcher()
        web_research = WebResearchService()
        role_profile = resolve_role_prompt_profile(
            template=template,
            role_key=role_key,
            role_title=role_title,
            description=description,
        )
        intent_profile = infer_research_intent(instruction, tickers)
        role_family_label = (role_family or "").strip()
        assignment_scope = "multi-company / theme work" if (
            intent_profile.key in {"industry_map", "peer_comparison"}
            or len([ticker for ticker in tickers if str(ticker).strip().upper() != "GENERAL"]) > 1
        ) else "single-company work"

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

                # Current market context with source URLs and extracted snippets.
                browser_context = ""
                try:
                    focus = instruction[:150] if instruction else "fundamentals and investment thesis"
                    browser_context = web_research.research_text(
                        (
                            f"{ticker_upper} {role_profile.web_query_hint} "
                            f"{intent_profile.search_hint} {focus}"
                        ),
                        topic="finance",
                        max_results=4,
                        extract_top_k=2,
                        time_range="month",
                    )
                except Exception as _e:
                    logger.warning(f"Web research failed for {ticker_upper}: {_e}")

                browser_section = f"\nCURRENT WEB RESEARCH:\n{browser_context}" if browser_context else ""

                comparative_rule = ""
                if assignment_scope == "multi-company / theme work":
                    comparative_rule = (
                        "- This is part of a broader industry/theme or peer assignment. "
                        "Explain how this company fits into the wider map and what should be compared across the full set.\n"
                    )

                prompt = f"""You are the {role_profile.title}.

ROLE FAMILY: {role_family_label or "coverage"}
ROLE MANDATE: {role_profile.mandate}
ANALYST LENS: {role_profile.lens}

ISSUE INTENT: {intent_profile.title}
INTENT MANDATE: {intent_profile.mandate}
ASSIGNMENT SCOPE: {assignment_scope}

USER ASSIGNMENT:

{instruction or f"Provide a comprehensive {role_profile.title.lower()} analysis."}

TICKER: {ticker_upper}
COMPANY: {stock_info.get("company_name", ticker_upper)}
SECTOR: {stock_info.get("sector", "Unknown")}

ROLE FOCUS QUESTIONS:
{format_bullets(role_profile.focus_questions)}

HISTORICAL FINANCIALS:
{data_block}{browser_section}

Interpret the assignment as an investment research mandate. Do not copy the user's raw wording into the report.
Write a polished analyst report that directly answers the mandate.

Required markdown sections:
{format_required_sections(intent_profile)}

Rules:
- Lead with your investment signal (BULLISH / BEARISH / NEUTRAL) and the single most important reason.
- Support every claim with specific numbers from the data.
- Use the web research context for recent developments, catalysts, competitive context, and source-backed watch items.
- Cite source titles or URLs briefly when web context materially affects the conclusion.
- In Agent Suggestions, include 3-5 follow-up angles the user may not have asked for but should consider based on the numbers, risks, or peer comparison.
- {role_profile.report_emphasis}
{comparative_rule}- Do not include internal fields such as task type, priority, assignment text, current issue, or resolved scope.
- Do not use filler, preamble, or process narration.
- 500-800 words."""

                response = self._anthropic.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60.0,
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

        return outputs, [role_key or template] if outputs else []

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

        last_summary = _agent_config_attr(agent_config, "last_run_summary", "") or ""
        instruction = _agent_config_attr(agent_config, "instruction", "") or ""
        raw_tickers = _agent_config_attr(agent_config, "tickers", "[]")
        tickers = json.loads(raw_tickers or "[]") if isinstance(raw_tickers, str) else (raw_tickers or [])
        role_profile = resolve_role_prompt_profile(
            template=_agent_config_attr(agent_config, "template", ""),
            role_key=_agent_config_attr(agent_config, "role_key"),
            role_title=(
                _agent_config_attr(agent_config, "role_title")
                or _agent_config_attr(agent_config, "name")
            ),
            description=_agent_config_attr(agent_config, "description"),
        )
        intent_profile = infer_research_intent(instruction, tickers)
        raw_topics = _agent_config_attr(agent_config, "topics", "[]")
        topics = json.loads(raw_topics or "[]") if isinstance(raw_topics, str) else (raw_topics or [])
        topics_str = ", ".join(topics) if topics else ""

        prompt = f"""You are synthesizing investment research findings for a retail investor.

AGENT ROLE: {role_profile.title}
ROLE MANDATE: {role_profile.mandate}
ROLE LENS: {role_profile.lens}
ANALYSIS INTENT: {intent_profile.title}
INTENT MANDATE: {intent_profile.mandate}
REQUIRED REPORT SECTIONS:
{format_required_sections(intent_profile)}

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
  "full_report": "A polished markdown investment research report written from the {role_profile.title} lens. Use the required sections above, preserve role-specific analysis, and include a compact comparison table when multiple companies or an industry/theme are covered. In Agent Suggestions, add 3-5 follow-up angles the user may not have asked for but should consider based on the numbers, risks, or comparisons. Use real numbers. Do not quote the raw user request. Do not include task type, priority, current issue, resolved scope, or internal process notes. No emojis. No ASCII borders."
}}

Return ONLY the JSON object — no preamble, no explanation."""

        try:
            response = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                timeout=90.0,
            )
            text = response.content[0].text.strip()
            parsed = _extract_json_object(text)
            if parsed is None:
                raise ValueError("Synthesis response did not contain valid JSON")
            return parsed
        except Exception as exc:
            logger.error(f"Synthesis Haiku call failed: {exc}")
            cleaned_sections: list[tuple[str, str]] = []
            all_findings: list[str] = []
            all_suggestions: list[str] = []
            summaries: list[str] = []

            for key, value in raw_outputs.items():
                cleaned = _clean_report_for_display(value, key)
                if not cleaned:
                    continue
                cleaned_sections.append((key, cleaned))
                summary = _extract_summary_from_report(cleaned)
                if summary:
                    summaries.append(summary)
                all_findings.extend(_extract_key_findings_from_report(cleaned))
                all_suggestions.extend(_extract_suggestions_from_report(cleaned))

            deduped_findings = _dedupe_preserve_order(all_findings, limit=5)
            deduped_suggestions = _dedupe_preserve_order(all_suggestions, limit=4)

            if len(cleaned_sections) == 1:
                fallback_report = _render_structured_fallback_report(
                    summary=summaries[0] if summaries else "Research completed. Review the saved analyst output.",
                    key_findings=deduped_findings,
                    suggestions=deduped_suggestions,
                    cleaned_sections=cleaned_sections,
                )
                fallback_summary = summaries[0] if summaries else "Research completed. Review the saved analyst output."
            else:
                fallback_summary = (
                    "Research completed across multiple analyst inputs. "
                    + (summaries[0] if summaries else "Review the saved analyst output for the consolidated view.")
                )
                fallback_report = _render_structured_fallback_report(
                    summary=fallback_summary,
                    key_findings=deduped_findings,
                    suggestions=deduped_suggestions,
                    cleaned_sections=cleaned_sections,
                )

            return {
                "summary": fallback_summary,
                "key_findings": deduped_findings,
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
