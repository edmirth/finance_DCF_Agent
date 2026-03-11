import { useMemo } from 'react';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line,
  CartesianGrid, ReferenceLine,
} from 'recharts';
import { ChartDataPoint, TimePeriod } from '../api';

type ViewMode = 'orig' | 'pctChg';

interface StockChartProps {
  tickers: string[];
  historicalByTicker: Record<string, ChartDataPoint[]>;
  colors: Record<string, string>;
  period: TimePeriod;
  viewMode: ViewMode;
}

interface MergedPoint {
  date: string;
  [key: string]: number | string | undefined;
}

function StockChart({
  tickers,
  historicalByTicker,
  colors,
  period,
  viewMode,
}: StockChartProps) {
  // Merge and normalize data
  const { chartData, yDomain } = useMemo(() => {
    // Reverse each ticker's data to chronological order
    const sortedByTicker: Record<string, ChartDataPoint[]> = {};
    for (const t of tickers) {
      const raw = historicalByTicker[t] || [];
      sortedByTicker[t] = [...raw].reverse();
    }

    // Collect all dates across tickers
    const dateSet = new Set<string>();
    for (const t of tickers) {
      for (const p of sortedByTicker[t]) {
        if (p.date) dateSet.add(p.date.split(' ')[0]);
      }
    }
    const allDates = Array.from(dateSet).sort();

    // Build lookup: ticker -> date -> close price
    const lookup: Record<string, Record<string, number>> = {};
    const startPrices: Record<string, number> = {};
    for (const t of tickers) {
      lookup[t] = {};
      for (const p of sortedByTicker[t]) {
        const d = p.date.split(' ')[0];
        lookup[t][d] = p.close;
      }
      // First available price for % change baseline
      const first = sortedByTicker[t][0];
      startPrices[t] = first?.close ?? 1;
    }

    // Build merged array
    const merged: MergedPoint[] = [];
    let minVal = Infinity;
    let maxVal = -Infinity;

    for (const date of allDates) {
      const point: MergedPoint = { date };
      let hasAnyValue = false;

      for (const t of tickers) {
        const raw = lookup[t][date];
        if (raw === undefined) continue;

        let val: number;
        if (viewMode === 'pctChg') {
          val = ((raw - startPrices[t]) / startPrices[t]) * 100;
        } else {
          val = raw;
        }
        point[t] = val;
        hasAnyValue = true;
        if (val < minVal) minVal = val;
        if (val > maxVal) maxVal = val;
      }

      if (hasAnyValue) merged.push(point);
    }

    // Add padding to Y domain
    const range = maxVal - minVal || 1;
    const pad = range * 0.08;

    return {
      chartData: merged,
      yDomain: [minVal - pad, maxVal + pad] as [number, number],
    };
  }, [tickers, historicalByTicker, viewMode]);

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No chart data available
      </div>
    );
  }

  // Format functions
  const formatXAxis = (dateStr: string) => {
    const date = new Date(dateStr);
    if (period === '1M') {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    if (period === '6M' || period === 'YTD') {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '");
  };

  const formatYAxis = (value: number) => {
    if (viewMode === 'pctChg') {
      return `${value >= 0 ? '+' : ''}${value.toFixed(0)}%`;
    }
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
    if (value >= 100) return `$${Math.round(value)}`;
    if (value >= 1) return `$${value.toFixed(1)}`;
    return `$${value.toFixed(2)}`;
  };

  // Endpoint labels: get last value for each ticker, then resolve collisions
  const endpointLabels = useMemo(() => {
    const CHART_HEIGHT = 300;
    const MARGIN_TOP = 10;
    const MIN_GAP = 18; // px minimum between label centres

    const raw = tickers
      .map((t) => {
        const lastPoint = chartData[chartData.length - 1];
        const val = lastPoint?.[t] as number | undefined;
        if (val === undefined) return null;
        return { ticker: t, value: val, color: colors[t] ?? '#6B7280' };
      })
      .filter((e): e is { ticker: string; value: number; color: string } => e !== null);

    // Compute initial y positions (no index-based offset)
    const positioned = raw.map((ep) => ({
      ...ep,
      y: calculateEndpointY(ep.value, yDomain, CHART_HEIGHT, MARGIN_TOP),
    }));

    // Sort top-to-bottom and push overlapping labels apart
    positioned.sort((a, b) => a.y - b.y);
    for (let i = 1; i < positioned.length; i++) {
      if (positioned[i].y - positioned[i - 1].y < MIN_GAP) {
        positioned[i] = { ...positioned[i], y: positioned[i - 1].y + MIN_GAP };
      }
    }
    // Clamp all within the plot area
    const bottom = CHART_HEIGHT - 25;
    positioned.forEach((lp, i) => {
      positioned[i] = { ...lp, y: Math.max(MARGIN_TOP, Math.min(bottom, lp.y)) };
    });

    return positioned;
  }, [tickers, chartData, colors, yDomain]);

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const date = new Date(label);
    const dateLabel = date.toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    });

    return (
      <div
        className="rounded-lg px-3 py-2 shadow-lg border"
        style={{
          backgroundColor: '#fff',
          borderColor: '#E5E7EB',
          fontFamily: 'Inter, sans-serif',
        }}
      >
        <div className="text-xs mb-1" style={{ color: '#9CA3AF' }}>{dateLabel}</div>
        {payload.map((entry: any) => (
          <div key={entry.dataKey} className="flex items-center gap-2 text-xs">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="font-medium" style={{ color: '#1A1A1A' }}>
              {entry.dataKey}
            </span>
            <span style={{ color: '#6B7280' }}>
              {viewMode === 'pctChg'
                ? `${entry.value >= 0 ? '+' : ''}${entry.value.toFixed(2)}%`
                : `$${entry.value.toFixed(2)}`}
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 10, right: 80, bottom: 5, left: 5 }}>
          <CartesianGrid
            stroke="#F3F4F6"
            strokeWidth={1}
            vertical={false}
          />
          <XAxis
            dataKey="date"
            tickFormatter={formatXAxis}
            stroke="#D1D5DB"
            style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={60}
          />
          <YAxis
            domain={yDomain}
            stroke="#D1D5DB"
            style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatYAxis}
            width={55}
            tickCount={6}
          />
          {viewMode === 'pctChg' && (
            <ReferenceLine y={0} stroke="#D1D5DB" strokeDasharray="4 4" />
          )}
          <Tooltip content={<CustomTooltip />} />
          {tickers.map((t) => (
            <Line
              key={t}
              type="linear"
              dataKey={t}
              stroke={colors[t]}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 1.5, stroke: colors[t], fill: '#fff' }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Endpoint labels */}
      {endpointLabels.map((ep) => {
        const label = viewMode === 'pctChg'
          ? `${ep.ticker} ${ep.value >= 0 ? '+' : ''}${ep.value.toFixed(1)}%`
          : `${ep.ticker} $${ep.value.toFixed(2)}`;

        return (
          <div
            key={ep.ticker}
            className="absolute text-xs font-medium px-1.5 py-0.5 rounded"
            style={{
              right: 4,
              top: `${ep.y}px`,
              color: ep.color,
              backgroundColor: hexToRgba(ep.color, 0.08),
              fontFamily: 'Inter, sans-serif',
              fontSize: '10px',
              whiteSpace: 'nowrap',
              transform: 'translateY(-50%)',
            }}
          >
            {label}
          </div>
        );
      })}
    </div>
  );
}

/** Convert a data value to pixel Y position within the chart area.
 *
 * Recharts' rendered plot area height = chartHeight - marginTop - marginBottom - xAxisHeight.
 * The LineChart uses margin={{ top: 10, right: 80, bottom: 5, left: 5 }}.
 * XAxis with 11px font and tickLine=false consumes approximately 20px.
 * Total bottom offset = marginBottom (5) + xAxisHeight (20) = 25px.
 */
function calculateEndpointY(
  value: number,
  domain: [number, number],
  chartHeight: number,
  marginTop: number,
): number {
  const [min, max] = domain;
  const range = max - min || 1;
  const bottomOffset = 25; // marginBottom (5) + XAxis tick area (~20px)
  const plotHeight = chartHeight - marginTop - bottomOffset;
  const ratio = (value - min) / range;
  // Y is inverted: high values = low pixel
  const y = marginTop + plotHeight * (1 - ratio);
  return Math.max(marginTop, Math.min(chartHeight - bottomOffset, y));
}

function hexToRgba(hex: string | undefined, alpha: number): string {
  if (!hex || hex.length < 7 || hex[0] !== '#') {
    return `rgba(0, 0, 0, ${alpha})`;
  }
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default StockChart;
