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


def _extract_financial_charts(
    ticker: str,
    stock_info: dict,
    financials: dict,
    key_metrics: Optional[dict],
) -> list[dict]:
    """
    Generate dark-themed chart specs from raw financial data.
    Returns a list of AgentChartProps-compatible dicts (serialisable to JSON).
    Only includes charts that have at least 3 data points.
    """
    charts: list[dict] = []

    income = financials.get("income_statements") or []
    cashflow = financials.get("cash_flow_statements") or []

    # Sort ascending by report_period so charts read left-to-right chronologically.
    income_sorted = sorted(
        [r for r in income if isinstance(r, dict) and r.get("report_period")],
        key=lambda r: r["report_period"],
    )[-8:]

    cf_sorted = sorted(
        [r for r in cashflow if isinstance(r, dict) and r.get("report_period")],
        key=lambda r: r["report_period"],
    )[-8:]

    # ── Chart 1: Revenue + Gross Margin (bar_line) ──────────────────────────
    rev_margin_rows: list[dict] = []
    for row in income_sorted:
        rev = row.get("revenue")
        gp = row.get("gross_profit")
        if not rev or not gp:
            continue
        try:
            rev_margin_rows.append({
                "period": row["report_period"][:7],
                "revenue": round(float(rev) / 1e6, 1),
                "gross_margin": round(float(gp) / float(rev) * 100, 1),
            })
        except (ZeroDivisionError, TypeError, ValueError):
            continue

    if len(rev_margin_rows) >= 3:
        charts.append({
            "id": f"{ticker}_revenue_margin",
            "chart_type": "bar_line",
            "title": f"{ticker} — Revenue & Gross Margin",
            "subtitle": "Annual, $M",
            "x_key": "period",
            "y_format": "currency_m",
            "y_right_format": "percent",
            "data": rev_margin_rows,
            "series": [
                {"key": "revenue", "label": "Revenue ($M)", "type": "bar", "color": "#E8522A", "yAxis": "left"},
                {"key": "gross_margin", "label": "Gross Margin %", "type": "line", "color": "#3B82F6", "yAxis": "right"},
            ],
        })

    # ── Chart 2: Net Income trend (bar) ─────────────────────────────────────
    net_income_rows: list[dict] = []
    for row in income_sorted:
        ni = row.get("net_income")
        if ni is None:
            continue
        try:
            net_income_rows.append({
                "period": row["report_period"][:7],
                "net_income": round(float(ni) / 1e6, 1),
            })
        except (TypeError, ValueError):
            continue

    if len(net_income_rows) >= 3:
        charts.append({
            "id": f"{ticker}_net_income",
            "chart_type": "bar",
            "title": f"{ticker} — Net Income",
            "subtitle": "Annual, $M",
            "x_key": "period",
            "y_format": "currency_m",
            "data": net_income_rows,
            "series": [
                {"key": "net_income", "label": "Net Income ($M)", "type": "bar", "color": "#A78BFA", "yAxis": "left"},
            ],
        })

    # ── Chart 3: Operating Cash Flow (bar) ──────────────────────────────────
    ocf_rows: list[dict] = []
    for row in cf_sorted:
        ocf = row.get("operating_cash_flow")
        if ocf is None:
            continue
        try:
            ocf_rows.append({
                "period": row["report_period"][:7],
                "operating_cash_flow": round(float(ocf) / 1e6, 1),
            })
        except (TypeError, ValueError):
            continue

    if len(ocf_rows) >= 3:
        charts.append({
            "id": f"{ticker}_fcf",
            "chart_type": "bar",
            "title": f"{ticker} — Operating Cash Flow",
            "subtitle": "Annual, $M",
            "x_key": "period",
            "y_format": "currency_m",
            "data": ocf_rows,
            "series": [
                {"key": "operating_cash_flow", "label": "Operating Cash Flow ($M)", "type": "bar", "color": "#10B981", "yAxis": "left"},
            ],
        })

    return charts


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
            chart_specs_list: list[dict] = []

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
                raw_outputs, agents_used, chart_specs_list = self._run_instruction_driven_research(
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
                "hire_proposal": synthesis.get("hire_proposal"),
                "chart_specs": chart_specs_list,
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
    ) -> tuple[dict, list, list[dict]]:
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
        system_prompt_override: Optional[str] = (
            getattr(agent_config, "system_prompt_override", None) or None
        )
        role_profile = resolve_role_prompt_profile(
            template=template,
            role_key=role_key,
            role_title=role_title,
            description=description,
        )
        intent_profile = infer_research_intent(instruction, tickers)
        role_family_label = (role_family or "").strip()
        concrete_tickers = [t for t in tickers if str(t).strip().upper() != "GENERAL"]
        assignment_scope = "multi-company / theme work" if (
            not concrete_tickers
            or intent_profile.key in {"industry_map", "peer_comparison"}
            or len(concrete_tickers) > 1
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

        def _analyze_general_screen() -> tuple[str, Optional[str], list[dict]]:
            """Handle screening/discovery requests where no specific ticker is set."""
            try:
                focus = instruction[:200] if instruction else "investment opportunities"
                screen_context = ""
                try:
                    screen_context = web_research.research_text(
                        f"{role_profile.web_query_hint} {focus} {intent_profile.search_hint}",
                        topic="finance",
                        max_results=6,
                        extract_top_k=3,
                        time_range="month",
                    )
                except Exception as _e:
                    logger.warning(f"Web research failed for GENERAL screen: {_e}")

                browser_section = f"\nCURRENT WEB RESEARCH:\n{screen_context}" if screen_context else ""
                prompt = f"""You are the {role_profile.title}.

ROLE FAMILY: {role_family_label or "coverage"}
ROLE MANDATE: {role_profile.mandate}
ANALYST LENS: {role_profile.lens}

ISSUE INTENT: {intent_profile.title}
ASSIGNMENT SCOPE: universe / theme screen — no single company in scope

USER ASSIGNMENT:

{instruction or f"Identify investment opportunities matching the mandate above."}
{browser_section}

This is a universe or theme-level screening request. Your job is to produce a structured
candidate identification report.

Rules:
- Use the web research above as your primary data source for naming and ranking candidates.
- Do NOT fabricate financial figures. If you cite a metric (revenue, P/E, margin), it must
  appear in the web research context above. If you cannot source a figure, say "verify via run."
- Produce a ranked shortlist of 5-8 candidates with a 1-2 sentence thesis per name and
  the screening criteria each satisfies.
- Conclude with an "Agent Suggestions" section listing 3-5 specific tickers the user should
  run a per-ticker deep-dive analysis on next.
- Do not include internal fields such as task type, priority, or resolved scope.
- 400-700 words."""

                response = self._anthropic.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60.0,
                )
                return "SCREEN", response.content[0].text.strip(), []
            except Exception as exc:
                logger.error(f"General screen analysis failed: {exc}")
                return "SCREEN", None, []

        # Templates whose instruments (indices, FX, rates, commodities) have no
        # equity financials in Financial Datasets.  Skip the equity fetch/validation
        # gate and drive the report entirely from web research.
        _WEBRESEARCH_ONLY_TEMPLATES = {"macro_analyst", "sentiment_analyst"}

        def _analyze_macro(ticker_upper: str) -> tuple[str, Optional[str], list[dict]]:
            """Web-research + FRED-driven analysis for macro instruments and sentiment tickers."""
            try:
                from data.fred_client import get_fred_client
                focus = instruction[:200] if instruction else f"{ticker_upper} analysis"

                # --- FRED hard data ---
                fred_block = ""
                try:
                    fred_block = get_fred_client().get_macro_context_block(ticker_upper)
                except Exception as _e:
                    logger.warning(f"FRED fetch failed for {ticker_upper}: {_e}")

                # --- Tavily narrative context ---
                macro_context = ""
                try:
                    macro_context = web_research.research_text(
                        (
                            f"{ticker_upper} {role_profile.web_query_hint} "
                            f"{intent_profile.search_hint} {focus}"
                        ),
                        topic="finance",
                        max_results=6,
                        extract_top_k=3,
                        time_range="month",
                    )
                except Exception as _e:
                    logger.warning(f"Web research failed for macro ticker {ticker_upper}: {_e}")

                fred_section = f"\nLIVE MACRO DATA (FRED):\n{fred_block}" if fred_block else ""
                browser_section = f"\nCURRENT WEB RESEARCH:\n{macro_context}" if macro_context else ""

                if system_prompt_override:
                    prompt = (
                        f"{system_prompt_override}\n\n"
                        f"INSTRUMENT: {ticker_upper}"
                        f"{fred_section}"
                        f"{browser_section}"
                    )
                else:
                    prompt = f"""You are the {role_profile.title}.

ROLE FAMILY: {role_family_label or "macro"}
ROLE MANDATE: {role_profile.mandate}
ANALYST LENS: {role_profile.lens}

ISSUE INTENT: {intent_profile.title}
INTENT MANDATE: {intent_profile.mandate}
ASSIGNMENT SCOPE: macro / market-level analysis

USER ASSIGNMENT:

{instruction or f"Provide a comprehensive macro analysis for {ticker_upper}."}

INSTRUMENT: {ticker_upper}
{fred_section}
{browser_section}

You are analyzing a macro instrument, market index, currency, commodity, or rate —
NOT a single equity. Do not look for income statements or balance sheets.

ROLE FOCUS QUESTIONS:
{format_bullets(role_profile.focus_questions)}

Rules:
- Use FRED data above for hard numbers (yields, spreads, CPI, payrolls, etc.).
  Cite specific values when making rate or inflation claims.
- Use the web research for narrative context, recent events, and forward guidance.
- If the assignment asks for correlations, tables, or multi-instrument comparisons,
  build them from the FRED figures. If a figure is unavailable, say so explicitly.
- Lead with the most actionable macro signal (RISK-ON / RISK-OFF / NEUTRAL) and why.
- In Agent Suggestions, include 3-5 follow-up angles or instruments the user should examine.
- {role_profile.report_emphasis}
- Do not include internal fields such as task type, priority, or resolved scope.
- 400-700 words."""

                response = self._anthropic.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60.0,
                )
                return ticker_upper, response.content[0].text.strip(), []
            except Exception as exc:
                logger.error(f"Macro analysis failed for {ticker_upper}: {exc}")
                return ticker_upper, None, []

        def _analyze(ticker: str) -> tuple[str, Optional[str], list[dict]]:
            try:
                ticker_upper = ticker.strip().upper()

                if ticker_upper == "GENERAL":
                    return _analyze_general_screen()

                if template in _WEBRESEARCH_ONLY_TEMPLATES:
                    return _analyze_macro(ticker_upper)

                stock_info = fetcher.get_stock_info(ticker_upper) or {}
                financials = fetcher.get_financial_statements(ticker_upper) or {}
                key_metrics = fetcher.get_key_metrics(ticker_upper) or {}
                validation_error = _validation_error(ticker_upper, stock_info, financials, key_metrics)
                if validation_error:
                    logger.warning("Instruction-driven research blocked for %s: %s", ticker_upper, validation_error)
                    return ticker_upper, None, []

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

                if system_prompt_override:
                    prompt = (
                        f"{system_prompt_override}\n\n"
                        f"TICKER: {ticker_upper}\n"
                        f"COMPANY: {stock_info.get('company_name', ticker_upper)}\n"
                        f"SECTOR: {stock_info.get('sector', 'Unknown')}\n\n"
                        f"HISTORICAL FINANCIALS:\n{data_block}"
                        f"{browser_section}"
                    )
                else:
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
                charts = _extract_financial_charts(ticker_upper, stock_info, financials, key_metrics)
                return ticker_upper, response.content[0].text.strip(), charts

            except Exception as exc:
                logger.error(f"Instruction-driven research failed for {ticker}: {exc}")
                return ticker.strip().upper(), None, []

        all_chart_specs: list[dict] = []
        effective_tickers = tickers if tickers else ["GENERAL"]
        with ThreadPoolExecutor(max_workers=min(MAX_TICKER_WORKERS, len(effective_tickers))) as ex:
            futures = {ex.submit(_analyze, t): t for t in effective_tickers}
            for future in as_completed(futures):
                ticker_sym, result, charts = future.result()
                if result:
                    outputs[ticker_sym] = result
                all_chart_specs.extend(charts)

        return outputs, [role_key or template] if outputs else [], all_chart_specs

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
        def _to_str(v) -> str:
            if isinstance(v, list):
                return "\n\n".join(str(item).strip() for item in v if item)
            return str(v) if v is not None else ""

        sections = "\n\n".join(
            f"### {key}\n{_to_str(value)[:3000]}"  # cap per section to keep prompt manageable
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

        shared_context = f"""AGENT ROLE: {role_profile.title}
ROLE MANDATE: {role_profile.mandate}
ROLE LENS: {role_profile.lens}
ANALYSIS INTENT: {intent_profile.title}
INTENT MANDATE: {intent_profile.mandate}

INVESTOR INSTRUCTION / THESIS:
{instruction or "No specific instruction — provide general findings."}
{f"FOCUS TOPICS: {topics_str}" if topics_str else ""}

PREVIOUS RUN SUMMARY (for detecting material changes):
{last_summary or "No previous run — this is the first run."}

AGENT RESEARCH OUTPUTS:
{sections}"""

        # --- Call 1: small structured JSON (no freeform text → no newline escaping issues) ---
        meta_prompt = f"""{shared_context}

Produce a JSON object with ONLY these four keys — no other text:
{{
  "summary": "2-3 sentence plain-English digest of the most important findings",
  "key_findings": ["finding 1", "finding 2", "finding 3"],
  "material_change": true,
  "alert_level": "high"
}}

Rules:
- summary: one escaped string, no newlines inside the value
- key_findings: array of short strings (one line each, no embedded newlines)
- material_change: JSON boolean (true/false)
- alert_level: one of "high", "medium", "low", "none"
Return ONLY the JSON object — no preamble, no explanation, no markdown fences."""

        # --- Call 2: full report as plain markdown (no JSON quoting needed) ---
        report_prompt = f"""{shared_context}

REQUIRED REPORT SECTIONS:
{format_required_sections(intent_profile)}

Write a polished markdown investment research report from the {role_profile.title} lens.
- Use the required sections above.
- Include a compact comparison table when multiple companies or a theme are covered.
- In Agent Suggestions, add 3-5 follow-up angles based on the numbers, risks, or comparisons.
- Use real numbers. No emojis. No ASCII borders.
- Do not quote the raw user request or include internal process notes.
- 400-700 words.
Return ONLY the markdown report — no JSON, no preamble."""

        try:
            meta_response = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": meta_prompt}],
                timeout=60.0,
            )
            meta_text = meta_response.content[0].text.strip()
            parsed = _extract_json_object(meta_text)
            if parsed is None:
                raise ValueError("Synthesis response did not contain valid JSON")

            # Sanitize: Haiku occasionally returns string fields as arrays
            for _str_field in ("summary",):
                _val = parsed.get(_str_field)
                if isinstance(_val, list):
                    parsed[_str_field] = " ".join(str(v).strip() for v in _val if v)
                elif _val is not None and not isinstance(_val, str):
                    parsed[_str_field] = str(_val)
            raw_findings = parsed.get("key_findings") or []
            parsed["key_findings"] = [
                str(item).strip()
                for item in (raw_findings if isinstance(raw_findings, list) else [])
                if str(item).strip()
            ]

            # Fetch the full report separately as plain markdown
            report_response = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": report_prompt}],
                timeout=90.0,
            )
            parsed["full_report"] = report_response.content[0].text.strip()
            parsed["hire_proposal"] = self._maybe_propose_hire(shared_context, agent_config)
            return parsed
        except Exception as exc:
            logger.error(f"Synthesis Haiku call failed: {exc}")
            cleaned_sections: list[tuple[str, str]] = []
            all_findings: list[str] = []
            all_suggestions: list[str] = []
            summaries: list[str] = []

            for key, value in raw_outputs.items():
                cleaned = _clean_report_for_display(_to_str(value), key)
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
                "hire_proposal": None,
            }

    def _maybe_propose_hire(self, shared_context: str, agent_config) -> Optional[dict]:
        """
        Ask the agent whether it needs to propose hiring a direct-report specialist.
        Only runs for properly role-keyed agents. Returns a hire spec dict or None.
        """
        agent_role_key = _agent_config_attr(agent_config, "role_key") or ""
        agent_id = _agent_config_attr(agent_config, "id") or ""
        if not agent_role_key or not agent_id:
            return None

        from backend.agent_roles import ROLE_CATALOG
        role_catalog_lines = "\n".join(
            f"- {role.key}: {role.title} ({role.family})"
            for role in ROLE_CATALOG.values()
        )

        hire_prompt = f"""{shared_context}

You are {_agent_config_attr(agent_config, "role_title") or agent_role_key}. Based on the research above, decide if you need to propose hiring ONE direct-report specialist under you.

AVAILABLE ROLES:
{role_catalog_lines}

Rules (strict — default is null):
- Only propose if findings reveal a PERSISTENT gap that recurs every run and you cannot fill it alone
- The proposed role must clearly complement your mandate, not duplicate it
- Do NOT propose if you could cover the gap yourself with a different instruction
- Do NOT propose a role that already sounds like your own role
- When in doubt, return null

If proposing, return JSON:
{{
  "propose_hire": {{
    "role_key": "<valid key from the list above>",
    "role_title": "<title>",
    "name": "<specific name, e.g. 'NVDA Risk Monitor'>",
    "description": "<one sentence>",
    "tickers": ["TICKER"],
    "topics": ["topic"],
    "instruction": "<clear mandate, 2-4 sentences>",
    "schedule_label": "weekly_monday"
  }}
}}

If NOT proposing (the default):
{{"propose_hire": null}}

Return ONLY valid JSON. No preamble, no markdown fences."""

        try:
            response = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": hire_prompt}],
                timeout=30.0,
            )
            parsed = _extract_json_object(response.content[0].text.strip())
            if not parsed or not parsed.get("propose_hire"):
                return None
            proposal = parsed["propose_hire"]
            proposal["manager_agent_id"] = agent_id
            return proposal
        except Exception as exc:
            logger.warning("Hire proposal LLM call failed: %s", exc)
            return None

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
            "chart_specs": [],
            "error": error,
        }


# Singleton
_runner: Optional[AgentRunnerService] = None


def get_runner() -> AgentRunnerService:
    global _runner
    if _runner is None:
        _runner = AgentRunnerService()
    return _runner
