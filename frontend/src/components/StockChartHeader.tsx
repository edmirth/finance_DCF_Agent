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

function formatMarketCap(v: number): string {
  if (!v) return '—';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

function formatVolume(v: number): string {
  if (!v) return '—';
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}

function fmt(v: number | null | undefined, d = 2): string {
  return v == null ? '—' : v.toFixed(d);
}

interface StatCellProps {
  label: string;
  value: string;
}

function StatCell({ label, value }: StatCellProps) {
  return (
    <div className="min-w-0">
      <div className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>{label}</div>
      <div className="text-xs font-medium truncate" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}>{value}</div>
    </div>
  );
}

function StockChartHeader({ tickers, quotesByTicker, colors }: StockChartHeaderProps) {
  const isSingle = tickers.length === 1;

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

            {/* Stats grid — single ticker only */}
            {isSingle && (
              <>
                <div className="my-3" style={{ borderTop: '1px solid #F3F4F6' }} />
                <div className="grid grid-cols-5 gap-x-4 gap-y-2">
                  <StatCell label="Mkt Cap" value={formatMarketCap(quote.marketCap)} />
                  <StatCell label="P/E" value={fmt(quote.pe)} />
                  <StatCell label="Beta" value={fmt(quote.beta)} />
                  <StatCell label="52W Hi" value={quote.yearHigh ? `$${quote.yearHigh.toFixed(2)}` : '—'} />
                  <StatCell label="52W Lo" value={quote.yearLow ? `$${quote.yearLow.toFixed(2)}` : '—'} />

                  <StatCell label="Volume" value={formatVolume(quote.volume)} />
                  <StatCell label="Avg Vol" value={formatVolume(quote.avgVolume)} />
                  <StatCell label="Open" value={quote.open ? `$${quote.open.toFixed(2)}` : '—'} />
                  <StatCell label="Prev Close" value={quote.previousClose ? `$${quote.previousClose.toFixed(2)}` : '—'} />
                  <StatCell label="EPS" value={quote.eps != null ? `$${fmt(quote.eps)}` : '—'} />
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default StockChartHeader;
