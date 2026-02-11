import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

interface EarningsSettingsPopoverProps {
  quarters: number;
  focusQuery: string;
  onQuartersChange: (quarters: number) => void;
  onFocusQueryChange: (query: string) => void;
  onClose: () => void;
}

export default function EarningsSettingsPopover({
  quarters,
  focusQuery,
  onQuartersChange,
  onFocusQueryChange,
  onClose,
}: EarningsSettingsPopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [onClose]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    // Delay to prevent immediate close from the settings button click
    const timeoutId = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);

    return () => {
      clearTimeout(timeoutId);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [onClose]);

  return (
    <div
      ref={popoverRef}
      role="dialog"
      aria-modal="true"
      aria-label="Analysis settings"
      className="absolute bottom-full left-0 right-0 mb-3 glass-effect rounded-2xl border border-slate-200/80 shadow-2xl p-6 animate-slide-up"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-900">Analysis Settings</h3>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          aria-label="Close settings"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Quarters selector */}
      <div className="mb-5">
        <label className="block text-sm font-medium text-slate-700 mb-3">
          Number of Quarters
        </label>
        <div className="flex gap-2">
          {[1, 2, 3, 4].map((q) => (
            <button
              key={q}
              onClick={() => onQuartersChange(q)}
              className={`flex-1 py-2.5 px-4 rounded-xl font-semibold transition-all duration-200 ${
                quarters === q
                  ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/30'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
              aria-pressed={quarters === q}
            >
              {q}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Analyze the last {quarters} quarter{quarters > 1 ? 's' : ''} of earnings
        </p>
      </div>

      {/* Focus query input */}
      <div>
        <label htmlFor="focus-query" className="block text-sm font-medium text-slate-700 mb-2">
          Focus Query <span className="text-slate-400 font-normal">(optional)</span>
        </label>
        <input
          id="focus-query"
          type="text"
          value={focusQuery}
          onChange={(e) => onFocusQueryChange(e.target.value)}
          placeholder="e.g., AI strategy, margin trends, iPhone demand..."
          className="w-full px-4 py-2.5 border border-slate-300 rounded-xl
            focus:ring-2 focus:ring-blue-500 focus:border-blue-500 focus:outline-none
            text-slate-900 placeholder-slate-400
            transition-all duration-200"
        />
        <p className="mt-2 text-xs text-slate-500">
          Add a specific question to focus the earnings call analysis
        </p>
      </div>
    </div>
  );
}
