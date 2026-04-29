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
    "YTD": 365,  # Overridden in filter_chart_data_by_period for exact Jan 1
    "1Y": 365,
    "5Y": 1825,
    "ALL": MAX_HISTORICAL_DAYS,
    "MAX": MAX_HISTORICAL_DAYS,
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
    'uber': 'UBER',
    'lyft': 'LYFT',
    'airbnb': 'ABNB',
    'salesforce': 'CRM',
    'adobe': 'ADBE',
    'paypal': 'PYPL',
    'shopify': 'SHOP',
    'spotify': 'SPOT',
    'snap': 'SNAP',
    'twitter': 'X',
    'palantir': 'PLTR',
    'coinbase': 'COIN',
    'robinhood': 'HOOD',
    'snowflake': 'SNOW',
    'datadog': 'DDOG',
    'crowdstrike': 'CRWD',
    'servicenow': 'NOW',
    'workday': 'WDAY',
    'oracle': 'ORCL',
    'ibm': 'IBM',
    'qualcomm': 'QCOM',
    'broadcom': 'AVGO',
    'arm': 'ARM',
    'tsmc': 'TSM',
    'samsung': '005930.KS',
    'alibaba': 'BABA',
    'tencent': 'TCEHY',
    'baidu': 'BIDU',
    'goldman sachs': 'GS',
    'goldman': 'GS',
    'morgan stanley': 'MS',
    'blackrock': 'BLK',
    'costco': 'COST',
    'target': 'TGT',
    'home depot': 'HD',
    'lowes': 'LOW',
    'mcdonalds': 'MCD',
    'starbucks': 'SBUX',
    'nike': 'NKE',
    'boeing': 'BA',
    'caterpillar': 'CAT',
    'deere': 'DE',
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
    'HAS', 'HAD', 'ITS', 'OUR', 'OWN', 'USE', 'MAY', 'ONE', 'TWO',
    'HOW', 'WHY', 'HIM', 'HER', 'WHO', 'HIS', 'ANY',

    # Country codes
    'USA', 'UK', 'EU',

    # Business acronyms
    'API', 'CEO', 'CFO', 'CTO', 'IPO', 'ETF', 'SEC', 'FDA',
    'COO', 'CMO', 'HR', 'PR', 'IR', 'IT', 'AI', 'ML',

    # Technology terms (commonly appear ALL-CAPS in questions)
    'GPU', 'CPU', 'LLM', 'NLP', 'SaaS', 'PaaS', 'IaaS',

    # Financial metrics (could be mistaken for tickers)
    'FCF', 'EBITDA', 'EBIT', 'EPS', 'ROE', 'ROI', 'ROIC', 'CAGR',
    'DCF', 'NPV', 'IRR', 'WACC', 'PE', 'PS', 'PB', 'EV',
    'ROA', 'ROCE', 'EBITDA', 'NOPAT',

    # Fiscal / reporting period abbreviations
    'FY', 'FQ', 'YTD', 'HTD', 'QTD', 'TTM', 'LTM',
    'QoQ', 'YoY', 'MoM', 'Q1', 'Q2', 'Q3', 'Q4',

    # SEC filing / document references
    'MD', 'MDA', 'QA', 'ITEM',

    # Common follow-up words / phrases typed in caps
    'US', 'vs', 'VS', 'RE', 'NO', 'YES', 'OK',
])

# ============================================================================
# Stock Context Keywords
# ============================================================================

# Keywords that indicate a query is genuinely about a stock/company.
# Pattern 4 (the aggressive all-caps catch-all) only fires when at least one
# of these words is present, preventing false positives in follow-up messages.
STOCK_CONTEXT_KEYWORDS = frozenset([
    'stock', 'share', 'shares', 'equity', 'ticker', 'symbol',
    'earnings', 'revenue', 'profit', 'margin', 'valuation',
    'price', 'chart', 'dcf', 'market cap', 'dividend',
    'invest', 'investment', 'buy', 'sell', 'hold', 'short',
    'analyze', 'analysis', 'research', 'report',
    'quarterly', 'annual', 'fiscal', 'guidance', 'outlook',
    'trading', 'traded', 'listed', 'exchange',
])

# ============================================================================
# Database Configuration
# ============================================================================

# SQLite by default; set to postgresql+asyncpg://... to use Postgres
import os as _os
DATABASE_URL: str = _os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./finance_agent.db")

# Finance routines default to U.S. market hours unless explicitly overridden.
MARKET_SCHEDULE_TIMEZONE: str = _os.getenv("MARKET_SCHEDULE_TIMEZONE", "America/New_York")

# ============================================================================
# Agent Configuration
# ============================================================================

# Default LLM model for agents
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Agent types and their available names
AGENT_TYPES = ["analyst", "research", "market", "portfolio", "earnings"]
