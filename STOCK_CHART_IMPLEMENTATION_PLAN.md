# Stock Chart Feature Implementation Plan

## 🎯 Goal

Add interactive stock charts to message responses that:
1. **Auto-detect** stock tickers mentioned in responses
2. **Display** real-time price charts at the top of the message
3. **Use FMP API** for live data
4. **Allow inspection** with time period switching (1D, 1W, 1M, 3M, 1Y)
5. **Show key metrics** (current price, change %, volume)

---

## 📊 Architecture Design

### Component Hierarchy

```
Message Component (Message.tsx)
├── [If ticker detected]
│   └── StockChartCard Component (NEW)
│       ├── StockChartHeader (ticker, price, change %)
│       ├── TimeRangeSelector (1D, 1W, 1M, 3M, 1Y, ALL)
│       └── StockChart (lightweight-charts or Recharts)
└── Message Content (markdown)
```

### Data Flow

```
1. Message rendered
   ↓
2. Extract ticker(s) from content
   ↓
3. Fetch chart data from backend
   ↓
4. Backend calls FMP API
   ↓
5. Return OHLCV data to frontend
   ↓
6. Render interactive chart
```

---

## 🔍 Ticker Detection Strategy

### Method 1: Backend Metadata (Recommended)
- Modify agent state to include `ticker` field
- Backend passes ticker in message metadata
- Frontend reads `message.metadata.ticker`

### Method 2: Frontend Regex Parsing (Fallback)
```typescript
function extractTicker(content: string): string | null {
  // Pattern 1: Explicit ticker mentions
  const patterns = [
    /\b([A-Z]{1,5})\s+(?:stock|shares|earnings|analysis)/i,
    /(?:ticker|symbol):\s*([A-Z]{1,5})\b/i,
    /\$([A-Z]{1,5})\b/,  // $AAPL format
  ];

  for (const pattern of patterns) {
    const match = content.match(pattern);
    if (match && isValidTicker(match[1])) {
      return match[1];
    }
  }
  return null;
}

function isValidTicker(ticker: string): boolean {
  // Filter out common false positives
  const blacklist = ['USA', 'API', 'CEO', 'CFO', 'IPO', 'ETF'];
  return !blacklist.includes(ticker) && ticker.length >= 2 && ticker.length <= 5;
}
```

---

## 📡 FMP API Integration

### Endpoints to Use

#### 1. Real-Time Quote (Current Price)
```
GET https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey=XXX

Response:
{
  "symbol": "AAPL",
  "price": 234.52,
  "changesPercentage": 1.45,
  "change": 3.35,
  "dayLow": 231.20,
  "dayHigh": 235.80,
  "yearHigh": 250.00,
  "yearLow": 180.00,
  "marketCap": 3650000000000,
  "volume": 52000000,
  "avgVolume": 48000000,
  "open": 232.00,
  "previousClose": 231.17
}
```

#### 2. Historical Daily Data (for 1W, 1M, 3M, 1Y, ALL charts)
```
GET https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&apikey=XXX

Response:
{
  "symbol": "AAPL",
  "historical": [
    {
      "date": "2025-01-10",
      "open": 232.00,
      "high": 235.80,
      "low": 231.20,
      "close": 234.52,
      "volume": 52000000
    },
    ...
  ]
}
```

#### 3. Intraday Data (for 1D chart)
```
GET https://financialmodelingprep.com/stable/historical-chart/5min?symbol=AAPL&apikey=XXX

Response: [
  {
    "date": "2025-01-10 15:55:00",
    "open": 234.20,
    "high": 234.60,
    "low": 234.10,
    "close": 234.52,
    "volume": 125000
  },
  ...
]
```

---

## 🛠️ Implementation Steps

### Phase 1: Backend API Endpoint (30 min)

**File**: `/backend/api_server.py`

