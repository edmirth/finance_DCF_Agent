interface EarningsLoadingStateProps {
  elapsedTime: string;
  sourceCount: number;
}

export default function EarningsLoadingState({ elapsedTime, sourceCount }: EarningsLoadingStateProps) {
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

      {/* Skeleton content blocks */}
      <div className="mt-6 space-y-6">
        {/* Title skeleton */}
        <div className="space-y-3">
          <div className="h-7 bg-[#F3F4F6] rounded-md w-3/4 animate-pulse" />
          <div className="h-4 bg-[#F3F4F6] rounded w-1/2 animate-pulse" style={{ animationDelay: '0.1s' }} />
        </div>

        {/* Paragraph skeleton */}
        <div className="space-y-2.5">
          <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.2s' }} />
          <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.25s' }} />
          <div className="h-4 bg-[#F3F4F6] rounded w-5/6 animate-pulse" style={{ animationDelay: '0.3s' }} />
        </div>

        {/* Divider */}
        <hr className="section-divider" />

        {/* Section heading skeleton */}
        <div className="h-5 bg-[#F3F4F6] rounded w-2/5 animate-pulse" style={{ animationDelay: '0.35s' }} />

        {/* More paragraph skeleton */}
        <div className="space-y-2.5">
          <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.4s' }} />
          <div className="h-4 bg-[#F3F4F6] rounded w-full animate-pulse" style={{ animationDelay: '0.45s' }} />
          <div className="h-4 bg-[#F3F4F6] rounded w-3/4 animate-pulse" style={{ animationDelay: '0.5s' }} />
        </div>

        {/* Table skeleton */}
        <div className="mt-6 space-y-3">
          <div className="flex gap-8">
            <div className="h-4 bg-[#F3F4F6] rounded w-24 animate-pulse" style={{ animationDelay: '0.55s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-20 animate-pulse" style={{ animationDelay: '0.6s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-28 animate-pulse" style={{ animationDelay: '0.65s' }} />
            <div className="h-4 bg-[#F3F4F6] rounded w-20 animate-pulse" style={{ animationDelay: '0.7s' }} />
          </div>
          <hr className="border-[#F3F4F6]" />
          {[1, 2, 3].map(i => (
            <div key={i} className="flex gap-8">
              <div className="h-4 bg-[#F9FAFB] rounded w-24 animate-pulse" style={{ animationDelay: `${0.7 + i * 0.1}s` }} />
              <div className="h-4 bg-[#F9FAFB] rounded w-20 animate-pulse" style={{ animationDelay: `${0.75 + i * 0.1}s` }} />
              <div className="h-4 bg-[#F9FAFB] rounded w-28 animate-pulse" style={{ animationDelay: `${0.8 + i * 0.1}s` }} />
              <div className="h-4 bg-[#F9FAFB] rounded w-20 animate-pulse" style={{ animationDelay: `${0.85 + i * 0.1}s` }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
