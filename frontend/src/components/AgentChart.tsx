import {
  ComposedChart,
  Bar,
  Line,
  Area,
  ScatterChart,
  Scatter,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LabelList,
  ResponsiveContainer,
} from 'recharts';
import html2canvas from 'html2canvas';
import { useRef } from 'react';
import { Download } from 'lucide-react';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface ChartSeriesConfig {
  key: string;
  label: string;
  type: 'bar' | 'line' | 'area';
  color: string;
  yAxis?: 'left' | 'right';
  colorByField?: string;
  colorIfTrue?: string;
  colorIfFalse?: string;
}

export interface AgentChartProps {
  id: string;
  chart_type:
    | 'line' | 'multi_line' | 'area'
    | 'bar' | 'bar_line' | 'grouped_bar' | 'stacked_bar' | 'beat_miss_bar'
    | 'pie' | 'donut'
    | 'scatter' | 'waterfall' | 'heatmap' | 'stat_card'
    | 'table';
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number | boolean>>;
  series?: ChartSeriesConfig[];
  x_key?: string;
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
  // scatter axis labels
  x_label?: string;
  y_label?: string;
  // heatmap row/col labels (when data is {row, col, value} flat array)
  row_labels?: string[];
  col_labels?: string[];
  // table-only
  columns?: string[];
  rows?: string[][];
}

// ─────────────────────────────────────────────
// Shared constants
// ─────────────────────────────────────────────

const FORMAT: Record<string, (v: number) => string> = {
  currency_b: (v) => `$${v.toFixed(1)}B`,
  currency_t: (v) => `$${v.toFixed(1)}T`,
  currency:   (v) => `$${v.toFixed(2)}`,
  percent:    (v) => `${v.toFixed(1)}%`,
  number:     (v) => v.toLocaleString(),
};

const TICK_STYLE = { fill: '#6B7280', fontSize: 12, fontFamily: 'Inter' };

const TOOLTIP_STYLE = {
  backgroundColor: '#FFFFFF',
  border: '1px solid #E5E7EB',
  borderRadius: '6px',
  fontFamily: 'Inter',
  fontSize: 12,
  padding: '8px 12px',
};

const PALETTE = ['#2563EB', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316'];

// ─────────────────────────────────────────────
// Chart components
// ─────────────────────────────────────────────

/**
 * Composed: handles line, multi_line, bar_line, beat_miss_bar, single bar/line.
 */
function ChartComposed({
  data,
  series = [],
  x_key = 'period',
  y_format = 'number',
  y_right_format,
}: Pick<AgentChartProps, 'data' | 'series' | 'x_key' | 'y_format' | 'y_right_format'>) {
  const leftFmt  = FORMAT[y_format ?? 'number'] ?? FORMAT.number;
  const rightFmt = y_right_format ? (FORMAT[y_right_format] ?? FORMAT.number) : FORMAT.number;
  const hasRight = series.some(s => s.yAxis === 'right');

  const renderSeries = (s: ChartSeriesConfig) => {
    const yId = s.yAxis === 'right' ? 'right' : 'left';
    if (s.type === 'bar') {
      if (s.colorByField) {
        return (
          <Bar key={s.key} dataKey={s.key} name={s.label} yAxisId={yId} radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry[s.colorByField!] ? (s.colorIfTrue ?? s.color) : (s.colorIfFalse ?? s.color)} />
            ))}
          </Bar>
        );
      }
      return <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} yAxisId={yId} radius={[4, 4, 0, 0]} />;
    }
    return (
      <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color}
        yAxisId={yId} strokeWidth={2} dot={{ r: 3, fill: s.color, strokeWidth: 0 }} activeDot={{ r: 5 }} />
    );
  };

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
        <XAxis dataKey={x_key} tick={TICK_STYLE} />
        <YAxis yAxisId="left" tick={TICK_STYLE} tickFormatter={leftFmt} />
        {hasRight && <YAxis yAxisId="right" orientation="right" tick={TICK_STYLE} tickFormatter={rightFmt} />}
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontFamily: 'Inter', fontSize: 12 }} />
        {series.map(renderSeries)}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Area: filled area chart — cumulative returns, AUM growth, volume over time.
 */
