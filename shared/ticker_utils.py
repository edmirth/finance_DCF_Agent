"""
Unified ticker extraction utility.

Single source of truth for pulling a stock ticker symbol out of a natural-language
query. Replaces three divergent copies that lived in:
  - agents/earnings_agent.py  (_extract_ticker)
  - agents/finance_qa_agent.py (_extract_ticker)
  - backend/api_server.py      (extract_ticker_from_query)
"""
from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Company name → ticker lookup (case-insensitive; keys are stored lowercase)
# Merged from backend/config.py COMPANY_TICKER_MAP and earnings_agent's
# inline COMPANY_NAME_MAP. The backend map is the superset.
# ---------------------------------------------------------------------------
COMPANY_NAME_MAP: dict[str, str] = {
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
    'palo alto': 'PANW',
    'palo alto networks': 'PANW',
}

# ---------------------------------------------------------------------------
# Well-known large-cap tickers — matched verbatim before the common-words filter
# ---------------------------------------------------------------------------
KNOWN_TICKERS: frozenset[str] = frozenset([
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'TSLA',
    'META', 'NFLX', 'AMD', 'INTC', 'CSCO', 'ADBE', 'CRM',
    'ORCL', 'IBM', 'JPM', 'BAC', 'WFC', 'GS', 'MS',
    'V', 'MA', 'PYPL', 'SQ', 'DIS', 'CMCSA', 'VZ',
    'KO', 'PEP', 'WMT', 'TGT', 'HD', 'NKE', 'SBUX',
    'MCD', 'BA', 'CAT', 'MMM', 'GE', 'F', 'GM',
    'UBER', 'LYFT', 'SNAP', 'PINS', 'SPOT', 'HOOD', 'COIN',
    'SHOP', 'SE', 'MELI', 'BABA', 'JD', 'PDD', 'TSM',
    'AVGO', 'QCOM', 'TXN', 'MU', 'LRCX', 'AMAT', 'KLAC',
    'PANW', 'CRWD', 'ZS', 'OKTA', 'DDOG', 'SNOW', 'MDB',
    'NOW', 'WDAY', 'VEEV', 'HUBS', 'ZM', 'TEAM', 'DOCN',
    'AMGN', 'GILD', 'BIIB', 'REGN', 'MRNA', 'PFE', 'JNJ',
    'UNH', 'CVS', 'CI', 'HUM', 'MCK', 'ABT', 'MDT',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD', 'OXY',
    'BRK', 'BRKB', 'C', 'AXP', 'BLK', 'SCHW',
    'PLTR', 'ABNB', 'RBLX', 'DASH', 'RIVN', 'LCID',
])

# Multi-part dotted tickers that regex alone won't catch cleanly
DOTTED_TICKERS: dict[str, str] = {
    'BRK.A': 'BRK.A', 'BRK.B': 'BRK.B',
    'BF.A': 'BF.A',  'BF.B': 'BF.B',
}

