import { KeyboardEvent } from 'react';

interface EarningsEmptyStateProps {
  ticker: string;
  onTickerChange: (ticker: string) => void;
  onAnalyze: () => void;
}

export default function EarningsEmptyState({ ticker, onTickerChange, onAnalyze }: EarningsEmptyStateProps) {
  const suggestedQueries = [
    { ticker: 'AAPL', label: 'Apple earnings breakdown' },
    { ticker: 'MSFT', label: 'Microsoft quarterly results' },
    { ticker: 'NVDA', label: 'NVIDIA earnings & AI outlook' },
    { ticker: 'TSLA', label: 'Tesla delivery & margins' },
  ];

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && ticker.trim()) {
      onAnalyze();
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] animate-fade-in">
      {/* Title */}
      <div className="text-center mb-10">
        <h1
          className="text-[2.5rem] font-semibold text-[#1A1A1A] tracking-tight mb-3"
          style={{ fontFamily: 'Inter, sans-serif', letterSpacing: '-0.03em' }}
        >
          Earnings Analysis
        </h1>
        <p
          className="text-lg text-[#6B7280] max-w-md mx-auto"
          style={{ fontFamily: 'Inter, sans-serif', lineHeight: 1.6 }}
        >
          AI-powered earnings research with management commentary, analyst outlook, and peer comparison.
        </p>
      </div>

      {/* Search input */}
      <div className="w-full max-w-[520px] mb-8">
        <div className="followup-input-bar" style={{ borderRadius: '9999px', padding: '0.625rem 0.625rem 0.625rem 1.5rem' }}>
          <input
            id="ticker"
            type="text"
            value={ticker}
            onChange={(e) => onTickerChange(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            placeholder="Enter ticker to analyze earnings..."
            maxLength={5}
            style={{ fontSize: '1rem' }}
          />
          <button
            onClick={onAnalyze}
            disabled={!ticker.trim()}
            className={`followup-send-btn ${ticker.trim() ? 'active' : 'disabled'}`}
            style={{ width: '2.5rem', height: '2.5rem' }}
            aria-label="Analyze earnings"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 8H13M13 8L8.5 3.5M13 8L8.5 12.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Suggested queries */}
      <div className="flex flex-wrap justify-center gap-2.5">
        {suggestedQueries.map(({ ticker: t, label }) => (
          <button
            key={t}
            onClick={() => {
              onTickerChange(t);
              setTimeout(() => {
                const input = document.getElementById('ticker');
                if (input) input.focus();
              }, 50);
            }}
            className="px-4 py-2 rounded-full text-sm transition-all duration-200"
            style={{
              fontFamily: 'Inter, sans-serif',
              color: '#6B7280',
              background: '#F9FAFB',
              border: '1px solid #E5E5E5',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#10B981';
              e.currentTarget.style.color = '#1A1A1A';
              e.currentTarget.style.background = '#F0FDF4';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#E5E5E5';
              e.currentTarget.style.color = '#6B7280';
              e.currentTarget.style.background = '#F9FAFB';
            }}
          >
            <span className="font-medium">{t}</span>
            <span className="ml-1.5 text-[#9CA3AF]">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
