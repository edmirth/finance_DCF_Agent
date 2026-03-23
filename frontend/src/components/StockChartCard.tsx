import { useState, useEffect } from 'react';
import {
  getStockChart, getStockChartComparison,
  ComparisonChartData, TimePeriod,
} from '../api';
import StockChart from './StockChart';
import StockChartHeader from './StockChartHeader';
import StockChartPeriodSelector from './StockChartPeriodSelector';

type ViewMode = 'orig' | 'pctChg';

// Fixed color palette for comparison
const COMPARISON_COLORS = ['#2563EB', '#10B981'];

interface StockChartCardProps {
  tickers: string[];
}

function StockChartCard({ tickers }: StockChartCardProps) {
  const [period, setPeriod] = useState<TimePeriod>('1M');
  const [viewMode, setViewMode] = useState<ViewMode>('orig');
  const [showMA, setShowMA] = useState(false);
  const [data, setData] = useState<ComparisonChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isComparison = tickers.length > 1;

  useEffect(() => {
    loadData();
  }, [tickers.join(','), period]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      if (isComparison) {
        const result = await getStockChartComparison(tickers, period);
        setData(result);
      } else {
        // Single ticker — normalize to ComparisonChartData shape
        const result = await getStockChart(tickers[0], period);
        setData({
          tickers: [result.ticker],
          quotes: { [result.ticker]: result.quote },
          historical: { [result.ticker]: result.historical },
        });
      }
    } catch (err) {
      console.error('Error loading chart:', err);
      setError('Failed to load chart data');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="mb-4 py-6">
        <div className="animate-pulse">
          <div className="h-5 bg-gray-100 rounded w-1/4 mb-3"></div>
          <div className="h-4 bg-gray-50 rounded w-1/3 mb-6"></div>
          <div className="h-64 bg-gray-50 rounded"></div>
        </div>
      </div>
    );
  }

  if (error || !data) return null;

  // Determine colors
  const colorMap: Record<string, string> = {};
  if (isComparison) {
    tickers.forEach((t, i) => {
      colorMap[t] = COMPARISON_COLORS[i] || COMPARISON_COLORS[0];
    });
  } else {
    // Single stock: green if up, red if down
    const ticker = tickers[0];
    const quote = data.quotes[ticker];
    const isUp = quote && (quote.changesPercentage ?? 0) >= 0;
    colorMap[ticker] = isUp ? '#10B981' : '#EF4444';
  }

  return (
    <div className="mb-4">
      {/* Header */}
      <div className="mb-3">
        <StockChartHeader
          tickers={tickers}
          quotesByTicker={data.quotes}
          colors={colorMap}
        />
      </div>

      {/* Period selector + toggle */}
      <div className="mb-3">
        <StockChartPeriodSelector
          period={period}
          onPeriodChange={setPeriod}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          showToggle={true}
          showMA={showMA}
          onToggleMA={() => setShowMA((v) => !v)}
        />
      </div>

      {/* Chart */}
      <StockChart
        tickers={tickers}
        historicalByTicker={data.historical}
        colors={colorMap}
        period={period}
        viewMode={viewMode}
        showMA={showMA}
      />
    </div>
  );
}

export default StockChartCard;
