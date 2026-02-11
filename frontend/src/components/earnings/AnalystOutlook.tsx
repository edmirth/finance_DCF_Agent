import { Target, TrendingUp, TrendingDown, Minus, Calendar } from 'lucide-react';
import { PriceTargetData, RatingsData, RatingChange } from '../../types/earnings';

interface AnalystOutlookProps {
  priceTargets: PriceTargetData;
  ratings: RatingsData;
  recentChanges: RatingChange[];
  currentPrice?: number;
}

export default function AnalystOutlook({
  priceTargets,
  ratings,
  recentChanges,
  currentPrice,
}: AnalystOutlookProps) {
  // Calculate total ratings
  const totalRatings = ratings.buy + ratings.hold + ratings.sell;
  const buyPercent = totalRatings > 0 ? (ratings.buy / totalRatings) * 100 : 0;
  const holdPercent = totalRatings > 0 ? (ratings.hold / totalRatings) * 100 : 0;
  const sellPercent = totalRatings > 0 ? (ratings.sell / totalRatings) * 100 : 0;

  // Calculate upside/downside
  const upside = currentPrice && priceTargets.median
    ? ((priceTargets.median - currentPrice) / currentPrice) * 100
    : null;

  const getConsensusColor = (consensus: string) => {
    const lower = consensus.toLowerCase();
    if (lower.includes('buy') || lower.includes('strong buy')) return 'text-green-600';
    if (lower.includes('sell') || lower.includes('strong sell')) return 'text-red-600';
    return 'text-yellow-600';
  };

  const getRatingChangeIcon = (action: string) => {
    if (action.toLowerCase().includes('upgrade') || action.toLowerCase().includes('initiat')) {
      return <TrendingUp className="h-4 w-4 text-green-600" />;
    } else if (action.toLowerCase().includes('downgrade')) {
      return <TrendingDown className="h-4 w-4 text-red-600" />;
    }
    return <Minus className="h-4 w-4 text-slate-400" />;
  };

  return (
    <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-2 flex items-center gap-2">
          <Target className="h-5 w-5 text-purple-600" />
          Analyst Outlook
        </h3>
        <p className="text-sm text-slate-600">
          Wall Street consensus and price target analysis
        </p>
      </div>

      {/* Price Targets Section */}
      <div className="mb-6">
        <h4 className="text-sm font-semibold text-slate-700 mb-4">Price Targets</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Price Range Visualization */}
          <div className="space-y-4">
            <div className="relative">
              {/* Price Range Bar */}
              <div className="h-12 bg-gradient-to-r from-red-100 via-yellow-100 to-green-100 rounded-lg relative overflow-hidden">
                {/* Current Price Marker */}
                {currentPrice && priceTargets.median && (
                  <div
                    className="absolute top-0 bottom-0 w-1 bg-blue-600"
                    style={{
                      left: `${Math.min(100, Math.max(0, ((currentPrice - priceTargets.low) / (priceTargets.high - priceTargets.low)) * 100))}%`,
                    }}
                  >
                    <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs font-semibold text-blue-600 whitespace-nowrap">
                      Current
                    </div>
                  </div>
                )}

                {/* Median Target Marker */}
                <div
                  className="absolute top-0 bottom-0 w-1 bg-slate-800"
                  style={{
                    left: `${Math.min(100, Math.max(0, ((priceTargets.median - priceTargets.low) / (priceTargets.high - priceTargets.low)) * 100))}%`,
                  }}
                >
                  <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-xs font-semibold text-slate-800 whitespace-nowrap">
                    Target
                  </div>
                </div>
              </div>

              {/* Range Labels */}
              <div className="flex justify-between mt-2 text-xs text-slate-600">
                <span>Low: ${priceTargets.low.toFixed(2)}</span>
                <span>High: ${priceTargets.high.toFixed(2)}</span>
              </div>
            </div>

            {/* Upside Indicator */}
            {upside !== null && (
              <div className={`p-4 rounded-lg border ${
                upside > 0
                  ? 'bg-green-50 border-green-200'
                  : 'bg-red-50 border-red-200'
              }`}>
                <div className="text-sm text-slate-600 mb-1">Implied Upside/Downside</div>
                <div className={`text-2xl font-bold ${upside > 0 ? 'text-green-700' : 'text-red-700'}`}>
                  {upside > 0 ? '+' : ''}{upside.toFixed(2)}%
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  To median target of ${priceTargets.median.toFixed(2)}
                </div>
              </div>
            )}
          </div>

          {/* Price Target Stats */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
              <div className="text-xs text-slate-600 mb-1">Median Target</div>
              <div className="text-xl font-bold text-slate-900">${priceTargets.median.toFixed(2)}</div>
            </div>

            <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
              <div className="text-xs text-slate-600 mb-1">Analysts</div>
              <div className="text-xl font-bold text-slate-900">{priceTargets.numAnalysts}</div>
            </div>

            <div className="bg-green-50 rounded-lg p-4 border border-green-200">
              <div className="text-xs text-slate-600 mb-1">High Target</div>
              <div className="text-xl font-bold text-green-700">${priceTargets.high.toFixed(2)}</div>
            </div>

            <div className="bg-red-50 rounded-lg p-4 border border-red-200">
              <div className="text-xs text-slate-600 mb-1">Low Target</div>
              <div className="text-xl font-bold text-red-700">${priceTargets.low.toFixed(2)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Ratings Distribution */}
      <div className="mb-6">
        <h4 className="text-sm font-semibold text-slate-700 mb-4">Ratings Distribution</h4>
        <div className="space-y-4">
          {/* Stacked Bar Chart */}
          <div className="h-8 flex rounded-lg overflow-hidden shadow-inner">
            <div
              className="bg-green-500 flex items-center justify-center text-white text-sm font-semibold"
              style={{ width: `${buyPercent}%` }}
            >
              {buyPercent > 15 && `${buyPercent.toFixed(0)}%`}
            </div>
            <div
              className="bg-yellow-500 flex items-center justify-center text-white text-sm font-semibold"
              style={{ width: `${holdPercent}%` }}
            >
              {holdPercent > 15 && `${holdPercent.toFixed(0)}%`}
            </div>
            <div
              className="bg-red-500 flex items-center justify-center text-white text-sm font-semibold"
              style={{ width: `${sellPercent}%` }}
            >
              {sellPercent > 15 && `${sellPercent.toFixed(0)}%`}
            </div>
          </div>

          {/* Rating Counts */}
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
              <div className="text-2xl font-bold text-green-700">{ratings.buy}</div>
              <div className="text-xs text-slate-600 mt-1">Buy</div>
            </div>
            <div className="text-center p-3 bg-yellow-50 rounded-lg border border-yellow-200">
              <div className="text-2xl font-bold text-yellow-700">{ratings.hold}</div>
              <div className="text-xs text-slate-600 mt-1">Hold</div>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg border border-red-200">
              <div className="text-2xl font-bold text-red-700">{ratings.sell}</div>
              <div className="text-xs text-slate-600 mt-1">Sell</div>
            </div>
          </div>

          {/* Consensus */}
          <div className="text-center p-4 bg-gradient-to-r from-slate-50 to-gray-50 rounded-lg border border-slate-200">
            <div className="text-sm text-slate-600 mb-1">Consensus Rating</div>
            <div className={`text-xl font-bold ${getConsensusColor(ratings.consensus)}`}>
              {ratings.consensus}
            </div>
          </div>
        </div>
      </div>

      {/* Recent Rating Changes */}
      {recentChanges && recentChanges.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Recent Rating Changes
          </h4>
          <div className="space-y-2">
            {recentChanges.slice(0, 5).map((change, idx) => (
              <div key={idx} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors">
                {getRatingChangeIcon(change.action)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900 text-sm">{change.firm}</span>
                    <span className="text-xs text-slate-500">{change.date}</span>
                  </div>
                  <div className="text-xs text-slate-600 mt-0.5">
                    {change.action}: {change.fromRating} → {change.toRating}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
