import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle, Loader2, ChevronDown, ChevronUp, Filter, XCircle } from 'lucide-react';
import { getInbox } from '../api';
import { AgentRun, AlertLevel } from '../types';

type InboxItem = AgentRun & { agent_name: string };

const ALERT_CONFIG: Record<AlertLevel, { label: string; color: string; bg: string; Icon: any }> = {
  high:   { label: 'Alert',     color: '#EF4444', bg: '#FEE2E2', Icon: AlertTriangle },
  medium: { label: 'Watch',     color: '#F59E0B', bg: '#FEF3C7', Icon: AlertTriangle },
  low:    { label: 'Update',    color: '#10B981', bg: '#D1FAE5', Icon: CheckCircle   },
  none:   { label: 'No change', color: '#9CA3AF', bg: '#F1F5F9', Icon: CheckCircle   },
};

const FILTERS: { id: string; label: string }[] = [
  { id: '',       label: 'All' },
  { id: 'high',   label: 'Alerts' },
  { id: 'medium', label: 'Watch' },
  { id: 'low',    label: 'Updates' },
];

function formatDate(iso?: string): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function markdownToHtml(md: string): string {
  return md
    .replace(/^### (.+)$/gm, '<h3 style="font-size:13px;font-weight:700;color:#0F172A;margin:14px 0 5px">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:14px;font-weight:700;color:#0F172A;margin:18px 0 7px">$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li style="margin-bottom:4px">$1</li>')
    .replace(/(<li.*<\/li>\n?)+/g, s => `<ul style="padding-left:18px;margin:6px 0">${s}</ul>`)
    .replace(/\n\n/g, '</p><p style="margin:8px 0">')
    .replace(/\n/g, '<br>');
}

function InboxCard({ item }: { item: InboxItem }) {
  const [expanded, setExpanded] = useState(false);

  // Running state — show a minimal spinner card, not expandable yet
  if (item.status === 'running') {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4 flex items-center gap-4">
        <div className="w-8 h-8 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
          <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-semibold text-slate-900">{item.agent_name}</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-blue-50 text-blue-600">Running</span>
          </div>
          <p className="text-xs text-slate-400">Started {formatDate(item.started_at)}</p>
        </div>
      </div>
    );
  }

  // Failed state
  if (item.status === 'failed') {
    return (
      <div className="bg-white border border-red-100 rounded-2xl px-5 py-4 flex items-center gap-4">
        <div className="w-8 h-8 rounded-xl bg-red-50 flex items-center justify-center flex-shrink-0">
          <XCircle className="w-4 h-4 text-red-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-semibold text-slate-900">{item.agent_name}</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-red-50 text-red-500">Failed</span>
          </div>
          <p className="text-xs text-slate-400 truncate">{item.error || 'Run failed — no details available.'}</p>
        </div>
      </div>
    );
  }

  // Completed state
  const alert = ALERT_CONFIG[item.alert_level as AlertLevel] || ALERT_CONFIG.none;
  const { Icon } = alert;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden hover:border-slate-300 transition-colors duration-150">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-start gap-4 px-5 py-4 text-left"
      >
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: alert.bg }}
        >
          <Icon className="w-4 h-4" style={{ color: alert.color }} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-sm font-semibold text-slate-900 truncate">{item.agent_name}</span>
            <span
              className="text-xs font-semibold px-2 py-0.5 rounded-lg flex-shrink-0"
              style={{ background: alert.bg, color: alert.color }}
            >
              {alert.label}
            </span>
            {item.material_change && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-amber-50 text-amber-700 flex-shrink-0">
                Material change
              </span>
            )}
          </div>

          <p className="text-sm text-slate-600 leading-relaxed line-clamp-2">
            {item.findings_summary || 'No summary available.'}
          </p>

          {/* Key findings preview */}
          {!expanded && item.key_findings?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {item.key_findings.slice(0, 2).map((f, i) => (
                <span key={i} className="text-xs px-2 py-0.5 bg-slate-50 border border-slate-200 text-slate-500 rounded-lg">
                  {f.length > 60 ? f.slice(0, 60) + '…' : f}
                </span>
              ))}
              {item.key_findings.length > 2 && (
                <span className="text-xs text-slate-400">+{item.key_findings.length - 2} more</span>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
            {item.tickers_analyzed?.length > 0 && (
              <span className="font-medium text-slate-500">{item.tickers_analyzed.join(' · ')}</span>
            )}
            <span>{formatDate(item.started_at)}</span>
          </div>
        </div>

        <div className="flex-shrink-0 mt-1">
          {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-slate-100">
          {/* All key findings */}
          {item.key_findings?.length > 0 && (
            <div className="pt-4 mb-4">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Key findings</p>
              <ul className="space-y-1.5">
                {item.key_findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="text-emerald-500 mt-0.5 flex-shrink-0">·</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* Full report */}
          {item.report && (
            <div
              className="text-slate-700 leading-relaxed border-t border-slate-100 pt-4"
              style={{ fontSize: '13px', lineHeight: '1.65' }}
              dangerouslySetInnerHTML={{ __html: markdownToHtml(item.report) }}
            />
          )}
        </div>
      )}
    </div>
  );
}

function groupByDate(items: InboxItem[]): Record<string, InboxItem[]> {
  const groups: Record<string, InboxItem[]> = {};
  for (const item of items) {
    const date = new Date(item.started_at).toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric',
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(item);
  }
  return groups;
}

export default function InboxPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');

  useEffect(() => { load(); }, [filter]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getInbox(50, filter || undefined);
      setItems(data);
    } catch (e: any) {
      setError('Could not load inbox. Check that the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const grouped = groupByDate(items);

  return (
    <div className="min-h-screen bg-slate-50" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="mx-auto w-full max-w-3xl px-6 py-12 lg:px-10">

        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 mb-1" style={{ letterSpacing: '-0.03em' }}>Inbox</h1>
            <p className="text-slate-500 text-sm">All research findings from your agents</p>
          </div>
          <button
            onClick={() => navigate('/')}
            className="text-sm text-emerald-600 hover:text-emerald-700 font-medium transition-colors duration-150"
          >
            View dashboard →
          </button>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2 mb-6">
          <Filter className="w-4 h-4 text-slate-400" />
          {FILTERS.map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-xl transition-colors duration-150 ${
                filter === f.id
                  ? 'bg-slate-900 text-white'
                  : 'bg-white border border-slate-200 text-slate-600 hover:border-slate-300'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <XCircle className="w-8 h-8 text-red-300 mb-3" />
            <p className="text-slate-500 text-sm">{error}</p>
            <button onClick={load} className="mt-3 text-sm text-emerald-600 hover:text-emerald-700 font-medium">Retry</button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mb-4">
              <CheckCircle className="w-7 h-7 text-slate-300" />
            </div>
            <p className="text-slate-500 text-sm">No reports yet.</p>
            <button onClick={() => navigate('/issues?new=1')} className="mt-4 text-sm text-emerald-600 hover:text-emerald-700 font-medium">
              Open a new issue →
            </button>
          </div>
        ) : (
          <div className="space-y-8">
            {Object.entries(grouped).map(([date, dateItems]) => (
              <div key={date}>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">{date}</p>
                <div className="space-y-3">
                  {dateItems.map(item => <InboxCard key={item.id} item={item} />)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
