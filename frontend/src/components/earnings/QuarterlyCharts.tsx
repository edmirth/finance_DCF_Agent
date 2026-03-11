import { memo, useMemo } from 'react';
import { ComposedChart, LineChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { QuarterlyDataPoint } from '../../types/earnings';

interface QuarterlyChartsProps {
  revenueData: QuarterlyDataPoint[];
  epsData: QuarterlyDataPoint[];
}

function QuarterlyCharts({ revenueData, epsData }: QuarterlyChartsProps) {
  // Custom tooltip for better formatting
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="glass-effect rounded-lg p-4 border border-slate-200/50 shadow-xl">
          <p className="font-semibold text-slate-900 mb-2">{label}</p>
          {payload.map((entry: any, index: number) => (
            <div key={index} className="flex items-center justify-between gap-4">
              <span className="text-sm text-slate-600">{entry.name}:</span>
              <span className="font-semibold" style={{ color: entry.color }}>
                {entry.name.includes('%')
                  ? `${entry.value.toFixed(2)}%`
                  : `$${entry.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                }
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  // Prepare data for combined chart (memoized).
  // Match eps to revenue by quarter label instead of by index so mismatched
  // array lengths or different orderings don't silently corrupt the chart.
  const combinedData = useMemo(() => {
    const epsMap = new Map(epsData.map(e => [e.quarter, e]));
    return revenueData.map((revPoint) => {
      const eps = epsMap.get(revPoint.quarter);
      return {
        quarter: revPoint.quarter,
        revenue: revPoint.value,
        revenueGrowth: revPoint.yoyGrowth || 0,
        eps: eps?.value || 0,
        epsGrowth: eps?.yoyGrowth || 0,
      };
    });
  }, [revenueData, epsData]);

  return (
    <div className="space-y-6">
      {/* Revenue Chart */}
      <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
        <h3 className="text-lg font-semibold text-slate-900 mb-6">Quarterly Revenue Trend</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={combinedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="quarter"
              stroke="#64748b"
              style={{ fontSize: '12px', fontFamily: 'IBM Plex Sans' }}
            />
            <YAxis
              yAxisId="left"
              stroke="#64748b"
              style={{ fontSize: '12px', fontFamily: 'IBM Plex Sans' }}
              tickFormatter={(value) => `$${(value / 1000000000).toFixed(1)}B`}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#64748b"
              style={{ fontSize: '12px', fontFamily: 'IBM Plex Sans' }}
              tickFormatter={(value) => `${value.toFixed(0)}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontFamily: 'IBM Plex Sans', fontSize: '14px' }}
              iconType="line"
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="revenue"
              stroke="#3b82f6"
              strokeWidth={3}
              dot={{ fill: '#3b82f6', r: 5 }}
              activeDot={{ r: 7 }}
              name="Revenue ($)"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="revenueGrowth"
              stroke="#10b981"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={{ fill: '#10b981', r: 4 }}
              name="YoY Growth (%)"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* EPS Chart */}
      <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
        <h3 className="text-lg font-semibold text-slate-900 mb-6">Quarterly Earnings Per Share</h3>
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={combinedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="quarter"
              stroke="#64748b"
              style={{ fontSize: '12px', fontFamily: 'IBM Plex Sans' }}
            />
            <YAxis
              yAxisId="left"
              stroke="#64748b"
              style={{ fontSize: '12px', fontFamily: 'IBM Plex Sans' }}
              tickFormatter={(value) => `$${value.toFixed(2)}`}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#64748b"
              style={{ fontSize: '12px', fontFamily: 'IBM Plex Sans' }}
              tickFormatter={(value) => `${value.toFixed(0)}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontFamily: 'IBM Plex Sans', fontSize: '14px' }}
              iconType="rect"
            />
            <Bar
              yAxisId="left"
              dataKey="eps"
              fill="#6366f1"
              radius={[8, 8, 0, 0]}
              name="EPS ($)"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="epsGrowth"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={{ fill: '#f59e0b', r: 4 }}
              name="YoY Growth (%)"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Growth Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-100">
          <div className="text-sm font-medium text-slate-600 mb-2">Latest Quarter Revenue Growth</div>
          <div className={`text-3xl font-bold ${
            (revenueData[revenueData.length - 1]?.yoyGrowth || 0) >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {((revenueData[revenueData.length - 1]?.yoyGrowth || 0) >= 0 ? '+' : '')}
            {(revenueData[revenueData.length - 1]?.yoyGrowth || 0).toFixed(2)}%
          </div>
          <div className="text-xs text-slate-500 mt-1">Year-over-year</div>
        </div>

        <div className="bg-gradient-to-br from-purple-50 to-pink-50 rounded-xl p-6 border border-purple-100">
          <div className="text-sm font-medium text-slate-600 mb-2">Latest Quarter EPS Growth</div>
          <div className={`text-3xl font-bold ${
            (epsData[epsData.length - 1]?.yoyGrowth || 0) >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {((epsData[epsData.length - 1]?.yoyGrowth || 0) >= 0 ? '+' : '')}
            {(epsData[epsData.length - 1]?.yoyGrowth || 0).toFixed(2)}%
          </div>
          <div className="text-xs text-slate-500 mt-1">Year-over-year</div>
        </div>
      </div>
    </div>
  );
}

// Memoize to prevent unnecessary re-renders.
// Compare all quarter labels AND the last data values so any revision to
// numbers (not just length changes) triggers a re-render.
export default memo(QuarterlyCharts, (prevProps, nextProps) => {
  const sameRevenue =
    prevProps.revenueData.length === nextProps.revenueData.length &&
    prevProps.revenueData.every((p, i) =>
      p.quarter === nextProps.revenueData[i]?.quarter &&
      p.value === nextProps.revenueData[i]?.value
    );
  const sameEps =
    prevProps.epsData.length === nextProps.epsData.length &&
    prevProps.epsData.every((p, i) =>
      p.quarter === nextProps.epsData[i]?.quarter &&
      p.value === nextProps.epsData[i]?.value
    );
  return sameRevenue && sameEps;
});
