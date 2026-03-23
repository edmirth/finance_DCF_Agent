import { useMemo } from 'react';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer, ComposedChart, Line, Bar,
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
  showMA: boolean;
}

interface MergedPoint {
  date: string;
  [key: string]: number | string | undefined;
}

function formatVolumeTick(v: number): string {
  if (!v) return '0';
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(v);
}

function calcMovingAverage(
  data: ChartDataPoint[],
  window: number
): Record<string, number> {
  const result: Record<string, number> = {};
  for (let i = window - 1; i < data.length; i++) {
    const avg = data.slice(i - window + 1, i + 1)
      .reduce((s, p) => s + p.close, 0) / window;
    result[data[i].date.split(' ')[0]] = avg;
  }
  return result;
}

function StockChart({
  tickers,
  historicalByTicker,
  colors,
  period,
  viewMode,
  showMA,
}: StockChartProps) {
  const isSingle = tickers.length === 1;

  // Merge and normalize data
  const { chartData, yDomain, volumeDomain } = useMemo(() => {
    // Reverse each ticker's data to chronological order
    const sortedByTicker: Record<string, ChartDataPoint[]> = {};
    for (const t of tickers) {
      const raw = historicalByTicker[t] || [];
      sortedByTicker[t] = [...raw].reverse();
    }

    // Pre-calculate moving averages per ticker
    const ma20ByTicker: Record<string, Record<string, number>> = {};
    const ma50ByTicker: Record<string, Record<string, number>> = {};
    for (const t of tickers) {
      ma20ByTicker[t] = calcMovingAverage(sortedByTicker[t], 20);
      ma50ByTicker[t] = calcMovingAverage(sortedByTicker[t], 50);
    }

    // Collect all dates across tickers
    const dateSet = new Set<string>();
    for (const t of tickers) {
      for (const p of sortedByTicker[t]) {
        if (p.date) dateSet.add(p.date.split(' ')[0]);
      }
    }
    const allDates = Array.from(dateSet).sort();

    // Build lookup: ticker -> date -> full ChartDataPoint
    const lookup: Record<string, Record<string, ChartDataPoint>> = {};
    const startPrices: Record<string, number> = {};
    for (const t of tickers) {
      lookup[t] = {};
      for (const p of sortedByTicker[t]) {
        const d = p.date.split(' ')[0];
        lookup[t][d] = p;
      }
      const first = sortedByTicker[t][0];
      startPrices[t] = first?.close ?? 1;
    }

    // Build merged array
    const merged: MergedPoint[] = [];
    let minVal = Infinity;
    let maxVal = -Infinity;
    let maxVolume = 0;

    for (const date of allDates) {
      const point: MergedPoint = { date };
      let hasAnyValue = false;

      for (const t of tickers) {
        const raw = lookup[t][date];
        if (!raw) continue;

        const close = raw.close;
        let val: number;
        if (viewMode === 'pctChg') {
          val = ((close - startPrices[t]) / startPrices[t]) * 100;
        } else {
          val = close;
        }
        point[t] = val;
        point[`${t}_open`] = raw.open;
        point[`${t}_high`] = raw.high;
        point[`${t}_low`] = raw.low;
        point[`${t}_volume`] = raw.volume;
        hasAnyValue = true;

        if (val < minVal) minVal = val;
        if (val > maxVal) maxVal = val;
        if (raw.volume > maxVolume) maxVolume = raw.volume;

        // MA values
        const ma20 = ma20ByTicker[t][date];
        if (ma20 !== undefined) {
          point[`${t}_ma20`] = viewMode === 'pctChg'
            ? ((ma20 - startPrices[t]) / startPrices[t]) * 100
            : ma20;
        }
        const ma50 = ma50ByTicker[t][date];
        if (ma50 !== undefined) {
          point[`${t}_ma50`] = viewMode === 'pctChg'
            ? ((ma50 - startPrices[t]) / startPrices[t]) * 100
            : ma50;
        }
      }

      if (hasAnyValue) merged.push(point);
    }

    const range = maxVal - minVal || 1;
    const pad = range * 0.08;

    return {
      chartData: merged,
      yDomain: [minVal - pad, maxVal + pad] as [number, number],
      volumeDomain: [0, maxVolume * 1.15] as [number, number],
      ma20ByTicker,
      ma50ByTicker,
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

  // Endpoint labels using updated CHART_HEIGHT=220
  const endpointLabels = useMemo(() => {
    const CHART_HEIGHT = 220;
    const MARGIN_TOP = 10;
    const MIN_GAP = 18;

    const raw = tickers
      .map((t) => {
        const lastPoint = chartData[chartData.length - 1];
        const val = lastPoint?.[t] as number | undefined;
        if (val === undefined) return null;
        return { ticker: t, value: val, color: colors[t] ?? '#6B7280' };
      })
      .filter((e): e is { ticker: string; value: number; color: string } => e !== null);

    const positioned = raw.map((ep) => ({
      ...ep,
      y: calculateEndpointY(ep.value, yDomain, CHART_HEIGHT, MARGIN_TOP),
    }));

    positioned.sort((a, b) => a.y - b.y);
    for (let i = 1; i < positioned.length; i++) {
      if (positioned[i].y - positioned[i - 1].y < MIN_GAP) {
        positioned[i] = { ...positioned[i], y: positioned[i - 1].y + MIN_GAP };
      }
    }
    const bottom = CHART_HEIGHT - 20;
    positioned.forEach((lp, i) => {
      positioned[i] = { ...lp, y: Math.max(MARGIN_TOP, Math.min(bottom, lp.y)) };
    });

    return positioned;
  }, [tickers, chartData, colors, yDomain]);

  // Single-ticker OHLCV tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const date = new Date(label);
    const dateLabel = date.toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    });

    if (isSingle) {
      const t = tickers[0];
      // Find the price entry (the main line, not MA)
      const priceEntry = payload.find((e: any) => e.dataKey === t);
      if (!priceEntry) return null;
      const pt = priceEntry.payload as MergedPoint;
      const open = pt[`${t}_open`] as number | undefined;
      const high = pt[`${t}_high`] as number | undefined;
      const low = pt[`${t}_low`] as number | undefined;
      const vol = pt[`${t}_volume`] as number | undefined;

      const Row = ({ label, value, color = '#6B7280', bold = false }: { label: string; value: string; color?: string; bold?: boolean }) => (
        <div className="flex justify-between gap-4 text-xs">
          <span style={{ color: '#9CA3AF' }}>{label}</span>
          <span style={{ color, fontWeight: bold ? 600 : 400 }}>{value}</span>
        </div>
      );

      const closeVal = priceEntry.value as number;
      const closeDisplay = viewMode === 'pctChg'
        ? `${closeVal >= 0 ? '+' : ''}${closeVal.toFixed(2)}%`
        : `$${closeVal.toFixed(2)}`;

      return (
        <div
          className="rounded-lg px-3 py-2 shadow-lg border"
          style={{ backgroundColor: '#fff', borderColor: '#E5E7EB', fontFamily: 'Inter, sans-serif', minWidth: 150 }}
        >
          <div className="text-xs mb-1.5" style={{ color: '#9CA3AF' }}>{dateLabel}</div>
          <Row label="Close" value={closeDisplay} color={colors[t]} bold />
          {open != null && !viewMode.startsWith('pct') && <Row label="Open" value={`$${open.toFixed(2)}`} />}
          {high != null && !viewMode.startsWith('pct') && <Row label="High" value={`$${high.toFixed(2)}`} color="#10B981" />}
          {low != null && !viewMode.startsWith('pct') && <Row label="Low" value={`$${low.toFixed(2)}`} color="#EF4444" />}
          {vol != null && <Row label="Vol" value={formatVolumeTick(vol)} />}
        </div>
      );
    }

    // Comparison tooltip
    return (
      <div
        className="rounded-lg px-3 py-2 shadow-lg border"
        style={{ backgroundColor: '#fff', borderColor: '#E5E7EB', fontFamily: 'Inter, sans-serif' }}
      >
        <div className="text-xs mb-1" style={{ color: '#9CA3AF' }}>{dateLabel}</div>
        {payload
          .filter((e: any) => !String(e.dataKey).includes('_ma'))
          .map((entry: any) => (
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

  // Volume sub-chart tooltip
  const VolumeTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const date = new Date(label);
    const dateLabel = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    return (
      <div
        className="rounded px-2 py-1 shadow border text-xs"
        style={{ backgroundColor: '#fff', borderColor: '#E5E7EB', fontFamily: 'Inter, sans-serif', color: '#6B7280' }}
      >
        {dateLabel} · Vol: {formatVolumeTick(payload[0]?.value ?? 0)}
      </div>
    );
  };

  const ticker0 = tickers[0];

  return (
    <div className="relative">
      {/* Price + MA chart */}
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 80, bottom: 0, left: 5 }}>
          <CartesianGrid stroke="#F3F4F6" strokeWidth={1} vertical={false} />
          <XAxis dataKey="date" hide />
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

          {/* Price lines */}
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

          {/* MA lines */}
          {showMA && tickers.map((t) => (
            <Line
              key={`${t}_ma20`}
              type="linear"
              dataKey={`${t}_ma20`}
              stroke={colors[t]}
              strokeDasharray="4 2"
              strokeWidth={1}
              dot={false}
              connectNulls
              legendType="none"
              activeDot={false}
            />
          ))}
          {showMA && tickers.map((t) => (
            <Line
              key={`${t}_ma50`}
              type="linear"
              dataKey={`${t}_ma50`}
              stroke={colors[t]}
              strokeDasharray="2 3"
              strokeWidth={1}
              strokeOpacity={0.6}
              dot={false}
              connectNulls
              legendType="none"
              activeDot={false}
            />
          ))}
        </ComposedChart>
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

      {/* MA legend strip — single ticker + showMA only */}
      {showMA && isSingle && (
        <div
          className="flex items-center gap-4 mt-1"
          style={{ marginLeft: 60, fontFamily: 'Inter, sans-serif' }}
        >
          <div className="flex items-center gap-1.5">
            <svg width="20" height="10">
              <line x1="0" y1="5" x2="20" y2="5" stroke={colors[ticker0]} strokeWidth="1.5" strokeDasharray="4 2" />
            </svg>
            <span className="text-xs" style={{ color: '#9CA3AF' }}>20-day</span>
          </div>
          <div className="flex items-center gap-1.5">
            <svg width="20" height="10">
              <line x1="0" y1="5" x2="20" y2="5" stroke={colors[ticker0]} strokeWidth="1.5" strokeDasharray="2 3" opacity={0.6} />
            </svg>
            <span className="text-xs" style={{ color: '#9CA3AF' }}>50-day</span>
          </div>
        </div>
      )}

      {/* Volume sub-chart — single ticker only */}
      {isSingle && (
        <ResponsiveContainer width="100%" height={80}>
          <ComposedChart data={chartData} margin={{ top: 0, right: 80, bottom: 5, left: 5 }}>
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
              yAxisId="vol"
              orientation="right"
              domain={volumeDomain}
              tickFormatter={formatVolumeTick}
              tickCount={3}
              width={50}
              stroke="#D1D5DB"
              style={{ fontSize: '10px', fontFamily: 'Inter, sans-serif' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<VolumeTooltip />} />
            <Bar
              yAxisId="vol"
              dataKey={`${ticker0}_volume`}
              fill={colors[ticker0]}
              fillOpacity={0.25}
              radius={[1, 1, 0, 0]}
              maxBarSize={8}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

/** Convert a data value to pixel Y position within the chart area. */
function calculateEndpointY(
  value: number,
  domain: [number, number],
  chartHeight: number,
  marginTop: number,
): number {
  const [min, max] = domain;
  const range = max - min || 1;
  const bottomOffset = 20;
  const plotHeight = chartHeight - marginTop - bottomOffset;
  const ratio = (value - min) / range;
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
