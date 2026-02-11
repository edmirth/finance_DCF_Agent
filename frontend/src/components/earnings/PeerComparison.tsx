import { Building2, TrendingUp, TrendingDown } from 'lucide-react';
import { PeerMetric } from '../../types/earnings';

interface PeerComparisonProps {
  comparison: PeerMetric[];
  targetTicker: string;
}

export default function PeerComparison({ comparison, targetTicker }: PeerComparisonProps) {
  if (!comparison || comparison.length === 0) {
    return (
      <div className="glass-effect rounded-2xl p-12 border border-slate-200/50 text-center">
        <Building2 className="h-12 w-12 text-slate-300 mx-auto mb-4" />
        <p className="text-slate-500">No peer comparison data available.</p>
      </div>
    );
  }

  // Sort by revenue descending
  const sortedPeers = [...comparison].sort((a, b) => b.revenue - a.revenue);

  // Find max values for relative sizing
  const maxRevenue = Math.max(...sortedPeers.map(p => p.revenue));
  const maxEPS = Math.max(...sortedPeers.map(p => p.eps));

  // Helper to format large numbers
  const formatNumber = (value: number) => {
    if (value >= 1000000000) {
      return `$${(value / 1000000000).toFixed(1)}B`;
    } else if (value >= 1000000) {
      return `$${(value / 1000000).toFixed(1)}M`;
    } else {
      return `$${value.toLocaleString()}`;
    }
  };

  const getGrowthColor = (growth: number) => {
    if (growth >= 15) return 'text-green-600 bg-green-50';
    if (growth >= 5) return 'text-green-700 bg-green-50';
    if (growth >= 0) return 'text-slate-600 bg-slate-50';
    if (growth >= -5) return 'text-orange-600 bg-orange-50';
    return 'text-red-600 bg-red-50';
  };

  return (
    <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-2 flex items-center gap-2">
          <Building2 className="h-5 w-5 text-indigo-600" />
          Peer Comparison
        </h3>
        <p className="text-sm text-slate-600">
          Competitive positioning and relative performance
        </p>
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700">Company</th>
              <th className="text-right py-3 px-4 text-sm font-semibold text-slate-700">Revenue</th>
              <th className="text-right py-3 px-4 text-sm font-semibold text-slate-700">EPS</th>
              <th className="text-right py-3 px-4 text-sm font-semibold text-slate-700">YoY Growth</th>
              <th className="text-right py-3 px-4 text-sm font-semibold text-slate-700">Margin</th>
            </tr>
          </thead>
          <tbody>
            {sortedPeers.map((peer, idx) => {
              const isTarget = peer.ticker === targetTicker;
              const rowClass = isTarget
                ? 'bg-blue-50 border-l-4 border-blue-500'
                : idx % 2 === 0
                ? 'bg-slate-50/50'
                : 'bg-white';

              return (
                <tr key={idx} className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${rowClass}`}>
                  <td className="py-4 px-4">
                    <div className="flex items-center gap-3">
                      {isTarget && (
                        <div className="px-2 py-0.5 bg-blue-500 text-white text-xs font-semibold rounded">
                          You
                        </div>
                      )}
                      <div>
                        <div className="font-semibold text-slate-900">{peer.ticker}</div>
                        <div className="text-xs text-slate-500">{peer.companyName}</div>
                      </div>
                    </div>
                  </td>

                  <td className="py-4 px-4 text-right">
                    <div className="font-semibold text-slate-900">{formatNumber(peer.revenue)}</div>
                    {/* Revenue bar */}
                    <div className="mt-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${(peer.revenue / maxRevenue) * 100}%` }}
                      ></div>
                    </div>
                  </td>

                  <td className="py-4 px-4 text-right">
                    <div className="font-semibold text-slate-900">${peer.eps.toFixed(2)}</div>
                    {/* EPS bar */}
                    <div className="mt-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-purple-500 rounded-full"
                        style={{ width: `${(peer.eps / maxEPS) * 100}%` }}
                      ></div>
                    </div>
                  </td>

                  <td className="py-4 px-4 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {peer.yoyGrowth >= 0 ? (
                        <TrendingUp className="h-4 w-4 text-green-600" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-600" />
                      )}
                      <span className={`font-semibold ${peer.yoyGrowth >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {peer.yoyGrowth >= 0 ? '+' : ''}{peer.yoyGrowth.toFixed(1)}%
                      </span>
                    </div>
                  </td>

                  <td className="py-4 px-4 text-right">
                    <span className={`px-2 py-1 rounded-full text-sm font-semibold ${getGrowthColor(peer.margin)}`}>
                      {peer.margin.toFixed(1)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden space-y-3">
        {sortedPeers.map((peer, idx) => {
          const isTarget = peer.ticker === targetTicker;

          return (
            <div
              key={idx}
              className={`border rounded-xl p-4 ${
                isTarget
                  ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                  : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-900">{peer.ticker}</span>
                    {isTarget && (
                      <span className="px-2 py-0.5 bg-blue-500 text-white text-xs font-semibold rounded">
                        You
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-slate-600">{peer.companyName}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-slate-600 mb-1">Revenue</div>
                  <div className="font-semibold text-slate-900">{formatNumber(peer.revenue)}</div>
                </div>

                <div>
                  <div className="text-xs text-slate-600 mb-1">EPS</div>
                  <div className="font-semibold text-slate-900">${peer.eps.toFixed(2)}</div>
                </div>

                <div>
                  <div className="text-xs text-slate-600 mb-1">YoY Growth</div>
                  <div className={`font-semibold ${peer.yoyGrowth >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {peer.yoyGrowth >= 0 ? '+' : ''}{peer.yoyGrowth.toFixed(1)}%
                  </div>
                </div>

                <div>
                  <div className="text-xs text-slate-600 mb-1">Margin</div>
                  <div className="font-semibold text-slate-900">{peer.margin.toFixed(1)}%</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Insights */}
      <div className="mt-6 p-4 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-lg border border-indigo-200">
        <h4 className="text-sm font-semibold text-slate-900 mb-2">Competitive Position</h4>
        <div className="text-sm text-slate-700 space-y-1">
          {(() => {
            const target = sortedPeers.find(p => p.ticker === targetTicker);
            if (!target) return null;

            const rank = sortedPeers.findIndex(p => p.ticker === targetTicker) + 1;
            const avgGrowth = sortedPeers.reduce((sum, p) => sum + p.yoyGrowth, 0) / sortedPeers.length;
            const avgMargin = sortedPeers.reduce((sum, p) => sum + p.margin, 0) / sortedPeers.length;

            return (
              <>
                <p>• Ranked #{rank} of {sortedPeers.length} by revenue</p>
                <p>
                  • Growth rate {target.yoyGrowth > avgGrowth ? 'above' : 'below'} peer average
                  ({target.yoyGrowth >= 0 ? '+' : ''}{target.yoyGrowth.toFixed(1)}% vs {avgGrowth >= 0 ? '+' : ''}{avgGrowth.toFixed(1)}%)
                </p>
                <p>
                  • Margins {target.margin > avgMargin ? 'above' : 'below'} peer average
                  ({target.margin.toFixed(1)}% vs {avgMargin.toFixed(1)}%)
                </p>
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
