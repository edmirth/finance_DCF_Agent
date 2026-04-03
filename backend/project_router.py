"""Project router — LLM-based agent routing for project queries."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class AgentTask:
    agent_type: str
    task: str


@dataclass
class ProjectRoutingDecision:
    agents: List[AgentTask] = field(default_factory=list)
    reasoning: str = ""


_ROUTING_SYSTEM = """You are a financial query router for an investment thesis workspace.

Given a user query and project context, decide which 1–3 agents to invoke.

Available agents:
- analyst: Deep equity research — moat, competitive position, industry analysis, valuation. Use for in-depth thesis validation, fair value questions, or "should I invest" queries.
- earnings: Quarterly earnings results, EPS beats/misses, revenue guidance, earnings call commentary. Use when query explicitly mentions earnings, EPS, quarterly results, or management guidance.
- market: Macro conditions, sector rotation, indices (S&P 500, NASDAQ, VIX), Fed policy, inflation, recession risk. Use for broad market questions or macro thesis checks.
- research: General financial research, company info, metrics, follow-up questions, comparisons, and anything that doesn't clearly fit another agent.

Rules:
1. Select 1–3 agents. Select more only when the query genuinely requires multiple perspectives.
2. research is the default/fallback for follow-ups and ambiguous queries.
3. Never select portfolio — it requires structured portfolio JSON input.
4. For each agent, write a task string that includes a brief thesis excerpt so the agent is grounded.

Return ONLY valid JSON with this exact structure (no markdown, no extra text):
{
  "agents": [
    {"agent_type": "...", "task": "..."},
    ...
  ],
  "reasoning": "one sentence explaining your routing decision"
}"""


async def route_for_project(
    query: str,
    context_block: str,
    project_config: dict,
) -> ProjectRoutingDecision:
    """Use Claude Haiku to select 1–3 agents for a project query.

    Falls back to [AgentTask(agent_type="research", task=query)] on any error.
    """
    import anthropic

    fallback = ProjectRoutingDecision(
        agents=[AgentTask(agent_type="research", task=query)],
        reasoning="fallback",
    )

    # Extract thesis excerpt for grounding (first 300 chars)
    thesis_excerpt = ""
    if context_block:
        try:
            start = context_block.find("<thesis>")
            end = context_block.find("</thesis>")
            if start != -1 and end != -1:
                thesis_excerpt = context_block[start + 8 : end].strip()[:300]
        except Exception:
            pass

    tickers = project_config.get("tickers", []) if isinstance(project_config, dict) else []
    ticker_hint = f" Key tickers: {', '.join(tickers)}." if tickers else ""
    preferred_agents = project_config.get("preferred_agents", []) if isinstance(project_config, dict) else []
    preferred_hint = (
        " Preferred analytical angles for this project: "
        + ", ".join(preferred_agents)
        + ". Use them as a bias when the query is ambiguous, but do not force them when clearly irrelevant."
        if preferred_agents
        else ""
    )

    user_message = (
        f"Thesis excerpt: {thesis_excerpt}{ticker_hint}{preferred_hint}\n\n"
        f"User query: {query}\n\n"
        "Select the appropriate agent(s) and write grounded task strings that include the thesis context."
    )

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_ROUTING_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text.strip()
        data = json.loads(raw)

        agents = [
            AgentTask(agent_type=a["agent_type"], task=a["task"])
            for a in data.get("agents", [])
            if a.get("agent_type") in ("analyst", "earnings", "market", "research")
        ]
        if not agents:
            return fallback

        return ProjectRoutingDecision(
            agents=agents,
            reasoning=data.get("reasoning", ""),
        )

    except Exception as e:
        logger.warning(f"route_for_project failed, using fallback: {e}")
        return fallback
