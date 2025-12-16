"""
FastAPI Backend Server for Financial Analysis Agents
Provides REST API and Server-Sent Events (SSE) for streaming responses
"""
import os
import json
import asyncio
from typing import Optional, AsyncGenerator, Any, Dict, List
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import sys
from langchain.callbacks.base import AsyncCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult

# Add parent directory to path to import agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.dcf_agent import create_dcf_agent
from agents.equity_analyst_agent import create_equity_analyst_agent
from agents.research_assistant_agent import create_research_assistant
from agents.market_agent import create_market_agent
from agents.portfolio_agent import create_portfolio_agent

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Financial Analysis API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active agents (in production, use proper session management)
agents_cache = {}


class StreamingCallbackHandler(AsyncCallbackHandler):
    """Custom callback handler to stream agent thinking process"""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.tool_count = 0

    # Friendly tool descriptions (same as reasoning_callback.py)
    TOOL_DESCRIPTIONS = {
        'get_quick_data': '📊 Fetching financial metrics',
        'get_date_context': '📅 Understanding time period',
        'get_stock_info': 'ℹ️  Getting company information',
        'get_financial_metrics': '📈 Retrieving historical financials',
        'search_web': '🌐 Searching the web for current data',
        'perform_dcf_analysis': '🧮 Running DCF valuation model',
        'calculate': '🔢 Performing calculation',
        'get_recent_news': '📰 Fetching recent news',
        'compare_companies': '⚖️  Comparing companies',
        'analyze_industry': '🏭 Analyzing industry structure',
        'analyze_competitors': '🥊 Analyzing competitive landscape',
        'analyze_moat': '🏰 Evaluating competitive moat',
        'analyze_management': '👔 Assessing management quality',
        'get_market_overview': '📊 Getting market overview',
        'get_sector_rotation': '🔄 Analyzing sector rotation',
        'classify_market_regime': '🎯 Classifying market regime',
        'get_market_news': '📰 Fetching market news',
        'screen_stocks': '🔍 Screening stocks',
        'get_value_stocks': '💎 Finding value stocks',
        'get_growth_stocks': '🚀 Finding growth stocks',
        'get_dividend_stocks': '💰 Finding dividend stocks',
        'calculate_portfolio_metrics': '📊 Calculating portfolio metrics',
        'analyze_diversification': '🎯 Analyzing diversification',
        'identify_tax_loss_harvesting': '💸 Finding tax loss opportunities',
    }

    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        """Called when LLM starts"""
        if self.tool_count == 0:  # Only show for first LLM call
            await self.queue.put({"type": "thinking", "content": "🤔 Analyzing your question..."})

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM ends"""
        pass

    async def on_agent_action(self, action: AgentAction, **kwargs: Any) -> None:
        """Called when agent takes an action"""
        self.tool_count += 1
        tool_name = action.tool
        tool_input = action.tool_input

        # Get friendly description
        friendly_desc = self.TOOL_DESCRIPTIONS.get(tool_name, f'🔍 Using {tool_name}')

        # Send as a thought (user-friendly description)
        await self.queue.put({
            "type": "thought",
            "content": friendly_desc
        })

        # Send the tool info (for technical details if needed)
        # Only include simple, readable input parameters
        if isinstance(tool_input, dict):
            # Filter out complex/code-like inputs
            simple_params = {}
            for k, v in tool_input.items():
                # Only show simple parameters, skip complex ones
                if isinstance(v, (str, int, float, bool)) and len(str(v)) < 100:
                    simple_params[k] = v

            if simple_params:
                input_str = ", ".join([f"{k}={v}" for k, v in simple_params.items()])
            else:
                input_str = None
        else:
            input_str = str(tool_input)[:100] if tool_input else None

        await self.queue.put({
            "type": "tool",
            "tool": friendly_desc,  # Use friendly name
            "input": input_str
        })

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Called when tool execution ends"""
        # Just send a completion indicator, don't show truncated data
        await self.queue.put({
            "type": "tool_result",
            "content": "✓ Data retrieved"
        })

    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        """Called when agent finishes"""
        await self.queue.put({"type": "agent_finish"})


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    agent_type: str = "research"  # dcf, analyst, research, market
    model: str = "gpt-5.2"
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    agent_type: str
    timestamp: str
    session_id: str


def get_or_create_agent(agent_type: str, model: str):
    """Get cached agent or create new one"""
    cache_key = f"{agent_type}_{model}"

    if cache_key not in agents_cache:
        try:
            if agent_type == "dcf":
                agents_cache[cache_key] = create_dcf_agent(model=model)
            elif agent_type == "analyst":
                agents_cache[cache_key] = create_equity_analyst_agent(model=model)
            elif agent_type == "research":
                agents_cache[cache_key] = create_research_assistant(model=model)
            elif agent_type == "market":
                agents_cache[cache_key] = create_market_agent(model=model)
            elif agent_type == "portfolio":
                agents_cache[cache_key] = create_portfolio_agent(model=model)
            else:
                raise ValueError(f"Unknown agent type: {agent_type}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")

    return agents_cache[cache_key]


