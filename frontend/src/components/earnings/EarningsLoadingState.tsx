import { motion } from 'framer-motion';
import type { ProgressStep } from '../../pages/EarningsPage';

// Parallel nodes are indented to signal concurrency
const PARALLEL_NODES = new Set([
  'fetch_earnings_history',
  'fetch_analyst_estimates',
  'fetch_guidance_and_news',
]);

interface EarningsLoadingStateProps {
  elapsedTime: string;
  sourceCount: number;
  progressSteps?: ProgressStep[];
}

function StepIcon({ status }: { status: ProgressStep['status'] }) {
  if (status === 'completed') {
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="flex-shrink-0">
        <circle cx="9" cy="9" r="9" fill="#10B981" />
        <path d="M5.5 9.5L7.5 11.5L12.5 6.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (status === 'active') {
    return (
      <div className="flex-shrink-0 w-[18px] h-[18px] relative">
        <svg width="18" height="18" viewBox="0 0 18 18" className="animate-spin">
          <circle cx="9" cy="9" r="7.5" stroke="#E5E7EB" strokeWidth="2" fill="none" />
          <path d="M9 1.5A7.5 7.5 0 0 1 16.5 9" stroke="#10B981" strokeWidth="2" strokeLinecap="round" fill="none" />
        </svg>
      </div>
    );
  }
  // pending
  return (
    <div className="flex-shrink-0 w-[18px] h-[18px] flex items-center justify-center">
      <div className="w-2 h-2 rounded-full bg-[#D1D5DB]" />
    </div>
  );
}

export default function EarningsLoadingState({ elapsedTime, sourceCount, progressSteps = [] }: EarningsLoadingStateProps) {
  const hasSteps = progressSteps.length > 0;
  const allDone = hasSteps && progressSteps.every(s => s.status === 'completed');

  return (
    <div className="animate-fade-in">
      {/* Status bar */}
      <div className="status-bar">
        <div className="status-time">
          <span>Working</span>
          <span className="ml-1 flex gap-1">
            <span className="loading-dot" />
            <span className="loading-dot" />
            <span className="loading-dot" />
          </span>
          <span className="ml-2 text-[#9CA3AF]">{elapsedTime}</span>
        </div>

        {sourceCount > 0 && (
          <div className="sources-badge">
            <div className="source-icons">
              <div className="source-icon" style={{ background: '#3B82F6' }} />
              <div className="source-icon" style={{ background: '#10B981' }} />
              {sourceCount > 2 && <div className="source-icon" style={{ background: '#F59E0B' }} />}
            </div>
            <span>{sourceCount} sources</span>
          </div>
        )}
      </div>

      {/* Progress timeline */}
      {hasSteps && (
        <div className="mt-5 space-y-0.5">
          {progressSteps.map((step) => {
            const isParallel = PARALLEL_NODES.has(step.node);
            return (
              <motion.div
                key={step.node}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className={`flex items-start gap-2.5 py-1.5 ${isParallel ? 'pl-6' : ''}`}
              >
                <div className="mt-px">
                  <StepIcon status={step.status} />
                </div>
                <div className="flex-1 min-w-0">
                  <span
                    className={`text-sm leading-5 ${
                      step.status === 'completed'
                        ? 'text-[#6B7280]'
                        : step.status === 'active'
                        ? 'text-[#1A1A1A] font-medium'
                        : 'text-[#9CA3AF]'
                    }`}
                  >
                    {step.label}
                  </span>
                  {step.detail && (
                    <span className="text-sm text-[#9CA3AF] ml-1.5">
                      &mdash; {step.detail}
                    </span>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Reduced skeleton (fades out once all steps complete) */}
      {!allDone && (
        <div className={`mt-6 space-y-6 ${hasSteps ? 'opacity-30' : ''}`}>
          <div className="space-y-3">
            <div className="h-7 bg-[#F3F4F6] rounded-md w-3/4 animate-pulse" />
            <div className="h-4 bg-[#F3F4F6] rounded w-1/2 animate-pulse" style={{ animationDelay: '0.1s' }} />
          </div>
          <div className="space-y-2.5">
            <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.2s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.25s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-5/6 animate-pulse" style={{ animationDelay: '0.3s' }} />
          </div>
          <hr className="section-divider" />
          <div className="h-5 bg-[#F3F4F6] rounded w-2/5 animate-pulse" style={{ animationDelay: '0.35s' }} />
          <div className="space-y-2.5">
            <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.4s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.45s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-3/4 animate-pulse" style={{ animationDelay: '0.5s' }} />
          </div>
        </div>
      )}
    </div>
  );
}
