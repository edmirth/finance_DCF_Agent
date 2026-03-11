"""
Project Analysis Agent — LangGraph-based multi-agent orchestrator for investment thesis workspaces.

Architecture:
  route → [run_agent_dcf, run_agent_analyst, run_agent_earnings, run_agent_market, run_agent_research]
        → sync_point → synthesize → extract_memory_patch → END
"""
from __future__ import annotations

import operator
import logging
import re
import time
from typing import Annotated, Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, START, END

from agents.dcf_agent import create_dcf_agent
from agents.equity_analyst_agent import create_equity_analyst_agent
from agents.earnings_agent import create_earnings_agent
from agents.market_agent import create_market_agent
from agents.finance_qa_agent import create_finance_qa_agent

logger = logging.getLogger(__name__)


# ============================================================================
# State Schema
# ============================================================================

class ProjectAnalysisState(TypedDict):
    # Input (populated by API handler before graph invocation)
    query: str
    project_id: str
    context_block: str      # pre-assembled by assemble_project_context()
    routing_decision: dict  # serialised ProjectRoutingDecision (agents list + reasoning)

    # Agent outputs — use operator.add so parallel nodes can append concurrently
    agent_results: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]

    # Sequential synthesis outputs
    synthesis: str
    memory_patch: dict
    final_response: str

    # Metadata
    start_time: float


# ============================================================================
# Agent node names (used for conditional edge routing)
# ============================================================================

AGENT_NODE_NAMES = {
    "dcf": "run_agent_dcf",
    "analyst": "run_agent_analyst",
    "earnings": "run_agent_earnings",
    "market": "run_agent_market",
    "research": "run_agent_research",
}


# ============================================================================
# ProjectAnalysisGraph
# ============================================================================

