import { StockQuote } from '../api';

interface StockChartHeaderProps {
  tickers: string[];
  quotesByTicker: Record<string, StockQuote>;
  colors: Record<string, string>;
}

function formatChange(change: number, pct: number): string {
  const sign = change >= 0 ? '+' : '';
  return `${sign}$${Math.abs(change).toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

function shortenExchange(exchange: string): string {
  if (!exchange) return '';
  if (exchange.includes('NASDAQ')) return 'NASDAQ';
  if (exchange.includes('New York')) return 'NYSE';
  return exchange;
}

function StockChartHeader({ tickers, quotesByTicker, colors }: StockChartHeaderProps) {
  return (
    <div className={`flex ${tickers.length > 1 ? 'gap-8' : ''}`}>
      {tickers.map((ticker) => {
        const quote = quotesByTicker[ticker];
        if (!quote) return null;

        const isPositive = (quote.changesPercentage ?? 0) >= 0;
        const exchangeLabel = shortenExchange(quote.exchange);

        return (
          <div key={ticker} className="flex-1 min-w-0">
            {/* Ticker + exchange */}
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: colors[ticker] }}
              />
              <span
                className="text-sm font-semibold tracking-wide"
                style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}
              >
                {ticker}
              </span>
              {exchangeLabel && (
                <span
                  className="text-xs"
                  style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}
                >
                  {exchangeLabel}
                </span>
              )}
            </div>

            {/* Stock price */}
            <div
              className="text-xl font-bold mb-0.5"
              style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}
            >
              ${quote.price.toFixed(2)} <span className="text-xs font-normal" style={{ color: '#9CA3AF' }}>USD</span>
            </div>

            {/* Change */}
            <div
              className="text-xs font-medium"
              style={{
                color: isPositive ? '#10B981' : '#EF4444',
                fontFamily: 'Inter, sans-serif',
              }}
            >
              {formatChange(quote.change, quote.changesPercentage)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default StockChartHeader;