```python
@app.get("/stock-chart/{ticker}")
async def get_stock_chart(ticker: str, period: str = "1M"):
    """
    Fetch stock chart data from FMP API

    Args:
        ticker: Stock ticker symbol
        period: Time period (1D, 1W, 1M, 3M, 1Y, ALL)
    """
    fmp_key = os.getenv("FMP_API_KEY")

    # Get current quote
    quote_url = f"https://financialmodelingprep.com/stable/quote"
    quote_params = {"symbol": ticker, "apikey": fmp_key}
    quote_response = requests.get(quote_url, params=quote_params, timeout=10)
    quote_data = quote_response.json()[0] if quote_response.status_code == 200 else {}

    # Get historical data
    if period == "1D":
        # Intraday 5-minute data
        hist_url = f"https://financialmodelingprep.com/stable/historical-chart/5min"
        hist_params = {"symbol": ticker, "apikey": fmp_key}
    else:
        # Daily data
        hist_url = f"https://financialmodelingprep.com/stable/historical-price-eod/full"
        hist_params = {"symbol": ticker, "apikey": fmp_key}

    hist_response = requests.get(hist_url, params=hist_params, timeout=10)
    hist_data = hist_response.json()

    # Filter by period
    filtered_data = filter_by_period(hist_data, period)

    return {
        "ticker": ticker,
        "quote": quote_data,
        "historical": filtered_data
    }

def filter_by_period(data, period):
    """Filter historical data by time period"""
    from datetime import datetime, timedelta

    if period == "1D":
        return data  # Already filtered by API

    days_map = {
        "1W": 7,
        "1M": 30,
        "3M": 90,
        "1Y": 365,
        "ALL": 10000
    }

    days = days_map.get(period, 30)
    cutoff_date = datetime.now() - timedelta(days=days)

    historical = data.get("historical", data)
    if isinstance(historical, list):
        return [
            item for item in historical
            if datetime.strptime(item["date"].split(" ")[0], "%Y-%m-%d") >= cutoff_date
        ]
    return []
```

### Phase 2: Frontend API Client (15 min)

**File**: `/frontend/src/api.ts`

```typescript
export interface StockQuote {
  symbol: string;
  price: number;
  changesPercentage: number;
  change: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
  marketCap: number;
}

export interface ChartDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockChartData {
  ticker: string;
  quote: StockQuote;
  historical: ChartDataPoint[];
}

export async function getStockChart(
  ticker: string,
  period: '1D' | '1W' | '1M' | '3M' | '1Y' | 'ALL' = '1M'
): Promise<StockChartData> {
  const response = await axios.get(`${API_BASE}/stock-chart/${ticker}`, {
    params: { period }
  });
  return response.data;
}
```

### Phase 3: Ticker Detection Utility (20 min)

**File**: `/frontend/src/utils/tickerDetection.ts` (NEW)

```typescript
/**
 * Extract stock ticker from message content
 * Looks for common patterns like "AAPL stock", "$AAPL", "ticker: AAPL"
 */
export function extractTicker(content: string): string | null {
  if (!content) return null;

  // Pattern 1: Explicit ticker mentions with context
  const contextPattern = /\b([A-Z]{2,5})\b(?:'s)?\s+(?:stock|shares|earnings|analysis|price|chart)/i;
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

  // Pattern 4: First all-caps word in first sentence (if > 2 chars)
  const firstCapsPattern = /\b([A-Z]{2,5})\b/;
  match = content.substring(0, 200).match(firstCapsPattern);
  if (match && isValidTicker(match[1])) {
    return match[1].toUpperCase();
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
    'USA', 'API', 'CEO', 'CFO', 'CTO', 'COO', 'IPO', 'ETF',
    'SEC', 'NYSE', 'NASDAQ', 'GDP', 'CPI', 'THE', 'AND',
    'FOR', 'ARE', 'WAS', 'NOT', 'BUT', 'HAD', 'HAS', 'CAN',
    'ALL', 'NEW', 'OLD', 'TOP', 'BIG', 'KEY', 'LOW', 'HIGH'
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
```

### Phase 4: Stock Chart Component (60 min)

**File**: `/frontend/src/components/StockChartCard.tsx` (NEW)

