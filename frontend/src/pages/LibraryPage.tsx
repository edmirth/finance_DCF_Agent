import { useState, useEffect, useCallback } from 'react';
import { Search, Download, Trash2, Tag, X, BookOpen, ChevronDown, ChevronUp } from 'lucide-react';
import { getAnalyses, getAnalysis, updateAnalysisTags, deleteAnalysis, exportAnalysis } from '../api';
import { AnalysisSummary, AnalysisDetail } from '../types';
import ReactMarkdown from 'react-markdown';

const AGENT_TYPE_LABELS: Record<string, string> = {
  dcf: 'DCF',
  analyst: 'Equity Analyst',
  earnings: 'Earnings',
  graph: 'Graph Research',
};

const AGENT_TYPE_COLORS: Record<string, string> = {
  dcf: '#3B82F6',
  analyst: '#8B5CF6',
  earnings: '#F59E0B',
  graph: '#10B981',
};

const FILTER_AGENT_TYPES = ['dcf', 'analyst', 'earnings', 'graph'];

function AgentChip({ agentType }: { agentType: string }) {
  const color = AGENT_TYPE_COLORS[agentType] || '#6B7280';
  const label = AGENT_TYPE_LABELS[agentType] || agentType;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: '9999px',
        fontSize: '0.75rem',
        fontWeight: 600,
        background: `${color}18`,
        color,
        border: `1px solid ${color}30`,
        fontFamily: 'Inter, sans-serif',
      }}
    >
      {label}
    </span>
  );
}

function TagEditor({
  tags,
  onSave,
}: {
  tags: string[];
  onSave: (tags: string[]) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [newTag, setNewTag] = useState('');
  const [localTags, setLocalTags] = useState(tags);

  const addTag = () => {
    const t = newTag.trim();
    if (t && !localTags.includes(t)) {
      const updated = [...localTags, t];
      setLocalTags(updated);
      onSave(updated);
    }
    setNewTag('');
    setEditing(false);
  };

  const removeTag = (tag: string) => {
    const updated = localTags.filter(t => t !== tag);
    setLocalTags(updated);
    onSave(updated);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-2">
      {localTags.map(tag => (
        <span
          key={tag}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            padding: '2px 8px',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            background: '#F3F4F6',
            color: '#374151',
            border: '1px solid #E5E7EB',
            fontFamily: 'Inter, sans-serif',
          }}
        >
          {tag}
          <button
            onClick={() => removeTag(tag)}
            style={{ display: 'flex', alignItems: 'center', color: '#9CA3AF', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
          >
            <X size={10} />
          </button>
        </span>
      ))}
      {editing ? (
        <input
          autoFocus
          value={newTag}
          onChange={e => setNewTag(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') addTag();
            if (e.key === 'Escape') setEditing(false);
          }}
          onBlur={addTag}
          placeholder="Add tag…"
          style={{
            fontSize: '0.75rem',
            fontFamily: 'Inter, sans-serif',
            padding: '2px 8px',
            border: '1px solid #10B981',
            borderRadius: '9999px',
            outline: 'none',
            width: '100px',
            color: '#1A1A1A',
          }}
        />
      ) : (
        <button
          onClick={() => setEditing(true)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '3px',
            padding: '2px 8px',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            background: 'none',
            color: '#10B981',
            border: '1px dashed #10B981',
            cursor: 'pointer',
            fontFamily: 'Inter, sans-serif',
          }}
        >
          <Tag size={10} /> tag
        </button>
      )}
    </div>
  );
}

