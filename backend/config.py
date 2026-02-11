"""
Configuration constants for the Finance DCF Agent backend API server.

This module contains all configuration values, magic numbers, and constants
used throughout the backend API server.
"""

from typing import Dict, List

# ============================================================================
# Streaming Configuration
# ============================================================================

# Size of each chunk when streaming responses via SSE
SSE_CHUNK_SIZE = 50

# Delay between streaming chunks to prevent overwhelming the client (seconds)
SSE_STREAM_DELAY_SECONDS = 0.01

# ============================================================================
# LLM Output Parsing Thresholds
# ============================================================================

# Minimum length for extracted thoughts to be considered valid
MIN_THOUGHT_LENGTH = 5

# Minimum number of steps required for a plan to be valid
MIN_PLAN_STEPS = 2

# Minimum length for plan steps to be considered valid (ignores very short steps)
MIN_STEP_LENGTH = 5

# Maximum length for parameter values to display in logs (truncate if longer)
MAX_PARAM_DISPLAY_LENGTH = 100

# ============================================================================
# Chart Data Configuration
# ============================================================================

# Maximum number of days for historical chart data
# Used for "ALL" period - effectively unlimited
MAX_HISTORICAL_DAYS = 10000

# Chart period to days mapping
CHART_PERIOD_DAYS: Dict[str, int] = {
    "1D": 1,
    "5D": 5,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "YTD": 365,  # Approximate, will be calculated based on current date
    "1Y": 365,
    "5Y": 1825,
    "ALL": MAX_HISTORICAL_DAYS,
}

# ============================================================================
# API Configuration
# ============================================================================

# Timeout for external API requests (seconds)
EXTERNAL_API_TIMEOUT_SECONDS = 10

# ============================================================================
# CORS Configuration
# ============================================================================

# Allowed origins for CORS (React dev servers)
CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
]

# ============================================================================
# Company Ticker Mapping
# ============================================================================

# Common company names to ticker symbols mapping
# Used for smart ticker extraction from natural language queries
COMPANY_TICKER_MAP: Dict[str, str] = {
    'apple': 'AAPL',
    'microsoft': 'MSFT',
    'google': 'GOOGL',
    'alphabet': 'GOOGL',
    'amazon': 'AMZN',
    'meta': 'META',
    'facebook': 'META',
    'tesla': 'TSLA',
    'nvidia': 'NVDA',
    'netflix': 'NFLX',
    'intel': 'INTC',
    'amd': 'AMD',
    'disney': 'DIS',
    'walmart': 'WMT',
    'visa': 'V',
    'mastercard': 'MA',
    'jpmorgan': 'JPM',
    'jp morgan': 'JPM',
    'bank of america': 'BAC',
    'wells fargo': 'WFC',
    'coca cola': 'KO',
    'coca-cola': 'KO',
    'pepsi': 'PEP',
    'pepsico': 'PEP',
    'procter & gamble': 'PG',
    'johnson & johnson': 'JNJ',
    'pfizer': 'PFE',
    'exxon': 'XOM',
    'chevron': 'CVX',
    'berkshire': 'BRK.B',
    'berkshire hathaway': 'BRK.B',
}

# ============================================================================
# Ticker Blacklist
# ============================================================================

# Common words that look like tickers but should be excluded
# Prevents false positives when extracting tickers from queries
TICKER_BLACKLIST = frozenset([
    # Common words
    'THE', 'AND', 'FOR', 'ARE', 'WAS', 'NOT', 'BUT', 'CAN', 'ALL', 'NEW',
    'GET', 'SET', 'PUT', 'OUT', 'TO', 'AT', 'IN', 'ON', 'OF', 'BY', 'AS',
    'IS', 'AN', 'OR', 'IF', 'IT', 'BE', 'SO', 'DO', 'UP',

    # Country codes
    'USA', 'UK', 'EU',

    # Business acronyms
    'API', 'CEO', 'CFO', 'CTO', 'IPO', 'ETF', 'SEC', 'FDA',

    # Financial metrics (could be mistaken for tickers)
    'FCF', 'EBITDA', 'EBIT', 'EPS', 'ROE', 'ROI', 'ROIC', 'CAGR',
    'DCF', 'NPV', 'IRR', 'WACC', 'PE', 'PS', 'PB', 'EV',
])

# ============================================================================
# Agent Configuration
# ============================================================================

# Default LLM model for agents
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Agent types and their available names
AGENT_TYPES = ["dcf", "analyst", "research", "market", "portfolio", "earnings"]