```typescript
import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { getStockChart, StockChartData } from '../api';
import StockChart from './StockChart';

interface StockChartCardProps {
  ticker: string;
}

type TimePeriod = '1D' | '1W' | '1M' | '3M' | '1Y' | 'ALL';

function StockChartCard({ ticker }: StockChartCardProps) {
  const [period, setPeriod] = useState<TimePeriod>('1M');
  const [data, setData] = useState<StockChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadChartData();
  }, [ticker, period]);

  const loadChartData = async () => {
    try {
      setLoading(true);
      setError(null);
      const chartData = await getStockChart(ticker, period);
      setData(chartData);
    } catch (err) {
      console.error('Error loading chart:', err);
      setError('Failed to load chart data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-1/4 mb-4"></div>
          <div className="h-64 bg-gray-100 rounded"></div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return null; // Silently fail - don't show chart if data unavailable
  }

  const { quote, historical } = data;
  const isPositive = quote.changesPercentage >= 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm mb-4 overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-lg font-bold text-gray-900">{ticker}</h3>
              {isPositive ? (
                <TrendingUp className="w-5 h-5 text-green-600" />
              ) : (
                <TrendingDown className="w-5 h-5 text-red-600" />
              )}
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-2xl font-bold text-gray-900">
                ${quote.price.toFixed(2)}
              </span>
              <span className={`text-sm font-semibold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {isPositive ? '+' : ''}{quote.change.toFixed(2)} ({isPositive ? '+' : ''}{quote.changesPercentage.toFixed(2)}%)
              </span>
            </div>
          </div>

          {/* Time Period Selector */}
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
            {(['1D', '1W', '1M', '3M', '1Y', 'ALL'] as TimePeriod[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 text-xs font-semibold rounded transition-all ${
                  period === p
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t border-gray-100">
          <div>
            <p className="text-xs text-gray-500 mb-1">Day Range</p>
            <p className="text-sm font-semibold text-gray-900">
              ${quote.dayLow.toFixed(2)} - ${quote.dayHigh.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Volume</p>
            <p className="text-sm font-semibold text-gray-900">
              {(quote.volume / 1_000_000).toFixed(2)}M
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Market Cap</p>
            <p className="text-sm font-semibold text-gray-900">
              ${(quote.marketCap / 1_000_000_000).toFixed(2)}B
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Open</p>
            <p className="text-sm font-semibold text-gray-900">
              ${quote.open?.toFixed(2) || 'N/A'}
            </p>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="p-4 bg-gray-50">
        <StockChart data={historical} period={period} />
      </div>
    </div>
  );
}

export default StockChartCard;
```

### Phase 5: Chart Rendering Component (45 min)

**Option A: Using Recharts (Simpler)**

Install Recharts:
```bash
cd frontend
npm install recharts
```

**File**: `/frontend/src/components/StockChart.tsx` (NEW)

```typescript
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { ChartDataPoint } from '../api';

interface StockChartProps {
  data: ChartDataPoint[];
  period: string;
}

function StockChart({ data, period }: StockChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-500">
        No chart data available
      </div>
    );
  }

  // Format data for Recharts (reverse for chronological order)
  const chartData = [...data].reverse().map(point => ({
    date: point.date,
    price: point.close,
    high: point.high,
    low: point.low,
    volume: point.volume,
  }));

  // Determine color based on trend
  const firstPrice = chartData[0]?.price || 0;
  const lastPrice = chartData[chartData.length - 1]?.price || 0;
  const isPositive = lastPrice >= firstPrice;
  const strokeColor = isPositive ? '#10b981' : '#ef4444';
  const fillColor = isPositive ? '#10b98120' : '#ef444420';

  // Format X-axis based on period
  const formatXAxis = (dateStr: string) => {
    const date = new Date(dateStr);
    if (period === '1D') {
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } else if (period === '1W') {
      return date.toLocaleDateString('en-US', { weekday: 'short' });
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  };

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={chartData}>
        <defs>
          <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={strokeColor} stopOpacity={0.3}/>
            <stop offset="95%" stopColor={strokeColor} stopOpacity={0}/>
          </linearGradient>
        </defs>
        <XAxis
          dataKey="date"
          tickFormatter={formatXAxis}
          stroke="#9ca3af"
          style={{ fontSize: '12px' }}
          tickLine={false}
        />
        <YAxis
          domain={['auto', 'auto']}
          stroke="#9ca3af"
          style={{ fontSize: '12px' }}
          tickLine={false}
          tickFormatter={(value) => `$${value.toFixed(2)}`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1f2937',
            border: 'none',
            borderRadius: '8px',
            color: '#fff',
            fontSize: '12px'
          }}
          formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
          labelFormatter={(label) => {
            const date = new Date(label);
            return date.toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
              hour: period === '1D' ? '2-digit' : undefined,
              minute: period === '1D' ? '2-digit' : undefined
            });
          }}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke={strokeColor}
          strokeWidth={2}
          fill="url(#colorPrice)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default StockChart;
```

### Phase 6: Integrate into Message Component (15 min)

**File**: `/frontend/src/components/Message.tsx`

```typescript
import { Message, Agent } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, BarChart3, TrendingUp, Search, Globe, Briefcase, DollarSign } from 'lucide-react';
import StockChartCard from './StockChartCard';  // NEW
import { extractTicker } from '../utils/tickerDetection';  // NEW

// ... existing code ...