function AnalysisCard({
  summary,
  onDelete,
  onTagsChange,
}: {
  summary: AnalysisSummary;
  onDelete: (id: string) => void;
  onTagsChange: (id: string, tags: string[]) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const handleExpand = async () => {
    if (!expanded && !detail) {
      setLoadingDetail(true);
      try {
        const d = await getAnalysis(summary.id);
        setDetail(d);
      } catch {
        // ignore
      }
      setLoadingDetail(false);
    }
    setExpanded(prev => !prev);
  };

  const handleExport = () => {
    const url = exportAnalysis(summary.id);
    window.open(url, '_blank');
  };

  const handleSaveTags = async (tags: string[]) => {
    try {
      await updateAnalysisTags(summary.id, tags);
      onTagsChange(summary.id, tags);
    } catch {
      // ignore
    }
  };

  const dateStr = new Date(summary.created_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E5E7EB',
        borderRadius: '12px',
        overflow: 'hidden',
        transition: 'box-shadow 0.2s',
      }}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)')}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
    >
      <div style={{ padding: '16px 20px' }}>
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              {summary.ticker && (
                <span
                  style={{
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontSize: '0.8125rem',
                    fontWeight: 700,
                    background: '#1A1A1A',
                    color: '#FFFFFF',
                    fontFamily: 'IBM Plex Mono, monospace',
                    letterSpacing: '0.02em',
                  }}
                >
                  {summary.ticker}
                </span>
              )}
              <AgentChip agentType={summary.agent_type} />
              <span
                style={{
                  fontSize: '0.75rem',
                  color: '#9CA3AF',
                  fontFamily: 'Inter, sans-serif',
                }}
              >
                {dateStr}
              </span>
            </div>
            <h3
              style={{
                fontSize: '0.9375rem',
                fontWeight: 600,
                color: '#1A1A1A',
                fontFamily: 'Inter, sans-serif',
                letterSpacing: '-0.01em',
                margin: 0,
              }}
            >
              {summary.title}
            </h3>
            {!expanded && (
              <p
                style={{
                  fontSize: '0.8125rem',
                  color: '#6B7280',
                  fontFamily: 'Inter, sans-serif',
                  lineHeight: 1.5,
                  marginTop: '6px',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                }}
              >
                {summary.content_preview}
              </p>
            )}
            <TagEditor tags={summary.tags} onSave={handleSaveTags} />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              onClick={handleExport}
              title="Export as .md"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                border: '1px solid #E5E7EB',
                background: '#F9FAFB',
                color: '#6B7280',
                cursor: 'pointer',
              }}
            >
              <Download size={14} />
            </button>
            <button
              onClick={() => onDelete(summary.id)}
              title="Delete"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                border: '1px solid #FEE2E2',
                background: '#FFF5F5',
                color: '#EF4444',
                cursor: 'pointer',
              }}
            >
              <Trash2 size={14} />
            </button>
            <button
              onClick={handleExpand}
              title={expanded ? 'Collapse' : 'Expand'}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                border: '1px solid #E5E7EB',
                background: '#F9FAFB',
                color: '#6B7280',
                cursor: 'pointer',
              }}
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div
          style={{
            borderTop: '1px solid #F3F4F6',
            padding: '20px',
            background: '#FAFAFA',
          }}
        >
          {loadingDetail ? (
            <p style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif', fontSize: '0.875rem' }}>
              Loading…
            </p>
          ) : detail ? (
            <div
              className="prose prose-sm max-w-none"
              style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.875rem', color: '#374151' }}
            >
              <ReactMarkdown>{detail.content}</ReactMarkdown>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function LibraryPage() {
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeAgentFilter, setActiveAgentFilter] = useState<string | null>(null);
  const [activeTagFilter, setActiveTagFilter] = useState<string | null>(null);

  const loadAnalyses = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (searchQuery) params.q = searchQuery;
      if (activeAgentFilter) params.agent_type = activeAgentFilter;
      if (activeTagFilter) params.tag = activeTagFilter;
      const data = await getAnalyses(params);
      setAnalyses(data);
    } catch {
      // ignore
    }
    setLoading(false);
  }, [searchQuery, activeAgentFilter, activeTagFilter]);

  useEffect(() => {
    loadAnalyses();
  }, [loadAnalyses]);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => loadAnalyses(), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this analysis?')) return;
    try {
      await deleteAnalysis(id);
      setAnalyses(prev => prev.filter(a => a.id !== id));
    } catch {
      // ignore
    }
  };

  const handleTagsChange = (id: string, tags: string[]) => {
    setAnalyses(prev => prev.map(a => (a.id === id ? { ...a, tags } : a)));
  };

  // Collect all unique tags for filter
  const allTags = Array.from(new Set(analyses.flatMap(a => a.tags)));

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#FAFAFA',
        paddingLeft: '80px', // sidebar offset
      }}
    >
      <div style={{ maxWidth: '800px', margin: '0 auto', padding: '40px 24px' }}>
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: '#1A1A1A',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <BookOpen size={18} color="#FFFFFF" />
          </div>
          <div>
            <h1
              style={{
                fontSize: '1.25rem',
                fontWeight: 700,
                color: '#1A1A1A',
                fontFamily: 'Inter, sans-serif',
                letterSpacing: '-0.02em',
                margin: 0,
              }}
            >
              Research Library
            </h1>
            <p
              style={{
                fontSize: '0.8125rem',
                color: '#9CA3AF',
                fontFamily: 'Inter, sans-serif',
                margin: 0,
              }}
            >
              {analyses.length} saved {analyses.length === 1 ? 'analysis' : 'analyses'}
            </p>
          </div>
        </div>

        {/* Search */}
        <div
          style={{
            position: 'relative',
            marginBottom: '16px',
          }}
        >
          <Search
            size={16}
            style={{
              position: 'absolute',
              left: '12px',
              top: '50%',
              transform: 'translateY(-50%)',
              color: '#9CA3AF',
            }}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search by ticker, keyword, or content…"
            style={{
              width: '100%',
              padding: '10px 12px 10px 38px',
              border: '1px solid #E5E7EB',
              borderRadius: '10px',
              background: '#FFFFFF',
              fontSize: '0.875rem',
              fontFamily: 'Inter, sans-serif',
              color: '#1A1A1A',
              outline: 'none',
              boxSizing: 'border-box',
            }}
            onFocus={e => (e.target.style.borderColor = '#10B981')}
            onBlur={e => (e.target.style.borderColor = '#E5E7EB')}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={{
                position: 'absolute',
                right: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: '#9CA3AF',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2 mb-6">
          {/* Agent type filters */}
          {FILTER_AGENT_TYPES.map(type => (
            <button
              key={type}
              onClick={() => setActiveAgentFilter(activeAgentFilter === type ? null : type)}
              style={{
                padding: '4px 12px',
                borderRadius: '9999px',
                fontSize: '0.8125rem',
                fontWeight: 500,
                fontFamily: 'Inter, sans-serif',
                cursor: 'pointer',
                border: '1px solid',
                borderColor: activeAgentFilter === type ? AGENT_TYPE_COLORS[type] : '#E5E7EB',
                background: activeAgentFilter === type ? `${AGENT_TYPE_COLORS[type]}12` : '#FFFFFF',
                color: activeAgentFilter === type ? AGENT_TYPE_COLORS[type] : '#6B7280',
                transition: 'all 0.15s',
              }}
            >
              {AGENT_TYPE_LABELS[type]}
            </button>
          ))}

          {/* Tag filters */}
          {allTags.map(tag => (
            <button
              key={tag}
              onClick={() => setActiveTagFilter(activeTagFilter === tag ? null : tag)}
              style={{
                padding: '4px 12px',
                borderRadius: '9999px',
                fontSize: '0.8125rem',
                fontWeight: 500,
                fontFamily: 'Inter, sans-serif',
                cursor: 'pointer',
                border: '1px solid',
                borderColor: activeTagFilter === tag ? '#10B981' : '#E5E7EB',
                background: activeTagFilter === tag ? '#10B98112' : '#FFFFFF',
                color: activeTagFilter === tag ? '#10B981' : '#6B7280',
                transition: 'all 0.15s',
              }}
            >
              # {tag}
            </button>
          ))}
        </div>

        {/* Content */}
        {loading ? (
          <div className="text-center py-16">
            <p style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif', fontSize: '0.875rem' }}>
              Loading…
            </p>
          </div>
        ) : analyses.length === 0 ? (
          <div
            className="text-center py-16"
            style={{
              border: '1px dashed #E5E7EB',
              borderRadius: '12px',
              background: '#FFFFFF',
            }}
          >
            <BookOpen size={32} style={{ color: '#D1D5DB', margin: '0 auto 12px' }} />
            <p
              style={{
                fontSize: '0.9375rem',
                fontWeight: 600,
                color: '#374151',
                fontFamily: 'Inter, sans-serif',
                marginBottom: '6px',
              }}
            >
              {searchQuery || activeAgentFilter || activeTagFilter
                ? 'No matching analyses'
                : 'No saved analyses yet'}
            </p>
            <p
              style={{
                fontSize: '0.8125rem',
                color: '#9CA3AF',
                fontFamily: 'Inter, sans-serif',
              }}
            >
              {searchQuery || activeAgentFilter || activeTagFilter
                ? 'Try adjusting your filters'
                : 'Run a DCF, Equity Analyst, or Earnings analysis to get started'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {analyses.map(analysis => (
              <AnalysisCard
                key={analysis.id}
                summary={analysis}
                onDelete={handleDelete}
                onTagsChange={handleTagsChange}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
