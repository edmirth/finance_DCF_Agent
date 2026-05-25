"""
FastAPI Backend Server for Financial Analysis Agents
Provides REST API and Server-Sent Events (SSE) for streaming responses
"""
from __future__ import annotations
import os
import json
import asyncio
import logging
import threading
import uuid as uuid_mod
from collections import OrderedDict
from typing import Optional, AsyncGenerator, Any, Dict, List
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
import sys
import re
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path to import agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import (
    SSE_CHUNK_SIZE, SSE_STREAM_DELAY_SECONDS,
    CORS_ORIGINS,
)
from shared.ticker_utils import extract_ticker as _extract_ticker_shared
from backend.callbacks.streaming import StreamingCallbackHandler
from backend.core_router import create_core_router
from backend.database import init_db, get_db, SyncSessionLocal, AsyncSessionLocal
from backend.models import Session as DBSession, DBMessage, Analysis, Project, ProjectSession
from backend.task_api_contracts import (
    TASK_TYPE_TITLES,
    VALID_PRIORITIES,
    VALID_TASK_STATUSES,
    VALID_TASK_TYPES,
    TaskCreate,
    TaskPatch,
)
from backend.task_serialization import task_to_dict as _task_to_dict
from backend.http_client import requests_get_json as _requests_get_json
from backend.document_upload_router import router as document_upload_router
from backend.firm_router import router as firm_router
from backend.memo_router import router as memo_router
from backend.project_documents_router import router as project_documents_router
from backend.sessions_router import create_sessions_router
from backend.task_activity import append_task_activity as _append_task_activity
from backend.task_chat_router import create_task_chat_router
from backend.task_documents_router import router as task_documents_router
from backend.task_mutation_router import router as task_mutation_router
from backend.task_read_router import router as task_read_router
from backend.ticker_router import router as ticker_router
from agents.finance_qa_agent import create_finance_qa_agent
from agents.market_agent import create_market_agent
from agents.portfolio_agent import create_portfolio_agent
from agents.earnings_agent import create_earnings_agent
from agents.dcf_agent import DCFAgent

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

STALE_RUN_RECOVERY_AGE = timedelta(
    minutes=max(1, int(os.getenv("STALE_RUN_RECOVERY_MINUTES", "20")))
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    await init_db()
    logger.info("Database initialized")
    try:
        async with AsyncSessionLocal() as db:
            recovery = await _recover_stale_issue_work(db)
            normalization = await _normalize_terminal_issue_states(db)
            await db.commit()
        if recovery["stale_runs_recovered"] > 0:
            logger.warning(
                "Recovered %s stale runs on startup (%s tasks returned to queue, %s moved to review)",
                recovery["stale_runs_recovered"],
                recovery["tasks_returned_to_queue"],
                recovery["tasks_moved_to_review"],
            )
        if normalization["tasks_moved_to_done"] > 0:
            logger.info(
                "Normalized %s issue(s) from review to done on startup",
                normalization["tasks_moved_to_done"],
            )
    except Exception as _e:
        logger.warning(f"Stale issue-work recovery failed on startup (non-fatal): {_e}")
    # Pre-load Chroma embedding model so the ~90MB download happens before first request
    try:
        from data.chroma_client import ProjectChromaClient
        _ = ProjectChromaClient()
        logger.info("ProjectChromaClient initialised")
    except Exception as _e:
        logger.warning(f"ProjectChromaClient pre-load failed (non-fatal): {_e}")
    # Start heartbeat scheduler
    try:
        from backend.scheduler import start_scheduler, stop_scheduler
        await start_scheduler()
        logger.info("Heartbeat scheduler started")
        yield
        await stop_scheduler()
    except Exception as _e:
        logger.warning(f"Scheduler startup failed (non-fatal): {_e}")
        yield


_TICKER_INPUT_RE = re.compile(r"^[A-Z0-9]{1,5}(?:[.-][A-Z0-9]{1,2})?$")


# Path to frontend build — defined early so root route can reference it
FRONTEND_BUILD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

# ASGI middleware that strips /api prefix so production requests from the
# frontend (which use /api/... paths) reach the same routes as the Vite
# dev proxy did locally. Uses raw ASGI to avoid buffering SSE streams.
class StripApiPrefix:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/"):
            scope["path"] = scope["path"][4:]
            scope["raw_path"] = scope["path"].encode("utf-8")
        await self.app(scope, receive, send)

# Initialize FastAPI app
app = FastAPI(title="Financial Analysis API", version="1.0.0", lifespan=lifespan)
app.add_middleware(StripApiPrefix)
app.include_router(create_core_router(FRONTEND_BUILD_DIR))

# Register scheduled agents router
from backend.scheduled_agents_router import router as scheduled_agents_router
app.include_router(scheduled_agents_router)

# Register CIO router
from backend.cio_router import router as cio_router
app.include_router(cio_router)

# Register stock chart router
from backend.stock_chart_router import router as stock_chart_router
app.include_router(stock_chart_router)

# Register watchlists router
from backend.watchlists_router import router as watchlists_router
app.include_router(watchlists_router)

# Register analyses router
from backend.analyses_router import router as analyses_router
app.include_router(analyses_router)

# Register system router
from backend.system_router import create_system_router
app.include_router(create_system_router(lambda: len(agents_cache)))

# Register sessions router
def _evict_session_agents(session_id: str) -> None:
    with agents_cache_lock:
        stale_keys = [k for k in agents_cache if k.endswith(f"_{session_id}")]
        for key in stale_keys:
            del agents_cache[key]


app.include_router(create_sessions_router(_evict_session_agents))

# Register projects router
from backend.projects_router import router as projects_router
app.include_router(projects_router)
app.include_router(project_documents_router)
app.include_router(document_upload_router)
app.include_router(firm_router)
app.include_router(memo_router)
app.include_router(task_documents_router)
app.include_router(task_mutation_router)
app.include_router(task_read_router)
app.include_router(ticker_router)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add validation error handler for better debugging
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging"""
    body = await request.body()
    logger.error(f"Validation error on {request.url.path}")
    logger.error(f"Request body: {body}")
    logger.error(f"Validation errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode('utf-8')}
    )

# Store active agents with bounded LRU eviction
_AGENTS_CACHE_MAX = 100
agents_cache: OrderedDict = OrderedDict()
agents_cache_lock = threading.Lock()
class DCFAgentAdapter:
    """
    Wraps DCFAgent to match the string-in / string-out interface expected by
    the backend.  Extracts the ticker from the user's message, runs the two-
    stage FMP DCF pipeline, and returns the formatted report as a string.
    """

    def __init__(self, model: str):
        self._agent = DCFAgent(model=model)

    def analyze(self, message: str) -> str:
        ticker = _extract_ticker_shared(message)
        if not ticker:
            return (
                "Please include a stock ticker in your message. "
                "Example: 'Run a DCF analysis on AAPL'"
            )
        result = self._agent.analyze(ticker)
        return self._agent.format_report(result)


SESSION_SCOPED_AGENT_TYPES = frozenset({"research", "market", "earnings"})

# Hold strong references to fire-and-forget tasks so they aren't GC'd before completion
_background_tasks: set = set()

# ---------------------------------------------------------------------------
# Research Workstation — WebSocket connection manager
# ---------------------------------------------------------------------------
from backend.research_orchestrator import ResearchOrchestrator, AGENT_META
import uuid as uuid_mod_research


class ResearchConnectionManager:
    def __init__(self):
        self._connections: dict = {}

    async def connect(self, run_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)

    def disconnect(self, run_id: str, ws: WebSocket):
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns and run_id in self._connections:
            del self._connections[run_id]

    async def broadcast(self, run_id: str, data: dict):
        stale_connections = []
        for ws in list(self._connections.get(run_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                stale_connections.append(ws)
        for ws in stale_connections:
            self.disconnect(run_id, ws)


research_manager = ResearchConnectionManager()


def _fire_and_forget(coro) -> asyncio.Task:
    """Schedule a coroutine as a background task, keeping a reference until it completes."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _normalize_selected_agents(
    requested_agents: Any,
    *,
    default_to_all: bool = False,
) -> List[str]:
    """
    Validate and normalize a selected-agents payload.

    - `None` can default to the full research suite when `default_to_all=True`
    - values are lowercased, stripped, and de-duplicated in first-seen order
    - invalid or empty explicit selections are rejected instead of silently
      expanding into an expensive full-agent run
    """
    if requested_agents is None:
        return list(AGENT_META.keys()) if default_to_all else []

    if not isinstance(requested_agents, list):
        raise ValueError("agents must be provided as a list")

    normalized: List[str] = []
    invalid: List[str] = []

    for raw_agent in requested_agents:
        if not isinstance(raw_agent, str):
            invalid.append(str(raw_agent))
            continue
        agent = raw_agent.strip().lower()
        if not agent:
            continue
        if agent not in AGENT_META:
            invalid.append(raw_agent)
            continue
        if agent not in normalized:
            normalized.append(agent)

    if invalid:
        valid_agents = ", ".join(AGENT_META.keys())
        invalid_agents = ", ".join(sorted({str(agent) for agent in invalid}))
        raise ValueError(
            f"Invalid agents: {invalid_agents}. Valid agents are: {valid_agents}"
        )

    if not normalized:
        raise ValueError("At least one valid agent must be selected")

    return normalized


def _normalize_single_ticker(raw_ticker: Any, *, field_name: str = "ticker") -> str:
    """Validate a single explicit ticker input from API payloads."""
    ticker = str(raw_ticker or "").strip().upper()
    if not ticker:
        raise ValueError(f"{field_name} required")
    if not _TICKER_INPUT_RE.fullmatch(ticker):
        raise ValueError(
            f"Invalid {field_name} format. Use a ticker like AAPL, BRK.B, or 005930.KS"
        )
    return ticker

# Map agent types to their fallback methods (when agent_executor is not available)
AGENT_FALLBACK_METHODS = {
    "research": "chat",  # Research uses 'chat' instead of 'analyze'
    "market": "analyze",
    "portfolio": "analyze",
    "earnings": "analyze",
    "dcf": "analyze",
}


