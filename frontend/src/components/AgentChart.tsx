import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import html2canvas from 'html2canvas';
import { useRef } from 'react';
import { Download } from 'lucide-react';

interface ChartSeriesConfig {
  key: string;
  label: string;
  type: 'bar' | 'line';
  color: string;
  yAxis?: 'left' | 'right';
  colorByField?: string;
  colorIfTrue?: string;
  colorIfFalse?: string;
}

interface AgentChartProps {
  id: string;
  chart_type: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar';
  title: string;
  data: Array<Record<string, string | number | boolean>>;
  series: ChartSeriesConfig[];
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
}

const FORMAT: Record<string, (v: number) => string> = {
  currency_b: (v) => `$${v.toFixed(1)}B`,
  currency_t: (v) => `$${v.toFixed(1)}T`,
  currency:   (v) => `$${v.toFixed(2)}`,
  percent:    (v) => `${v.toFixed(1)}%`,
  number:     (v) => v.toLocaleString(),
};

const tickStyle = { fill: '#6B7280', fontSize: 12, fontFamily: 'Inter' };

export function AgentChart({
  title,
  data,
  series,
  y_format = 'number',
  y_right_format,
}: AgentChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);

  const leftFormatter = FORMAT[y_format] ?? FORMAT.number;
  const rightFormatter = y_right_format ? (FORMAT[y_right_format] ?? FORMAT.number) : FORMAT.number;

  const hasRightAxis = series.some(s => s.yAxis === 'right');

  const handleDownload = async () => {
    if (!chartRef.current) return;
    const canvas = await html2canvas(chartRef.current, { scale: 2 });
    const link = document.createElement('a');
    link.download = `${title.replace(/\s+/g, '_')}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  const renderSeries = (s: ChartSeriesConfig) => {
    const yAxisId = s.yAxis === 'right' ? 'right' : 'left';

    if (s.type === 'bar') {
      if (s.colorByField) {
        return (
          <Bar key={s.key} dataKey={s.key} name={s.label} yAxisId={yAxisId}>
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={
                  entry[s.colorByField!]
                    ? (s.colorIfTrue ?? s.color)
                    : (s.colorIfFalse ?? s.color)
                }
              />
            ))}
          </Bar>
        );
      }
      return (
        <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} yAxisId={yAxisId} />
      );
    }

    return (
      <Line
        key={s.key}
        type="monotone"
        dataKey={s.key}
        name={s.label}
        stroke={s.color}
        yAxisId={yAxisId}
        dot={false}
        strokeWidth={2}
      />
    );
  };

  return (
    <div
      ref={chartRef}
      className="bg-[#F8FAFC] border border-[#E5E7EB] rounded-lg p-4 my-4 w-full"
    >
      <div className="flex justify-between items-start mb-3">
        <span className="text-[#111827] text-base font-semibold font-inter">{title}</span>
        <button
          onClick={handleDownload}
          className="text-[#6B7280] hover:text-[#111827] transition-colors p-1 rounded"
          title="Download chart as PNG"
        >
          <Download className="w-4 h-4" />
        </button>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
          <XAxis
            dataKey="period"
            tick={tickStyle}
          />
          <YAxis
            yAxisId="left"
            tick={tickStyle}
            tickFormatter={leftFormatter}
          />
          {hasRightAxis && (
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={tickStyle}
              tickFormatter={rightFormatter}
            />
          )}
          <Tooltip
            contentStyle={{
              backgroundColor: '#FFFFFF',
              border: '1px solid #E5E7EB',
              borderRadius: '6px',
              fontFamily: 'Inter',
              fontSize: 12,
            }}
          />
          <Legend
            iconType="square"
            iconSize={10}
            wrapperStyle={{ fontFamily: 'Inter', fontSize: 12 }}
          />
          {series.map(renderSeries)}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