async def run_agent_with_callbacks(agent, message: str, agent_type: str, queue: asyncio.Queue):
    """Run agent in executor with callback handler"""
    loop = asyncio.get_event_loop()
    callback = StreamingCallbackHandler(queue)

    try:
        # Different agents have different methods
        if agent_type == "dcf":
            # Get the agent executor and run with callbacks
            if hasattr(agent, 'agent_executor'):
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.agent_executor.invoke(
                        {"input": message},
                        config={"callbacks": [callback]}
                    )["output"]
                )
            else:
                response = await loop.run_in_executor(None, agent.analyze, message)
        elif agent_type == "analyst":
            if hasattr(agent, 'agent_executor'):
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.agent_executor.invoke(
                        {"input": message},
                        config={"callbacks": [callback]}
                    )["output"]
                )
            else:
                response = await loop.run_in_executor(None, agent.analyze, message)
        elif agent_type == "research":
            # Research Assistant uses 'chat' method
            if hasattr(agent, 'agent_executor'):
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.agent_executor.invoke(
                        {"input": message},
                        config={"callbacks": [callback]}
                    )["output"]
                )
            else:
                response = await loop.run_in_executor(None, agent.chat, message)
        elif agent_type == "market":
            if hasattr(agent, 'agent_executor'):
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.agent_executor.invoke(
                        {"input": message},
                        config={"callbacks": [callback]}
                    )["output"]
                )
            else:
                response = await loop.run_in_executor(None, agent.analyze, message)
        elif agent_type == "portfolio":
            if hasattr(agent, 'agent_executor'):
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.agent_executor.invoke(
                        {"input": message},
                        config={"callbacks": [callback]}
                    )["output"]
                )
            else:
                response = await loop.run_in_executor(None, agent.analyze, message)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        await queue.put({"type": "response", "content": response})
        await queue.put({"type": "done"})

    except Exception as e:
        await queue.put({"type": "error", "error": str(e)})


async def stream_agent_response(message: str, agent_type: str, model: str) -> AsyncGenerator[str, None]:
    """Stream agent response using Server-Sent Events with thinking process"""
    queue = asyncio.Queue()

    try:
        agent = get_or_create_agent(agent_type, model)

        # Send start event
        yield f"data: {json.dumps({'type': 'start', 'agent': agent_type})}\n\n"

        # Start agent execution in background
        task = asyncio.create_task(run_agent_with_callbacks(agent, message, agent_type, queue))

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
                chunk_size = 50
                for i in range(0, len(response), chunk_size):
                    chunk = response[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                    await asyncio.sleep(0.01)
            else:
                # Stream thinking events (thought, tool, tool_result)
                yield f"data: {json.dumps(event)}\n\n"

        # Wait for task to complete
        await task

        # Send end event
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Financial Analysis API",
        "version": "1.0.0",
        "agents": ["dcf", "analyst", "research", "market", "portfolio"]
    }


@app.get("/agents")
async def list_agents():
    """List available agents"""
    return {
        "agents": [
            {
                "id": "dcf",
                "name": "DCF Analyst",
                "description": "Fast quantitative valuation using Discounted Cash Flow methodology",
                "example": "What is the intrinsic value of AAPL?"
            },
            {
                "id": "analyst",
                "name": "Equity Analyst",
                "description": "Comprehensive equity research reports with industry and competitive analysis",
                "example": "Analyze Tesla's competitive position and moat"
            },
            {
                "id": "research",
                "name": "Research Assistant",
                "description": "Interactive research tool for exploring companies and answering questions",
                "example": "What's Microsoft's revenue growth rate?"
            },
            {
                "id": "market",
                "name": "Market Analyst",
                "description": "Market conditions, sentiment, and sector analysis",
                "example": "What's the current market sentiment?"
            },
            {
                "id": "portfolio",
                "name": "Portfolio Analyzer",
                "description": "Portfolio analysis with metrics, diversification, and tax optimization",
                "example": "Analyze my portfolio: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, {'ticker': 'MSFT', 'shares': 50, 'cost_basis': 250.00}]"
            }
        ]
    }


@app.post("/chat/stream")
async def chat_stream(chat_message: ChatMessage):
    """Stream chat response using Server-Sent Events"""
    return StreamingResponse(
        stream_agent_response(
            chat_message.message,
            chat_message.agent_type,
            chat_message.model
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
        agent = get_or_create_agent(chat_message.agent_type, chat_message.model)

        # Get response synchronously - research agent uses 'chat' method, others use 'analyze'
        if chat_message.agent_type == "research":
            response = agent.chat(chat_message.message)
        else:
            response = agent.analyze(chat_message.message)

        return ChatResponse(
            response=response,
            agent_type=chat_message.agent_type,
            timestamp=datetime.now().isoformat(),
            session_id=chat_message.session_id or "default"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Detailed health check"""
    # Check if API keys are set
    api_keys = {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "financial_datasets": bool(os.getenv("FINANCIAL_DATASETS_API_KEY")),
        "perplexity": bool(os.getenv("PERPLEXITY_API_KEY")),
        "massive": bool(os.getenv("MASSIVE_API_KEY"))
    }

    return {
        "status": "healthy",
        "api_keys_configured": api_keys,
        "agents_cached": len(agents_cache),
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn

    # Check for required API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set in .env file")
        sys.exit(1)

    print("Starting Financial Analysis API Server...")
    print("API will be available at: http://localhost:8000")
    print("API documentation: http://localhost:8000/docs")
    print("Available agents: DCF, Equity Analyst, Research Assistant, Market Analyst, Portfolio Analyzer")

    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
