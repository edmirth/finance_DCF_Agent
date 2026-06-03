/**
 * ReportChart — dark-themed chart component for scheduled agent run reports.
 *
 * Design: Fiscal.ai-inspired dark aesthetic.
 *   Background:   #1A1A2E
 *   Bar primary:  #E8522A  (orange/coral)
 *   Bar secondary:#A78BFA  (purple)
 *   Line:         #3B82F6  (blue)
 *   Text:         #E5E7EB
 *   Axis labels:  rgba(255,255,255,0.45)
 *   Grid lines:   rgba(255,255,255,0.07), horizontal only
 */
import { useRef } from 'react';
import {
  ComposedChart,
  Bar,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LabelList,
  ResponsiveContainer,
} from 'recharts';
import html2canvas from 'html2canvas';
import { Download } from 'lucide-react';
import type { AgentChartProps } from './AgentChart';

// ─────────────────────────────────────────────
// Format helpers
// ─────────────────────────────────────────────

const fmtVal = (v: number, format?: string): string => {
  if (format === 'currency_b') return `$${(v / 1e9).toFixed(1)}B`;
  if (format === 'currency_t') return `$${(v / 1e12).toFixed(1)}T`;
  if (format === 'currency_m') return `$${(v / 1e6).toFixed(0)}M`;
  if (format === 'percent') return `${v.toFixed(1)}%`;
  if (format === 'currency') return `$${v.toFixed(2)}`;
  return v.toLocaleString();
};

const formatLabel = (v: unknown, format?: string): string => {
  if (typeof v !== 'number') return String(v ?? '');
  return fmtVal(v, format);
};

// ─────────────────────────────────────────────
// Shared dark theme constants
// ─────────────────────────────────────────────

const BG = '#1A1A2E';
const BORDER = '1px solid rgba(255,255,255,0.08)';
const GRID_STROKE = 'rgba(255,255,255,0.07)';
const TICK_STYLE = {
  fill: 'rgba(255,255,255,0.45)',
  fontSize: 11,
  fontFamily: 'Inter',
};
const TOOLTIP_STYLE = {
  backgroundColor: '#0F0F1E',
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: '8px',
  fontFamily: 'Inter',
  fontSize: 12,
  padding: '8px 12px',
  color: '#E5E7EB',
};
const LEGEND_STYLE = {
  fontFamily: 'Inter',
  fontSize: 11,
  color: 'rgba(255,255,255,0.6)',
};

// Ordered palette — first bar uses primary, second uses secondary, etc.
const BAR_COLORS = ['#E8522A', '#A78BFA', '#10B981', '#F59E0B', '#EC4899'];
const LINE_COLOR = '#3B82F6';

// ─────────────────────────────────────────────
// Main dark chart renderer
// ─────────────────────────────────────────────

