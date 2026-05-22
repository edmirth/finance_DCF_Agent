"""Reusable issue-planning copy for agent delegation."""
from __future__ import annotations


def role_specific_plan_steps(role_key: str, scope_reference: str) -> list[str] | None:
    steps: dict[str, list[str]] = {
        "semis_analyst": [
            f"Map {scope_reference} across the semiconductor value chain: design, foundry, equipment, memory, networking, and AI accelerators.",
            "Check AI/data-center exposure, hyperscaler capex sensitivity, pricing, gross margin, supply constraints, and customer concentration.",
            "Compare the setup against direct semis peers and identify where the cycle or valuation can break.",
            "Write a semiconductor desk note with value-chain position, demand drivers, risks, and next watchpoints.",
        ],
        "software_analyst": [
            f"Frame {scope_reference} through software economics: ARR/recurring mix, retention, expansion, churn, and pricing power.",
            "Check AI monetization, cloud consumption, sales efficiency, margin trajectory, and competitive displacement risk.",
            "Separate product narrative from measurable financial evidence.",
            "Write a software coverage brief with the investment view, key KPIs, risks, and next checks.",
        ],
        "financials_analyst": [
            f"Frame {scope_reference} through financial-sector drivers: NII, credit quality, fee income, funding, capital, and ROE.",
            "Check rate sensitivity, deposit/funding pressure, reserves, leverage, and regulatory constraints.",
            "Compare valuation and profitability against the relevant financials peer set.",
            "Write a financials coverage brief with earnings drivers, balance-sheet risk, and watchpoints.",
        ],
        "healthcare_analyst": [
            f"Frame {scope_reference} through healthcare drivers: pipeline, regulatory catalysts, reimbursement, patent risk, and utilization.",
            "Check the durability of revenue streams, clinical/regulatory milestones, payer/provider dynamics, and margin risk.",
            "Separate near-term catalysts from long-duration pipeline optionality.",
            "Write a healthcare coverage brief with catalysts, evidence, risks, and next checks.",
        ],
        "consumer_analyst": [
            f"Frame {scope_reference} through consumer drivers: volume, pricing, mix, brand health, traffic, inventory, and category growth.",
            "Check consumer sensitivity, promotions, market share, margin durability, and channel performance.",
            "Separate one-time demand effects from durable brand or unit-economic strength.",
            "Write a consumer coverage brief with demand drivers, margin risk, and next watchpoints.",
        ],
        "industrials_analyst": [
            f"Frame {scope_reference} through industrial drivers: backlog, orders, book-to-bill, end-market exposure, and operating leverage.",
            "Check capex cycles, supply-chain risk, input costs, margin sensitivity, and revenue visibility.",
            "Compare cyclical exposure and valuation against relevant industrial peers.",
            "Write an industrials coverage brief with cycle position, key risks, and next checks.",
        ],
        "energy_analyst": [
            f"Frame {scope_reference} through commodity exposure, production mix, reserves, breakevens, capex, and free cash flow.",
            "Check balance sheet resilience, capital return capacity, regulatory/geopolitical exposure, and price sensitivity.",
            "Compare cycle risk and cash generation against relevant energy peers.",
            "Write an energy coverage brief with commodity assumptions, cash-flow setup, risks, and watchpoints.",
        ],
    }
    return steps.get(role_key)


def role_specific_deliverable(role_key: str) -> str | None:
    deliverables = {
        "semis_analyst": "Semiconductor coverage brief with value-chain position, AI/data-center exposure, cycle risk, valuation context, and next watchpoints.",
        "software_analyst": "Software coverage brief with growth quality, retention/AI monetization evidence, margin path, valuation context, and risks.",
        "financials_analyst": "Financials coverage brief with earnings drivers, credit/capital risk, rate sensitivity, valuation context, and monitoring triggers.",
        "healthcare_analyst": "Healthcare coverage brief with clinical/regulatory catalysts, reimbursement risk, durability of revenue, and next checks.",
        "consumer_analyst": "Consumer coverage brief with demand drivers, brand health, pricing/mix, margin durability, and risks.",
        "industrials_analyst": "Industrials coverage brief with backlog/orders, cycle position, operating leverage, valuation context, and watchpoints.",
        "energy_analyst": "Energy coverage brief with commodity assumptions, cash-flow setup, balance-sheet resilience, cycle risk, and watchpoints.",
    }
    return deliverables.get(role_key)
