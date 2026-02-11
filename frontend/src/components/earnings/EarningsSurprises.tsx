import { TrendingUp, TrendingDown, Target } from 'lucide-react';
import { SurpriseData } from '../../types/earnings';

interface EarningsSurprisesProps {
  surprises: SurpriseData[];
}

export default function EarningsSurprises({ surprises }: EarningsSurprisesProps) {
  if (!surprises || surprises.length === 0) {
    return (
      <div className="glass-effect rounded-2xl p-12 border border-slate-200/50 text-center">
        <Target className="h-12 w-12 text-slate-300 mx-auto mb-4" />
        <p className="text-slate-500">No earnings surprise data available.</p>
      </div>
    );
  }

  // Calculate statistics
  const beatsCount = surprises.filter(s => s.beat).length;
  const missesCount = surprises.filter(s => !s.beat).length;
  const beatRate = (beatsCount / surprises.length) * 100;
  const avgSurprise = surprises.reduce((sum, s) => sum + s.surprisePercent, 0) / surprises.length;

  return (
    <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-2 flex items-center gap-2">
          <Target className="h-5 w-5 text-blue-600" />
          Earnings Surprises Timeline
        </h3>
        <p className="text-sm text-slate-600">
          Historical performance vs. analyst expectations
        </p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-4 border border-green-100">
          <div className="text-sm text-slate-600 mb-1">Beat Rate</div>
          <div className="text-2xl font-bold text-green-700">{beatRate.toFixed(0)}%</div>
          <div className="text-xs text-slate-500 mt-1">{beatsCount} of {surprises.length} quarters</div>
        </div>

        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-100">
          <div className="text-sm text-slate-600 mb-1">Avg Surprise</div>
          <div className={`text-2xl font-bold ${avgSurprise >= 0 ? 'text-green-700' : 'text-red-700'}`}>
            {avgSurprise >= 0 ? '+' : ''}{avgSurprise.toFixed(2)}%
          </div>
          <div className="text-xs text-slate-500 mt-1">Per quarter</div>
        </div>

        <div className="bg-gradient-to-br from-slate-50 to-gray-50 rounded-lg p-4 border border-slate-200">
          <div className="text-sm text-slate-600 mb-1">Track Record</div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-lg font-bold text-green-600">{beatsCount} Beats</span>
            <span className="text-slate-400">•</span>
            <span className="text-lg font-bold text-red-600">{missesCount} Misses</span>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="space-y-3">
        {surprises.map((surprise, idx) => {
          const isBeat = surprise.beat;
          const isRecent = idx === surprises.length - 1;

          return (
            <div
              key={idx}
              className={`relative border rounded-xl p-4 transition-all hover:shadow-md ${
                isBeat
                  ? 'border-green-200 bg-green-50/30 hover:bg-green-50/50'
                  : 'border-red-200 bg-red-50/30 hover:bg-red-50/50'
              } ${isRecent ? 'ring-2 ring-blue-500 ring-offset-2' : ''}`}
            >
              {isRecent && (
                <div className="absolute -top-3 left-4 px-2 py-0.5 bg-blue-500 text-white text-xs font-semibold rounded-full">
                  Most Recent
                </div>
              )}

              <div className="flex items-center justify-between gap-4">
                {/* Quarter Info */}
                <div className="flex items-center gap-4 flex-1">
                  <div className={`p-2 rounded-lg ${isBeat ? 'bg-green-100' : 'bg-red-100'}`}>
                    {isBeat ? (
                      <TrendingUp className="h-5 w-5 text-green-600" />
                    ) : (
                      <TrendingDown className="h-5 w-5 text-red-600" />
                    )}
                  </div>

                  <div>
                    <div className="font-semibold text-slate-900">{surprise.quarter}</div>
                    <div className="text-sm text-slate-500">{surprise.date}</div>
                  </div>
                </div>

                {/* EPS Data */}
                <div className="grid grid-cols-3 gap-6 text-right">
                  <div>
                    <div className="text-xs text-slate-600 mb-1">Actual</div>
                    <div className="font-semibold text-slate-900">
                      ${surprise.actualEPS.toFixed(2)}
                    </div>
                  </div>

                  <div>
                    <div className="text-xs text-slate-600 mb-1">Expected</div>
                    <div className="font-semibold text-slate-700">
                      ${surprise.estimatedEPS.toFixed(2)}
                    </div>
                  </div>

                  <div>
                    <div className="text-xs text-slate-600 mb-1">Surprise</div>
                    <div className={`font-bold ${isBeat ? 'text-green-600' : 'text-red-600'}`}>
                      {isBeat ? '+' : ''}{surprise.surprisePercent.toFixed(2)}%
                    </div>
                    <div className={`text-xs ${isBeat ? 'text-green-600' : 'text-red-600'}`}>
                      {isBeat ? '+' : ''}{surprise.surprise >= 0 ? '$' : '-$'}
                      {Math.abs(surprise.surprise).toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Consistency Note */}
      {beatRate >= 75 && (
        <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
          <span className="font-semibold">Strong Track Record:</span> Consistently beats analyst expectations ({beatRate.toFixed(0)}% beat rate)
        </div>
      )}

      {beatRate < 50 && (
        <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
          <span className="font-semibold">Mixed Results:</span> Below 50% beat rate suggests execution challenges or conservative guidance
        </div>
      )}
    </div>
  );
}