function DarkComposedChart({
  data,
  series = [],
  x_key = 'period',
  y_format,
  y_right_format,
}: Pick<AgentChartProps, 'data' | 'series' | 'x_key' | 'y_format' | 'y_right_format'>) {
  const hasRight = series.some(s => s.yAxis === 'right');
  const leftFmt = (v: number) => fmtVal(v, y_format);
  const rightFmt = (v: number) => fmtVal(v, y_right_format ?? 'percent');

  let barColorIdx = 0;

  const renderSeries = (s: (typeof series)[number]) => {
    const yId = s.yAxis === 'right' ? 'right' : 'left';
    const seriesFmt = s.yAxis === 'right' ? (y_right_format ?? 'percent') : y_format;

    if (s.type === 'bar') {
      const fill = s.color || BAR_COLORS[barColorIdx % BAR_COLORS.length];
      barColorIdx++;
      return (
        <Bar
          key={s.key}
          dataKey={s.key}
          name={s.label}
          fill={fill}
          yAxisId={yId}
          radius={[3, 3, 0, 0]}
          maxBarSize={52}
        >
          <LabelList
            dataKey={s.key}
            position="top"
            style={{
              fill: '#E5E7EB',
              fontSize: 11,
              fontFamily: "'IBM Plex Mono', monospace",
              fontWeight: 600,
            }}
            formatter={(v: unknown) => formatLabel(v, seriesFmt)}
          />
        </Bar>
      );
    }

    // line / area
    const strokeColor = s.color || LINE_COLOR;
    if (s.type === 'area') {
      return (
        <Area
          key={s.key}
          type="monotone"
          dataKey={s.key}
          name={s.label}
          stroke={strokeColor}
          fill={`${strokeColor}22`}
          yAxisId={yId}
          strokeWidth={2}
          dot={{ r: 3, fill: strokeColor, strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        >
          <LabelList
            dataKey={s.key}
            position="top"
            style={{
              fill: '#E5E7EB',
              fontSize: 11,
              fontFamily: "'IBM Plex Mono', monospace",
              fontWeight: 600,
            }}
            formatter={(v: unknown) => formatLabel(v, seriesFmt)}
          />
        </Area>
      );
    }

    return (
      <Line
        key={s.key}
        type="monotone"
        dataKey={s.key}
        name={s.label}
        stroke={strokeColor}
        yAxisId={yId}
        strokeWidth={2.5}
        dot={{ r: 3, fill: strokeColor, strokeWidth: 0 }}
        activeDot={{ r: 5 }}
      >
        <LabelList
          dataKey={s.key}
          position="top"
          style={{
            fill: '#E5E7EB',
            fontSize: 11,
            fontFamily: "'IBM Plex Mono', monospace",
            fontWeight: 600,
          }}
          formatter={(v: unknown) => formatLabel(v, seriesFmt)}
        />
      </Line>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 24, right: hasRight ? 48 : 16, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID_STROKE} />
        <XAxis
          dataKey={x_key}
          tick={TICK_STYLE}
          axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
          tickLine={false}
        />
        <YAxis
          yAxisId="left"
          tick={TICK_STYLE}
          tickFormatter={leftFmt}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        {hasRight && (
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={TICK_STYLE}
            tickFormatter={rightFmt}
            axisLine={false}
            tickLine={false}
            width={48}
          />
        )}
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelStyle={{ color: 'rgba(255,255,255,0.6)', marginBottom: 4 }}
          itemStyle={{ color: '#E5E7EB' }}
        />
        <Legend
          iconType="square"
          iconSize={8}
          wrapperStyle={LEGEND_STYLE}
        />
        {series.map(renderSeries)}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ─────────────────────────────────────────────
// ReportChart — outer wrapper with download + watermark
// ─────────────────────────────────────────────

export function ReportChart(props: AgentChartProps) {
  const { title, subtitle, y_format, y_right_format } = props;
  const chartRef = useRef<HTMLDivElement>(null);

  const handleDownload = async () => {
    if (!chartRef.current) return;
    try {
      const canvas = await html2canvas(chartRef.current, {
        scale: 2,
        backgroundColor: BG,
        useCORS: true,
      });
      const link = document.createElement('a');
      link.download = `${title.replace(/\s+/g, '_')}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('ReportChart download failed:', err);
    }
  };

  return (
    <div
      ref={chartRef}
      style={{
        background: BG,
        border: BORDER,
        borderRadius: 12,
        padding: '20px 20px 28px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div
            style={{
              color: '#E5E7EB',
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'Inter, sans-serif',
              letterSpacing: '-0.01em',
            }}
          >
            {title}
          </div>
          {subtitle && (
            <div
              style={{
                color: 'rgba(255,255,255,0.4)',
                fontSize: 11,
                fontFamily: 'Inter, sans-serif',
                marginTop: 3,
              }}
            >
              {subtitle}
            </div>
          )}
        </div>
        <button
          onClick={handleDownload}
          title="Download chart as PNG"
          style={{
            background: 'rgba(255,255,255,0.06)',
            border: 'none',
            borderRadius: 6,
            padding: '5px 7px',
            cursor: 'pointer',
            color: 'rgba(255,255,255,0.4)',
            display: 'flex',
            alignItems: 'center',
            transition: 'color 0.15s, background 0.15s',
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.color = '#E5E7EB';
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.1)';
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.4)';
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.06)';
          }}
        >
          <Download size={13} />
        </button>
      </div>

      {/* Chart body */}
      <DarkComposedChart
        data={props.data}
        series={props.series}
        x_key={props.x_key}
        y_format={y_format}
        y_right_format={y_right_format}
      />

      {/* Watermark */}
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          right: 14,
          fontSize: 10,
          fontFamily: 'Inter, sans-serif',
          color: 'rgba(255,255,255,0.2)',
          pointerEvents: 'none',
          userSelect: 'none',
        }}
      >
        Powered by Finance Agent
      </div>
    </div>
  );
}