# ---------------------------------------------------------------------------
# Common words / abbreviations that must never be returned as tickers.
# Merged from all three callers. All uppercase.
# ---------------------------------------------------------------------------
TICKER_BLACKLIST: frozenset[str] = frozenset([
    # Articles / prepositions / conjunctions
    'THE', 'AND', 'FOR', 'WITH', 'FROM', 'ABOUT', 'WHAT', 'HOW', 'WHY',
    'BUT', 'NOT', 'ARE', 'WAS', 'HAS', 'HAD', 'HAVE', 'BEEN', 'WILL',
    'WHEN', 'THAT', 'THIS', 'THEN', 'THAN', 'THEY', 'THEM', 'THEIR',
    'SOME', 'EACH', 'SUCH', 'ALSO', 'INTO', 'OVER', 'ONLY',
    'MORE', 'MOST', 'VERY', 'JUST', 'BACK', 'EVEN', 'BOTH', 'WELL',
    'MUCH', 'SAME', 'WERE', 'DOES', 'SAID', 'SAYS', 'COME', 'CAME',
    'MAKE', 'MADE', 'LIKE', 'LOOK', 'GOOD', 'NEXT', 'NEAR', 'HERE',
    'GIVE', 'GAVE', 'TAKE', 'TOOK', 'KNOW', 'KNEW', 'SHOW', 'SHOWED',
    # 2-letter words
    'THE', 'AN', 'OR', 'IT', 'AT', 'IN', 'ON', 'OF', 'BY', 'AS', 'BE',
    'SO', 'DO', 'UP', 'TO', 'IF', 'MY', 'NO', 'GO', 'HE', 'ME', 'WE',
    'IS', 'US', 'RE', 'OK', 'VS',
    # Short connectors / question words
    'ALL', 'NEW', 'GET', 'SET', 'PUT', 'OUT', 'CAN', 'YOU', 'OUR',
    'OWN', 'USE', 'MAY', 'ONE', 'TWO', 'WHO', 'HIM', 'HER', 'HIS',
    'ANY', 'NOW', 'OLD', 'SEE', 'BOY', 'DID', 'LET', 'SAY', 'SHE',
    'TOO', 'YET', 'BIG', 'END', 'FAR', 'FEW', 'GOT', 'RAN', 'SAT',
    'SAW', 'SIX', 'TEN', 'TOP', 'TRY', 'WIN', 'YES', 'AGO', 'AIR',
    'ASK', 'BAD', 'BAG', 'BED', 'BOX', 'CAR', 'CUT', 'DOG', 'EAT',
    'EYE', 'FLY', 'FUN', 'GUN', 'HIT', 'HOT', 'JOB', 'KEY', 'LAW',
    'LAY', 'LEG', 'LIE', 'LOT', 'LOW', 'MAP', 'MET', 'MIX', 'NOR',
    'ODD', 'OFF', 'OIL', 'PAY', 'PER', 'POT', 'RUN', 'SIT', 'SKY',
    'SON', 'SUM', 'TAX', 'TEA', 'TIE', 'VOW', 'WAR', 'WET', 'WON',
    'ZIP', 'TELL', 'SHOW', 'FIND', 'HELP', 'INFO',
    # Question words (4-5 letters)
    'WHICH', 'WHERE', 'WHOSE', 'WHILE',
    # Finance/context words that are NOT tickers
    'SURGE', 'THESE', 'MIGHT', 'COULD', 'WOULD', 'SHOULD', 'SHALL',
    'YOUR', 'OURS', 'MINE', 'HERS', 'YEAR', 'HALF', 'FULL',
    'PLAN', 'PART', 'SIDE', 'CALL', 'SELL', 'HOLD', 'BEAT', 'MISS',
    'RISE', 'FELL', 'GREW', 'LOST', 'RATE', 'COST', 'CASH', 'DEBT',
    'GAIN', 'LOSS', 'DEAL', 'HIGH', 'LAST', 'UPON', 'AFTER',
    'BEFORE', 'BELOW', 'ABOVE', 'ALONG', 'SINCE', 'UNTIL',
    'PRICE', 'STOCK', 'SHARE', 'VALUE', 'DATA',
    'MARKET', 'SECTOR', 'QUARTER', 'FISCAL', 'ANNUAL', 'GUIDANCE',
    'REVENUE', 'MARGIN', 'GROWTH', 'INCOME',
    'LONG', 'DOWN', 'RISK', 'HIGH', 'BULL', 'BEAR', 'TERM',
    'FREE', 'FLOW', 'BETA', 'EBIT', 'PUTS', 'DROP', 'MOVE',
    'FEES', 'SAFE', 'GROW', 'FALL',
    # Country / region codes
    'USA', 'EUR', 'UK', 'EU',
    # Business acronyms
    'CEO', 'CFO', 'CTO', 'COO', 'CMO', 'IPO', 'ETF', 'SEC', 'FDA',
    'HR', 'PR', 'IR', 'IT', 'AI', 'ML', 'API',
    # Technology terms
    'GPU', 'CPU', 'LLM', 'NLP',
    # Financial metrics
    'FCF', 'EBITDA', 'EPS', 'ROE', 'ROI', 'ROIC', 'CAGR',
    'DCF', 'NPV', 'IRR', 'WACC', 'PE', 'PS', 'PB', 'EV',
    'ROA', 'ROCE', 'NOPAT',
    'USD', 'GDP', 'CPI', 'PMI',
    'NYSE', 'NASDAQ', 'AMEX', 'INC', 'LLC', 'LTD', 'CORP',
    # Reporting period abbreviations
    'FY', 'FQ', 'YTD', 'HTD', 'QTD', 'TTM', 'LTM',
    'QOQ', 'YOY', 'MOM', 'Q1', 'Q2', 'Q3', 'Q4',
    # SEC filing references
    'MD', 'MDA', 'QA', 'ITEM',
    # Follow-up words
    'YES', 'NO',
])

