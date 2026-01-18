"""
FastAPI Backend Server for Financial Analysis Agents
Provides REST API and Server-Sent Events (SSE) for streaming responses
"""
import os
import json
import asyncio
import logging
from typing import Optional, AsyncGenerator, Any, Dict, List
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import sys
import requests
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path to import agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import (
    SSE_CHUNK_SIZE, SSE_STREAM_DELAY_SECONDS,
    CHART_PERIOD_DAYS, CORS_ORIGINS, COMPANY_TICKER_MAP, TICKER_BLACKLIST
)
from backend.callbacks.streaming import StreamingCallbackHandler
from agents.dcf_agent import create_dcf_agent
from agents.equity_analyst_agent import create_equity_analyst_agent
from agents.research_assistant_agent import create_research_assistant
from agents.market_agent import create_market_agent
from agents.portfolio_agent import create_portfolio_agent
from agents.earnings_agent import create_earnings_agent

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Initialize FastAPI app
app = FastAPI(title="Financial Analysis API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active agents (in production, use proper session management)
agents_cache = {}

# Map agent types to their fallback methods (when agent_executor is not available)
AGENT_FALLBACK_METHODS = {
    "dcf": "analyze",
    "analyst": "analyze",
    "research": "chat",  # Research uses 'chat' instead of 'analyze'
    "market": "analyze",
    "portfolio": "analyze",
    "earnings": "analyze",
}


def extract_ticker_from_query(query: str) -> Optional[str]:
    """
    Extract stock ticker from user query using smart pattern matching.
    Supports: "AAPL", "$AAPL", "Apple", "Tesla stock", etc.
    """
    if not query:
        return None

    query_lower = query.lower()

    # Pattern 1: $TICKER format
    dollar_pattern = r'\$([A-Z]{2,5})\b'
    match = re.search(dollar_pattern, query)
    if match:
        return match.group(1).upper()

    # Pattern 2: Explicit ticker with context
    ticker_pattern = r'\b([A-Z]{2,5})\b\s*(?:stock|shares|earnings|analysis|price|chart|valuation)'
    match = re.search(ticker_pattern, query, re.IGNORECASE)
    if match:
        ticker = match.group(1).upper()
        if ticker not in TICKER_BLACKLIST:
            return ticker

    # Pattern 3: Company name mapping
    for company, ticker in COMPANY_TICKER_MAP.items():
        if re.search(r'\b' + company + r'\b', query_lower):
            return ticker

    # Pattern 4: All-caps ticker (2-5 chars) standalone
    caps_pattern = r'\b([A-Z]{2,5})\b'
    match = re.search(caps_pattern, query)
    if match:
        ticker = match.group(1)
        if ticker not in TICKER_BLACKLIST:
            return ticker

    return None


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
            elif agent_type == "earnings":
                agents_cache[cache_key] = create_earnings_agent(model=model)
            else:
                raise ValueError(f"Unknown agent type: {agent_type}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")

    return agents_cache[cache_key]


async def run_agent_with_callbacks(agent, message: str, agent_type: str, queue: asyncio.Queue):
    """
    Run agent in executor with callback handler.

    Executes the agent synchronously in a thread pool executor while streaming
    events (thoughts, tool calls, results) to an async queue for SSE delivery.

    Args:
        agent: LangChain agent instance (with agent_executor or fallback method)
        message: User's input message to process
        agent_type: One of 'dcf', 'analyst', 'research', 'market', 'portfolio', 'earnings'
        queue: Async queue for streaming events to SSE response
    """
    loop = asyncio.get_event_loop()
    callback = StreamingCallbackHandler(queue)

    try:
        # Validate agent type
        if agent_type not in AGENT_FALLBACK_METHODS:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # Try to use agent_executor first (preferred method with callbacks)
        if hasattr(agent, 'agent_executor'):
            response = await loop.run_in_executor(
                None,
                lambda: agent.agent_executor.invoke(
                    {"input": message},
                    config={"callbacks": [callback]}
                )["output"]
            )
        else:
            # Fallback to agent's direct method (analyze or chat)
            fallback_method_name = AGENT_FALLBACK_METHODS[agent_type]
            fallback_method = getattr(agent, fallback_method_name)
            response = await loop.run_in_executor(None, fallback_method, message)

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

        # Extract ticker from user query and send as metadata
        ticker = extract_ticker_from_query(message)
        if ticker:
            print(f"[INFO] Detected ticker from query: {ticker}")
            yield f"data: {json.dumps({'type': 'ticker_metadata', 'ticker': ticker})}\n\n"

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
                for i in range(0, len(response), SSE_CHUNK_SIZE):
                    chunk = response[i:i + SSE_CHUNK_SIZE]
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                    await asyncio.sleep(SSE_STREAM_DELAY_SECONDS)
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
            },
            {
                "id": "earnings",
                "name": "Earnings Analyst",
                "description": "Fast earnings-focused equity research (15 min) with quarterly trends and estimates",
                "example": "Analyze NVDA's latest earnings and forward outlook"
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


@app.get("/stock-chart/{ticker}")
async def get_stock_chart(ticker: str, period: str = "1M"):
    """
    Fetch stock chart data from FMP API

    Args:
        ticker: Stock ticker symbol (e.g., AAPL, MSFT)
        period: Time period (1D, 1W, 1M, 3M, 1Y, ALL)

    Returns:
        JSON with quote data and historical price data
    """
    try:
        fmp_key = os.getenv("FMP_API_KEY")
        if not fmp_key:
            raise HTTPException(status_code=500, detail="FMP_API_KEY not configured")

        ticker = ticker.upper()

        # Get current quote
        quote_url = "https://financialmodelingprep.com/stable/quote"
        quote_params = {"symbol": ticker, "apikey": fmp_key}

        try:
            quote_response = requests.get(quote_url, params=quote_params, timeout=10)
            quote_response.raise_for_status()
            quote_data_list = quote_response.json()
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to fetch quote for {ticker}: {e}")
            raise HTTPException(status_code=404, detail=f"Could not fetch data for ticker {ticker}")

        if not quote_data_list or len(quote_data_list) == 0:
            print(f"[ERROR] Empty quote response for {ticker}")
            raise HTTPException(status_code=404, detail=f"No quote data found for {ticker}")

        quote_data = quote_data_list[0]

        # Log the quote data structure for debugging
        print(f"[DEBUG] FMP Quote Response for {ticker}: {quote_data}")

        # Ensure required fields exist with fallbacks
        quote_data = {
            "symbol": quote_data.get("symbol", ticker),
            "price": quote_data.get("price", 0),
            "changesPercentage": quote_data.get("changesPercentage", 0),
            "change": quote_data.get("change", 0),
            "dayHigh": quote_data.get("dayHigh", 0),
            "dayLow": quote_data.get("dayLow", 0),
            "volume": quote_data.get("volume", 0),
            "marketCap": quote_data.get("marketCap", 0),
            "open": quote_data.get("open"),
            "previousClose": quote_data.get("previousClose", 0),
            "yearHigh": quote_data.get("yearHigh", 0),
            "yearLow": quote_data.get("yearLow", 0),
            "avgVolume": quote_data.get("avgVolume", 0)
        }

        # Get historical data based on period
        if period == "1D":
            # Intraday 5-minute data for 1-day chart
            hist_url = "https://financialmodelingprep.com/stable/historical-chart/5min"
            hist_params = {"symbol": ticker, "apikey": fmp_key}
        else:
            # Daily data for other periods
            hist_url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
            hist_params = {"symbol": ticker, "apikey": fmp_key}

        try:
            hist_response = requests.get(hist_url, params=hist_params, timeout=10)
            hist_response.raise_for_status()
            hist_data = hist_response.json()
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to fetch historical data for {ticker}: {e}")
            # Return quote data even if historical fails
            hist_data = []

        # Log sample of historical data for debugging
        if isinstance(hist_data, list) and len(hist_data) > 0:
            print(f"[DEBUG] FMP Historical Response sample (first item): {hist_data[0]}")
        elif isinstance(hist_data, dict) and "historical" in hist_data:
            print(f"[DEBUG] FMP Historical Response sample (first item): {hist_data['historical'][0] if hist_data['historical'] else 'empty'}")

        # Filter historical data by period
        filtered_data = filter_chart_data_by_period(hist_data, period)

        return {
            "ticker": ticker,
            "quote": quote_data,
            "historical": filtered_data
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"FMP API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def filter_chart_data_by_period(data: Any, period: str) -> List[Dict]:
    """Filter historical chart data by time period"""
    if period == "1D":
        # Intraday data is already filtered by API (last trading day)
        return data if isinstance(data, list) else []

    # Use configured period to days mapping
    days = CHART_PERIOD_DAYS.get(period, CHART_PERIOD_DAYS["1M"])
    cutoff_date = datetime.now() - timedelta(days=days)

    # Handle both list and dict responses
    historical = data.get("historical", data) if isinstance(data, dict) else data

    if not isinstance(historical, list):
        return []

    # Filter by date
    filtered = []
    for item in historical:
        try:
            # Parse date (format: "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS")
            item_date_str = item.get("date", "").split(" ")[0]
            item_date = datetime.strptime(item_date_str, "%Y-%m-%d")

            if item_date >= cutoff_date:
                filtered.append(item)
        except (ValueError, AttributeError):
            continue

    return filtered


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
