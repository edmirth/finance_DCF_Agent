import { Quote, TrendingUp, AlertCircle, Info } from 'lucide-react';
import { ManagementQuote, GuidanceData } from '../../types/earnings';

interface ManagementCommentaryProps {
  quotes: ManagementQuote[];
  guidance: GuidanceData;
  sentiment: string;
}

export default function ManagementCommentary({ quotes, guidance, sentiment }: ManagementCommentaryProps) {
  const getSentimentIcon = (sentiment?: string) => {
    if (!sentiment) return null;
    switch (sentiment.toLowerCase()) {
      case 'positive':
        return <TrendingUp className="h-4 w-4 text-green-600" />;
      case 'negative':
        return <AlertCircle className="h-4 w-4 text-red-600" />;
      default:
        return <Info className="h-4 w-4 text-yellow-600" />;
    }
  };

  const getSentimentColor = (sentiment?: string) => {
    if (!sentiment) return 'border-slate-200';
    switch (sentiment.toLowerCase()) {
      case 'positive':
        return 'border-l-green-500 bg-green-50/30';
      case 'negative':
        return 'border-l-red-500 bg-red-50/30';
      default:
        return 'border-l-yellow-500 bg-yellow-50/30';
    }
  };

  const getOverallSentimentColor = () => {
    const lower = sentiment.toLowerCase();
    if (lower.includes('positive') || lower.includes('strong') || lower.includes('optimistic')) {
      return 'from-green-50 to-emerald-50 border-green-200';
    } else if (lower.includes('negative') || lower.includes('weak') || lower.includes('pessimistic')) {
      return 'from-red-50 to-rose-50 border-red-200';
    }
    return 'from-yellow-50 to-amber-50 border-yellow-200';
  };

  return (
    <div className="space-y-6">
      {/* Overall Sentiment Card */}
      <div className={`rounded-xl p-6 border bg-gradient-to-br ${getOverallSentimentColor()}`}>
        <div className="flex items-center gap-3 mb-3">
          <Quote className="h-6 w-6 text-slate-700" />
          <h3 className="text-lg font-semibold text-slate-900">Management Sentiment</h3>
        </div>
        <p className="text-slate-700 leading-relaxed">{sentiment}</p>
      </div>

      {/* Forward Guidance */}
      {(guidance.nextQuarter || guidance.fullYear || guidance.commentary) && (
        <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-blue-600" />
            Forward Guidance
          </h3>

          <div className="space-y-4">
            {guidance.nextQuarter && (
              <div className="bg-blue-50/50 rounded-lg p-4 border border-blue-100">
                <div className="text-sm font-semibold text-slate-700 mb-2">Next Quarter</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {guidance.nextQuarter.revenue && (
                    <div>
                      <span className="text-xs text-slate-600">Revenue:</span>
                      <div className="font-semibold text-slate-900">{guidance.nextQuarter.revenue}</div>
                    </div>
                  )}
                  {guidance.nextQuarter.eps && (
                    <div>
                      <span className="text-xs text-slate-600">EPS:</span>
                      <div className="font-semibold text-slate-900">{guidance.nextQuarter.eps}</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {guidance.fullYear && (
              <div className="bg-indigo-50/50 rounded-lg p-4 border border-indigo-100">
                <div className="text-sm font-semibold text-slate-700 mb-2">Full Year</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {guidance.fullYear.revenue && (
                    <div>
                      <span className="text-xs text-slate-600">Revenue:</span>
                      <div className="font-semibold text-slate-900">{guidance.fullYear.revenue}</div>
                    </div>
                  )}
                  {guidance.fullYear.eps && (
                    <div>
                      <span className="text-xs text-slate-600">EPS:</span>
                      <div className="font-semibold text-slate-900">{guidance.fullYear.eps}</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {guidance.commentary && (
              <div className="text-sm text-slate-700 leading-relaxed italic border-l-4 border-slate-300 pl-4">
                "{guidance.commentary}"
              </div>
            )}
          </div>
        </div>
      )}

      {/* Management Quotes */}
      {quotes && quotes.length > 0 && (
        <div className="glass-effect rounded-2xl p-6 border border-slate-200/50 shadow-lg">
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Quote className="h-5 w-5 text-slate-600" />
            Key Quotes from Earnings Call
          </h3>

          <div className="space-y-4">
            {quotes.map((quote, idx) => (
              <div
                key={idx}
                className={`border-l-4 rounded-r-lg p-4 transition-all hover:shadow-md ${getSentimentColor(quote.sentiment)}`}
              >
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <div className="font-semibold text-slate-900">{quote.speaker}</div>
                    <div className="text-sm text-slate-600">{quote.role}</div>
                  </div>
                  {quote.sentiment && (
                    <div className="flex items-center gap-1">
                      {getSentimentIcon(quote.sentiment)}
                    </div>
                  )}
                </div>

                <blockquote className="text-slate-700 leading-relaxed mb-3 italic">
                  "{quote.quote}"
                </blockquote>

                {quote.topic && (
                  <div className="inline-flex items-center gap-2 px-3 py-1 bg-slate-100 rounded-full text-xs font-medium text-slate-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                    {quote.topic}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {(!quotes || quotes.length === 0) && !guidance.commentary && (
        <div className="glass-effect rounded-2xl p-12 border border-slate-200/50 text-center">
          <Quote className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500">No management commentary available for this quarter.</p>
        </div>
      )}
    </div>
  );
}
