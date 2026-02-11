import { Search, TrendingUp } from 'lucide-react';

interface EarningsHeaderProps {
  ticker: string;
  setTicker: (value: string) => void;
  quarters: number;
  setQuarters: (value: number) => void;
  focusQuery: string;
  setFocusQuery: (value: string) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
}

export default function EarningsHeader({
  ticker,
  setTicker,
  quarters,
  setQuarters,
  focusQuery,
  setFocusQuery,
  onAnalyze,
  isAnalyzing,
}: EarningsHeaderProps) {
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (ticker.trim() && !isAnalyzing) {
      onAnalyze();
    }
  };

  return (
    <div className="sticky top-0 z-10 glass-effect border-b border-slate-200/50 shadow-sm">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Main input row */}
          <div className="flex flex-col md:flex-row gap-3">
            {/* Ticker input */}
            <div className="flex-1 min-w-0">
              <label htmlFor="ticker" className="block text-sm font-medium text-slate-700 mb-1">
                Stock Ticker
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  id="ticker"
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="AAPL, MSFT, TSLA..."
                  className="block w-full pl-10 pr-4 py-2.5 border border-slate-300 rounded-xl
                    focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                    text-slate-900 placeholder-slate-400 font-medium
                    transition-all duration-200"
                  maxLength={5}
                  disabled={isAnalyzing}
                />
              </div>
            </div>

            {/* Quarters selector */}
            <div className="w-full md:w-40">
              <label htmlFor="quarters" className="block text-sm font-medium text-slate-700 mb-1">
                Quarters
              </label>
              <select
                id="quarters"
                value={quarters}
                onChange={(e) => setQuarters(Number(e.target.value))}
                className="block w-full px-4 py-2.5 border border-slate-300 rounded-xl
                  focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                  text-slate-900 font-medium
                  transition-all duration-200"
                disabled={isAnalyzing}
              >
                <option value={1}>1 Quarter</option>
                <option value={2}>2 Quarters</option>
                <option value={3}>3 Quarters</option>
                <option value={4}>4 Quarters</option>
              </select>
            </div>

            {/* Analyze button */}
            <div className="flex items-end">
              <button
                type="submit"
                disabled={!ticker.trim() || isAnalyzing}
                className="w-full md:w-auto px-6 py-2.5 rounded-xl font-semibold
                  text-white bg-gradient-to-r from-blue-600 to-blue-700
                  hover:from-blue-700 hover:to-blue-800
                  disabled:from-slate-300 disabled:to-slate-400 disabled:cursor-not-allowed
                  shadow-lg shadow-blue-500/30 hover:shadow-xl hover:shadow-blue-500/40
                  transform hover:scale-105 active:scale-95
                  transition-all duration-200
                  flex items-center justify-center gap-2"
              >
                {isAnalyzing ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent"></div>
                    <span>Analyzing...</span>
                  </>
                ) : (
                  <>
                    <TrendingUp className="h-5 w-5" />
                    <span>Analyze Earnings</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Focus query (optional) */}
          <div>
            <label htmlFor="focusQuery" className="block text-sm font-medium text-slate-700 mb-1">
              Focus Query <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="focusQuery"
              type="text"
              value={focusQuery}
              onChange={(e) => setFocusQuery(e.target.value)}
              placeholder="What did management say about AI? iPhone demand trends?"
              className="block w-full px-4 py-2.5 border border-slate-300 rounded-xl
                focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                text-slate-900 placeholder-slate-400
                transition-all duration-200"
              disabled={isAnalyzing}
            />
            <p className="mt-1 text-xs text-slate-500">
              Add a specific question to focus the earnings call analysis
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
