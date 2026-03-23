import { TimePeriod } from '../api';

type ViewMode = 'orig' | 'pctChg';

interface StockChartPeriodSelectorProps {
  period: TimePeriod;
  onPeriodChange: (p: TimePeriod) => void;
  viewMode: ViewMode;
  onViewModeChange: (m: ViewMode) => void;
  showToggle: boolean;
  showMA: boolean;
  onToggleMA: () => void;
}

const PERIODS: TimePeriod[] = ['1M', '6M', 'YTD', '1Y', '5Y', 'MAX'];

function StockChartPeriodSelector({
  period,
  onPeriodChange,
  viewMode,
  onViewModeChange,
  showToggle,
  showMA,
  onToggleMA,
}: StockChartPeriodSelectorProps) {
  return (
    <div className="flex items-center justify-between">
      {/* Period pills */}
      <div className="flex gap-1">
        {PERIODS.map((p) => (
          <button
            key={p}
            onClick={() => onPeriodChange(p)}
            className="px-3 py-1 text-xs font-medium rounded-md transition-all"
            style={{
              fontFamily: 'Inter, sans-serif',
              backgroundColor: period === p ? '#F3F4F6' : 'transparent',
              color: period === p ? '#1A1A1A' : '#9CA3AF',
            }}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Right-side controls */}
      <div className="flex items-center gap-2">
        {/* Orig / % Chg toggle */}
        {showToggle && (
          <div
            className="flex rounded-md overflow-hidden border"
            style={{ borderColor: '#E5E7EB' }}
          >
            <button
              onClick={() => onViewModeChange('orig')}
              className="px-3 py-1 text-xs font-medium transition-all"
              style={{
                fontFamily: 'Inter, sans-serif',
                backgroundColor: viewMode === 'orig' ? '#F3F4F6' : 'transparent',
                color: viewMode === 'orig' ? '#1A1A1A' : '#9CA3AF',
              }}
            >
              Orig
            </button>
            <button
              onClick={() => onViewModeChange('pctChg')}
              className="px-3 py-1 text-xs font-medium transition-all border-l"
              style={{
                fontFamily: 'Inter, sans-serif',
                borderColor: '#E5E7EB',
                backgroundColor: viewMode === 'pctChg' ? '#F3F4F6' : 'transparent',
                color: viewMode === 'pctChg' ? '#1A1A1A' : '#9CA3AF',
              }}
            >
              % Chg
            </button>
          </div>
        )}

        {/* MA toggle */}
        <button
          onClick={onToggleMA}
          className="px-3 py-1 text-xs font-medium rounded-md transition-all border"
          style={{
            borderColor: showMA ? '#10B981' : '#E5E7EB',
            backgroundColor: showMA ? 'rgba(16,185,129,0.06)' : 'transparent',
            color: showMA ? '#10B981' : '#9CA3AF',
            fontFamily: 'Inter, sans-serif',
          }}
        >
          MA
        </button>
      </div>
    </div>
  );
}

export default StockChartPeriodSelector;
