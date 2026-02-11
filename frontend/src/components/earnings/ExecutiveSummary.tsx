import { memo } from 'react';
import { TrendingUp, TrendingDown, DollarSign, BarChart3 } from 'lucide-react';
import { EarningsAnalysis } from '../../types/earnings';

interface ExecutiveSummaryProps {
  data: EarningsAnalysis;
}

function ExecutiveSummary({ data }: ExecutiveSummaryProps) {
  const { summary, thesis } = data;

  const getRatingColor = (rating: string) => {
    switch (rating.toLowerCase()) {
      case 'buy': return 'bg-green-500';
      case 'sell': return 'bg-red-500';
      default: return 'bg-yellow-500';
    }
  };

  const formatChange = (value: number, isPercent: boolean = false) => {
    const sign = value >= 0 ? '+' : '';
    const formatted = isPercent ? `${value.toFixed(2)}%` : value.toFixed(2);
    return `${sign}${formatted}`;
  };

  const MetricCard = ({
    label,
    value,
    change,
    changePercent,
    icon: Icon
  }: {
    label: string;
    value: number;
    change: number;
    changePercent: number;
    icon: any;
  }) => (
    <div className="bg-white rounded-xl p-6 border border-slate-200/50 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <Icon className="h-5 w-5 text-slate-400" />
      </div>
      <div className="mb-2">
        <div className="text-2xl font-bold text-slate-900">
          ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className={`flex items-center gap-1 text-sm font-medium ${
          change >= 0 ? 'text-green-600' : 'text-red-600'
        }`}>
          {change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
          <span>{formatChange(change)}</span>
        </div>
        <span className="text-sm text-slate-500">
          ({formatChange(changePercent, true)})
        </span>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-2xl font-bold text-slate-900">{data.companyName}</h2>
              <span className="text-lg font-semibold text-slate-600">({data.ticker})</span>
            </div>
            <div className="flex items-center gap-4 text-sm text-slate-600">
              <span>{summary.quarter}</span>
              <span>•</span>
              <span>Reported {summary.reportDate}</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-sm text-slate-600 mb-1">Price Target</div>
              <div className="text-2xl font-bold text-slate-900">
                ${thesis.priceTarget.toFixed(2)}
              </div>
            </div>
            <div className={`px-6 py-3 rounded-xl ${getRatingColor(thesis.rating)} shadow-lg`}>
              <div className="text-sm font-semibold text-white/90 mb-1">Rating</div>
              <div className="text-xl font-bold text-white">{thesis.rating.toUpperCase()}</div>
            </div>
          </div>
        </div>

        {/* Sentiment Badge */}
        <div className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-slate-100 rounded-full">
          <div className={`w-2 h-2 rounded-full ${
            summary.sentiment.toLowerCase().includes('positive') || summary.sentiment.toLowerCase().includes('strong')
              ? 'bg-green-500'
              : summary.sentiment.toLowerCase().includes('negative') || summary.sentiment.toLowerCase().includes('weak')
              ? 'bg-red-500'
              : 'bg-yellow-500'
          }`}></div>
          <span className="text-sm font-medium text-slate-700">
            Overall Sentiment: <span className="font-semibold">{summary.sentiment}</span>
          </span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <MetricCard
          label="Revenue"
          value={summary.revenue.value}
          change={summary.revenue.change}
          changePercent={summary.revenue.changePercent}
          icon={DollarSign}
        />
        <MetricCard
          label="Earnings Per Share"
          value={summary.eps.value}
          change={summary.eps.change}
          changePercent={summary.eps.changePercent}
          icon={BarChart3}
        />
      </div>

      {/* Highlights */}
      {summary.highlights && summary.highlights.length > 0 && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-100">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">Key Highlights</h3>
          <ul className="space-y-2">
            {summary.highlights.map((highlight, idx) => (
              <li key={idx} className="flex items-start gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-2 flex-shrink-0"></div>
                <span className="text-slate-700 leading-relaxed">{highlight}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Memoize component to prevent unnecessary re-renders
export default memo(ExecutiveSummary, (prevProps, nextProps) => {
  return (
    prevProps.data.ticker === nextProps.data.ticker &&
    prevProps.data.summary.quarter === nextProps.data.summary.quarter &&
    prevProps.data.summary.reportDate === nextProps.data.summary.reportDate
  );
});
