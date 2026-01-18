import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { getStockChart, StockChartData, TimePeriod } from '../api';
import StockChart from './StockChart';

interface StockChartCardProps {
  ticker: string;
}

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

      // Validate that we have required data
      if (!chartData || !chartData.quote || !chartData.historical) {
        throw new Error('Invalid chart data structure');
      }

      setData(chartData);
    } catch (err) {
      console.error('Error loading chart:', err);
      setError('Failed to load chart data');
      setData(null); // Clear any stale data
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

  // Early return for any error or missing data
  if (error || !data || !data.quote || !data.historical) {
    return null; // Silently fail - don't show chart if data unavailable
  }

  const { quote, historical } = data;

  // Defensive checks: ensure all required fields exist with fallbacks
  const price = quote?.price ?? 0;
  const change = quote?.change ?? 0;
  const changesPercentage = quote?.changesPercentage ?? 0;
  const dayLow = quote?.dayLow ?? 0;
  const dayHigh = quote?.dayHigh ?? 0;
  const volume = quote?.volume ?? 0;
  const marketCap = quote?.marketCap ?? 0;
  const open = quote?.open ?? null;

  const isPositive = changesPercentage >= 0;

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
                ${price.toFixed(2)}
              </span>
              <span className={`text-sm font-semibold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {isPositive ? '+' : ''}{change.toFixed(2)} ({isPositive ? '+' : ''}{changesPercentage.toFixed(2)}%)
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
              ${dayLow.toFixed(2)} - ${dayHigh.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Volume</p>
            <p className="text-sm font-semibold text-gray-900">
              {volume > 0 ? (volume / 1_000_000).toFixed(2) : '0.00'}M
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Market Cap</p>
            <p className="text-sm font-semibold text-gray-900">
              ${marketCap > 0 ? (marketCap / 1_000_000_000).toFixed(2) : '0.00'}B
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Open</p>
            <p className="text-sm font-semibold text-gray-900">
              ${open !== null ? open.toFixed(2) : 'N/A'}
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