# ---------------------------------------------------------------------------
# Stock-context keywords: if a follow-up query lacks these, skip the greedy
# all-caps pattern to prevent false positives ("What about their AI strategy?")
# ---------------------------------------------------------------------------
STOCK_CONTEXT_KEYWORDS: frozenset[str] = frozenset([
    'stock', 'share', 'shares', 'equity', 'ticker', 'symbol',
    'earnings', 'revenue', 'profit', 'margin', 'valuation',
    'price', 'chart', 'dcf', 'market cap', 'dividend',
    'invest', 'investment', 'buy', 'sell', 'hold', 'short',
    'analyze', 'analysis', 'research', 'report',
    'quarterly', 'annual', 'fiscal', 'guidance', 'outlook',
    'trading', 'traded', 'listed', 'exchange',
])


def extract_ticker(query: str, is_followup: bool = False) -> Optional[str]:
    """Extract a stock ticker symbol from a natural-language query.

    Signals are evaluated in order of decreasing confidence. Returns the first
    match, or None if no ticker can be identified.

    Args:
        query: Raw user input string.
        is_followup: When True the greedy all-caps pattern (Signal 7) is only
            used when the query also contains stock-context keywords.  This
            prevents a follow-up like "What about their AI strategy?" from
            being mapped to a ticker during an ongoing conversation.
    """
    if not query:
        return None

    # -- Signal 0: $BRK.B / $BF.B dotted format --
    dot_match = re.search(r'\$([A-Za-z]{1,5})[.\-]([A-Za-z]{1,2})\b', query)
    if dot_match:
        return f"{dot_match.group(1).upper()}.{dot_match.group(2).upper()}"

    # -- Signal 1: $AAPL dollar-prefix --
    dollar_match = re.search(r'\$([A-Za-z]{1,5})\b', query)
    if dollar_match:
        return dollar_match.group(1).upper()

    # -- Signal 2: "Company Name (TICK)" parentheses format --
    paren_match = re.search(r'\(([A-Za-z]{1,5})\)', query)
    if paren_match:
        return paren_match.group(1).upper()

    # -- Signal 3: company full-name lookup (case-insensitive) --
    query_lower = query.lower()
    for name, ticker in COMPANY_NAME_MAP.items():
        if re.search(r'\b' + re.escape(name) + r'\b', query_lower):
            return ticker

    # -- Signal 4: dotted large-cap tickers (e.g. BRK.B without $) --
    query_upper = query.upper()
    for word in query_upper.split():
        clean = re.sub(r'[^\w.]', '', word)
        if clean in DOTTED_TICKERS:
            return DOTTED_TICKERS[clean]

    # -- Signal 5: well-known ticker mentioned verbatim --
    for word in query_upper.split():
        clean = re.sub(r'[^\w]', '', word)
        if clean in KNOWN_TICKERS:
            return clean

    # -- Signal 6: explicit context pattern "TICK stock/shares/earnings/…" --
    context_match = re.search(
        r'\b([A-Z]{1,5})\b\s*(?:stock|shares|earnings|analysis|price|chart|valuation)',
        query,
        re.IGNORECASE,
    )
    if context_match:
        candidate = context_match.group(1).upper()
        if candidate not in TICKER_BLACKLIST:
            return candidate

    # -- Signal 7: all-caps word catch-all (gated for follow-ups) --
    has_stock_context = any(kw in query_lower for kw in STOCK_CONTEXT_KEYWORDS)
    if not is_followup or has_stock_context:
        for match in re.finditer(r'\b([A-Z]{2,5})\b', query):
            candidate = match.group(1)
            if candidate not in TICKER_BLACKLIST:
                return candidate

    # -- Signal 8 (weakest): lowercase "about/for/analyze X" tail pattern --
    explicit_match = re.search(
        r'\b(?:about|for|analyze|research|check)\s+([a-z]{1,5})\s*[?.]?$',
        query_lower,
    )
    if explicit_match:
        candidate = explicit_match.group(1).upper()
        if candidate not in TICKER_BLACKLIST:
            return candidate

    return None
