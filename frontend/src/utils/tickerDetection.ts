/**
 * Ticker Detection Utility
 * Extracts stock tickers from message content with smart pattern matching
 */

/**
 * Extract stock ticker from message content
 * Looks for common patterns like "AAPL stock", "$AAPL", "ticker: AAPL"
 */
export function extractTicker(content: string): string | null {
  if (!content) return null;

  // Pattern 1: Explicit ticker mentions with context
  const contextPattern = /\b([A-Z]{2,5})\b(?:'s)?\s+(?:stock|shares|earnings|analysis|price|chart|valuation|report)/i;
  let match = content.match(contextPattern);
  if (match && isValidTicker(match[1])) {
    return match[1].toUpperCase();
  }

  // Pattern 2: "ticker: AAPL" or "symbol: AAPL"
  const labelPattern = /(?:ticker|symbol):\s*([A-Z]{2,5})\b/i;
  match = content.match(labelPattern);
  if (match && isValidTicker(match[1])) {
    return match[1].toUpperCase();
  }

  // Pattern 3: $AAPL format
  const dollarPattern = /\$([A-Z]{2,5})\b/;
  match = content.match(dollarPattern);
  if (match && isValidTicker(match[1])) {
    return match[1].toUpperCase();
  }

  // Pattern 4: "Analyze TICKER" or "TICKER's"
  const analyzePattern = /(?:analyze|analyzing)\s+([A-Z]{2,5})(?:'s|\b)/i;
  match = content.match(analyzePattern);
  if (match && isValidTicker(match[1])) {
    return match[1].toUpperCase();
  }

  // Pattern 5: Only match tickers with clear stock context
  // This pattern is conservative to avoid false positives
  if (containsStockAnalysis(content)) {
    const firstSentence = content.substring(0, 200);
    const firstCapsPattern = /\b([A-Z]{3,5})\b/; // Only 3-5 chars to avoid common words
    match = firstSentence.match(firstCapsPattern);
    if (match && isValidTicker(match[1])) {
      return match[1].toUpperCase();
    }
  }

  return null;
}

/**
 * Validate ticker to avoid false positives
 */
function isValidTicker(ticker: string): boolean {
  if (!ticker || ticker.length < 2 || ticker.length > 5) {
    return false;
  }

  // Common false positives to filter out
  const blacklist = [
    // Common words
    'THE', 'AND', 'FOR', 'ARE', 'WAS', 'NOT', 'BUT', 'HAD', 'HAS', 'CAN',
    'ALL', 'NEW', 'OLD', 'TOP', 'BIG', 'KEY', 'LOW', 'HIGH', 'GET', 'SET',
    'PUT', 'OUT', 'OFF', 'ONE', 'TWO', 'OUR', 'ITS', 'MAY', 'NOW', 'WAY',
    'TO', 'AT', 'IN', 'ON', 'OF', 'BY', 'AS', 'IS', 'AN', 'OR', 'IF', 'IT',
    'BE', 'SO', 'DO', 'UP', 'NO', 'WE', 'MY', 'HE', 'GO',
    // Finance terms & metrics (NOT stock tickers)
    'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CAD', 'AUD',
    'FCF', 'EBITDA', 'EBIT', 'EPS', 'ROE', 'ROI', 'ROIC', 'CAGR',
    'P/E', 'PE', 'PS', 'PB', 'EV', 'DCF', 'NPV', 'IRR', 'WACC',
    // Tech/business acronyms
    'USA', 'API', 'CEO', 'CFO', 'CTO', 'COO', 'CIO', 'CMO', 'EVP', 'SVP',
    'IPO', 'ETF', 'SEC', 'FDA', 'FTC', 'DOJ', 'IRS',
    'NYSE', 'NASDAQ', 'AMEX',
    'GDP', 'CPI', 'PPI', 'PMI', 'PCE',
    'YOY', 'QOQ', 'MOM', 'TTM', 'LTM',
    // Common abbreviations
    'INC', 'LLC', 'LTD', 'PLC', 'CORP', 'CO',
    'VS', 'EST', 'AVG', 'MAX', 'MIN',
    'JAN', 'FEB', 'MAR', 'APR', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
    'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN',
  ];

  return !blacklist.includes(ticker.toUpperCase());
}

/**
 * Extract multiple tickers from content
 */
export function extractAllTickers(content: string): string[] {
  const tickers = new Set<string>();

  // Find all potential tickers
  const pattern = /\b([A-Z]{2,5})\b/g;
  const matches = content.matchAll(pattern);

  for (const match of matches) {
    if (isValidTicker(match[1])) {
      tickers.add(match[1].toUpperCase());
    }
  }

  return Array.from(tickers);
}

/**
 * Check if content likely contains stock analysis
 * (useful for deciding whether to attempt ticker extraction)
 */
export function containsStockAnalysis(content: string): boolean {
  const stockKeywords = [
    'stock', 'shares', 'earnings', 'revenue', 'profit', 'valuation',
    'price target', 'analyst', 'rating', 'dividend', 'market cap',
    'quarter', 'fiscal', 'guidance', 'beat', 'miss', 'EPS', 'P/E'
  ];

  const lowerContent = content.toLowerCase();
  return stockKeywords.some(keyword => lowerContent.includes(keyword));
}