def extract_ticker_from_query(query: str, is_followup: bool = False) -> Optional[str]:
    """Delegate to shared.ticker_utils.extract_ticker."""
    return _extract_ticker_shared(query, is_followup=is_followup)


def _infer_issue_ticker(*parts: Any) -> Optional[str]:
    for raw_part in parts:
        text = str(raw_part or "").strip()
        if not text:
            continue
        candidate = extract_ticker_from_query(text)
        if candidate:
            return candidate
    return None


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    agent_type: str = "research"  # research, market, portfolio, earnings, dcf
    model: str = "claude-sonnet-4-6"
    session_id: Optional[str] = None
    is_followup: bool = False
    # Persistence metadata (populated by frontend after receiving session_id)
    persist: bool = True   # set False to skip DB write (e.g. health checks)
    project_id: Optional[str] = None  # Set when chat is inside a project workspace


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    agent_type: str
    timestamp: str
    session_id: str


def _build_agent_cache_key(agent_type: str, model: str, session_id: Optional[str]) -> Optional[str]:
    """Use session-scoped cache keys for stateful agents to prevent context leakage."""
    if agent_type in SESSION_SCOPED_AGENT_TYPES:
        # Market analysis is conversational when a session_id is present, but a
        # few internal/test call sites still invoke it without session context.
        # Reuse a shared instance in that case instead of rebuilding the agent
        # on every request.
        if agent_type == "market" and not session_id:
            return f"{agent_type}_{model}"
        if not session_id:
            return None
        return f"{agent_type}_{model}_{session_id}"
    return f"{agent_type}_{model}"


def _create_agent_instance(agent_type: str, model: str):
    """Create a single agent instance for the requested type."""
    if agent_type == "research":
        return create_finance_qa_agent(model=model, db_session_factory=SyncSessionLocal)
    if agent_type == "market":
        return create_market_agent(model=model)
    if agent_type == "portfolio":
        return create_portfolio_agent(model=model)
    if agent_type == "earnings":
        return create_earnings_agent(model=model)
    if agent_type == "dcf":
        return DCFAgentAdapter(model=model)
    raise ValueError(f"Unknown agent type: {agent_type}")


def get_or_create_agent(agent_type: str, model: str, session_id: Optional[str] = None):
    """Get cached agent or create a fresh instance when session scoping is required."""
    cache_key = _build_agent_cache_key(agent_type, model, session_id)

    try:
        if cache_key is None:
            return _create_agent_instance(agent_type, model)

        with agents_cache_lock:
            if cache_key in agents_cache:
                agents_cache.move_to_end(cache_key)  # LRU: mark as recently used
                return agents_cache[cache_key]
            agent = _create_agent_instance(agent_type, model)
            agents_cache[cache_key] = agent
            while len(agents_cache) > _AGENTS_CACHE_MAX:
                agents_cache.popitem(last=False)  # evict oldest (LRU)
            return agent
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