class ProjectAnalysisGraph:
    """LangGraph orchestrator for project-grounded multi-agent analysis."""

    def __init__(self):
        # Progress streaming (injected by api_server before graph invocation)
        self._progress_queue = None
        self._progress_loop = None

        self.graph = self._build_graph()
        logger.info("ProjectAnalysisGraph initialised")

    # -----------------------------------------------------------------------
    # Progress helpers
    # -----------------------------------------------------------------------

    def _emit_progress(self, event_type: str, data: dict) -> None:
        """Push a progress event to the SSE queue (no-op if no queue injected)."""
        queue = self._progress_queue
        loop = self._progress_loop
        if queue is not None and loop is not None:
            event = {"type": event_type, **data}
            loop.call_soon_threadsafe(queue.put_nowait, event)

    # -----------------------------------------------------------------------
    # Node 1: Route — select agent nodes from routing_decision
    # -----------------------------------------------------------------------

    def route(self, state: ProjectAnalysisState) -> ProjectAnalysisState:
        """No-op pass-through; routing logic is in the conditional edge function."""
        return state

    def _select_agent_nodes(self, state: ProjectAnalysisState) -> List[str]:
        """Conditional edge: maps routing_decision.agents → list of node names."""
        routing = state.get("routing_decision") or {}
        agents = routing.get("agents", [])
        node_names: List[str] = []
        for agent in agents:
            agent_type = agent.get("agent_type") if isinstance(agent, dict) else getattr(agent, "agent_type", None)
            if agent_type and agent_type in AGENT_NODE_NAMES:
                node_names.append(AGENT_NODE_NAMES[agent_type])

        if not node_names:
            logger.warning("routing_decision empty or unrecognised agents — falling back to research")
            node_names = ["run_agent_research"]

        logger.info(f"Routing to nodes: {node_names}")
        self._emit_progress("project_progress", {"node": "route", "status": "completed", "detail": f"Routing to: {', '.join(node_names)}"})
        return node_names

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_agent_task(self, state: ProjectAnalysisState, agent_type: str) -> str:
        """Extract task string for the given agent_type from routing_decision."""
        routing = state.get("routing_decision") or {}
        agents = routing.get("agents", [])
        for agent in agents:
            at = agent.get("agent_type") if isinstance(agent, dict) else getattr(agent, "agent_type", None)
            if at == agent_type:
                task = agent.get("task") if isinstance(agent, dict) else getattr(agent, "task", "")
                return task or state.get("query", "")
        return state.get("query", "")

    def _grounded_task(self, state: ProjectAnalysisState, agent_type: str) -> str:
        """Return context_block + task so agent is grounded in project thesis."""
        task = self._get_agent_task(state, agent_type)
        context_block = state.get("context_block", "")
        if context_block:
            return f"{context_block}\n\n{task}"
        return task

    @staticmethod
    def _extract_ticker(text: str) -> str:
        """Extract first plausible ticker symbol from a text string."""
        # $TICKER format
        m = re.search(r'\$([A-Z]{2,5})\b', text)
        if m:
            return m.group(1)
        # Standalone all-caps 2-5 char word
        for m in re.finditer(r'\b([A-Z]{2,5})\b', text):
            t = m.group(1)
            if t not in {"THE", "AND", "FOR", "ARE", "BUY", "SELL", "HOLD", "DCF", "CEO", "CFO", "IPO", "ETF"}:
                return t
        return ""

    @staticmethod
    def _ensure_str(value: Any) -> str:
        """Normalize Anthropic content blocks (list) to a plain string."""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in value
            )
        return str(value) if value else ""

    # -----------------------------------------------------------------------
    # Node 2–6: Agent runner nodes
    # -----------------------------------------------------------------------

    def run_agent_dcf(self, state: ProjectAnalysisState) -> dict:
        """Run DCF agent and append result to agent_results."""
        agent_type = "dcf"
        self._emit_progress("project_progress", {"node": agent_type, "status": "started", "detail": "Running DCF analysis"})
        task = self._grounded_task(state, agent_type)
        try:
            agent = create_dcf_agent()
            output = self._ensure_str(agent.analyze(task))
            logger.info(f"[project_graph] run_agent_dcf complete ({len(output)} chars)")
            self._emit_progress("project_progress", {"node": agent_type, "status": "completed"})
            return {"agent_results": [{"agent_type": agent_type, "task": task, "output": output}]}
        except Exception as exc:
            msg = f"DCF agent error: {exc}"
            logger.error(f"[project_graph] {msg}")
            self._emit_progress("project_progress", {"node": agent_type, "status": "error", "detail": msg})
            return {
                "errors": [msg],
                "agent_results": [{"agent_type": agent_type, "task": task, "output": f"Error: {exc}"}],
            }

    def run_agent_analyst(self, state: ProjectAnalysisState) -> dict:
        """Run equity analyst agent and append result to agent_results."""
        agent_type = "analyst"
        self._emit_progress("project_progress", {"node": agent_type, "status": "started", "detail": "Running equity analyst"})
        task = self._grounded_task(state, agent_type)
        try:
            agent = create_equity_analyst_agent()
            output = self._ensure_str(agent.analyze(task))
            logger.info(f"[project_graph] run_agent_analyst complete ({len(output)} chars)")
            self._emit_progress("project_progress", {"node": agent_type, "status": "completed"})
            return {"agent_results": [{"agent_type": agent_type, "task": task, "output": output}]}
        except Exception as exc:
            msg = f"Analyst agent error: {exc}"
            logger.error(f"[project_graph] {msg}")
            self._emit_progress("project_progress", {"node": agent_type, "status": "error", "detail": msg})
            return {
                "errors": [msg],
                "agent_results": [{"agent_type": agent_type, "task": task, "output": f"Error: {exc}"}],
            }

    def run_agent_earnings(self, state: ProjectAnalysisState) -> dict:
        """Run earnings agent and append result to agent_results."""
        agent_type = "earnings"
        self._emit_progress("project_progress", {"node": agent_type, "status": "started", "detail": "Running earnings analysis"})
        task = self._grounded_task(state, agent_type)
        ticker = self._extract_ticker(task)
        if not ticker:
            ticker = self._extract_ticker(state.get("query", ""))
        try:
            if not ticker:
                raise ValueError("No ticker symbol found in task for earnings agent")
            agent = create_earnings_agent()
            output = self._ensure_str(agent.analyze(ticker))
            logger.info(f"[project_graph] run_agent_earnings complete ({len(output)} chars)")
            self._emit_progress("project_progress", {"node": agent_type, "status": "completed"})
            return {"agent_results": [{"agent_type": agent_type, "task": task, "output": output}]}
        except Exception as exc:
            msg = f"Earnings agent error: {exc}"
            logger.error(f"[project_graph] {msg}")
            self._emit_progress("project_progress", {"node": agent_type, "status": "error", "detail": msg})
            return {
                "errors": [msg],
                "agent_results": [{"agent_type": agent_type, "task": task, "output": f"Error: {exc}"}],
            }

    def run_agent_market(self, state: ProjectAnalysisState) -> dict:
        """Run market agent and append result to agent_results."""
        agent_type = "market"
        self._emit_progress("project_progress", {"node": agent_type, "status": "started", "detail": "Running market analysis"})
        task = self._grounded_task(state, agent_type)
        try:
            agent = create_market_agent()
            output = self._ensure_str(agent.analyze(task))
            logger.info(f"[project_graph] run_agent_market complete ({len(output)} chars)")
            self._emit_progress("project_progress", {"node": agent_type, "status": "completed"})
            return {"agent_results": [{"agent_type": agent_type, "task": task, "output": output}]}
        except Exception as exc:
            msg = f"Market agent error: {exc}"
            logger.error(f"[project_graph] {msg}")
            self._emit_progress("project_progress", {"node": agent_type, "status": "error", "detail": msg})
            return {
                "errors": [msg],
                "agent_results": [{"agent_type": agent_type, "task": task, "output": f"Error: {exc}"}],
            }

    def run_agent_research(self, state: ProjectAnalysisState) -> dict:
        """Run research/Q&A agent and append result to agent_results."""
        agent_type = "research"
        self._emit_progress("project_progress", {"node": agent_type, "status": "started", "detail": "Running research assistant"})
        task = self._grounded_task(state, agent_type)
        try:
            agent = create_finance_qa_agent()
            output = self._ensure_str(agent.chat(task))
            logger.info(f"[project_graph] run_agent_research complete ({len(output)} chars)")
            self._emit_progress("project_progress", {"node": agent_type, "status": "completed"})
            return {"agent_results": [{"agent_type": agent_type, "task": task, "output": output}]}
        except Exception as exc:
            msg = f"Research agent error: {exc}"
            logger.error(f"[project_graph] {msg}")
            self._emit_progress("project_progress", {"node": agent_type, "status": "error", "detail": msg})
            return {
                "errors": [msg],
                "agent_results": [{"agent_type": agent_type, "task": task, "output": f"Error: {exc}"}],
            }

    # -----------------------------------------------------------------------
    # Node 7: sync_point — no-op aggregator, waits for all parallel nodes
    # -----------------------------------------------------------------------

    def sync_point(self, state: ProjectAnalysisState) -> dict:
        """No-op aggregator: LangGraph waits for all parallel branches before executing."""
        logger.info(f"[project_graph] sync_point reached — {len(state.get('agent_results', []))} results collected")
        return {}

    # -----------------------------------------------------------------------
    # Node 8: synthesize — stub (to be implemented in US-006c)
    # -----------------------------------------------------------------------

    def synthesize(self, state: ProjectAnalysisState) -> dict:
        """Stub: Synthesis LLM call (to be implemented in US-006c)."""
        logger.info("[project_graph] synthesize stub — pass-through")
        return {}

    # -----------------------------------------------------------------------
    # Node 9: extract_memory_patch — stub (to be implemented in US-006c)
    # -----------------------------------------------------------------------

    def extract_memory_patch(self, state: ProjectAnalysisState) -> dict:
        """Stub: Memory patch extraction LLM call (to be implemented in US-006c)."""
        logger.info("[project_graph] extract_memory_patch stub — pass-through")
        return {}

    # -----------------------------------------------------------------------
    # Graph construction
    # -----------------------------------------------------------------------

    def _build_graph(self):
        workflow = StateGraph(ProjectAnalysisState)

        # Register all nodes
        workflow.add_node("route", self.route)
        workflow.add_node("run_agent_dcf", self.run_agent_dcf)
        workflow.add_node("run_agent_analyst", self.run_agent_analyst)
        workflow.add_node("run_agent_earnings", self.run_agent_earnings)
        workflow.add_node("run_agent_market", self.run_agent_market)
        workflow.add_node("run_agent_research", self.run_agent_research)
        workflow.add_node("sync_point", self.sync_point)
        workflow.add_node("synthesize", self.synthesize)
        workflow.add_node("extract_memory_patch", self.extract_memory_patch)

        # Edges
        workflow.add_edge(START, "route")

        # Conditional fan-out: route → selected agent nodes
        all_agent_nodes = list(AGENT_NODE_NAMES.values())
        workflow.add_conditional_edges(
            "route",
            self._select_agent_nodes,
            {node: node for node in all_agent_nodes},
        )

        # All agent nodes converge at sync_point
        for node in all_agent_nodes:
            workflow.add_edge(node, "sync_point")

        # Sequential tail
        workflow.add_edge("sync_point", "synthesize")
        workflow.add_edge("synthesize", "extract_memory_patch")
        workflow.add_edge("extract_memory_patch", END)

        return workflow.compile()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def run(
        self,
        query: str,
        project_id: str,
        context_block: str,
        routing_decision: dict,
        callback_handler=None,
    ) -> dict:
        """Run the project analysis graph and return final state."""
        initial_state: ProjectAnalysisState = {
            "query": query,
            "project_id": project_id,
            "context_block": context_block,
            "routing_decision": routing_decision,
            "agent_results": [],
            "errors": [],
            "synthesis": "",
            "memory_patch": {},
            "final_response": "",
            "start_time": time.time(),
        }

        config = {}
        if callback_handler is not None:
            config["callbacks"] = [callback_handler]

        result = self.graph.invoke(initial_state, config=config or None)
        return result


# ============================================================================
# Adapter (same pattern as EarningsAgentExecutorAdapter)
# ============================================================================

class ProjectAnalysisGraphAdapter:
    """Adapter: translates backend invoke() calls to ProjectAnalysisGraph.run()."""

    def __init__(self, graph_instance: ProjectAnalysisGraph):
        self.graph_instance = graph_instance

    def invoke(self, input_dict: dict, config: dict | None = None) -> dict:
        """Invoke the graph with a standardised input dict."""
        query = input_dict.get("input", "")
        project_id = input_dict.get("project_id", "")
        context_block = input_dict.get("context_block", "")
        routing_decision = input_dict.get("routing_decision", {})

        callback_handler = None
        if config and "callbacks" in config:
            callbacks = config["callbacks"]
            if callbacks:
                callback_handler = callbacks[0]

        result = self.graph_instance.run(
            query=query,
            project_id=project_id,
            context_block=context_block,
            routing_decision=routing_decision,
            callback_handler=callback_handler,
        )

        final_response = result.get("final_response") or result.get("synthesis") or "Analysis complete."
        return {"output": final_response, "_state": result}
