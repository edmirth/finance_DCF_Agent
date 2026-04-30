"""
Role catalog for the finance-team control plane.

User-facing hires should look like firm seats, not raw execution templates.
Each role maps to the internal engine template that actually performs the work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AgentRoleDefinition:
    key: str
    title: str
    family: str
    template: str
    description: str
    requires_tickers: bool = True


ROLE_CATALOG: dict[str, AgentRoleDefinition] = {
    "generalist_analyst": AgentRoleDefinition(
        key="generalist_analyst",
        title="Generalist Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Generalist single-name coverage analyst.",
    ),
    "semis_analyst": AgentRoleDefinition(
        key="semis_analyst",
        title="Semis Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Semiconductor coverage analyst.",
    ),
    "software_analyst": AgentRoleDefinition(
        key="software_analyst",
        title="Software Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Enterprise and application software coverage analyst.",
    ),
    "financials_analyst": AgentRoleDefinition(
        key="financials_analyst",
        title="Financials Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Banks, insurers, exchanges, and diversified financials coverage analyst.",
    ),
    "healthcare_analyst": AgentRoleDefinition(
        key="healthcare_analyst",
        title="Healthcare Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Healthcare and life-sciences coverage analyst.",
    ),
    "consumer_analyst": AgentRoleDefinition(
        key="consumer_analyst",
        title="Consumer Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Consumer internet, retail, and staples coverage analyst.",
    ),
    "industrials_analyst": AgentRoleDefinition(
        key="industrials_analyst",
        title="Industrials Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Industrials and capital-goods coverage analyst.",
    ),
    "energy_analyst": AgentRoleDefinition(
        key="energy_analyst",
        title="Energy Analyst",
        family="sector_coverage",
        template="fundamental_analyst",
        description="Energy, utilities, and commodity-linked coverage analyst.",
    ),
    "earnings_analyst": AgentRoleDefinition(
        key="earnings_analyst",
        title="Earnings Analyst",
        family="event_driven",
        template="earnings_watcher",
        description="Tracks and interprets earnings results and guidance changes.",
    ),
    "portfolio_analyst": AgentRoleDefinition(
        key="portfolio_analyst",
        title="Portfolio Analyst",
        family="portfolio",
        template="portfolio_heartbeat",
        description="Monitors cross-position portfolio health and concentration.",
    ),
    "thesis_monitor": AgentRoleDefinition(
        key="thesis_monitor",
        title="Thesis Monitor",
        family="monitoring",
        template="thesis_guardian",
        description="Monitors a thesis for evidence that it is holding or breaking.",
    ),
    "quant_strategist": AgentRoleDefinition(
        key="quant_strategist",
        title="Quant Strategist",
        family="central_research",
        template="quant_analyst",
        description="Tracks revisions, momentum, volatility, and factor behavior.",
    ),
    "risk_manager": AgentRoleDefinition(
        key="risk_manager",
        title="Risk Manager",
        family="risk",
        template="risk_analyst",
        description="Monitors downside scenarios, balance-sheet risk, and stress conditions.",
    ),
    "macro_strategist": AgentRoleDefinition(
        key="macro_strategist",
        title="Macro Strategist",
        family="macro",
        template="market_pulse",
        description="Monitors the rates, policy, and macro backdrop for the team.",
        requires_tickers=False,
    ),
    "market_narrative_analyst": AgentRoleDefinition(
        key="market_narrative_analyst",
        title="Market Narrative Analyst",
        family="central_research",
        template="sentiment_analyst",
        description="Tracks positioning, narrative shifts, and sell-side tone.",
    ),
}


TEMPLATE_FALLBACK_ROLES: dict[str, AgentRoleDefinition] = {
    "earnings_watcher": ROLE_CATALOG["earnings_analyst"],
    "market_pulse": ROLE_CATALOG["macro_strategist"],
    "thesis_guardian": ROLE_CATALOG["thesis_monitor"],
    "portfolio_heartbeat": ROLE_CATALOG["portfolio_analyst"],
    "firm_pipeline": AgentRoleDefinition(
        key="investment_pipeline",
        title="Investment Pipeline",
        family="portfolio_management",
        template="firm_pipeline",
        description="Runs the multi-stage investment pipeline.",
    ),
    "fundamental_analyst": ROLE_CATALOG["generalist_analyst"],
    "quant_analyst": ROLE_CATALOG["quant_strategist"],
    "risk_analyst": ROLE_CATALOG["risk_manager"],
    "macro_analyst": ROLE_CATALOG["macro_strategist"],
    "sentiment_analyst": ROLE_CATALOG["market_narrative_analyst"],
}


def validate_role_key(role_key: str) -> str:
    normalized = (role_key or "").strip()
    if normalized not in ROLE_CATALOG:
        raise ValueError(f"Invalid role_key. Must be one of: {sorted(ROLE_CATALOG)}")
    return normalized


def get_role_definition(role_key: str) -> AgentRoleDefinition:
    return ROLE_CATALOG[validate_role_key(role_key)]


def resolve_role_definition(
    role_key: Optional[str] = None,
    template: Optional[str] = None,
) -> Optional[AgentRoleDefinition]:
    if role_key:
        return get_role_definition(role_key)
    if template:
        return TEMPLATE_FALLBACK_ROLES.get(template)
    return None


def infer_role_identity(
    *,
    role_key: Optional[str],
    role_title: Optional[str],
    role_family: Optional[str],
    template: str,
) -> dict[str, Optional[str]]:
    role = resolve_role_definition(role_key=role_key, template=template)
    return {
        "role_key": role.key if role else role_key,
        "role_title": role_title or (role.title if role else template.replace("_", " ").title()),
        "role_family": role_family or (role.family if role else None),
        "template": template if not role else role.template if role_key else template,
    }
