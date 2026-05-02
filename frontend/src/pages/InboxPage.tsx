import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Search,
  UserPlus,
  XCircle,
} from 'lucide-react';
import {
  approveHireProposal,
  getInbox,
  rejectHireProposal,
  triggerAgentRun,
} from '../api';
import type { AgentRunInboxItem, HireProposalInboxItem, InboxItem, TaskInboxItem } from '../types';

type InboxTab = 'mine' | 'recent' | 'unread' | 'all';

const TAB_LABELS: Array<{ id: InboxTab; label: string }> = [
  { id: 'mine', label: 'Mine' },
  { id: 'recent', label: 'Recent' },
  { id: 'unread', label: 'Unread' },
  { id: 'all', label: 'All' },
];

const READ_STATE_KEY = 'finance.inbox.read-state';

function itemKey(item: InboxItem): string {
  return `${item.item_type}:${item.id}`;
}

function itemTimestamp(item: InboxItem): string | null {
  return item.timestamp;
}

function formatRelativeTime(iso?: string | null): string {
  if (!iso) return 'Just now';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function isUnread(item: InboxItem, readState: Record<string, string>): boolean {
  const key = itemKey(item);
  const seenAt = readState[key];
  const ts = itemTimestamp(item);
  if (!ts) return !seenAt;
  if (!seenAt) return true;
  return new Date(ts).getTime() > new Date(seenAt).getTime();
}

function toneClasses(feedType: InboxItem['feed_type']) {
  switch (feedType) {
    case 'failure':
      return {
        dot: 'bg-red-500',
        badge: 'bg-red-50 text-red-700 border-red-200',
        Icon: XCircle,
        iconColor: 'text-red-400',
      };
    case 'approval':
      return {
        dot: 'bg-amber-400',
        badge: 'bg-amber-50 text-amber-700 border-amber-200',
        Icon: UserPlus,
        iconColor: 'text-amber-300',
      };
    case 'deliverable':
      return {
        dot: 'bg-emerald-400',
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        Icon: CheckCircle2,
        iconColor: 'text-emerald-400',
      };
    default:
      return {
        dot: 'bg-violet-400',
        badge: 'bg-violet-50 text-violet-700 border-violet-200',
        Icon: AlertTriangle,
        iconColor: 'text-violet-500',
      };
  }
}

function feedTypeLabel(item: InboxItem): string {
  switch (item.feed_type) {
    case 'failure':
      return 'failed';
    case 'approval':
      return 'approval';
    case 'deliverable':
      return 'ready';
    default:
      return 'update';
  }
}

function loadReadState(): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(READ_STATE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveReadState(state: Record<string, string>) {
  try {
    window.localStorage.setItem(READ_STATE_KEY, JSON.stringify(state));
  } catch {
    // Ignore local persistence failures.
  }
}

function sectioned(items: InboxItem[]) {
  const recent: InboxItem[] = [];
  const earlier: InboxItem[] = [];
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  for (const item of items) {
    const ts = itemTimestamp(item);
    if (ts && new Date(ts).getTime() < cutoff) {
      earlier.push(item);
    } else {
      recent.push(item);
    }
  }
  return { recent, earlier };
}

function AgentRunRow({
  item,
  unread,
  onRetry,
  onMarkRead,
}: {
  item: AgentRunInboxItem;
  unread: boolean;
  onRetry: (item: AgentRunInboxItem) => Promise<void>;
  onMarkRead: (item: InboxItem) => void;
}) {
  const tone = toneClasses(item.feed_type);
  const { Icon } = tone;

  return (
    <div
      className={`group flex items-center gap-3 border-b border-slate-100 px-4 py-3 transition hover:bg-slate-50 ${unread ? 'bg-blue-50/40' : ''}`}
      onClick={() => onMarkRead(item)}
    >
      <div className={`h-3 w-3 flex-shrink-0 rounded-full ${unread ? 'bg-blue-500' : 'bg-transparent'}`} />
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100">
        {item.status === 'running' ? <Loader2 className="h-4 w-4 animate-spin text-blue-400" /> : <Icon className={`h-4 w-4 ${tone.iconColor}`} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <p className="truncate text-[15px] font-semibold text-slate-900">{item.title}</p>
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${tone.badge}`}>
            {feedTypeLabel(item)}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-[13px] text-slate-500">
          <span className="truncate">{item.summary}</span>
          <span className="shrink-0">{formatRelativeTime(item.timestamp)}</span>
        </div>
      </div>
      <div className="flex flex-shrink-0 items-center gap-2">
        {item.status === 'failed' && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onRetry(item);
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        )}
        <span className="text-[13px] text-slate-400">{formatRelativeTime(item.timestamp)}</span>
      </div>
    </div>
  );
}

function HireProposalRow({
  item,
  unread,
  onApprove,
  onReject,
  onOpenIssue,
  onMarkRead,
}: {
  item: HireProposalInboxItem;
  unread: boolean;
  onApprove: (item: HireProposalInboxItem) => Promise<void>;
  onReject: (item: HireProposalInboxItem) => Promise<void>;
  onOpenIssue: (taskId: string) => void;
  onMarkRead: (item: InboxItem) => void;
}) {
  const tone = toneClasses(item.feed_type);
  const { Icon } = tone;

  return (
    <div
      className={`group flex items-start gap-3 border-b border-slate-100 px-4 py-3 transition hover:bg-slate-50 ${unread ? 'bg-blue-50/40' : ''}`}
      onClick={() => onMarkRead(item)}
    >
      <div className={`mt-3.5 h-3 w-3 flex-shrink-0 rounded-full ${unread ? 'bg-blue-500' : 'bg-transparent'}`} />
      <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100">
        <Icon className={`h-4 w-4 ${tone.iconColor}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <p className="truncate text-[15px] font-semibold text-slate-900">{item.title}</p>
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${tone.badge}`}>
            approval
          </span>
        </div>
        <p className="mt-0.5 text-[13px] text-slate-600">{item.summary}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          {item.source_task_title && <span>{item.source_task_title}</span>}
          {item.reports_to_label && <span>Reports to {item.reports_to_label}</span>}
          {item.tickers.map((ticker) => (
            <span key={ticker} className="rounded-full border border-slate-200 px-2 py-0.5 text-slate-500">
              {ticker}
            </span>
          ))}
        </div>
      </div>
      <div className="flex flex-shrink-0 items-center gap-2">
        {item.source_task_id && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenIssue(item.source_task_id!);
            }}
            className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
          >
            Open issue
          </button>
        )}
        <button
          type="button"
            onClick={(event) => {
              event.stopPropagation();
              onReject(item);
            }}
            className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
          >
            Decline
          </button>
        <button
          type="button"
            onClick={(event) => {
              event.stopPropagation();
              onApprove(item);
            }}
            className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[13px] font-semibold text-emerald-700 transition hover:bg-emerald-100"
          >
            Approve
          </button>
      </div>
    </div>
  );
}

function TaskMessageRow({
  item,
  unread,
  onOpenIssue,
  onMarkRead,
}: {
  item: TaskInboxItem;
  unread: boolean;
  onOpenIssue: (taskId: string) => void;
  onMarkRead: (item: InboxItem) => void;
}) {
  const tone = toneClasses(item.feed_type);
  const { Icon } = tone;

  return (
    <button
      type="button"
      onClick={() => {
        onMarkRead(item);
        onOpenIssue(item.task_id);
      }}
      className={`group flex w-full items-center gap-3 border-b border-slate-100 px-4 py-3 text-left transition hover:bg-slate-50 ${unread ? 'bg-blue-50/40' : ''}`}
    >
      <div className={`h-3 w-3 flex-shrink-0 rounded-full ${unread ? 'bg-blue-500' : 'bg-transparent'}`} />
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100">
        <Icon className={`h-4 w-4 ${tone.iconColor}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <p className="truncate text-[15px] font-semibold text-slate-900">{item.task_title}</p>
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${tone.badge}`}>
            {item.feed_type === 'deliverable' ? 'document' : 'issue update'}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-[13px] text-slate-500">
          <span className="truncate">{item.author_label}</span>
          <span className="truncate text-slate-500">{item.summary}</span>
        </div>
      </div>
      <span className="flex-shrink-0 text-[13px] text-slate-400">{formatRelativeTime(item.timestamp)}</span>
    </button>
  );
}

export default function InboxPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<InboxTab>('mine');
  const [query, setQuery] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [readState, setReadState] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getInbox(80);
      setItems(data);
    } catch {
      setError('Could not load inbox.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setReadState(loadReadState());
    load();
  }, []);

  const markRead = (item: InboxItem) => {
    const next = { ...readState, [itemKey(item)]: new Date().toISOString() };
    setReadState(next);
    saveReadState(next);
  };

  const visibleItems = useMemo(() => {
    const lower = query.trim().toLowerCase();
    const base = items.filter((item) => {
      const title = 'title' in item ? item.title : '';
      const summary = 'summary' in item ? item.summary : '';
      const haystack = `${title} ${summary}`.toLowerCase();
      if (lower && !haystack.includes(lower)) return false;

      if (activeTab === 'unread') return isUnread(item, readState);
      if (activeTab === 'recent') {
        const ts = itemTimestamp(item);
        return ts ? Date.now() - new Date(ts).getTime() < 7 * 24 * 60 * 60 * 1000 : true;
      }
      if (activeTab === 'mine') {
        return item.requires_action || item.item_type === 'task_message';
      }
      return true;
    });

    return base.sort((a, b) => {
      const aTs = itemTimestamp(a) || '';
      const bTs = itemTimestamp(b) || '';
      return bTs.localeCompare(aTs);
    });
  }, [activeTab, items, query, readState]);

  const { recent, earlier } = useMemo(() => sectioned(visibleItems), [visibleItems]);

  const handleRetry = async (item: AgentRunInboxItem) => {
    setBusyKey(itemKey(item));
    try {
      await triggerAgentRun(item.scheduled_agent_id);
      markRead(item);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const handleApprove = async (item: HireProposalInboxItem) => {
    setBusyKey(itemKey(item));
    try {
      await approveHireProposal(item.id);
      markRead(item);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const handleReject = async (item: HireProposalInboxItem) => {
    setBusyKey(itemKey(item));
    try {
      await rejectHireProposal(item.id);
      markRead(item);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const renderItem = (item: InboxItem) => {
    const unread = isUnread(item, readState);
    const key = itemKey(item);
    const disabled = busyKey === key;

    if (item.item_type === 'hire_proposal') {
      return (
        <div key={key} className={disabled ? 'pointer-events-none opacity-70' : ''}>
          <HireProposalRow
            item={item}
            unread={unread}
            onApprove={handleApprove}
            onReject={handleReject}
            onOpenIssue={(taskId) => {
              markRead(item);
              navigate(`/issues/${taskId}`);
            }}
            onMarkRead={markRead}
          />
        </div>
      );
    }

    if (item.item_type === 'task_message') {
      return (
        <TaskMessageRow
          key={key}
          item={item}
          unread={unread}
          onOpenIssue={(taskId) => navigate(`/issues/${taskId}`)}
          onMarkRead={markRead}
        />
      );
    }

    return (
      <div key={key} className={disabled ? 'pointer-events-none opacity-70' : ''}>
        <AgentRunRow item={item} unread={unread} onRetry={handleRetry} onMarkRead={markRead} />
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-[28px] font-semibold tracking-[-0.03em] text-slate-900">Inbox</h1>
      </div>

      <div className="px-6 py-6">
        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-6 border-b border-slate-200">
            {TAB_LABELS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`border-b-2 px-1 pb-2.5 text-[16px] font-medium transition ${
                  activeTab === tab.id
                    ? 'border-slate-900 text-slate-900'
                    : 'border-transparent text-slate-400 hover:text-slate-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <div className="flex w-full min-w-[300px] items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-2.5 lg:w-[340px]">
              <Search className="h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search inbox..."
                className="w-full bg-transparent text-[15px] text-slate-900 outline-none placeholder:text-slate-400"
              />
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-[20px] border border-slate-200 bg-white shadow-sm">
          {loading ? (
            <div className="flex items-center justify-center px-6 py-16">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : error ? (
            <div className="px-6 py-10 text-center text-sm text-red-600">{error}</div>
          ) : visibleItems.length === 0 ? (
            <div className="px-6 py-12 text-center text-sm text-slate-500">No inbox items.</div>
          ) : (
            <>
              {recent.length > 0 && recent.map(renderItem)}
              {earlier.length > 0 && (
                <>
                  <div className="flex items-center justify-end border-y border-slate-100 px-6 py-2.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                    Earlier
                  </div>
                  {earlier.map(renderItem)}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