function MessageComponent({ message, agent }: MessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  const AgentIcon = agentIcons[agent.id];

  // Don't render anything if message has no content
  if (!message.content) return null;

  // Extract ticker from message (NEW)
  const ticker = !isUser && !isSystem ? extractTicker(message.content) : null;

  // System messages (agent switches, notifications)
  if (isSystem) {
    return (
      <div className="flex justify-center my-4 animate-in fade-in">
        <div className="px-4 py-2 bg-gray-100/80 border border-gray-200/50 rounded-full text-xs text-gray-600 font-medium">
          <ReactMarkdown className="inline">{message.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2`}>
      {!isUser && (
        <div className="bg-gray-900 w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm mt-1">
          <AgentIcon className="w-3.5 h-3.5 text-white" strokeWidth={2} />
        </div>
      )}

      <div className={`flex flex-col max-w-3xl ${isUser ? 'items-end' : 'items-start'}`}>
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="text-xs font-semibold text-gray-700">
            {isUser ? 'You' : agent.name}
          </span>
          <span className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        {/* Stock Chart Card - NEW */}
        {ticker && !isUser && (
          <div className="w-full mb-3">
            <StockChartCard ticker={ticker} />
          </div>
        )}

        <div
          className={`px-5 py-3.5 rounded-3xl ${
            isUser
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-white border border-gray-100 text-gray-800 shadow-sm'
          }`}
        >
          {isUser ? (
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="markdown-content text-[15px] leading-relaxed overflow-x-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      {isUser && (
        <div className="bg-blue-600 w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm mt-1">
          <User className="w-3.5 h-3.5 text-white" strokeWidth={2} />
        </div>
      )}
    </div>
  );
}

export default MessageComponent;
```

---

## 📦 Dependencies to Install

```bash
cd frontend
npm install recharts
```

---

## 🧪 Testing Plan

### Manual Testing
1. Ask earnings agent: "Analyze AAPL's latest earnings"
2. Verify:
   - Chart appears at top of response
   - Shows current price and change %
   - Can switch time periods (1D, 1W, 1M, etc.)
   - Chart updates when switching periods
   - Stats row shows correct data

### Test Cases
- ✅ Single ticker detection (AAPL)
- ✅ Multiple tickers (show first one)
- ✅ No ticker (no chart shown)
- ✅ Invalid ticker (graceful failure, no chart)
- ✅ All time periods work (1D, 1W, 1M, 3M, 1Y, ALL)
- ✅ Intraday chart (1D) shows time labels
- ✅ Daily charts show date labels
- ✅ Chart colors match price direction (green up, red down)

---

## 🎨 UI/UX Considerations

### Design Principles
- **Minimal**: Chart shouldn't overpower the message content
- **Fast**: Load chart data asynchronously, show skeleton while loading
- **Responsive**: Chart should work on mobile and desktop
- **Accessible**: Include alt text, keyboard navigation

### Visual Design
- **Card Style**: White background, subtle shadow, rounded corners
- **Colors**: Green for positive, red for negative (standard finance colors)
- **Typography**: Clear hierarchy (ticker → price → stats)
- **Spacing**: Adequate padding and margins

---

## 🚀 Future Enhancements (Phase 2)

1. **Candlestick Charts**: Replace area chart with candlestick for OHLC data
2. **Technical Indicators**: Add moving averages (SMA, EMA)
3. **Volume Overlay**: Show volume bars below price chart
4. **Compare Mode**: Compare multiple stocks on same chart
5. **Drawing Tools**: Allow users to draw trendlines
6. **Export**: Download chart as PNG
7. **Full Screen**: Expand chart to fullscreen modal
8. **News Markers**: Show news events on chart timeline
9. **Earnings Markers**: Highlight earnings release dates

---

## 📝 Summary

### Files to Create (5 new files)
1. `/backend/api_server.py` - Add `/stock-chart/{ticker}` endpoint
2. `/frontend/src/components/StockChartCard.tsx` - Main chart card component
3. `/frontend/src/components/StockChart.tsx` - Chart rendering component
4. `/frontend/src/utils/tickerDetection.ts` - Ticker extraction utility
5. `/frontend/src/api.ts` - Add `getStockChart()` function

### Files to Modify (1 file)
1. `/frontend/src/components/Message.tsx` - Add chart display logic

### Dependencies (1 package)
```bash
npm install recharts
```

### Estimated Time
- **Phase 1-3** (Backend + API + Utils): ~1 hour
- **Phase 4-6** (Frontend Components): ~2 hours
- **Testing & Polish**: ~30 min
- **Total**: ~3.5 hours

### Key Benefits
✅ Real-time stock data from FMP API
✅ Interactive time period selection
✅ Auto-detection of tickers in responses
✅ Clean, professional UI
✅ Fast and responsive
✅ No additional costs (uses existing FMP API)

---

**Ready to implement when approved!**