function ChartArea({
  data, series = [], x_key = 'period', y_format = 'number',
}: Pick<AgentChartProps, 'data' | 'series' | 'x_key' | 'y_format'>) {
  const fmt = FORMAT[y_format] ?? FORMAT.number;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data}>
        <defs>
          {series.map(s => (
            <linearGradient key={s.key} id={`ag_${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={s.color} stopOpacity={0.18} />
              <stop offset="95%" stopColor={s.color} stopOpacity={0.01} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
        <XAxis dataKey={x_key} tick={TICK_STYLE} />
        <YAxis yAxisId="left" tick={TICK_STYLE} tickFormatter={fmt} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontFamily: 'Inter', fontSize: 12 }} />
        {series.map(s => (
          <Area key={s.key} type="monotone" dataKey={s.key} name={s.label}
            stroke={s.color} fill={`url(#ag_${s.key})`} yAxisId="left"
            strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Categorical bar: one bar per entry (company/country/etc.), each a distinct palette color.
 */
function ChartCategoricalBar({
  data, series = [], x_key = 'company', y_format = 'number',
}: Pick<AgentChartProps, 'data' | 'series' | 'x_key' | 'y_format'>) {
  const fmt      = FORMAT[y_format] ?? FORMAT.number;
  const valueKey = series[0]?.key ?? 'value';
  const label    = series[0]?.label ?? valueKey;
  const rotate   = data.length > 4;
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ bottom: rotate ? 52 : 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
        <XAxis dataKey={x_key} tick={{ ...TICK_STYLE, textAnchor: rotate ? 'end' : 'middle' }}
          angle={rotate ? -35 : 0} interval={0} />
        <YAxis yAxisId="left" tick={TICK_STYLE} tickFormatter={fmt} />
        <Tooltip contentStyle={TOOLTIP_STYLE}
          formatter={(v: number | string | undefined) => [
            typeof v === 'number' ? fmt(v) : (v ?? ''), label,
          ]} />
        <Bar dataKey={valueKey} name={label} yAxisId="left" radius={[4, 4, 0, 0]}>
          {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Grouped bar: multiple bar series side-by-side. Each series gets a distinct color.
 */
function ChartGroupedBar({
  data, series = [], x_key = 'period', y_format = 'number',
}: Pick<AgentChartProps, 'data' | 'series' | 'x_key' | 'y_format'>) {
  const fmt      = FORMAT[y_format] ?? FORMAT.number;
  const barSeries = series.filter(s => s.type === 'bar');
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
        <XAxis dataKey={x_key} tick={TICK_STYLE} />
        <YAxis yAxisId="left" tick={TICK_STYLE} tickFormatter={fmt} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontFamily: 'Inter', fontSize: 12 }} />
        {barSeries.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label}
            fill={s.color || PALETTE[i % PALETTE.length]} yAxisId="left" radius={[3, 3, 0, 0]} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Stacked bar: composition over time — revenue by segment per quarter, etc.
 */
function ChartStackedBar({
  data, series = [], x_key = 'period', y_format = 'number',
}: Pick<AgentChartProps, 'data' | 'series' | 'x_key' | 'y_format'>) {
  const fmt       = FORMAT[y_format] ?? FORMAT.number;
  const barSeries = series.filter(s => s.type === 'bar');
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
        <XAxis dataKey={x_key} tick={TICK_STYLE} />
        <YAxis yAxisId="left" tick={TICK_STYLE} tickFormatter={fmt} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontFamily: 'Inter', fontSize: 12 }} />
        {barSeries.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label}
            fill={s.color || PALETTE[i % PALETTE.length]}
            stackId="stack" yAxisId="left"
            radius={i === barSeries.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Pie / Donut: portfolio allocation, revenue mix, market share.
 */
function ChartPie({ data, innerRadius = 55 }: Pick<AgentChartProps, 'data'> & { innerRadius?: number }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="label"
          cx="50%" cy="50%" outerRadius={110} innerRadius={innerRadius}
          paddingAngle={3} stroke="none">
          {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontFamily: 'Inter', fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

/**
 * Waterfall (bridge chart): revenue → gross profit → net income, Q-o-Q changes.
 * Data format: [{label, value, type?}] where type is 'positive'|'negative'|'subtotal'|'total'
 */
function ChartWaterfall({
  data = [], y_format = 'number',
}: Pick<AgentChartProps, 'data' | 'y_format'>) {
  const fmt = FORMAT[y_format] ?? FORMAT.number;

  // Compute running total and stacked bar bases
  let running = 0;
  const bars = data.map((d) => {
    const value  = Number(d.value ?? 0);
    const type   = String(d.type ?? (value >= 0 ? 'positive' : 'negative'));
    const isTotal = type === 'total' || type === 'subtotal';

    if (isTotal) {
      return { label: String(d.label ?? ''), base: 0, bar: running, isTotal: true, isPositive: running >= 0, raw: running };
    }
    const base = Math.min(running, running + value);
    running += value;
    return { label: String(d.label ?? ''), base, bar: Math.abs(value), isTotal: false, isPositive: value >= 0, raw: value };
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={bars} margin={{ top: 20 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
        <XAxis dataKey="label" tick={TICK_STYLE} />
        <YAxis yAxisId="left" tick={TICK_STYLE} tickFormatter={fmt} />
        <Tooltip contentStyle={TOOLTIP_STYLE}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0]?.payload as typeof bars[number];
            return (
              <div style={TOOLTIP_STYLE}>
                <div style={{ fontWeight: 600, color: '#111827', marginBottom: 4 }}>{d.label}</div>
                <div style={{ color: '#374151' }}>{fmt(d.raw)}</div>
              </div>
            );
          }} />
        {/* Invisible base positions the bar at the correct height */}
        <Bar dataKey="base" stackId="wf" fill="transparent" yAxisId="left" legendType="none" />
        <Bar dataKey="bar" stackId="wf" yAxisId="left" radius={[3, 3, 0, 0]}>
          {bars.map((b, i) => (
            <Cell key={i} fill={b.isTotal ? '#2563EB' : b.isPositive ? '#10B981' : '#EF4444'} />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Scatter: risk vs return, P/E vs growth, any two-axis comparison across a universe.
 * Data format: [{x, y, label?}]
 */
function ChartScatter({
  data = [], x_label = 'X', y_label = 'Y', y_format = 'number',
}: Pick<AgentChartProps, 'data' | 'x_label' | 'y_label' | 'y_format'>) {
  const fmt = FORMAT[y_format] ?? FORMAT.number;
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 10, right: 24, bottom: 32, left: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
        <XAxis type="number" dataKey="x" name={x_label} tick={TICK_STYLE}
          label={{ value: x_label, position: 'insideBottom', offset: -16, style: { fill: '#6B7280', fontSize: 11 } }} />
        <YAxis type="number" dataKey="y" name={y_label} tick={TICK_STYLE} tickFormatter={fmt}
          label={{ value: y_label, angle: -90, position: 'insideLeft', offset: 12, style: { fill: '#6B7280', fontSize: 11 } }} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: '3 3' }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0]?.payload as Record<string, unknown>;
            return (
              <div style={TOOLTIP_STYLE}>
                {(typeof d.label === 'string' || typeof d.label === 'number') ? (
                  <div style={{ fontWeight: 600, color: '#111827', marginBottom: 4 }}>{String(d.label)}</div>
                ) : null}
                <div style={{ color: '#6B7280' }}>{x_label}: <span style={{ color: '#111827' }}>{String(d.x)}</span></div>
                <div style={{ color: '#6B7280' }}>{y_label}: <span style={{ color: '#111827' }}>{fmt(Number(d.y))}</span></div>
              </div>
            );
          }} />
        <Scatter data={data} fill="#2563EB" fillOpacity={0.75}>
          {data.length <= 20 && <LabelList dataKey="label" position="top" style={{ ...TICK_STYLE, fontSize: 10 }} />}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/**
 * Heatmap: correlation matrices, sector grids, monthly return tables.
 * Data format: [{row, col, value}] (flat) — row_labels/col_labels control ordering.
 */
function ChartHeatmap({
  data = [], row_labels, col_labels,
}: Pick<AgentChartProps, 'data' | 'row_labels' | 'col_labels'>) {
  // Build lookup map and discover unique rows/cols from data
  const valMap: Record<string, Record<string, number>> = {};
  const rowSet = new Set<string>();
  const colSet = new Set<string>();

  for (const d of data) {
    const r = String(d.row ?? d.label ?? '');
    const c = String(d.col ?? d.period ?? '');
    if (!valMap[r]) valMap[r] = {};
    valMap[r][c] = Number(d.value ?? 0);
    rowSet.add(r);
    colSet.add(c);
  }

  const rows = row_labels ?? Array.from(rowSet);
  const cols = col_labels ?? Array.from(colSet);
  const allVals = data.map(d => Number(d.value ?? 0));
  const absMax  = Math.max(...allVals.map(Math.abs), 0.001);

  const cellBg = (v: number): string => {
    const norm = Math.max(-1, Math.min(1, v / absMax));
    if (norm > 0) return `rgba(16,185,129,${0.12 + norm * 0.72})`;
    return `rgba(239,68,68,${0.12 + (-norm) * 0.72})`;
  };
  const cellFg = (v: number): string =>
    Math.abs(v) / absMax > 0.55 ? '#FFFFFF' : '#111827';

  const fmtCell = (v: number): string => {
    if (Math.abs(v) <= 1.5) return (v * 100).toFixed(0) + '%'; // correlations
    if (Math.abs(v) >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
    return v.toFixed(1);
  };

  const cellW = cols.length > 8 ? 40 : cols.length > 5 ? 52 : 64;

  return (
    <div style={{ overflowX: 'auto', paddingTop: 4 }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 3, fontFamily: 'Inter', fontSize: 11 }}>
        <thead>
          <tr>
            <th style={{ width: 80, minWidth: 64 }} />
            {cols.map(c => (
              <th key={c} style={{ textAlign: 'center', color: '#6B7280', fontWeight: 500,
                fontSize: 10, whiteSpace: 'nowrap', padding: '2px 4px' }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r}>
              <td style={{ textAlign: 'right', color: '#374151', fontWeight: 500,
                whiteSpace: 'nowrap', paddingRight: 8, fontSize: 11 }}>{r}</td>
              {cols.map(c => {
                const v = valMap[r]?.[c] ?? 0;
                return (
                  <td key={c} style={{
                    width: cellW, height: cellW, textAlign: 'center',
                    backgroundColor: cellBg(v), borderRadius: 4,
                    color: cellFg(v), fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: 10, fontWeight: 500, cursor: 'default',
                  }} title={`${r} / ${c}: ${v}`}>
                    {fmtCell(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Stat card: single KPI display — price, market cap, P/E, growth rate.
 * Data format: [{label, value, change?, positive?}]
 */
function ChartStatCard({ data = [] }: Pick<AgentChartProps, 'data'>) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))', gap: 10 }}>
      {data.map((d, i) => {
        const label    = String(d.label ?? '');
        const value    = String(d.value ?? '');
        const change   = String(d.change ?? '');
        const positive = Boolean(d.positive);
        return (
          <div key={i} style={{ background: '#FFFFFF', border: '1px solid #E5E7EB',
            borderRadius: 8, padding: '12px 16px' }}>
            <div style={{ color: '#9CA3AF', fontSize: 10, fontFamily: 'Inter',
              fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              {label}
            </div>
            <div style={{ color: '#111827', fontSize: 22, fontFamily: "'IBM Plex Mono', monospace",
              fontWeight: 600, lineHeight: 1.2, wordBreak: 'break-all' }}>
              {value}
            </div>
            {d.change && (
              <div style={{ color: positive ? '#10B981' : '#EF4444',
                fontSize: 12, fontFamily: 'Inter', fontWeight: 500, marginTop: 5 }}>
                {change}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Table: financial statements, key metrics, structured data.
 */
function ChartTable({ columns = [], rows = [] }: Pick<AgentChartProps, 'columns' | 'rows'>) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th key={i} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '8px 12px',
                color: '#6B7280', fontWeight: 600, fontSize: 11, textTransform: 'uppercase',
                letterSpacing: '0.05em', borderBottom: '1px solid #E5E7EB',
                fontFamily: 'Inter, sans-serif', whiteSpace: 'nowrap' }}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ background: ri % 2 === 0 ? 'rgba(0,0,0,0.02)' : 'transparent' }}>
              {row.map((cell, ci) => {
                const str = cell.toString();
                const isPos = ci > 0 && str.startsWith('+');
                const isNeg = ci > 0 && str.startsWith('-');
                return (
                  <td key={ci} style={{ textAlign: ci === 0 ? 'left' : 'right', padding: '9px 12px',
                    color: isNeg ? '#EF4444' : isPos ? '#10B981' : ci === 0 ? '#111827' : '#374151',
                    fontFamily: ci > 0 ? "'IBM Plex Mono', monospace" : 'Inter, sans-serif',
                    fontWeight: ci === 0 ? 500 : 400, whiteSpace: 'nowrap' }}>
                    {cell}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────
// Smart renderer registry
// ─────────────────────────────────────────────

interface RendererEntry {
  render: (props: AgentChartProps) => React.ReactElement | null;
  /**
   * Returns 0–1 confidence that this renderer is the right choice.
   * Shape-driven detectors score 0.9–1.0 and override backend hints.
   * Generic fallbacks score ≤ 0.4; backend hint wins at 0.5 baseline.
   */
  detect: (props: AgentChartProps) => number;
}

const RENDERER_REGISTRY: Record<string, RendererEntry> = {
  // ── Shape-driven: detected from data structure ───────────────────────────
  pie: {
    detect: ({ data = [], chart_type }) => {
      if (!data.length) return 0;
      const d = data[0];
      if (!('label' in d) || !('value' in d)) return 0;
      // Exclude other types that also use {label, value}
      if ('x' in d || 'row' in d) return 0;      // scatter, heatmap
      if ('type' in d) return 0;                  // waterfall rows have a 'type' field
      if (typeof d.value === 'string') return 0;  // stat_card uses string values like "$391B"
      if (chart_type === 'donut') return 0;       // donut handles itself
      return 1.0;
    },
    render: (p) => <ChartPie data={p.data} innerRadius={55} />,
  },
  donut: {
    detect: ({ chart_type }) => chart_type === 'donut' ? 1.0 : 0,
    render: (p) => <ChartPie data={p.data} innerRadius={82} />,
  },
  table: {
    detect: ({ columns }) => columns?.length ? 1.0 : 0,
    render: (p) => <ChartTable columns={p.columns} rows={p.rows} />,
  },
  stat_card: {
    detect: ({ chart_type, data = [] }) => {
      if (chart_type === 'stat_card') return 0.95;
      // Auto-detect: data has string values (formatted numbers) and a label field
      return data.length > 0 && typeof data[0].value === 'string' && 'label' in data[0] ? 0.75 : 0;
    },
    render: (p) => <ChartStatCard data={p.data} />,
  },
  heatmap: {
    detect: ({ chart_type, data = [] }) => {
      if (chart_type === 'heatmap') return 0.95;
      return data.length > 0 && 'row' in data[0] && 'col' in data[0] ? 0.9 : 0;
    },
    render: (p) => <ChartHeatmap data={p.data} row_labels={p.row_labels} col_labels={p.col_labels} />,
  },
  scatter: {
    detect: ({ chart_type, data = [] }) => {
      if (chart_type === 'scatter') return 0.95;
      return data.length > 0 && 'x' in data[0] && 'y' in data[0] ? 0.9 : 0;
    },
    render: (p) => <ChartScatter data={p.data} x_label={p.x_label} y_label={p.y_label} y_format={p.y_format} />,
  },
  waterfall: {
    detect: ({ chart_type, data = [] }) => {
      if (chart_type === 'waterfall') return 0.95;
      return data.length > 0 && 'type' in data[0] && 'label' in data[0] ? 0.8 : 0;
    },
    render: (p) => <ChartWaterfall data={p.data} y_format={p.y_format} />,
  },

  // ── Series-driven: upgraded based on series composition ──────────────────
  categorical_bar: {
    detect: ({ x_key, series = [], data = [] }) => {
      const isCat    = x_key === 'company' || x_key === 'name' || x_key === 'category';
      const singleM  = series.filter(s => s.type === 'bar').length <= 1;
      return isCat && singleM && data.length > 0 ? 0.95 : 0;
    },
    render: (p) => <ChartCategoricalBar {...p} />,
  },
  stacked_bar: {
    detect: ({ chart_type }) => chart_type === 'stacked_bar' ? 0.95 : 0,
    render: (p) => <ChartStackedBar {...p} />,
  },
  grouped_bar: {
    detect: ({ series = [] }) => series.filter(s => s.type === 'bar').length >= 2 ? 0.9 : 0,
    render: (p) => <ChartGroupedBar {...p} />,
  },
  beat_miss_bar: {
    detect: ({ series = [] }) => series.some(s => s.colorByField) ? 0.95 : 0,
    render: (p) => <ChartComposed {...p} />,
  },
  area: {
    detect: ({ chart_type, series = [] }) => {
      if (chart_type === 'area') return 0.95;
      return series.some(s => s.type === 'area') ? 0.9 : 0;
    },
    render: (p) => <ChartArea {...p} />,
  },
  bar_line: {
    detect: ({ series = [] }) => {
      const bars  = series.filter(s => s.type === 'bar').length;
      const lines = series.filter(s => s.type === 'line').length;
      return bars >= 1 && lines >= 1 ? 0.9 : 0;
    },
    render: (p) => <ChartComposed {...p} />,
  },
  multi_line: {
    detect: ({ series = [] }) => series.filter(s => s.type === 'line').length >= 2 ? 0.85 : 0,
    render: (p) => <ChartComposed {...p} />,
  },

  // ── Generic fallbacks (backend hint wins at 0.5 baseline) ────────────────
  bar: {
    detect: () => 0.4,
    render: (p) => <ChartComposed {...p} />,
  },
  line: {
    detect: ({ series = [] }) => series.length === 1 && series[0]?.type === 'line' ? 0.6 : 0.35,
    render: (p) => <ChartComposed {...p} />,
  },
};

/**
 * Resolves the best renderer for the given chart props.
 *
 * The backend chart_type hint gets a 0.5 baseline — it wins all ties.
 * Shape-driven detectors (0.9–1.0) override it when data structure demands a different renderer.
 * This means the system works correctly even when the backend sends an imprecise hint.
 */
function resolveRenderer(props: AgentChartProps): RendererEntry['render'] {
  const { chart_type } = props;
  const hintScore = Math.max(RENDERER_REGISTRY[chart_type]?.detect(props) ?? 0, 0.5);
  let bestScore = hintScore;
  let bestKey: string = chart_type;

  for (const [key, entry] of Object.entries(RENDERER_REGISTRY)) {
    if (key === bestKey) continue;
    const score = entry.detect(props);
    if (score > bestScore) {
      bestScore = score;
      bestKey   = key;
    }
  }

  return (RENDERER_REGISTRY[bestKey] ?? RENDERER_REGISTRY.bar).render;
}

// ─────────────────────────────────────────────
// AgentChart — title + download + smart dispatch
// ─────────────────────────────────────────────

export function AgentChart(props: AgentChartProps) {
  const { title, subtitle } = props;
  const chartRef = useRef<HTMLDivElement>(null);

  const handleDownload = async () => {
    if (!chartRef.current) return;
    try {
      const canvas = await html2canvas(chartRef.current, { scale: 2 });
      const link = document.createElement('a');
      link.download = `${title.replace(/\s+/g, '_')}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('Chart download failed:', err);
    }
  };

  const renderer = resolveRenderer(props);

  return (
    <div ref={chartRef} className="bg-[#F8FAFC] border border-[#E5E7EB] rounded-lg p-4 my-4 w-full">
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-[#111827] text-base font-semibold font-inter">{title}</div>
          {subtitle && <div className="text-[#9CA3AF] text-xs mt-0.5 font-inter">{subtitle}</div>}
        </div>
        <button onClick={handleDownload}
          className="text-[#6B7280] hover:text-[#111827] transition-colors p-1 rounded"
          title="Download chart as PNG">
          <Download className="w-4 h-4" />
        </button>
      </div>
      {renderer(props)}
    </div>
  );
}
