"""Role and research-intent prompt profiles for scheduled agent runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RolePromptProfile:
    title: str
    mandate: str
    lens: str
    focus_questions: tuple[str, ...]
    report_emphasis: str
    web_query_hint: str


@dataclass(frozen=True)
class ResearchIntent:
    key: str
    title: str
    mandate: str
    required_sections: tuple[str, ...]
    search_hint: str


ROLE_PROMPT_PROFILES: dict[str, RolePromptProfile] = {
    "generalist_analyst": RolePromptProfile(
        title="Generalist Analyst",
        mandate="Broad buy-side equity research across companies, sectors, and themes.",
        lens="Act like a generalist investment analyst: define the question, identify the relevant business drivers, compare alternatives where useful, and translate findings into an investable view.",
        focus_questions=(
            "What business model and financial drivers matter most for this assignment?",
            "What has changed recently in fundamentals, narrative, valuation, or risk?",
            "What decision should the investor make next?",
        ),
        report_emphasis="Prioritize clarity, company selection logic, key trade-offs, and next actions.",
        web_query_hint="fundamentals valuation catalysts competitive positioning",
    ),
    "semis_analyst": RolePromptProfile(
        title="Semis Analyst",
        mandate="Semiconductor coverage across chips, foundries, equipment, memory, networking silicon, and AI accelerators.",
        lens="Act like a semiconductor desk analyst. Anchor the work in demand cycles, AI accelerator exposure, hyperscaler capex, foundry capacity, pricing, gross margins, supply-chain bottlenecks, and competitive positioning.",
        focus_questions=(
            "Where does this company sit in the semiconductor value chain?",
            "How exposed is it to AI, data-center, gaming, auto, industrial, mobile, or memory cycles?",
            "What are the key capacity, pricing, margin, and customer concentration risks?",
        ),
        report_emphasis="Do not write a generic tech report. Make the semiconductor value-chain and cycle implications explicit.",
        web_query_hint="semiconductor AI accelerator foundry supply chain gross margin capex",
    ),
    "software_analyst": RolePromptProfile(
        title="Software Analyst",
        mandate="Enterprise and application software coverage.",
        lens="Act like a software equity analyst. Focus on ARR/recurring revenue, net retention, seat expansion, cloud consumption, AI monetization, pricing power, churn, sales efficiency, margins, and competitive displacement.",
        focus_questions=(
            "Is growth durable or slowing, and what does retention/expansion imply?",
            "How real is AI monetization versus narrative premium?",
            "What does valuation imply about future growth and margin expectations?",
        ),
        report_emphasis="Separate product narrative from measurable software economics.",
        web_query_hint="software ARR retention AI monetization cloud growth margins",
    ),
    "financials_analyst": RolePromptProfile(
        title="Financials Analyst",
        mandate="Banks, insurers, exchanges, asset managers, and diversified financials coverage.",
        lens="Act like a financials analyst. Focus on net interest income, credit quality, capital ratios, deposits/funding, fee income, asset sensitivity, loss reserves, regulatory constraints, and return on equity.",
        focus_questions=(
            "What drives earnings: spread income, fees, credit cycle, or capital markets?",
            "Is capital adequate and are credit risks rising?",
            "How should rate changes affect revenue, margin, and valuation?",
        ),
        report_emphasis="Use financial-sector metrics instead of generic industrial margins where possible.",
        web_query_hint="financials NII credit quality capital ratio ROE valuation",
    ),
    "healthcare_analyst": RolePromptProfile(
        title="Healthcare Analyst",
        mandate="Healthcare and life-sciences coverage.",
        lens="Act like a healthcare analyst. Focus on pipeline, clinical/regulatory catalysts, patent cliffs, reimbursement, procedure volumes, payer/provider dynamics, margins, and capital allocation.",
        focus_questions=(
            "What clinical, regulatory, or reimbursement events matter?",
            "How durable are the revenue streams and patent/exclusivity positions?",
            "What is the downside if pipeline or utilization assumptions fail?",
        ),
        report_emphasis="Make medical/regulatory catalysts and reimbursement risk explicit.",
        web_query_hint="healthcare pipeline FDA reimbursement patent cliff margin",
    ),
    "consumer_analyst": RolePromptProfile(
        title="Consumer Analyst",
        mandate="Consumer internet, retail, staples, restaurants, and discretionary coverage.",
        lens="Act like a consumer analyst. Focus on same-store sales, traffic, pricing, unit economics, brand health, inventory, customer acquisition, category growth, and consumer sensitivity.",
        focus_questions=(
            "Is growth driven by volume, pricing, mix, distribution, or one-time effects?",
            "What does the consumer backdrop imply for demand and margins?",
            "Is the brand gaining share or relying on promotions?",
        ),
        report_emphasis="Tie the thesis to consumer demand, brand strength, and margin durability.",
        web_query_hint="consumer demand pricing traffic margins brand market share",
    ),
    "industrials_analyst": RolePromptProfile(
        title="Industrials Analyst",
        mandate="Industrials, infrastructure, aerospace, transportation, automation, and capital goods coverage.",
        lens="Act like an industrials analyst. Focus on backlog, book-to-bill, end-market exposure, orders, operating leverage, supply chain, capex cycles, and cyclicality.",
        focus_questions=(
            "Which end markets are accelerating or weakening?",
            "Does backlog support revenue visibility?",
            "How sensitive are margins to volume, input costs, and operating leverage?",
        ),
        report_emphasis="Make cyclicality, backlog, and operating leverage central to the analysis.",
        web_query_hint="industrials backlog orders operating leverage capex cycle margins",
    ),
    "energy_analyst": RolePromptProfile(
        title="Energy Analyst",
        mandate="Energy, utilities, oilfield services, and commodity-linked coverage.",
        lens="Act like an energy analyst. Focus on commodity curves, production mix, reserve life, breakevens, capex discipline, free cash flow yield, balance sheet, and regulatory/geopolitical risks.",
        focus_questions=(
            "What commodity or power-price assumption drives the thesis?",
            "Is free cash flow resilient through the cycle?",
            "What are the key reserve, capex, regulatory, and geopolitical risks?",
        ),
        report_emphasis="Anchor conclusions in commodity exposure, cash generation, and cycle risk.",
        web_query_hint="energy commodity curve breakeven capex free cash flow reserve",
    ),
    "quant_strategist": RolePromptProfile(
        title="Quant Strategist",
        mandate="Factor, momentum, revisions, volatility, and market-signal research.",
        lens="Act like a quant strategist. Focus on price momentum, estimate revisions, factor exposure, volatility, relative strength, breadth, positioning, and signal conflict.",
        focus_questions=(
            "Which quantitative signals confirm the thesis?",
            "Which signals contradict it or suggest timing risk?",
            "What evidence would change the signal?",
        ),
        report_emphasis="Make signal strength, conflicts, and timing explicit.",
        web_query_hint="momentum revisions volatility factor relative strength analyst estimates",
    ),
    "risk_manager": RolePromptProfile(
        title="Risk Manager",
        mandate="Downside, liquidity, balance-sheet, valuation, concentration, and thesis-break risk.",
        lens="Act like a risk manager. Focus on what can go wrong, what breaks first, how severe the drawdown could be, and what monitoring triggers should force action.",
        focus_questions=(
            "What are the most plausible downside scenarios?",
            "What data would prove the thesis is breaking?",
            "What risk controls or monitoring triggers should be used?",
        ),
        report_emphasis="Lead with risks, breakpoints, and mitigation actions, not upside narrative.",
        web_query_hint="downside risk debt liquidity valuation stress scenario",
    ),
    "macro_strategist": RolePromptProfile(
        title="Macro Strategist",
        mandate="Rates, policy, inflation, growth, liquidity, sector rotation, and market regime research.",
        lens="Act like a macro strategist. Focus on rates, policy, inflation, growth, liquidity, credit conditions, FX, commodities, and sector-level implications.",
        focus_questions=(
            "What macro variable matters most for this issue?",
            "Is the current regime a tailwind or headwind?",
            "Which market indicators should be monitored next?",
        ),
        report_emphasis="Tie macro conditions directly to portfolio or company implications.",
        web_query_hint="macro rates policy inflation sector rotation liquidity",
    ),
    "market_narrative_analyst": RolePromptProfile(
        title="Market Narrative Analyst",
        mandate="Narrative, positioning, sentiment, sell-side tone, and perception-change research.",
        lens="Act like a market narrative analyst. Focus on investor positioning, narrative shifts, sentiment, sell-side framing, media attention, and mismatch between fundamentals and perception.",
        focus_questions=(
            "What is the dominant market narrative?",
            "Is the narrative improving, deteriorating, or detached from fundamentals?",
            "What catalyst could change perception?",
        ),
        report_emphasis="Separate narrative momentum from fundamental evidence.",
        web_query_hint="investor sentiment positioning narrative analyst commentary news",
    ),
}

TEMPLATE_PROMPT_PROFILE_KEYS: dict[str, str] = {
    "fundamental_analyst": "generalist_analyst",
    "quant_analyst": "quant_strategist",
    "risk_analyst": "risk_manager",
    "macro_analyst": "macro_strategist",
    "market_pulse": "macro_strategist",
    "sentiment_analyst": "market_narrative_analyst",
}

INTENT_PROFILES: dict[str, ResearchIntent] = {
    "industry_map": ResearchIntent(
        key="industry_map",
        title="Industry / Theme Map",
        mandate="Identify the relevant public companies, map the value chain, compare winners and risks, and explain the industry-level setup.",
        required_sections=(
            "## Executive Summary",
            "## Industry Map",
            "## Company Comparison",
            "## Key Findings",
            "## Investment View",
            "## Agent Suggestions",
            "## Risks And Watch Items",
            "## Next Steps",
        ),
        search_hint="industry beneficiaries value chain market map winners risks",
    ),
    "peer_comparison": ResearchIntent(
        key="peer_comparison",
        title="Peer Comparison",
        mandate="Compare the companies directly and identify which one has the stronger setup for the user's objective.",
        required_sections=(
            "## Executive Summary",
            "## Peer Comparison",
            "## Investment View",
            "## Key Findings",
            "## Agent Suggestions",
            "## Risks And Watch Items",
            "## Next Steps",
        ),
        search_hint="peer comparison valuation growth margins competitive position",
    ),
    "earnings_review": ResearchIntent(
        key="earnings_review",
        title="Earnings Review",
        mandate="Analyze the latest quarter, guidance, revisions, and what changed versus expectations.",
        required_sections=(
            "## Executive Summary",
            "## Earnings Read-Through",
            "## Guidance And Revisions",
            "## Investment View",
            "## Agent Suggestions",
            "## Risks And Watch Items",
            "## Next Steps",
        ),
        search_hint="latest earnings guidance revisions quarter results transcript",
    ),
    "risk_review": ResearchIntent(
        key="risk_review",
        title="Risk Review",
        mandate="Stress-test the setup and surface what could break the thesis.",
        required_sections=(
            "## Executive Summary",
            "## Downside Scenarios",
            "## Risk Triggers",
            "## Investment View",
            "## Agent Suggestions",
            "## Next Steps",
        ),
        search_hint="risk downside debt liquidity valuation pressure",
    ),
    "valuation": ResearchIntent(
        key="valuation",
        title="Valuation Work",
        mandate="Frame valuation, expectations, upside/downside, and what must be true for the current price to work.",
        required_sections=(
            "## Executive Summary",
            "## Valuation Setup",
            "## Expectations Embedded In Price",
            "## Investment View",
            "## Agent Suggestions",
            "## Risks And Watch Items",
            "## Next Steps",
        ),
        search_hint="valuation multiples price target DCF expectations upside downside",
    ),
    "single_name": ResearchIntent(
        key="single_name",
        title="Single-Name Research",
        mandate="Produce a focused company-level research view that directly answers the issue.",
        required_sections=(
            "## Executive Summary",
            "## Investment View",
            "## Key Findings",
            "## Company Analysis",
            "## Agent Suggestions",
            "## Risks And Watch Items",
            "## Next Steps",
        ),
        search_hint="stock analysis fundamentals catalysts valuation risks",
    ),
}


def resolve_role_prompt_profile(
    *,
    template: str,
    role_key: Optional[str] = None,
    role_title: Optional[str] = None,
    description: Optional[str] = None,
) -> RolePromptProfile:
    profile_key = (role_key or "").strip() or TEMPLATE_PROMPT_PROFILE_KEYS.get(template, "")
    base = ROLE_PROMPT_PROFILES.get(profile_key) or ROLE_PROMPT_PROFILES["generalist_analyst"]

    title = (role_title or "").strip() or base.title
    extra_description = (description or "").strip()
    if not extra_description:
        return RolePromptProfile(
            title=title,
            mandate=base.mandate,
            lens=base.lens,
            focus_questions=base.focus_questions,
            report_emphasis=base.report_emphasis,
            web_query_hint=base.web_query_hint,
        )

    return RolePromptProfile(
        title=title,
        mandate=f"{base.mandate} Agent-specific mandate: {extra_description}",
        lens=base.lens,
        focus_questions=base.focus_questions,
        report_emphasis=base.report_emphasis,
        web_query_hint=base.web_query_hint,
    )


def infer_research_intent(instruction: str, tickers: list[str]) -> ResearchIntent:
    """
    Score each candidate intent by counting keyword hits, then return the
    highest-scoring one.  Ties resolve left-to-right in _INTENT_SIGNALS.
    This replaces a fragile sequential if-chain that could misclassify
    ambiguous queries (e.g. "compare peers on earnings guidance" was always
    classified as peer_comparison before earnings_review had a chance to score).
    """
    text = (instruction or "").lower()
    normalized_tickers = [t for t in tickers if str(t).strip().upper() != "GENERAL"]

    _INTENT_SIGNALS: list[tuple[str, tuple[str, ...]]] = [
        (
            "industry_map",
            (
                "industry", "sector", "theme", "trend", "wave", "ecosystem",
                "value chain", "beneficiaries", "companies that", "players",
                "who benefits", "who wins",
            ),
        ),
        (
            "peer_comparison",
            ("compare", "versus", " vs ", "peer", "relative to", "competitors", "peers"),
        ),
        (
            "earnings_review",
            ("earnings", "quarter", "guidance", "transcript", "beat", "miss", "revisions", "eps"),
        ),
        (
            "risk_review",
            ("risk", "downside", "stress", "bear case", "liquidity", "debt", "drawdown", "exposure"),
        ),
        (
            "valuation",
            ("valuation", "dcf", "price target", "intrinsic", "multiple", "upside", "fair value"),
        ),
    ]

    scores: dict[str, int] = {intent: 0 for intent, _ in _INTENT_SIGNALS}
    for intent, markers in _INTENT_SIGNALS:
        for marker in markers:
            if marker in text:
                scores[intent] += 1

    # Multiple tickers are a strong peer_comparison signal even with no keywords.
    if len(normalized_tickers) > 1:
        scores["peer_comparison"] += 2

    best_intent = max(_INTENT_SIGNALS, key=lambda pair: scores[pair[0]])[0]
    if scores[best_intent] == 0:
        return INTENT_PROFILES["single_name"]
    return INTENT_PROFILES[best_intent]


def format_bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def format_required_sections(intent: ResearchIntent) -> str:
    return "\n".join(intent.required_sections)
