import { useState, useCallback, useRef, useEffect } from 'react';
import { streamMessage } from '../api';
import EarningsEmptyState from '../components/earnings/EarningsEmptyState';
import EarningsLoadingState from '../components/earnings/EarningsLoadingState';
import EarningsReport from '../components/EarningsReport';
import EarningsFollowUpInput from '../components/earnings/EarningsInput';

export interface ProgressStep {
  node: string;
  label: string;
  status: 'pending' | 'active' | 'completed';
  detail?: string;
}

const STEP_LABELS: Record<string, string> = {
  fetch_company_info: 'Company info',
  fetch_earnings_history: 'Earnings history',
  fetch_analyst_estimates: 'Analyst estimates',
  fetch_guidance_and_news: 'Earnings calls & peers',
  comprehensive_analysis: 'Financial analysis',
  develop_thesis: 'Investment thesis',
  generate_report: 'Writing report',
};

function EarningsPage() {
  const [ticker, setTicker] = useState('');
  const [quarters] = useState(1);
  const [focusQuery] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [rawResponse, setRawResponse] = useState('');
  const [lastQuery, setLastQuery] = useState('');
  const [elapsedTime, setElapsedTime] = useState(0);
  const [sourceCount, setSourceCount] = useState(0);
  const [progressSteps, setProgressSteps] = useState<ProgressStep[]>([]);
  const [followUps, setFollowUps] = useState<Array<{question: string, answer: string, isLoading: boolean}>>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Timer for "Worked for Xs"
  useEffect(() => {
    if (isAnalyzing) {
      setElapsedTime(0);
      timerRef.current = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isAnalyzing]);

  // Count sources from tool calls in response
  const countSources = (text: string): number => {
    const toolMentions = new Set<string>();
    const patterns = [
      /get_quarterly_earnings/gi,
      /get_analyst_estimates/gi,
      /get_earnings_surprises/gi,
      /get_earnings_call_insights/gi,
      /compare_peer_earnings/gi,
      /get_price_targets/gi,
      /get_analyst_ratings/gi,
      /search_web/gi,
      /get_stock_info/gi,
      /get_financial_metrics/gi,
    ];
    patterns.forEach(p => {
      const matches = text.match(p);
      if (matches) toolMentions.add(p.source);
    });
    return Math.max(toolMentions.size, 3);
  };

  const analyzeEarnings = useCallback(async (queryOverride?: string) => {
    const activeTicker = ticker.trim();
    if (!activeTicker) return;

    const query = queryOverride || (focusQuery.trim()
      ? `Analyze ${activeTicker.toUpperCase()}'s last ${quarters} quarter(s) earnings. Focus on: ${focusQuery}`
      : `Analyze ${activeTicker.toUpperCase()}'s last ${quarters} quarter(s) earnings and forward outlook`);

    setIsAnalyzing(true);
    setRawResponse('');
    setLastQuery(query);
    setSourceCount(0);
    setProgressSteps([]);
    setFollowUps([]);

    let toolCount = 0;

    try {
      await streamMessage(
        {
          message: query,
          agent_type: 'earnings',
          model: 'claude-sonnet-4-5-20250929',
          session_id: `earnings-${Date.now()}`,
        },
        (event) => {
          if (event.type === 'earnings_progress' && event.node && event.status) {
            const node = event.node;
            const status = event.status;
            const detail = event.detail || '';
            const label = STEP_LABELS[node] || node;

            setProgressSteps(prev => {
              if (status === 'started') {
                const existing = prev.find(s => s.node === node);
                if (existing) {
                  return prev.map(s => s.node === node ? { ...s, status: 'active', detail } : s);
                }
                return [...prev, { node, label, status: 'active', detail }];
              } else if (status === 'completed') {
                const exists = prev.some(s => s.node === node);
                if (exists) {
                  return prev.map(s => s.node === node ? { ...s, status: 'completed', detail } : s);
                }
                return [...prev, { node, label, status: 'completed', detail }];
              } else if (status === 'sub_progress') {
                return prev.map(s => s.node === node ? { ...s, detail } : s);
              }
              return prev;
            });
          } else if (event.type === 'tool' || event.type === 'tool_result') {
            toolCount++;
            setSourceCount(Math.ceil(toolCount / 2));
          } else if (event.type === 'content' && event.content) {
            setRawResponse(prev => prev + event.content);
          } else if (event.type === 'end') {
            setRawResponse(prev => {
              const finalCount = countSources(prev);
              setSourceCount(Math.max(finalCount, Math.ceil(toolCount / 2)));
              return prev;
            });
            setIsAnalyzing(false);
          } else if (event.type === 'error') {
            console.error('Analysis error:', event.error);
            setIsAnalyzing(false);
          }
        },
        (error) => {
          console.error('Stream error:', error);
          setIsAnalyzing(false);
        }
      );
    } catch (error) {
      console.error('Error analyzing earnings:', error);
      setIsAnalyzing(false);
    }
  }, [ticker, quarters, focusQuery]);

  const askFollowUp = useCallback(async (question: string) => {
    const idx = followUps.length;
    setFollowUps(prev => [...prev, { question, answer: '', isLoading: true }]);

    try {
      await streamMessage(
        {
          message: `${question} for ${ticker.toUpperCase()}`,
          agent_type: 'earnings',
          model: 'claude-sonnet-4-5-20250929',
          session_id: `earnings-followup-${Date.now()}`,
          is_followup: true,
        },
        (event) => {
          if (event.type === 'content' && event.content) {
            setFollowUps(prev => prev.map((fu, i) =>
              i === idx ? { ...fu, answer: fu.answer + event.content } : fu
            ));
          } else if (event.type === 'end') {
            setFollowUps(prev => prev.map((fu, i) =>
              i === idx ? { ...fu, isLoading: false } : fu
            ));
          } else if (event.type === 'error') {
            setFollowUps(prev => prev.map((fu, i) =>
              i === idx ? { ...fu, answer: `Error: ${event.error}`, isLoading: false } : fu
            ));
          }
        },
        (error) => {
          setFollowUps(prev => prev.map((fu, i) =>
            i === idx ? { ...fu, answer: `Error: ${error}`, isLoading: false } : fu
          ));
        }
      );
    } catch (error) {
      console.error('Follow-up error:', error);
    }
  }, [followUps.length, ticker]);

  const handleFollowUp = useCallback((question: string) => {
    askFollowUp(question);
  }, [askFollowUp]);

  // Keyboard shortcut: Cmd+K to focus ticker
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const input = document.getElementById('ticker');
        if (input) input.focus();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (ticker.trim() && !isAnalyzing) {
          analyzeEarnings();
        }
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [ticker, isAnalyzing, analyzeEarnings]);

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  };

  const hasResults = !isAnalyzing && rawResponse;

  return (
    <div className="earnings-page">
      <a href="#main-content" className="skip-link">Skip to main content</a>

      <main id="main-content" tabIndex={-1} className="flex justify-center items-start min-h-screen">
        <div className="w-full max-w-[720px] px-4 sm:px-6 py-6 sm:py-8 mx-auto">

          {/* Empty State */}
          {!isAnalyzing && !rawResponse && (
            <EarningsEmptyState
              ticker={ticker}
              onTickerChange={setTicker}
              onAnalyze={analyzeEarnings}
            />
          )}

          {/* Loading State */}
          {isAnalyzing && (
            <>
              {/* User query bubble */}
              <div className="flex justify-end mb-6 animate-fade-in">
                <div className="query-bubble">{lastQuery}</div>
              </div>

              <EarningsLoadingState
                elapsedTime={formatTime(elapsedTime)}
                sourceCount={sourceCount}
                progressSteps={progressSteps}
              />
            </>
          )}

          {/* Results */}
          {hasResults && (
            <div ref={contentRef} className="animate-fade-in pb-32">
              {/* User query bubble */}
              <div className="flex justify-end mb-4">
                <div className="query-bubble">{lastQuery}</div>
              </div>

              {/* Status bar */}
              <div className="status-bar">
                <div className="status-time">
                  Worked for {formatTime(elapsedTime)}
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="ml-1">
                    <path d="M4.5 3L7.5 6L4.5 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>

                <div className="sources-badge">
                  <div className="source-icons">
                    <div className="source-icon" style={{ background: '#3B82F6' }} />
                    <div className="source-icon" style={{ background: '#10B981' }} />
                    <div className="source-icon" style={{ background: '#F59E0B' }} />
                    <div className="source-icon" style={{ background: '#8B5CF6' }} />
                  </div>
                  <span>{sourceCount} sources</span>
                </div>
              </div>

              {/* Document content */}
              <EarningsReport content={rawResponse} />

              {/* Follow-up Q&A thread */}
              {followUps.map((fu, i) => (
                <div key={i} className="mt-8 pt-6 border-t border-gray-200">
                  <div className="flex justify-end mb-4">
                    <div className="query-bubble">{fu.question}</div>
                  </div>
                  <div className="prose prose-sm max-w-none">
                    {fu.isLoading && !fu.answer ? (
                      <div className="text-gray-400 animate-pulse">Thinking...</div>
                    ) : (
                      <EarningsReport content={fu.answer} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Follow-up input bar - fixed at bottom */}
      {(hasResults || followUps.length > 0) && (
        <EarningsFollowUpInput
          isAnalyzing={isAnalyzing || followUps.some(fu => fu.isLoading)}
          onSubmit={handleFollowUp}
        />
      )}

      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only" />
    </div>
  );
}

export default EarningsPage;
