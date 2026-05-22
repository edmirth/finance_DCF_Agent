import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  FileText,
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
import type { AgentRunInboxItem, HireProposalInboxItem, InboxItem } from '../types';
import { formatRelativeApiTime, isApiDateAfter, parseApiDate } from '../utils/time';

type InboxTab = 'mine' | 'recent' | 'unread' | 'all';
type InboxFilter = 'all' | 'unread' | 'failure' | 'approval' | 'issue_update' | 'deliverable';

type InboxGroup = {
  key: string;
  taskId: string | null;
  taskTitle: string;
  items: InboxItem[];
  latestTimestamp: string | null;
  latestItem: InboxItem;
  unread: boolean;
  requiresAction: boolean;
  approvals: HireProposalInboxItem[];
  failures: AgentRunInboxItem[];
  deliverables: InboxItem[];
  updates: InboxItem[];
};

const TAB_LABELS: Array<{ id: InboxTab; label: string }> = [
  { id: 'recent', label: 'Recent' },
  { id: 'mine', label: 'Mine' },
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

function isUnread(item: InboxItem, readState: Record<string, string>): boolean {
  const key = itemKey(item);
  const seenAt = readState[key];
  const ts = itemTimestamp(item);
  if (!ts) return !seenAt;
  if (!seenAt) return true;
  return isApiDateAfter(ts, seenAt);
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

function toneClasses(feedType: InboxItem['feed_type']) {
  switch (feedType) {
    case 'failure':
      return {
        badge: 'bg-red-50 text-red-700 border-red-200',
        rail: 'border-l-red-400',
        accent: 'bg-red-500',
        soft: 'bg-red-50',
        Icon: XCircle,
        iconClass: 'text-red-500',
      };
    case 'approval':
      return {
        badge: 'bg-amber-50 text-amber-700 border-amber-200',
        rail: 'border-l-amber-400',
        accent: 'bg-amber-500',
        soft: 'bg-amber-50',
        Icon: UserPlus,
        iconClass: 'text-amber-500',
      };
    case 'deliverable':
      return {
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        rail: 'border-l-emerald-400',
        accent: 'bg-emerald-500',
        soft: 'bg-emerald-50',
        Icon: CheckCircle2,
        iconClass: 'text-emerald-500',
      };
    default:
      return {
        badge: 'bg-violet-50 text-violet-700 border-violet-200',
        rail: 'border-l-violet-400',
        accent: 'bg-violet-500',
        soft: 'bg-violet-50',
        Icon: AlertTriangle,
        iconClass: 'text-violet-500',
      };
  }
}

function feedTypeLabel(feedType: InboxItem['feed_type']): string {
  switch (feedType) {
    case 'failure':
      return 'Failure';
    case 'approval':
      return 'Approval';
    case 'deliverable':
      return 'Deliverable';
    default:
      return 'Update';
  }
}

function itemHeadline(item: InboxItem): string {
  if (item.item_type === 'task_message') return item.task_title;
  if (item.item_type === 'hire_proposal') return item.role_title || item.title;
  return item.task_title || item.title;
}

function itemActor(item: InboxItem): string {
  if (item.item_type === 'task_message') return item.author_label;
  if (item.item_type === 'hire_proposal') return 'CEO';
  return item.agent_name || 'Agent';
}

function itemSummary(item: InboxItem): string {
  return item.summary.replace(/\s+/g, ' ').trim();
}

function itemTaskId(item: InboxItem): string | null {
  if (item.item_type === 'task_message') return item.task_id;
  if (item.item_type === 'hire_proposal') return item.source_task_id ?? null;
  return item.task_id ?? null;
}

function itemTaskTitle(item: InboxItem): string {
  if (item.item_type === 'task_message') return item.task_title;
  if (item.item_type === 'hire_proposal') return item.source_task_title || item.role_title || item.title;
  return item.task_title || item.title;
}

function groupItems(items: InboxItem[], readState: Record<string, string>): InboxGroup[] {
  const groups = new Map<string, InboxGroup>();

  for (const item of items) {
    const taskId = itemTaskId(item);
    const key = taskId ? `task:${taskId}` : itemKey(item);
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(item);
      if (
        (itemTimestamp(item) || '') > (existing.latestTimestamp || '')
      ) {
        existing.latestTimestamp = itemTimestamp(item);
        existing.latestItem = item;
        existing.taskTitle = itemTaskTitle(item);
      }
      existing.unread = existing.unread || isUnread(item, readState);
      existing.requiresAction = existing.requiresAction || item.requires_action;
    } else {
      groups.set(key, {
        key,
        taskId,
        taskTitle: itemTaskTitle(item),
        items: [item],
        latestTimestamp: itemTimestamp(item),
        latestItem: item,
        unread: isUnread(item, readState),
        requiresAction: item.requires_action,
        approvals: [],
        failures: [],
        deliverables: [],
        updates: [],
      });
    }
  }

  return Array.from(groups.values())
    .map((group) => {
      group.items.sort((a, b) => (itemTimestamp(b) || '').localeCompare(itemTimestamp(a) || ''));
      group.latestItem = group.items[0];
      group.latestTimestamp = itemTimestamp(group.latestItem);
      group.approvals = group.items.filter((item): item is HireProposalInboxItem => item.item_type === 'hire_proposal');
      group.failures = group.items.filter(
        (item): item is AgentRunInboxItem => item.item_type === 'agent_run' && item.feed_type === 'failure',
      );
      group.deliverables = group.items.filter((item) => item.feed_type === 'deliverable');
      group.updates = group.items.filter((item) => item.feed_type === 'issue_update');
      return group;
    })
    .sort((a, b) => (b.latestTimestamp || '').localeCompare(a.latestTimestamp || ''));
}

function SummaryBar({
  groups,
  unreadCount,
  activeFilter,
  onFilterChange,
}: {
  groups: InboxGroup[];
  unreadCount: number;
  activeFilter: InboxFilter;
  onFilterChange: (filter: InboxFilter) => void;
}) {
  const counts = useMemo(() => {
    let failures = 0;
    let approvals = 0;
    let updates = 0;
    let deliverables = 0;
    for (const group of groups) {
      failures += group.failures.length;
      approvals += group.approvals.length;
      updates += group.updates.length;
      deliverables += group.deliverables.length;
    }
    return { failures, approvals, updates, deliverables };
  }, [groups]);

  const chips = [
    { id: 'all' as const, label: 'All', value: groups.length, className: 'bg-white text-slate-700 border-slate-200' },
    { id: 'unread' as const, label: 'Unread', value: unreadCount, className: 'bg-blue-50 text-blue-700 border-blue-200' },
    { id: 'failure' as const, label: 'Failures', value: counts.failures, className: 'bg-red-50 text-red-700 border-red-200' },
    { id: 'approval' as const, label: 'Approvals', value: counts.approvals, className: 'bg-amber-50 text-amber-700 border-amber-200' },
    { id: 'issue_update' as const, label: 'Updates', value: counts.updates, className: 'bg-violet-50 text-violet-700 border-violet-200' },
    { id: 'deliverable' as const, label: 'Deliverables', value: counts.deliverables, className: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  ].filter((chip) => chip.value > 0);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          onClick={() => onFilterChange(chip.id)}
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] transition hover:-translate-y-0.5 hover:shadow-sm ${
            activeFilter === chip.id ? 'ring-2 ring-slate-900/10' : ''
          } ${chip.className}`}
          aria-pressed={activeFilter === chip.id}
        >
          <span>{chip.label}</span>
          <span>{chip.value}</span>
        </button>
      ))}
    </div>
  );
}

function GroupCard({
  group,
  busyKey,
  onRetry,
  onApprove,
  onReject,
  onOpenIssue,
  onMarkRead,
}: {
  group: InboxGroup;
  busyKey: string | null;
  onRetry: (item: AgentRunInboxItem) => Promise<void>;
  onApprove: (item: HireProposalInboxItem) => Promise<void>;
  onReject: (item: HireProposalInboxItem) => Promise<void>;
  onOpenIssue: (taskId: string) => void;
  onMarkRead: (items: InboxItem[]) => void;
}) {
  const latest = group.latestItem;
  const latestTone = toneClasses(
    group.failures.length > 0
      ? 'failure'
      : group.approvals.length > 0
        ? 'approval'
        : latest.feed_type,
  );
  const { Icon } = latestTone;
  const latestFailedRun = group.failures[0];
  const latestApproval = group.approvals[0];
  const recentItems = group.items.slice(0, 3);
  const disabled = group.items.some((item) => busyKey === itemKey(item));
  const canOpenIssue = !!group.taskId;

  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:border-slate-300 ${disabled ? 'opacity-70' : ''}`}
    >
      <div className="flex items-start gap-4 px-4 py-4">
        <div className={`mt-1 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${latestTone.soft}`}>
          <Icon className={`h-4.5 w-4.5 ${latestTone.iconClass}`} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="truncate text-[16px] font-semibold text-slate-900">{group.taskTitle}</p>
                {group.unread ? <span className="h-2 w-2 rounded-full bg-blue-500" /> : null}
                {group.requiresAction ? (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-700">
                    Action needed
                  </span>
                ) : null}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-slate-500">
                <span>{recentItems.length} event{recentItems.length === 1 ? '' : 's'}</span>
                {group.failures.length > 0 ? <span>{group.failures.length} failure{group.failures.length === 1 ? '' : 's'}</span> : null}
                {group.approvals.length > 0 ? <span>{group.approvals.length} approval{group.approvals.length === 1 ? '' : 's'}</span> : null}
                {group.deliverables.length > 0 ? <span>{group.deliverables.length} deliverable{group.deliverables.length === 1 ? '' : 's'}</span> : null}
              </div>
            </div>
            <div className="min-w-[72px] text-right text-[12px] text-slate-400">
              {formatRelativeApiTime(group.latestTimestamp)}
            </div>
          </div>

          <div className="mt-3 space-y-2">
            {recentItems.map((item) => {
              const tone = toneClasses(item.feed_type);
              return (
                <div
                  key={itemKey(item)}
                  className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${tone.badge}`}>
                      {feedTypeLabel(item.feed_type)}
                    </span>
                    <span className="text-[12px] font-medium text-slate-700">{itemActor(item)}</span>
                    <span className="text-[11px] text-slate-400">{formatRelativeApiTime(item.timestamp)}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-slate-600">{itemSummary(item)}</p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-2">
          {canOpenIssue ? (
            <button
              type="button"
              onClick={() => {
                onMarkRead(group.items);
                onOpenIssue(group.taskId!);
              }}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            >
              <FileText className="h-3.5 w-3.5" />
              Open
            </button>
          ) : null}

          {latestFailedRun ? (
            <button
              type="button"
              onClick={() => onRetry(latestFailedRun)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry
            </button>
          ) : null}

          {latestApproval ? (
            <>
              <button
                type="button"
                onClick={() => onReject(latestApproval)}
                className="rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
              >
                Decline
              </button>
              <button
                type="button"
                onClick={() => onApprove(latestApproval)}
                className="rounded-xl border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-[12px] font-semibold text-emerald-700 transition hover:bg-emerald-100"
              >
                Approve
              </button>
            </>
          ) : null}

          {canOpenIssue ? <ChevronRight className="h-4 w-4 text-slate-300" /> : null}
        </div>
      </div>
    </div>
  );
}

function GroupSection({
  title,
  groups,
  busyKey,
  onRetry,
  onApprove,
  onReject,
  onOpenIssue,
  onMarkRead,
}: {
  title: string;
  groups: InboxGroup[];
  busyKey: string | null;
  onRetry: (item: AgentRunInboxItem) => Promise<void>;
  onApprove: (item: HireProposalInboxItem) => Promise<void>;
  onReject: (item: HireProposalInboxItem) => Promise<void>;
  onOpenIssue: (taskId: string) => void;
  onMarkRead: (items: InboxItem[]) => void;
}) {
  if (groups.length === 0) return null;

  return (
    <div className="mb-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.16em] text-slate-400">{title}</h2>
        <span className="text-[12px] text-slate-400">{groups.length}</span>
      </div>
      <div className="space-y-3">
        {groups.map((group) => (
          <GroupCard
            key={group.key}
            group={group}
            busyKey={busyKey}
            onRetry={onRetry}
            onApprove={onApprove}
            onReject={onReject}
            onOpenIssue={onOpenIssue}
            onMarkRead={onMarkRead}
          />
        ))}
      </div>
    </div>
  );
}

export default function InboxPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<InboxTab>('recent');
  const [activeFilter, setActiveFilter] = useState<InboxFilter>('all');
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

  const markItemsRead = (selectedItems: InboxItem[]) => {
    const next = { ...readState };
    const now = new Date().toISOString();
    for (const item of selectedItems) next[itemKey(item)] = now;
    setReadState(next);
    saveReadState(next);
  };

  const tabItems = useMemo(() => {
    const lower = query.trim().toLowerCase();
    const base = items.filter((item) => {
      const haystack = `${itemHeadline(item)} ${itemSummary(item)} ${itemActor(item)}`.toLowerCase();
      if (lower && !haystack.includes(lower)) return false;

      if (activeTab === 'unread') return isUnread(item, readState);
      if (activeTab === 'recent') {
        const ts = itemTimestamp(item);
        return ts ? Date.now() - (parseApiDate(ts)?.getTime() ?? 0) < 7 * 24 * 60 * 60 * 1000 : true;
      }
      if (activeTab === 'mine') return item.requires_action || item.item_type === 'task_message';
      return true;
    });

    return base.sort((a, b) => {
      const aTs = itemTimestamp(a) || '';
      const bTs = itemTimestamp(b) || '';
      return bTs.localeCompare(aTs);
    });
  }, [activeTab, items, query, readState]);

  const baseGroups = useMemo(() => groupItems(tabItems, readState), [readState, tabItems]);

  const visibleItems = useMemo(() => {
    if (activeFilter === 'all') return tabItems;
    return tabItems.filter((item) => {
      if (activeFilter === 'unread') return isUnread(item, readState);
      return item.feed_type === activeFilter;
    });
  }, [activeFilter, readState, tabItems]);

  const groups = useMemo(() => groupItems(visibleItems, readState), [readState, visibleItems]);

  const unreadCount = useMemo(
    () => tabItems.filter((item) => isUnread(item, readState)).length,
    [readState, tabItems],
  );

  const actionGroups = useMemo(
    () => groups.filter((group) => group.requiresAction || group.failures.length > 0 || group.approvals.length > 0),
    [groups],
  );

  const informationalGroups = useMemo(
    () => groups.filter((group) => !actionGroups.some((actionGroup) => actionGroup.key === group.key)),
    [actionGroups, groups],
  );

  const handleRetry = async (item: AgentRunInboxItem) => {
    setBusyKey(itemKey(item));
    try {
      await triggerAgentRun(item.scheduled_agent_id);
      markItemsRead([item]);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const handleApprove = async (item: HireProposalInboxItem) => {
    setBusyKey(itemKey(item));
    try {
      await approveHireProposal(item.id);
      markItemsRead([item]);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const handleReject = async (item: HireProposalInboxItem) => {
    setBusyKey(itemKey(item));
    try {
      await rejectHireProposal(item.id);
      markItemsRead([item]);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-[28px] font-semibold tracking-[-0.03em] text-slate-900">Inbox</h1>
      </div>

      <div className="px-6 py-5">
        <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex items-center gap-6 border-b border-slate-200">
            {TAB_LABELS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                  setActiveFilter('all');
                }}
                className={`border-b-2 px-1 pb-2 text-[15px] font-medium transition ${
                  activeTab === tab.id
                    ? 'border-slate-900 text-slate-900'
                    : 'border-transparent text-slate-400 hover:text-slate-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex w-full items-center gap-3 lg:w-auto">
            <div className="flex min-w-[280px] flex-1 items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-2.5 lg:w-[360px] lg:flex-none">
              <Search className="h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search inbox..."
                className="w-full bg-transparent text-[14px] text-slate-900 outline-none placeholder:text-slate-400"
              />
            </div>
          </div>
        </div>

        <SummaryBar
          groups={baseGroups}
          unreadCount={unreadCount}
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
        />

        {loading ? (
          <div className="flex items-center justify-center rounded-[20px] border border-slate-200 bg-white px-6 py-16 shadow-sm">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        ) : error ? (
          <div className="rounded-[20px] border border-slate-200 bg-white px-6 py-10 text-center text-sm text-red-600 shadow-sm">
            {error}
          </div>
        ) : groups.length === 0 ? (
          <div className="rounded-[20px] border border-slate-200 bg-white px-6 py-12 text-center text-sm text-slate-500 shadow-sm">
            No inbox items.
          </div>
        ) : (
          <>
            <GroupSection
              title="Needs Action"
              groups={actionGroups}
              busyKey={busyKey}
              onRetry={handleRetry}
              onApprove={handleApprove}
              onReject={handleReject}
              onOpenIssue={(taskId) => navigate(`/issues/${taskId}`)}
              onMarkRead={markItemsRead}
            />
            <GroupSection
              title="Recent Activity"
              groups={informationalGroups}
              busyKey={busyKey}
              onRetry={handleRetry}
              onApprove={handleApprove}
              onReject={handleReject}
              onOpenIssue={(taskId) => navigate(`/issues/${taskId}`)}
              onMarkRead={markItemsRead}
            />
          </>
        )}
      </div>
    </div>
  );
}