def _ensure_str_response(value) -> str:
    """Normalize Anthropic content blocks (list) or other types to a plain string.

    ChatAnthropic returns AIMessage.content as a list of content blocks
    (e.g., [{"type": "text", "text": "..."}]) instead of a plain string.
    This function extracts the text from all blocks and returns a single string.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(value) if value is not None else ""


async def run_agent_with_callbacks(agent, message: str, agent_type: str, queue: asyncio.Queue, is_followup: bool = False):
    """
    Run agent in executor with callback handler.

    Executes the agent synchronously in a thread pool executor while streaming
    events (thoughts, tool calls, results) to an async queue for SSE delivery.

    Args:
        agent: LangChain agent instance (with agent_executor or fallback method)
        message: User's input message to process
        agent_type: One of 'research', 'market', 'portfolio', 'earnings', 'dcf'
        queue: Async queue for streaming events to SSE response
        is_followup: Whether this is a follow-up question (earnings agent only)
    """
    loop = asyncio.get_running_loop()
    callback = StreamingCallbackHandler(queue)

    try:
        # Validate agent type
        if agent_type not in AGENT_FALLBACK_METHODS:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # Inject progress queue for agents that use direct tool calls (bypassing LangChain callbacks)
        if agent_type in ("earnings", "graph"):
            agent._progress_queue = queue
            agent._progress_loop = loop

        # Use _invoke() if available — it resets per-request callback state before calling
        # agent_executor, ensuring step counters don't accumulate on cached agent instances.
        # Fall back to agent_executor.invoke() for agents that don't implement _invoke().
        if hasattr(agent, '_invoke'):
            input_dict = {"input": message}
            if is_followup and agent_type == "earnings":
                input_dict["followup"] = True
            response = await loop.run_in_executor(
                None,
                lambda: agent._invoke(input_dict, [callback])
            )
        elif hasattr(agent, 'agent_executor'):
            input_dict = {"input": message}
            if is_followup and agent_type == "earnings":
                input_dict["followup"] = True
            response = await loop.run_in_executor(
                None,
                lambda: agent.agent_executor.invoke(
                    input_dict,
                    config={"callbacks": [callback]}
                )["output"]
            )
        else:
            # Fallback to agent's direct method (analyze or chat)
            fallback_method_name = AGENT_FALLBACK_METHODS[agent_type]
            fallback_method = getattr(agent, fallback_method_name)
            response = await loop.run_in_executor(None, fallback_method, message)

        # Clean up progress queue
        if agent_type in ("earnings", "graph"):
            agent._progress_queue = None
            agent._progress_loop = None

        # Normalize response to string — Anthropic returns list of content blocks
        response = _ensure_str_response(response)

        await queue.put({"type": "response", "content": response})
        await queue.put({"type": "done"})

    except Exception as e:
        # Clean up progress queue on error too
        if agent_type in ("earnings", "graph"):
            agent._progress_queue = None
            agent._progress_loop = None
        await queue.put({"type": "error", "error": str(e)})


async def run_project_graph_with_callbacks(
    adapter,
    input_dict: dict,
    queue: asyncio.Queue,
    state_container: dict,
) -> None:
    """Run ProjectAnalysisGraph in executor, stream progress events via queue.

    Final response is placed in queue as {"type": "response", "content": ...}.
    Extracted state (including memory_patch) is written to state_container["state"].
    """
    loop = asyncio.get_running_loop()
    graph_instance = adapter.graph_instance
    graph_instance._progress_queue = queue
    graph_instance._progress_loop = loop

    try:
        result = await loop.run_in_executor(None, lambda: adapter.invoke(input_dict))
        state_container["state"] = result.get("_state", {}) if result else {}
        output = result.get("output", "") if result else ""
        await queue.put({"type": "response", "content": output})
        await queue.put({"type": "done"})
    except Exception as exc:
        state_container["state"] = {}
        await queue.put({"type": "error", "error": str(exc)})
    finally:
        graph_instance._progress_queue = None
        graph_instance._progress_loop = None


async def route_agent_for_message(message: str) -> str:
    """Use Claude Haiku to classify a user message to the best chat agent.

    Returns one of: 'research', 'analyst', 'market'
    Falls back to 'research' on any error.
    """
    import anthropic
    client = anthropic.AsyncAnthropic()

    routing_prompt = (
        "Route this financial query to the best agent. Reply with ONLY one word.\n\n"
        "Agents:\n"
        "- earnings: Earnings reports, quarterly results, EPS beats/misses, earnings call analysis, "
        "analyst estimates, earnings surprises, revenue guidance, management commentary from calls. "
        "ONLY use this if the query explicitly mentions earnings, EPS, quarterly results, or beats/misses "
        "AND names a specific company or ticker.\n"
        "- analyst: Deep equity analysis, investment thesis, moat/competitive analysis, "
        "buy/sell recommendation, 'should I invest' questions, stock screeners\n"
        "- market: Market conditions, S&P 500/NASDAQ/Dow indices, VIX, sector rotation, "
        "macro trends, Fed policy, inflation, recession risk, market sentiment\n"
        "- research: Everything else — company info, stock comparisons, financial metrics, "
        "quick Q&A, revenue/profit data, R&D spending, product roadmaps, follow-up questions "
        "that reference earlier context without naming a new company, and any question that does "
        "NOT explicitly name a specific company or ticker.\n\n"
        "IMPORTANT: If the query looks like a follow-up (uses words like 'these', 'this', 'their', "
        "'the company', 'it', 'they' without naming a company), route to 'research'.\n\n"
        f"Message: {message}\n\n"
        "Agent:"
    )

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": routing_prompt}],
        )
        agent = _ensure_str_response(response.content).strip().lower()
        return agent if agent in ("research", "analyst", "market", "earnings") else "research"
    except Exception as e:
        logger.warning(f"Auto-routing failed, defaulting to research: {e}")
        return "research"


async def _fetch_json(url: str, *, params: Dict[str, Any], timeout: int = 10) -> Any:
    """Run blocking HTTP requests in a threadpool so async endpoints stay responsive."""
    return await run_in_threadpool(_requests_get_json, url, params=params, timeout=timeout)


async def generate_follow_up_questions(message: str, response: str, agent_type: str) -> list[str]:
    """Generate 3 contextual follow-up questions using Claude Haiku (fast + cheap).

    Returns an empty list if generation fails (non-blocking).
    """
    import anthropic

    client = anthropic.AsyncAnthropic()

    agent_context = {
        "analyst": "comprehensive equity research",
        "graph": "structured equity research",
        "research": "financial research",
        "market": "market analysis and sentiment",
        "portfolio": "portfolio analysis and optimization",
        "earnings": "earnings analysis and quarterly trends",
    }.get(agent_type, "financial analysis")

    try:
        result = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=(
                f"You are a follow-up question generator for a {agent_context} tool. "
                "Generate exactly 3 brief follow-up questions an investor might ask next, "
                "based on the conversation. Each question should explore a different angle. "
                "Return only the questions, one per line, no numbering or bullets."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"User asked: {message}\n\nAssistant responded (excerpt):\n{response[:2000]}",
                }
            ],
        )
        if not result.content:
            return []
        text = result.content[0].text.strip()
    except Exception:
        return []

    questions = [q.strip() for q in text.split("\n") if q.strip()]
    return questions[:3]


async def stream_agent_response(
    message: str,
    agent_type: str,
    model: str,
    is_followup: bool = False,
    session_id: Optional[str] = None,
    persist: bool = True,
    project_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream agent response using Server-Sent Events with thinking process"""
    queue = asyncio.Queue()

    # ── Project session path ──────────────────────────────────────────────────
    if project_id:
        try:
            from backend.database import AsyncSessionLocal
            from backend.context_assembly import assemble_project_context
            from backend.project_router import route_for_project
            from agents.project_agent import ProjectAnalysisGraph, ProjectAnalysisGraphAdapter
            from data.chroma_client import ProjectChromaClient

            # 1. Assemble context and load project config
            async with AsyncSessionLocal() as _db:
                _chroma = ProjectChromaClient()
                context_block = await assemble_project_context(project_id, message, _db, _chroma)
                _proj_result = await _db.execute(select(Project).where(Project.id == project_id))
                _proj = _proj_result.scalar_one_or_none()
                if not _proj:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Project not found'})}\n\n"
                    return
                project_config: dict = json.loads(_proj.config) if _proj.config else {}

            # 2. Route query to agents
            routing_decision_obj = await route_for_project(message, context_block, project_config)
            routing_decision = {
                "agents": [
                    {"agent_type": a.agent_type, "task": a.task}
                    for a in routing_decision_obj.agents
                ],
                "reasoning": routing_decision_obj.reasoning,
            }

            yield f"data: {json.dumps({'type': 'routing_decision', 'agent': 'project', 'routing': routing_decision})}\n\n"
            yield f"data: {json.dumps({'type': 'start', 'agent': 'project'})}\n\n"

            # 3. Run graph
            graph = ProjectAnalysisGraph()
            adapter = ProjectAnalysisGraphAdapter(graph)
            state_container: dict = {}
            task = asyncio.create_task(
                run_project_graph_with_callbacks(
                    adapter,
                    {
                        "input": message,
                        "project_id": project_id,
                        "context_block": context_block,
                        "routing_decision": routing_decision,
                    },
                    queue,
                    state_container,
                )
            )

            # 4. Drain queue (same pattern as regular path)
            collected_response = ""
            while True:
                event = await queue.get()
                if event["type"] == "done":
                    break
                elif event["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'error': event['error']})}\n\n"
                    task.cancel()
                    break
                elif event["type"] == "response":
                    collected_response = event["content"]
                    for i in range(0, len(collected_response), SSE_CHUNK_SIZE):
                        chunk = collected_response[i:i + SSE_CHUNK_SIZE]
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                        await asyncio.sleep(SSE_STREAM_DELAY_SECONDS)
                else:
                    yield f"data: {json.dumps(event)}\n\n"

            try:
                await task
            except asyncio.CancelledError:
                pass

            # 5a. Non-blocking memory update background task
            final_state = state_container.get("state", {})
            memory_patch = final_state.get("memory_patch") or {}
            if memory_patch:
                try:
                    _fire_and_forget(_run_memory_update(project_id, memory_patch))
                except Exception as _me:
                    logger.warning("Failed to schedule memory update for project %s: %s", project_id, _me)

            # 5. Persist with project_id linkage
            ticker = extract_ticker_from_query(message, is_followup=is_followup)
            if persist and collected_response:
                try:
                    _fire_and_forget(
                        _persist_conversation(
                            session_id=session_id,
                            user_message=message,
                            assistant_response=collected_response,
                            agent_type="project",
                            ticker=ticker,
                            thinking_steps=[],
                            follow_ups=[],
                            project_id=project_id,
                        )
                    )
                except Exception as _pe:
                    logger.warning(f"Failed to schedule project persistence: {_pe}")

            yield f"data: {json.dumps({'type': 'end'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Project analysis error: {str(e)}'})}\n\n"
        return
    # ── End project path ──────────────────────────────────────────────────────

    try:
        # Auto-route when agent_type is "auto" — use Claude Haiku to classify the query
        resolved_agent_type = agent_type
        if agent_type == "auto":
            resolved_agent_type = await route_agent_for_message(message)
            logger.info(f"[AUTO-ROUTE] '{message[:60]}...' → {resolved_agent_type}")
            yield f"data: {json.dumps({'type': 'routing_decision', 'agent': resolved_agent_type})}\n\n"

        agent = get_or_create_agent(resolved_agent_type, model, session_id=session_id)

        # Send start event
        yield f"data: {json.dumps({'type': 'start', 'agent': resolved_agent_type})}\n\n"

        # Extract ticker from user query and send as metadata
        ticker = extract_ticker_from_query(message, is_followup=is_followup)
        if ticker:
            logger.info("Detected ticker from query: %s", ticker)
            yield f"data: {json.dumps({'type': 'ticker_metadata', 'ticker': ticker})}\n\n"

        # Start agent execution in background
        task = asyncio.create_task(run_agent_with_callbacks(agent, message, resolved_agent_type, queue, is_followup))

        # Accumulate response text for follow-up generation
        collected_response = ""
        collected_thinking: list = []
        collected_charts: dict = {}

        # Stream events from queue
        while True:
            event = await queue.get()

            if event["type"] == "done":
                break
            elif event["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': event['error']})}\n\n"
                break
            elif event["type"] == "response":
                # Stream the final response in chunks
                response = event["content"]
                collected_response = response
                for i in range(0, len(response), SSE_CHUNK_SIZE):
                    chunk = response[i:i + SSE_CHUNK_SIZE]
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                    await asyncio.sleep(SSE_STREAM_DELAY_SECONDS)
            elif event["type"] == "chart_data":
                chart_id = event.get("id")
                if chart_id:
                    collected_charts[chart_id] = event
                yield f"data: {json.dumps(event)}\n\n"
            else:
                # Collect thinking steps for persistence
                if event["type"] in ("thought", "tool", "tool_result"):
                    collected_thinking.append(event)
                # Stream thinking events (thought, tool, tool_result)
                yield f"data: {json.dumps(event)}\n\n"

        # Wait for task to complete
        await task

        # Generate follow-up questions (non-blocking — failures are silently ignored)
        follow_ups: list[str] = []
        if collected_response:
            try:
                follow_ups = await generate_follow_up_questions(message, collected_response, resolved_agent_type)
                if follow_ups:
                    yield f"data: {json.dumps({'type': 'follow_ups', 'questions': follow_ups})}\n\n"
            except Exception:
                pass

        # Persist session + messages + optional analysis to DB
        if persist and collected_response:
            try:
                _fire_and_forget(
                    _persist_conversation(
                        session_id=session_id,
                        user_message=message,
                        assistant_response=collected_response,
                        agent_type=resolved_agent_type,
                        ticker=ticker,
                        thinking_steps=collected_thinking,
                        follow_ups=follow_ups,
                        chart_specs=collected_charts,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to schedule persistence task: {e}")

        # Send end event
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"


# Agent types that should auto-save to the analyses library
_ANALYSIS_AGENT_TYPES = {"earnings"}


async def _run_memory_update(project_id: str, memory_patch: dict) -> None:
    """Background wrapper: open own DB session and apply memory patch.

    Errors are logged but never raised — memory update failure must not affect
    the user-visible response.
    """
    try:
        from backend.database import AsyncSessionLocal
        from data.project_memory import update_project_memory
        async with AsyncSessionLocal() as db:
            await update_project_memory(project_id, memory_patch, db)
        logger.info("Memory update completed for project %s", project_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("_run_memory_update failed for project %s: %s", project_id, exc, exc_info=True)


async def _persist_conversation(
    session_id: Optional[str],
    user_message: str,
    assistant_response: str,
    agent_type: str,
    ticker: Optional[str],
    thinking_steps: list,
    follow_ups: list[str],
    chart_specs: Optional[dict] = None,
    project_id: Optional[str] = None,
) -> None:
    """Persist session, messages, and optional analysis to the database."""
    from backend.database import AsyncSessionLocal
    import uuid as _uuid_mod

    try:
        async with AsyncSessionLocal() as db:
            # Upsert session
            sid = session_id or str(_uuid_mod.uuid4())
            result = await db.execute(select(DBSession).where(DBSession.id == sid))
            db_session = result.scalar_one_or_none()

            if db_session is None:
                title = user_message[:60].strip() or "Conversation"
                db_session = DBSession(
                    id=sid,
                    title=title,
                    agent_type=agent_type,
                )
                db.add(db_session)
            else:
                db_session.last_active_at = datetime.now(timezone.utc)
                db_session.agent_type = agent_type

            # Insert user message
            user_msg = DBMessage(
                session_id=sid,
                role="user",
                content=user_message,
                agent_type=agent_type,
                ticker=ticker,
            )
            db.add(user_msg)
            await db.flush()  # get user_msg.id

            # Insert assistant message
            assistant_msg = DBMessage(
                session_id=sid,
                role="assistant",
                content=assistant_response,
                agent_type=agent_type,
                ticker=ticker,
                thinking_steps=json.dumps(thinking_steps) if thinking_steps else None,
                follow_ups=json.dumps(follow_ups) if follow_ups else None,
                chart_specs=json.dumps(chart_specs) if chart_specs else None,
            )
            db.add(assistant_msg)
            await db.flush()

            # Auto-save analysis for qualifying agent types
            if agent_type in _ANALYSIS_AGENT_TYPES and ticker:
                month_str = datetime.now(timezone.utc).strftime("%b %Y")
                agent_label = {
                    "analyst": "Equity Analyst",
                    "earnings": "Earnings",
                    "graph": "Equity Research",
                }.get(agent_type, agent_type.title())
                analysis = Analysis(
                    session_id=sid,
                    message_id=assistant_msg.id,
                    ticker=ticker,
                    agent_type=agent_type,
                    title=f"{ticker} {agent_label} Analysis — {month_str}",
                    content=assistant_response,
                    tags="[]",
                )
                db.add(analysis)

            # Link session to project (upsert — UNIQUE constraint prevents duplicates)
            if project_id:
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                link_stmt = sqlite_insert(ProjectSession).values(
                    id=str(_uuid_mod.uuid4()),
                    project_id=project_id,
                    session_id=sid,
                    created_at=datetime.now(timezone.utc),
                ).on_conflict_do_nothing()
                await db.execute(link_stmt)

            await db.commit()
            logger.info(f"[DB] Persisted session {sid} with {agent_type} message")
    except Exception as e:
        logger.error(f"[DB] Persistence error: {e}")


@app.post("/chat/stream")
async def chat_stream(chat_message: ChatMessage):
    """Stream chat response using Server-Sent Events"""
    logger.info(f"[CHAT_STREAM] Received request - agent_type: {chat_message.agent_type}, model: {chat_message.model}, message length: {len(chat_message.message)}")
    return StreamingResponse(
        stream_agent_response(
            chat_message.message,
            chat_message.agent_type,
            chat_message.model,
            chat_message.is_followup,
            session_id=chat_message.session_id,
            persist=chat_message.persist,
            project_id=chat_message.project_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(chat_message: ChatMessage):
    """Non-streaming chat endpoint (for simple requests)"""
    try:
        session_id = chat_message.session_id
        if chat_message.agent_type in SESSION_SCOPED_AGENT_TYPES and not session_id:
            session_id = str(uuid_mod.uuid4())

        agent = get_or_create_agent(chat_message.agent_type, chat_message.model, session_id=session_id)

        # Get response synchronously.
        # Use _invoke() where available (resets per-request state, no CLI stdout callbacks).
        # Research agent uses its own 'chat' method; other agents without _invoke fall back to analyze().
        if chat_message.agent_type == "research":
            response = await run_in_threadpool(agent.chat, chat_message.message)
        elif hasattr(agent, '_invoke'):
            response = await run_in_threadpool(
                lambda: agent._invoke({"input": chat_message.message}, [])
            )
        else:
            response = await run_in_threadpool(agent.analyze, chat_message.message)

        response = _ensure_str_response(response)

        return ChatResponse(
            response=response,
            agent_type=chat_message.agent_type,
            timestamp=datetime.now().isoformat(),
            session_id=session_id or "default"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Research Workstation endpoints
# ---------------------------------------------------------------------------

@app.websocket("/ws/research/{run_id}")
async def research_websocket(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for real-time research workstation updates."""
    await research_manager.connect(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping/pong
    except WebSocketDisconnect:
        pass
    finally:
        research_manager.disconnect(run_id, websocket)


@app.post("/research/start")
async def research_start(request: Request):
    """Start a parallel research run for a given ticker."""
    body = await request.json()
    title = body.get("title", "")
    title = title.strip() if isinstance(title, str) else ""
    focus = body.get("focus", "")
    focus = focus.strip() if isinstance(focus, str) else ""
    try:
        ticker = _normalize_single_ticker(body.get("ticker"))
        selected_agents = _normalize_selected_agents(
            body.get("agents"),
            default_to_all=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    run_id = str(uuid_mod_research.uuid4())

    loop = asyncio.get_running_loop()

    def sync_emit(event: dict):
        asyncio.run_coroutine_threadsafe(
            research_manager.broadcast(run_id, event), loop
        )

    async def run_orchestrator():
        orchestrator = ResearchOrchestrator(
            run_id=run_id,
            ticker=ticker,
            selected_agents=selected_agents,
            emit_fn=sync_emit,
            assignment_title=title,
            assignment_focus=focus,
        )
        await asyncio.to_thread(orchestrator.run)

    _fire_and_forget(run_orchestrator())
    return {"run_id": run_id, "ticker": ticker, "title": title or None, "focus": focus or None}


def _suggest_research_agents_sync(ticker: str) -> list[str]:
    from anthropic import Anthropic as _Anthropic
    import json as _json_mod

    client = _Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": (
                f"For the stock {ticker}, which of these analyst agents should run?\n"
                "Agents: dcf, fundamental, quant, risk, macro, sentiment\n\n"
                "Return ONLY a JSON array of agent names. For most stocks use all 6. "
                "Skip \"quant\" for stocks with <6 months history. "
                "Skip \"macro\" for micro-caps under $500M.\n"
                "Example: [\"dcf\",\"fundamental\",\"quant\",\"risk\",\"macro\",\"sentiment\"]"
            ),
        }],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = _json_mod.loads(text.strip())
    except Exception:
        logger.warning("[research/pm-suggest] Invalid model output for %s: %r", ticker, text[:200])
        return list(AGENT_META.keys())

    if not isinstance(parsed, list):
        return list(AGENT_META.keys())

    selected = [agent for agent in parsed if agent in AGENT_META]
    return selected or list(AGENT_META.keys())


@app.post("/research/pm-suggest")
async def research_pm_suggest(request: Request):
    """PM auto-suggests which agents to run for a given ticker."""
    body = await request.json()
    try:
        ticker = _normalize_single_ticker(body.get("ticker"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    agents = await run_in_threadpool(_suggest_research_agents_sync, ticker)
    return {"agents": agents}


# ---------------------------------------------------------------------------
# Research Tasks (the firm's "issue board")
# ---------------------------------------------------------------------------

async def _recover_stale_issue_work(
    db: AsyncSession,
    *,
    max_age: timedelta | None = None,
    limit: int = 500,
) -> Dict[str, int]:
    from backend.cio_router import _task_has_explicit_scope
    from backend.models import AgentRun, HeartbeatRun, ResearchTask, ScheduledAgent

    now = datetime.now(timezone.utc)
    cutoff = now - (max_age or STALE_RUN_RECOVERY_AGE)
    normalized_limit = min(max(limit, 1), 2000)

    result = await db.execute(
        select(AgentRun)
        .where(
            AgentRun.status == "running",
            AgentRun.started_at < cutoff,
        )
        .order_by(AgentRun.started_at.asc())
        .limit(normalized_limit)
    )
    stale_runs = result.scalars().all()

    recovered = 0
    returned_to_queue = 0
    moved_to_review = 0

    for run in stale_runs:
        recovered += 1
        stale_error = (
            "Run was marked stale during recovery. The background worker stopped "
            "before reporting a final result."
        )
        run.status = "failed"
        run.completed_at = now
        run.error = stale_error

        heartbeat_result = await db.execute(
            select(HeartbeatRun).where(
                HeartbeatRun.agent_run_id == run.id,
                HeartbeatRun.status == "running",
            )
        )
        for heartbeat in heartbeat_result.scalars().all():
            heartbeat.status = "failed"
            heartbeat.completed_at = now
            heartbeat.error = stale_error
            heartbeat.summary = heartbeat.summary or "Marked stale during recovery."
            heartbeat.outcome_json = json.dumps(
                {
                    "event": "stale_run_recovered",
                    "agent_run_id": run.id,
                    "recovered_at": now.isoformat(),
                }
            )

        task_result = await db.execute(
            select(ResearchTask).where(ResearchTask.run_id == run.id)
        )
        for task in task_result.scalars().all():
            task.run_id = None
            task.updated_at = now

            if task.assigned_agent_id:
                agent = await db.get(ScheduledAgent, task.assigned_agent_id)
                if agent is None:
                    task.status = "in_review"
                    task.error = "Assigned agent no longer exists. Reassign this issue."
                    moved_to_review += 1
                    await _append_task_activity(
                        db,
                        task.id,
                        "Recovered a stale run, but the assigned agent no longer exists. Issue moved to review.",
                        metadata={
                            "event": "stale_run_missing_agent",
                            "run_id": run.id,
                        },
                    )
                    continue

                if _task_has_explicit_scope(task):
                    task.status = "pending"
                    task.error = (
                        "Previous run went stale and the issue was returned to the queue "
                        "for redispatch."
                    )
                    returned_to_queue += 1
                    await _append_task_activity(
                        db,
                        task.id,
                        f"Recovered a stale {agent.role_title or agent.name} run and returned the issue to the queue.",
                        author_label="System",
                        author_agent_id=agent.id,
                        metadata={
                            "event": "stale_run_requeued",
                            "run_id": run.id,
                            "agent_id": agent.id,
                        },
                    )
                else:
                    role_title = agent.role_title or agent.name
                    task.status = "in_review"
                    task.error = (
                        f"{role_title} needs an explicit ticker or company scope before it can start. "
                        "Update the issue with a concrete company or symbol, then dispatch it again."
                    )
                    moved_to_review += 1
                    await _append_task_activity(
                        db,
                        task.id,
                        f"Recovered a stale run, but {role_title} still needs explicit ticker or company scope. Issue moved to review.",
                        author_label="System",
                        author_agent_id=agent.id,
                        metadata={
                            "event": "stale_run_scope_required",
                            "run_id": run.id,
                            "agent_id": agent.id,
                        },
                    )
                continue

            if task.owner_agent_id:
                task.status = "in_review"
                task.error = (
                    "Recovered a stale run, but this issue has an owner and no runnable assignee. "
                    "Review assignment before retrying."
                )
                moved_to_review += 1
                await _append_task_activity(
                    db,
                    task.id,
                    "Recovered a stale run, but the issue has an owner and no runnable assignee. Issue moved to review.",
                    metadata={
                        "event": "stale_run_owner_only",
                        "run_id": run.id,
                    },
                )
                continue

            task.status = "pending"
            task.error = "Previous run went stale and the issue was returned to the CEO queue."
            returned_to_queue += 1
            await _append_task_activity(
                db,
                task.id,
                "Recovered a stale run and returned the issue to the CEO queue.",
                metadata={
                    "event": "stale_run_returned_to_ceo",
                    "run_id": run.id,
                },
            )

    return {
        "stale_runs_recovered": recovered,
        "tasks_returned_to_queue": returned_to_queue,
        "tasks_moved_to_review": moved_to_review,
    }


async def _normalize_terminal_issue_states(
    db: AsyncSession,
    *,
    limit: int = 2000,
) -> Dict[str, int]:
    from backend.models import AgentRun, HireProposal, ResearchTask, ResearchTaskDocument, ResearchTaskMessage

    now = datetime.now(timezone.utc)
    normalized_limit = min(max(limit, 1), 5000)

    result = await db.execute(
        select(ResearchTask)
        .where(ResearchTask.status == "in_review")
        .order_by(ResearchTask.updated_at.asc())
        .limit(normalized_limit)
    )
    tasks = result.scalars().all()

    moved_to_done = 0

    for task in tasks:
        if task.error:
            continue

        proposal_result = await db.execute(
            select(HireProposal.id)
            .where(
                HireProposal.source_task_id == task.id,
                HireProposal.status == "pending",
            )
            .limit(1)
        )
        if proposal_result.scalar_one_or_none() is not None:
            continue

        if task.run_id:
            run = await db.get(AgentRun, task.run_id)
            if run and run.status == "completed" and not run.error:
                doc_result = await db.execute(
                    select(ResearchTaskDocument.id)
                    .where(
                        ResearchTaskDocument.task_id == task.id,
                        ResearchTaskDocument.document_type == "analysis",
                    )
                    .limit(1)
                )
                has_output_doc = doc_result.scalar_one_or_none() is not None
                if has_output_doc or run.report or run.findings_summary:
                    task.status = "done"
                    task.error = None
                    task.completed_at = task.completed_at or run.completed_at or now
                    task.updated_at = now
                    await _append_task_activity(
                        db,
                        task.id,
                        "Issue output is complete and has been moved from review to done.",
                        metadata={"event": "terminal_state_normalized", "source": "completed_run"},
                    )
                    moved_to_done += 1
                    continue

        if (
            task.triggered_by == "manual_pm_review"
            and task.assigned_agent_id is None
            and task.owner_agent_id is None
        ):
            ceo_message_result = await db.execute(
                select(ResearchTaskMessage.id)
                .where(
                    ResearchTaskMessage.task_id == task.id,
                    ResearchTaskMessage.kind == "chat",
                    ResearchTaskMessage.author_label == "CEO",
                )
                .limit(1)
            )
            if ceo_message_result.scalar_one_or_none() is not None:
                task.status = "done"
                task.error = None
                task.completed_at = task.completed_at or now
                task.updated_at = now
                await _append_task_activity(
                    db,
                    task.id,
                    "CEO provided a final answer and the issue has been moved from review to done.",
                    metadata={"event": "terminal_state_normalized", "source": "ceo_direct_answer"},
                )
                moved_to_done += 1

    return {
        "tasks_moved_to_done": moved_to_done,
    }


async def _task_has_pending_hire_proposal(db: AsyncSession, task_id: str) -> bool:
    from backend.models import HireProposal

    proposal_result = await db.execute(
        select(HireProposal.id)
        .where(
            HireProposal.source_task_id == task_id,
            HireProposal.status == "pending",
        )
        .limit(1)
    )
    return proposal_result.scalar_one_or_none() is not None


async def _latest_ceo_issue_message_id(db: AsyncSession, task_id: str) -> Optional[str]:
    from backend.models import ResearchTaskMessage

    ceo_message_result = await db.execute(
        select(ResearchTaskMessage.id)
        .where(
            ResearchTaskMessage.task_id == task_id,
            ResearchTaskMessage.kind == "chat",
            ResearchTaskMessage.author_label == "CEO",
        )
        .order_by(ResearchTaskMessage.created_at.desc())
        .limit(1)
    )
    return ceo_message_result.scalar_one_or_none()


async def _repair_scope_blocked_review_issue(
    db: AsyncSession,
    task,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Repair old in-review issues that are only stuck because they were created
    before scope inference and CEO/direct-answer normalization were tightened.
    """
    now = now or datetime.now(timezone.utc)
    ticker = (task.ticker or "").strip().upper()
    if ticker and ticker != "GENERAL":
        return {"action": "noop"}

    inferred_ticker = _infer_issue_ticker(task.title, task.notes)
    if inferred_ticker and inferred_ticker.upper() != "GENERAL":
        task.ticker = inferred_ticker.upper()
        task.error = None
        task.status = "pending"
        task.completed_at = None
        task.updated_at = now
        await _append_task_activity(
            db,
            task.id,
            f"Recovered explicit scope from the issue content ({task.ticker}). Issue returned to the queue.",
            metadata={
                "event": "issue_scope_backfilled",
                "scope": task.ticker,
            },
        )
        return {"action": "scope_backfilled", "ticker": task.ticker}

    if task.assigned_agent_id or task.owner_agent_id:
        from backend.cio_router import _looks_like_broad_scope_request

        if not _looks_like_broad_scope_request(task):
            ceo_message_id = await _latest_ceo_issue_message_id(db, task.id)
            if ceo_message_id is not None:
                task.status = "done"
                task.error = None
                task.completed_at = task.completed_at or now
                task.updated_at = now
                await _append_task_activity(
                    db,
                    task.id,
                    "Recovered a scope-blocked delegated issue that already had a final CEO answer. The issue has been moved to done.",
                    metadata={
                        "event": "scope_blocked_delegated_issue_closed",
                        "message_id": ceo_message_id,
                        "assigned_agent_id": task.assigned_agent_id,
                        "owner_agent_id": task.owner_agent_id,
                    },
                )
                return {"action": "done"}

        task.status = "pending"
        task.error = None
        task.completed_at = None
        task.updated_at = now
        await _append_task_activity(
            db,
            task.id,
            "Recovered a delegated issue that was incorrectly left scope-blocked. Returned it to the queue for runtime scope resolution.",
            metadata={
                "event": "scope_blocked_delegated_issue_requeued",
                "assigned_agent_id": task.assigned_agent_id,
                "owner_agent_id": task.owner_agent_id,
            },
        )
        return {"action": "requeued"}

    if not await _task_has_pending_hire_proposal(db, task.id):
        ceo_message_id = await _latest_ceo_issue_message_id(db, task.id)
        if ceo_message_id is not None:
            task.status = "done"
            task.error = None
            task.completed_at = task.completed_at or now
            task.updated_at = now
            await _append_task_activity(
                db,
                task.id,
                "Recovered a scope-blocked issue that already had a CEO answer. The issue has been moved to done.",
                metadata={
                    "event": "scope_blocked_ceo_answer_normalized",
                    "message_id": ceo_message_id,
                },
            )
            return {"action": "done"}

    return {"action": "noop"}


def _anthropic_text_response_sync(model: str, system_prompt: str, messages: list[dict[str, str]]) -> str:
    from anthropic import Anthropic as _Anthropic

    client = _Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=model,
        max_tokens=1200,
        system=system_prompt,
        messages=messages,
    )
    text_parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            text_parts.append(text)
    return "\n\n".join(text_parts).strip()


def _task_thread_transcript(messages: list[Any]) -> str:
    if not messages:
        return "No prior conversation."
    lines: list[str] = []
    for message in messages[-10:]:
        speaker = message.author_label or message.role.title()
        lines.append(f"{speaker}: {message.content}")
    return "\n".join(lines)


def _markdown_to_excerpt(content_md: str, limit: int = 320) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", content_md or "")
    text = re.sub(r"[*_#>\-\[\]\(\)\|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_task_artifact_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "unknown time"
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


async def _load_task_artifact_context(
    db: AsyncSession,
    task_id: str,
    linked_run_id: Optional[str],
) -> dict[str, Any]:
    from backend.models import AgentRun, ResearchTaskDocument

    documents_result = await db.execute(
        select(ResearchTaskDocument)
        .where(ResearchTaskDocument.task_id == task_id)
        .order_by(ResearchTaskDocument.updated_at.desc(), ResearchTaskDocument.created_at.desc())
        .limit(3)
    )
    documents = documents_result.scalars().all()

    linked_run = None
    normalized_run_id = (linked_run_id or "").strip() or None
    if normalized_run_id:
        run_result = await db.execute(select(AgentRun).where(AgentRun.id == normalized_run_id))
        linked_run = run_result.scalar_one_or_none()

    return {
        "documents": documents,
        "linked_run": linked_run,
    }


def _parse_task_findings_blob(raw_findings: Any) -> dict[str, Any]:
    if isinstance(raw_findings, dict):
        return raw_findings
    try:
        parsed = json.loads(raw_findings or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_task_pm_synthesis(raw_synthesis: Any) -> Optional[dict[str, Any]]:
    if isinstance(raw_synthesis, dict):
        return raw_synthesis
    try:
        parsed = json.loads(raw_synthesis or "null")
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _task_artifact_summary_block(artifact_context: dict[str, Any]) -> str:
    documents = artifact_context.get("documents") or []
    linked_run = artifact_context.get("linked_run")

    lines: list[str] = []
    if documents:
        lines.append("Existing issue documents:")
        for document in documents:
            excerpt = _markdown_to_excerpt(document.content_md or "", limit=220)
            lines.append(
                f"- {document.title} (type: {document.document_type}, rev {document.revision}, updated {_format_task_artifact_datetime(document.updated_at)})"
            )
            if excerpt:
                lines.append(f"  Excerpt: {excerpt}")
    else:
        lines.append("Existing issue documents: none.")

    if linked_run is not None:
        run_status = linked_run.status or "unknown"
        lines.append(f"Linked agent run status: {run_status}.")
        if linked_run.findings_summary:
            lines.append(f"Run summary: {_markdown_to_excerpt(linked_run.findings_summary, limit=220)}")
        elif linked_run.report:
            lines.append(f"Run report excerpt: {_markdown_to_excerpt(linked_run.report, limit=220)}")
        elif linked_run.error:
            lines.append(f"Run error: {linked_run.error}")
    else:
        lines.append("Linked agent run: none.")

    return "\n".join(lines)


def _build_task_chat_fallback(
    *,
    role_title: str,
    artifact_context: dict[str, Any],
) -> str:
    documents = artifact_context.get("documents") or []
    linked_run = artifact_context.get("linked_run")

    if documents:
        latest_document = documents[0]
        lines = [
            f"The live {role_title} reply failed, but this issue already has {len(documents)} saved document{'s' if len(documents) != 1 else ''}.",
            (
                f"Latest document: {latest_document.title} "
                f"(rev {latest_document.revision}, updated {_format_task_artifact_datetime(latest_document.updated_at)})."
            ),
        ]
        excerpt = _markdown_to_excerpt(latest_document.content_md or "", limit=320)
        if excerpt:
            lines.append(f"Latest document excerpt: {excerpt}")
        if linked_run is not None and linked_run.status == "completed" and linked_run.findings_summary:
            lines.append(f"Latest run summary: {_markdown_to_excerpt(linked_run.findings_summary, limit=220)}")
        lines.append("Open the Documents tab for the full report.")
        return "\n\n".join(lines)

    if linked_run is not None:
        if linked_run.status == "completed":
            summary = linked_run.findings_summary or linked_run.report or "A completed run exists, but it has no saved summary yet."
            return (
                f"The live {role_title} reply failed, but this issue has a completed run.\n\n"
                f"Latest run summary: {_markdown_to_excerpt(summary, limit=360)}"
            )
        if linked_run.status == "running":
            return f"The assigned agent is still running on this issue. Wait for the current run to finish, then ask again."
        if linked_run.status == "failed":
            error_detail = linked_run.error or "No error detail was recorded."
            return (
                f"The live {role_title} reply failed, and the latest linked run also failed.\n\n"
                f"Latest run error: {error_detail}"
            )

    return (
        f"The live {role_title} reply failed, and this issue does not yet have a saved document or completed linked run."
    )


def _looks_like_status_query(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(
        token in normalized
        for token in (
            "status",
            "progress",
            "where are we",
            "what's happening",
            "what is happening",
            "update",
            "running",
            "complete",
            "completed",
            "done",
            "failed",
            "blocked",
        )
    )


def _looks_like_report_query(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(
        token in normalized
        for token in (
            "report",
            "document",
            "memo",
            "writeup",
            "write-up",
            "analysis",
            "brief",
            "summary",
        )
    )


def _build_issue_state_reply(
    *,
    prompt: str,
    task: Any,
    role_title: str,
    artifact_context: dict[str, Any],
) -> Optional[str]:
    status_query = _looks_like_status_query(prompt)
    report_query = _looks_like_report_query(prompt)
    if not status_query and not report_query:
        return None

    documents = artifact_context.get("documents") or []
    linked_run = artifact_context.get("linked_run")
    findings = _parse_task_findings_blob(getattr(task, "findings", None))
    synthesis = _parse_task_pm_synthesis(getattr(task, "pm_synthesis", None))

    lines: list[str] = []
    if status_query:
        lines.append(f"Issue status: {task.status}.")
        if linked_run is not None:
            lines.append(f"Linked run status: {linked_run.status}.")
            if linked_run.status == "running":
                lines.append(
                    f"The assigned {role_title} is still running on this issue."
                )
            if linked_run.error:
                lines.append(f"Latest run error: {linked_run.error}")
        elif task.assigned_agent_id:
            lines.append(f"This issue is assigned to {role_title}, but there is no linked run record yet.")
        else:
            lines.append("No agent is currently assigned to this issue.")

    if report_query:
        if documents:
            latest_document = documents[0]
            lines.append(
                f"Latest saved document: {latest_document.title} "
                f"(rev {latest_document.revision}, updated {_format_task_artifact_datetime(latest_document.updated_at)})."
            )
            excerpt = _markdown_to_excerpt(latest_document.content_md or "", limit=320)
            if excerpt:
                lines.append(f"Document excerpt: {excerpt}")
            if len(documents) > 1:
                lines.append(f"There are {len(documents)} saved issue documents in total.")
        elif synthesis:
            summary = synthesis.get("summary") or synthesis.get("thesis") or json.dumps(synthesis)
            lines.append(f"Saved synthesis: {_markdown_to_excerpt(str(summary), limit=320)}")
        elif findings:
            first_key = next(iter(findings.keys()))
            finding_summary = findings[first_key].get("summary") if isinstance(findings[first_key], dict) else str(findings[first_key])
            if finding_summary:
                lines.append(f"Saved finding from {first_key}: {_markdown_to_excerpt(str(finding_summary), limit=320)}")
        elif linked_run is not None and linked_run.status == "completed":
            summary = linked_run.findings_summary or linked_run.report or ""
            if summary:
                lines.append(f"Latest run summary: {_markdown_to_excerpt(summary, limit=320)}")
            else:
                lines.append("There is a completed run, but it did not save a readable report summary.")
        elif linked_run is not None and linked_run.status == "running":
            lines.append("No finished report is saved yet. The current run is still in progress.")
        else:
            lines.append("No saved report or document exists on this issue yet.")

    if not lines:
        return None
    if documents and report_query:
        lines.append("Open the Documents tab for the full report.")
    return "\n\n".join(lines)


async def _run_task_chat_reply(
    db: AsyncSession,
    task,
    prompt: str,
    *,
    target_agent_id: Optional[str],
    thread_messages: list[Any],
) -> dict[str, Any]:
    from backend.cio_router import _run_cio_response
    from backend.models import Project, ScheduledAgent

    project_title: Optional[str] = None
    project_thesis: Optional[str] = None
    if task.project_id:
        project_result = await db.execute(
            select(Project.title, Project.thesis).where(Project.id == task.project_id)
        )
        project_row = project_result.one_or_none()
        if project_row is not None:
            project_title, project_thesis = project_row
    artifact_context = await _load_task_artifact_context(db, task.id, task.run_id)
    artifact_context_block = _task_artifact_summary_block(artifact_context)

    normalized_target_agent_id = (target_agent_id or "").strip() or None
    is_ceo_route = (
        normalized_target_agent_id in {None, "synthetic-ceo"}
        and (
            task.triggered_by == "manual_pm_review"
            or (task.assigned_agent_id is None and task.owner_agent_id is None)
        )
    )

    if is_ceo_route:
        issue_prompt = (
            f"Issue title: {task.title}\n"
            f"Issue ticker: {task.ticker}\n"
            f"Issue type: {task.task_type}\n"
            f"Issue priority: {task.priority}\n"
            f"Project: {project_title or 'None'}\n"
            f"Project thesis: {project_thesis or 'None'}\n"
            f"Issue brief: {task.notes or 'None'}\n\n"
            f"Recent issue thread:\n{_task_thread_transcript(thread_messages)}\n\n"
            f"Latest user follow-up:\n{prompt}"
        )
        response = await _run_cio_response(
            db,
            [{"role": "user", "content": issue_prompt}],
            proposed_by=f"issue:{task.id}",
            source_task_id=task.id,
        )
        return {
            "author_label": "CEO",
            "author_agent_id": None,
            "content": response.message,
            "action": response.action.model_dump() if response.action else None,
        }

    resolved_agent_id = normalized_target_agent_id or task.assigned_agent_id or task.owner_agent_id
    if not resolved_agent_id:
        return {
            "author_label": "System",
            "author_agent_id": None,
            "content": "No agent is assigned to this issue yet.",
            "action": None,
        }

    agent_result = await db.execute(select(ScheduledAgent).where(ScheduledAgent.id == resolved_agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        return {
            "author_label": "System",
            "author_agent_id": None,
            "content": "The assigned agent could not be found.",
            "action": None,
        }

    role_title = agent.role_title or agent.name
    instruction = (agent.instruction or "").strip() or "Answer as the analyst responsible for this issue."
    tickers = json.loads(agent.tickers or "[]")
    selected_agents = json.loads(task.selected_agents or "[]")

    direct_issue_reply = _build_issue_state_reply(
        prompt=prompt,
        task=task,
        role_title=role_title,
        artifact_context=artifact_context,
    )
    if direct_issue_reply:
        return {
            "author_label": role_title,
            "author_agent_id": agent.id,
            "content": direct_issue_reply,
            "action": None,
        }

    system_prompt = (
        f"You are the {role_title} in a finance research firm.\n"
        f"Your job is to respond inside one issue workspace.\n"
        f"Stay focused on the specific issue and give concrete next-step guidance.\n"
        f"Your current instruction:\n{instruction}\n\n"
        f"Issue context:\n"
        f"- Title: {task.title}\n"
        f"- Ticker: {task.ticker}\n"
        f"- Type: {task.task_type}\n"
        f"- Priority: {task.priority}\n"
        f"- Project: {project_title or 'None'}\n"
        f"- Project thesis: {project_thesis or 'None'}\n"
        f"- Assigned coverage: {', '.join(tickers) if tickers else 'General'}\n"
        f"- Selected engines: {', '.join(selected_agents) if selected_agents else 'None'}\n"
        f"- Issue brief: {task.notes or 'None'}\n\n"
        f"Saved issue artifacts:\n{artifact_context_block}\n\n"
        f"Keep the answer concise, specific, and actionable. If the user asks for a document, draft it directly."
    )
    recent_prompt_messages = [
        {"role": "assistant" if message.role == "assistant" else "user", "content": message.content}
        for message in thread_messages[-8:]
        if message.kind == "chat"
    ]
    if not recent_prompt_messages or recent_prompt_messages[-1]["role"] != "user":
        recent_prompt_messages.append({"role": "user", "content": prompt})

    try:
        content = await run_in_threadpool(
            _anthropic_text_response_sync,
            CIO_MODEL,
            system_prompt,
            recent_prompt_messages,
        )
    except Exception:
        logger.exception("task chat reply failed for agent %s", agent.id)
        content = _build_task_chat_fallback(
            role_title=role_title,
            artifact_context=artifact_context,
        )

    return {
        "author_label": role_title,
        "author_agent_id": agent.id,
        "content": content or "No reply generated.",
        "action": None,
    }


async def _run_task_chat_reply_proxy(*args, **kwargs):
    return await _run_task_chat_reply(*args, **kwargs)


app.include_router(create_task_chat_router(_run_task_chat_reply_proxy))


@app.post("/tasks", status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Create a new research task. Used by manual creation and by routines."""
    from backend.cio_router import _dispatch_agent_for_task, queue_cio_review_for_task
    from backend.models import Project, ResearchTask, ScheduledAgent

    task_type = (body.task_type or "ad_hoc").lower()
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task_type. Must be one of: {sorted(VALID_TASK_TYPES)}")

    priority = (body.priority or "medium").lower()
    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority. Must be one of: {sorted(VALID_PRIORITIES)}")

    raw_ticker = (body.ticker or "").strip()
    if raw_ticker:
        try:
            ticker = _normalize_single_ticker(raw_ticker, field_name="ticker")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        inferred_ticker = _infer_issue_ticker(body.title, body.notes)
        ticker = inferred_ticker or "GENERAL"

    if body.title:
        title = body.title
    elif ticker == "GENERAL":
        title = TASK_TYPE_TITLES.get(task_type, "Research")
    else:
        title = f"{TASK_TYPE_TITLES.get(task_type, 'Research')}: {ticker}"
    try:
        selected = _normalize_selected_agents(
            body.selected_agents,
            default_to_all=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    project_id = (body.project_id or "").strip() or None
    if project_id:
        project_result = await db.execute(select(Project.id).where(Project.id == project_id))
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Invalid project_id")

    owner_agent_id = (body.owner_agent_id or "").strip() or None
    if owner_agent_id:
        owner_result = await db.execute(select(ScheduledAgent.id).where(ScheduledAgent.id == owner_agent_id))
        if owner_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Invalid owner_agent_id")

    triggered_by = (body.triggered_by or "manual").strip() or "manual"

    assigned_agent_id = (body.assigned_agent_id or "").strip() or None
    assigned_agent = None
    if assigned_agent_id:
        assigned_result = await db.execute(select(ScheduledAgent).where(ScheduledAgent.id == assigned_agent_id))
        assigned_agent = assigned_result.scalar_one_or_none()
        if assigned_agent is None:
            raise HTTPException(status_code=400, detail="Invalid assigned_agent_id")
        if not assigned_agent.is_active:
            raise HTTPException(status_code=409, detail=f"{assigned_agent.role_title or assigned_agent.name} is paused")

    should_queue_cio_review = (
        assigned_agent is None
        and owner_agent_id is None
    )

    task = ResearchTask(
        ticker=ticker,
        task_type=task_type,
        title=title,
        priority=priority,
        selected_agents=json.dumps(selected),
        project_id=project_id,
        parent_task_id=body.parent_task_id,
        owner_agent_id=owner_agent_id,
        assigned_agent_id=assigned_agent_id,
        source_heartbeat_run_id=body.source_heartbeat_run_id,
        triggered_by=triggered_by,
        notes=body.notes,
    )
    db.add(task)
    await db.flush()
    await _append_task_activity(
        db,
        task.id,
        f"Issue created: {task.title}",
        metadata={
            "event": "task_created",
            "status": task.status,
            "priority": task.priority,
            "assigned_agent_id": task.assigned_agent_id,
            "owner_agent_id": task.owner_agent_id,
        },
    )
    if should_queue_cio_review:
        await _append_task_activity(
            db,
            task.id,
            "CEO review queued for this issue.",
            author_label="System",
            metadata={"event": "ceo_review_queued"},
        )
    await db.commit()
    await db.refresh(task)

    if assigned_agent is not None:
        await _dispatch_agent_for_task(
            db,
            task,
            assigned_agent,
            trigger_type="manual",
            initiated_by="System",
            note="Issue was assigned directly to this agent.",
        )
        await db.refresh(task)
    elif should_queue_cio_review:
        queue_cio_review_for_task(task.id)
    return _task_to_dict(task)


@app.patch("/tasks/{task_id}")
async def patch_task(task_id: str, body: TaskPatch, db: AsyncSession = Depends(get_db)):
    """Update a task's status / fields. Auto-stamps started_at and completed_at on status transitions."""
    from sqlalchemy import select
    from backend.cio_router import _dispatch_agent_for_task
    from backend.models import Project, ResearchTask, ScheduledAgent

    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")

    activity_changes: list[str] = []
    assignment_changed = False
    assigned_agent_to_dispatch = None

    if body.status is not None:
        if body.status not in VALID_TASK_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        prev = t.status
        t.status = body.status
        if body.status == "running" and t.started_at is None:
            t.started_at = datetime.utcnow()
        if body.status in ("done", "cancelled", "failed") and t.completed_at is None:
            t.completed_at = datetime.utcnow()
        if prev != body.status:
            activity_changes.append(f"Status changed from {prev} to {body.status}")
    if body.priority is not None:
        if body.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority")
        if t.priority != body.priority:
            activity_changes.append(f"Priority changed from {t.priority} to {body.priority}")
        t.priority = body.priority
    if body.title is not None:
        if t.title != body.title:
            activity_changes.append(f"Title updated to {body.title}")
        t.title = body.title
    if body.notes is not None:
        if (t.notes or "") != body.notes:
            activity_changes.append("Issue brief updated")
        t.notes = body.notes
    if body.project_id is not None:
        normalized_project_id = body.project_id.strip() or None
        if normalized_project_id:
            project_result = await db.execute(select(Project.id).where(Project.id == normalized_project_id))
            if project_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=400, detail="Invalid project_id")
        if t.project_id != normalized_project_id:
            activity_changes.append("Project linkage updated")
        t.project_id = normalized_project_id
    if body.overall_sentiment is not None:
        t.overall_sentiment = body.overall_sentiment
    if body.owner_agent_id is not None:
        normalized_owner_agent_id = body.owner_agent_id.strip() or None
        if normalized_owner_agent_id:
            owner_result = await db.execute(
                select(ScheduledAgent.id).where(ScheduledAgent.id == normalized_owner_agent_id)
            )
            if owner_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=400, detail="Invalid owner_agent_id")
        if t.owner_agent_id != normalized_owner_agent_id:
            activity_changes.append("Owner agent updated")
        t.owner_agent_id = normalized_owner_agent_id
    if body.assigned_agent_id is not None:
        normalized_assigned_agent_id = body.assigned_agent_id.strip() or None
        assigned_agent = None
        if normalized_assigned_agent_id:
            assigned_result = await db.execute(
                select(ScheduledAgent).where(ScheduledAgent.id == normalized_assigned_agent_id)
            )
            assigned_agent = assigned_result.scalar_one_or_none()
            if assigned_agent is None:
                raise HTTPException(status_code=400, detail="Invalid assigned_agent_id")
            if not assigned_agent.is_active:
                raise HTTPException(status_code=409, detail=f"{assigned_agent.role_title or assigned_agent.name} is paused")
        if t.assigned_agent_id != normalized_assigned_agent_id:
            activity_changes.append("Assigned agent updated")
            assignment_changed = True
        t.assigned_agent_id = normalized_assigned_agent_id
        assigned_agent_to_dispatch = assigned_agent
    if body.source_heartbeat_run_id is not None:
        t.source_heartbeat_run_id = body.source_heartbeat_run_id
    if body.completed_agents is not None:
        t.completed_agents = json.dumps(body.completed_agents)
    if body.findings is not None:
        t.findings = json.dumps(body.findings)
    if body.pm_synthesis is not None:
        t.pm_synthesis = json.dumps(body.pm_synthesis)
    if body.mandate_check is not None:
        t.mandate_check = body.mandate_check
    if body.risk_check is not None:
        t.risk_check = body.risk_check
    if body.compliance_check is not None:
        t.compliance_check = body.compliance_check
    if body.approval_status is not None:
        t.approval_status = body.approval_status
    if body.error is not None:
        t.error = body.error

    t.updated_at = datetime.utcnow()
    if activity_changes:
        await _append_task_activity(
            db,
            t.id,
            " · ".join(activity_changes),
            metadata={"event": "task_updated"},
        )
    await db.commit()
    await db.refresh(t)

    if assignment_changed and assigned_agent_to_dispatch is not None and t.status in {"pending", "failed"}:
        await _dispatch_agent_for_task(
            db,
            t,
            assigned_agent_to_dispatch,
            trigger_type="manual",
            initiated_by="System",
            note="Issue assignment was updated.",
        )
        await db.refresh(t)
    return _task_to_dict(t)


@app.post("/tasks/{task_id}/run")
async def run_task_pipeline(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Trigger the InvestmentPipeline for a pending task.
    Stage 1 (parallel research) + Stages 2-4 (Risk → Compliance → PM Decision).

    Returns immediately with a run_id; the pipeline runs in the background and
    streams events via the existing /ws/research/{run_id} WebSocket.
    """
    from sqlalchemy import select
    from backend.models import ResearchTask
    from backend.investment_pipeline import InvestmentPipeline

    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Task is already in status '{task.status}'. Only pending or failed tasks can be run.",
        )

    try:
        parsed_agents = json.loads(task.selected_agents or "[]")
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Task has invalid selected_agents payload. Update the task and retry.",
        )
    try:
        selected_agents = _normalize_selected_agents(parsed_agents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Task has invalid selected_agents: {exc}")

    ticker = task.ticker
    task_type = task.task_type or "ad_hoc"
    triggered_by = task.triggered_by or "manual"

    run_id = str(uuid_mod_research.uuid4())
    loop = asyncio.get_running_loop()

    def sync_emit(event: dict):
        asyncio.run_coroutine_threadsafe(
            research_manager.broadcast(run_id, event), loop
        )

    async def run_pipeline():
        pipeline = InvestmentPipeline(
            run_id=run_id,
            ticker=ticker,
            selected_agents=selected_agents,
            emit_fn=sync_emit,
            task_id=task_id,
            task_type=task_type,
            triggered_by=triggered_by,
        )
        await asyncio.to_thread(pipeline.run)

    _fire_and_forget(run_pipeline())
    return {"run_id": run_id, "task_id": task_id, "ticker": ticker}


@app.post("/tasks/{task_id}/run-now")
async def run_task_now(task_id: str, db: AsyncSession = Depends(get_db)):
    from backend.cio_router import _append_issue_activity, _dispatch_agent_for_task, queue_cio_review_for_task
    from backend.models import ResearchTask, ScheduledAgent

    result = await db.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "cancelled":
        raise HTTPException(
            status_code=400,
            detail=f"Task is already in status '{task.status}'. Cancelled tasks cannot be started again.",
        )

    if task.status == "in_review" and task.error and "explicit ticker or company scope" in task.error:
        repair = await _repair_scope_blocked_review_issue(db, task)
        if repair["action"] == "done":
            await db.commit()
            await db.refresh(task)
            return {
                "action": "completed",
                "task": _task_to_dict(task),
                "run_id": None,
                "reused": False,
                "skipped": False,
            }

    if task.assigned_agent_id:
        agent = await db.get(ScheduledAgent, task.assigned_agent_id)
        if agent is None:
            raise HTTPException(status_code=400, detail="Assigned agent no longer exists")
        if not agent.is_active:
            raise HTTPException(status_code=409, detail=f"{agent.role_title or agent.name} is paused")
        dispatch_result = await _dispatch_agent_for_task(
            db,
            task,
            agent,
            trigger_type="manual",
            initiated_by="User",
            note="Run now requested from the issue workspace.",
        )
        await db.refresh(task)
        return {
            "action": "dispatch",
            "task": _task_to_dict(task),
            **dispatch_result,
        }

    task.status = "pending"
    task.error = None
    task.updated_at = datetime.utcnow()
    await _append_issue_activity(
        db,
        task.id,
        "Run now requested. CEO review queued for this issue.",
        author_label="User",
        metadata={"event": "ceo_review_queued", "source": "run_now"},
    )
    await db.commit()
    await db.refresh(task)
    queue_cio_review_for_task(task.id)
    return {
        "action": "ceo_review_queued",
        "task": _task_to_dict(task),
        "run_id": None,
        "reused": False,
        "skipped": False,
    }


@app.post("/tasks/refresh-work")
async def refresh_task_work_queue(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually sweep pending issues and restart the routing/dispatch path.

    - Unassigned pending issues are re-queued to the CEO.
    - Agent-assigned pending issues are re-dispatched through the normal
      agent runner path.
    """
    from backend.cio_router import _append_issue_activity, _dispatch_agent_for_task, queue_cio_review_for_task
    from backend.models import HireProposal, ResearchTask, ResearchTaskMessage, ScheduledAgent

    normalized_limit = min(max(limit, 1), 500)
    recovery = await _recover_stale_issue_work(db, limit=normalized_limit)
    normalization = await _normalize_terminal_issue_states(db, limit=normalized_limit * 4)
    await db.flush()
    result = await db.execute(
        select(ResearchTask)
        .where(
            ResearchTask.status == "pending",
            ResearchTask.run_id.is_(None),
        )
        .order_by(ResearchTask.created_at.asc())
        .limit(normalized_limit)
    )
    tasks = result.scalars().all()

    queued_for_ceo = 0
    redispatched = 0
    moved_to_review = 0
    moved_scope_blocked_to_done = 0
    skipped = 0
    queueable_task_ids: list[str] = []

    for task in tasks:
        if (
            task.triggered_by == "manual_pm_review"
            and task.assigned_agent_id is None
            and task.owner_agent_id is None
        ):
            proposal_result = await db.execute(
                select(HireProposal.id)
                .where(
                    HireProposal.source_task_id == task.id,
                    HireProposal.status == "pending",
                )
                .limit(1)
            )
            pending_proposal_id = proposal_result.scalar_one_or_none()
            if pending_proposal_id is not None:
                task.status = "in_review"
                task.error = None
                task.updated_at = datetime.now(timezone.utc)
                await _append_task_activity(
                    db,
                    task.id,
                    "Queue refresh detected a pending CEO hire proposal. Issue moved to review.",
                    metadata={
                        "event": "queue_refresh_pending_proposal",
                        "proposal_id": pending_proposal_id,
                    },
                )
                moved_to_review += 1
                continue

            ceo_message_result = await db.execute(
                select(ResearchTaskMessage.id)
                .where(
                    ResearchTaskMessage.task_id == task.id,
                    ResearchTaskMessage.kind == "chat",
                    ResearchTaskMessage.author_label == "CEO",
                )
                .limit(1)
            )
            ceo_message_id = ceo_message_result.scalar_one_or_none()
            if ceo_message_id is not None:
                task.status = "in_review"
                task.error = None
                task.updated_at = datetime.now(timezone.utc)
                await _append_task_activity(
                    db,
                    task.id,
                    "Queue refresh detected an existing CEO response. Issue moved to review.",
                    metadata={
                        "event": "queue_refresh_existing_ceo_response",
                        "message_id": ceo_message_id,
                    },
                )
                moved_to_review += 1
                continue

        if task.assigned_agent_id:
            agent = await db.get(ScheduledAgent, task.assigned_agent_id)
            if agent is None:
                task.status = "in_review"
                task.error = "Assigned agent no longer exists. Reassign this issue."
                task.updated_at = datetime.now(timezone.utc)
                await _append_task_activity(
                    db,
                    task.id,
                    "Assigned agent was missing during queue refresh. Issue moved to review.",
                    metadata={"event": "queue_refresh_missing_agent"},
                )
                moved_to_review += 1
                continue

            dispatch_result = await _dispatch_agent_for_task(
                db,
                task,
                agent,
                trigger_type="manual",
                initiated_by="System",
                note="Manual queue refresh restarted this issue.",
            )
            if dispatch_result.get("run_id"):
                redispatched += 1
            elif dispatch_result.get("reason") == "scope_required":
                moved_to_review += 1
            else:
                skipped += 1
            continue

        if task.owner_agent_id:
            task.status = "in_review"
            task.error = "Issue has an owner but no runnable assignee. Review assignment."
            task.updated_at = datetime.now(timezone.utc)
            await _append_task_activity(
                db,
                task.id,
                "Queue refresh found an owner-only issue with no runnable assignee. Issue moved to review.",
                metadata={"event": "queue_refresh_owner_only"},
            )
            moved_to_review += 1
            continue

        await _append_issue_activity(
            db,
            task.id,
            "Manual queue refresh re-queued this issue for CEO routing.",
            author_label="System",
            metadata={"event": "queue_refresh_requeued"},
        )
        queued_for_ceo += 1
        queueable_task_ids.append(task.id)

    review_result = await db.execute(
        select(ResearchTask)
        .where(
            ResearchTask.status == "in_review",
            ResearchTask.error.is_not(None),
        )
        .order_by(ResearchTask.updated_at.asc())
        .limit(normalized_limit)
    )
    review_tasks = review_result.scalars().all()

    for task in review_tasks:
        task_error = task.error or ""
        if "explicit ticker or company scope" not in task_error:
            continue

        repair = await _repair_scope_blocked_review_issue(db, task)
        if repair["action"] == "scope_backfilled":
            if task.assigned_agent_id:
                agent = await db.get(ScheduledAgent, task.assigned_agent_id)
                if agent is not None and agent.is_active:
                    dispatch_result = await _dispatch_agent_for_task(
                        db,
                        task,
                        agent,
                        trigger_type="manual",
                        initiated_by="System",
                        note="Queue refresh recovered explicit issue scope and restarted this issue.",
                    )
                    if dispatch_result.get("run_id"):
                        redispatched += 1
                    elif dispatch_result.get("reason") == "scope_required":
                        moved_to_review += 1
                    else:
                        skipped += 1
                else:
                    moved_to_review += 1
            else:
                queued_for_ceo += 1
                queueable_task_ids.append(task.id)
        elif repair["action"] == "requeued":
            if task.assigned_agent_id:
                agent = await db.get(ScheduledAgent, task.assigned_agent_id)
                if agent is not None and agent.is_active:
                    dispatch_result = await _dispatch_agent_for_task(
                        db,
                        task,
                        agent,
                        trigger_type="manual",
                        initiated_by="System",
                        note="Queue refresh requeued a delegated broad-scope issue for runtime scope resolution.",
                    )
                    if dispatch_result.get("run_id"):
                        redispatched += 1
                    elif dispatch_result.get("reason") == "scope_required":
                        moved_to_review += 1
                    else:
                        skipped += 1
                else:
                    moved_to_review += 1
            else:
                queued_for_ceo += 1
                queueable_task_ids.append(task.id)
        elif repair["action"] == "done":
            moved_scope_blocked_to_done += 1
        elif task.assigned_agent_id:
            agent = await db.get(ScheduledAgent, task.assigned_agent_id)
            if agent is not None and agent.is_active:
                dispatch_result = await _dispatch_agent_for_task(
                    db,
                    task,
                    agent,
                    trigger_type="manual",
                    initiated_by="System",
                    note="Queue refresh retried a broad-scope issue with runtime scope resolution.",
                )
                if dispatch_result.get("run_id"):
                    redispatched += 1
                elif dispatch_result.get("reason") == "scope_required":
                    moved_to_review += 1
                else:
                    skipped += 1

    post_normalization = await _normalize_terminal_issue_states(
        db,
        limit=max(normalized_limit * 4, len(tasks) or 1),
    )
    normalization["tasks_moved_to_done"] += post_normalization["tasks_moved_to_done"]

    await db.commit()

    for task_id in queueable_task_ids:
        # CEO reviews must be launched after commit so the background worker
        # can observe the latest task state with a fresh session.
        queue_cio_review_for_task(task_id)

    return {
        "stale_runs_recovered": recovery["stale_runs_recovered"],
        "tasks_returned_to_queue": recovery["tasks_returned_to_queue"],
        "tasks_moved_to_review": recovery["tasks_moved_to_review"],
        "tasks_moved_to_done": normalization["tasks_moved_to_done"] + moved_scope_blocked_to_done,
        "queued_for_ceo": queued_for_ceo,
        "redispatched": redispatched,
        "moved_to_review": moved_to_review,
        "skipped": skipped,
        "scanned": len(tasks),
    }




# ---------------------------------------------------------------------------
# Static file serving for production (serves React build)
# ---------------------------------------------------------------------------

# Mount static files if build exists (production mode)
if os.path.isdir(FRONTEND_BUILD_DIR):
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_BUILD_DIR, "assets")), name="static")
    
    # Catch-all route for SPA - must be registered last
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes"""
        # Don't serve SPA for API routes
        if full_path.startswith("api/") or full_path in ["docs", "redoc", "openapi.json"]:
            raise HTTPException(status_code=404)
        
        # Check if requesting a specific file that exists
        file_path = os.path.join(FRONTEND_BUILD_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Otherwise serve index.html for SPA routing
        index_path = os.path.join(FRONTEND_BUILD_DIR, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        
        raise HTTPException(status_code=404, detail="Not found")
    
    logger.info(f"Serving frontend from {FRONTEND_BUILD_DIR}")
else:
    logger.info("Frontend build not found - API-only mode")


if __name__ == "__main__":
    import uvicorn

    # Check for required API keys
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set in .env file")
        sys.exit(1)

    logger.info("Starting Financial Analysis API Server...")
    logger.info("API will be available at: http://localhost:8000")
    logger.info("API documentation: http://localhost:8000/docs")
    logger.info("Available agents: Equity Analyst, Finance Q&A, Market Analyst, Portfolio Analyzer")

    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
