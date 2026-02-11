interface CitationBadgeProps {
  id: number;
  url?: string;
  title?: string;
}

export function CitationBadge({ id, url, title }: CitationBadgeProps) {
  const badge = (
    <sup
      className="citation-badge inline-flex items-center justify-center w-4 h-4 text-[10px] font-semibold rounded-sm ml-0.5 no-underline transition-colors"
      style={{
        color: '#10B981',
        border: '1px solid #10B981',
        background: 'transparent'
      }}
    >
      {id}
    </sup>
  );

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        title={title}
        className="inline no-underline"
      >
        {badge}
      </a>
    );
  }

  return badge;
}
