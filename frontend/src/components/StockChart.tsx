import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { ChartDataPoint, TimePeriod } from '../api';

interface StockChartProps {
  data: ChartDataPoint[];
  period: TimePeriod;
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
  // Add defensive checks for missing fields
  const chartData = [...data].reverse().map(point => ({
    date: point?.date || '',
    price: point?.close ?? 0,
    high: point?.high ?? 0,
    low: point?.low ?? 0,
    volume: point?.volume ?? 0,
  })).filter(point => point.date && point.price > 0); // Filter out invalid data points

  // Determine color based on trend
  const firstPrice = chartData[0]?.price || 0;
  const lastPrice = chartData[chartData.length - 1]?.price || 0;
  const isPositive = lastPrice >= firstPrice;
  const strokeColor = isPositive ? '#10b981' : '#ef4444';

  // Format X-axis based on period
  const formatXAxis = (dateStr: string) => {
    const date = new Date(dateStr);
    if (period === '1D') {
      // Intraday: Show time
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } else if (period === '1W') {
      // 1 Week: Show day of week
      return date.toLocaleDateString('en-US', { weekday: 'short' });
    } else if (period === '1M') {
      // 1 Month: Show day only (e.g., "15")
      return date.getDate().toString();
    } else {
      // 3M, 1Y, ALL: Show month and year (e.g., "Jan '24")
      return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '");
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
          style={{ fontSize: '11px' }}
          tickLine={false}
          interval="preserveStartEnd"
          minTickGap={50}
        />
        <YAxis
          domain={['auto', 'auto']}
          stroke="#9ca3af"
          style={{ fontSize: '11px' }}
          tickLine={false}
          tickFormatter={(value) => `$${Math.round(value)}`}
          width={65}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1f2937',
            border: 'none',
            borderRadius: '8px',
            color: '#fff',
            fontSize: '12px'
          }}
          formatter={(value: number | undefined) => [`$${(value ?? 0).toFixed(2)}`, 'Price']}
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
