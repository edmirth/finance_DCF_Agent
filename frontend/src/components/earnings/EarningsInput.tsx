import { useState, KeyboardEvent, useRef, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

interface EarningsInputProps {
  isAnalyzing: boolean;
  onSubmit: (question: string) => void;
}

export default function EarningsInput({
  isAnalyzing,
  onSubmit,
}: EarningsInputProps) {
  const [question, setQuestion] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (question.trim() && !isAnalyzing) {
        onSubmit(question.trim());
        setQuestion('');
      }
    }
  };

  useEffect(() => {
    const handleKeyPress = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  const canSubmit = question.trim().length > 0 && !isAnalyzing;

  return (
    <div
      className="fixed bottom-0 left-20 right-0 pb-6 pt-4 z-20"
      style={{ background: 'linear-gradient(to top, #FFFFFF 60%, transparent)' }}
    >
      <div className="max-w-[720px] mx-auto px-6">
        <div className="followup-input-bar">
          <input
            ref={inputRef}
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a follow up..."
            disabled={isAnalyzing}
          />
          <button
            onClick={() => {
              if (canSubmit) {
                onSubmit(question.trim());
                setQuestion('');
              }
            }}
            disabled={!canSubmit}
            className={`followup-send-btn ${canSubmit ? 'active' : 'disabled'}`}
            aria-label="Send follow-up question"
          >
            {isAnalyzing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 8H13M13 8L8.5 3.5M13 8L8.5 12.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
