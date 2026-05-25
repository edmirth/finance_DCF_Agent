import { useEffect, useMemo, useState } from 'react';
import { stripMarkdown } from '../utils/markdown';
import { useNavigate } from 'react-router-dom';
import {
  ChevronRight,
  Clock,
  FileText,
  Loader2,
  Pause,
  Play,
  Trash2,
  Zap,
} from 'lucide-react';
import {
  deleteScheduledAgent,
  getInbox,
  getScheduledAgents,
  listTasks,
  triggerAgentRun,
  updateScheduledAgent,
  type ResearchTask,
} from '../api';
import { roleMetaForAgent } from '../agentRoles';
import type { InboxItem, ScheduledAgent } from '../types';
import { compareApiDatesDesc, formatRelativeApiTime } from '../utils/time';

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market: 'Weekdays 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly: 'Monthly',
};

const TASK_STATUS_TONE: Record<string, string> = {
  pending: '#94A3B8',
  running: '#3B82F6',
  in_review: '#8B5CF6',
  done: '#10B981',
  failed: '#EF4444',
  cancelled: '#64748B',
};

const ACTIVE_TASK_STATUSES: Array<ResearchTask['status']> = ['pending', 'running', 'in_review', 'failed'];

function displayTicker(ticker: string): string {
  return ticker === 'GENERAL' ? 'General' : ticker;
}

function agentInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('') || 'AG';
}

type AgentWorkload = {
  openCount: number;
  runningCount: number;
  pendingCount: number;
  reviewCount: number;
  failedCount: number;
  currentTasks: ResearchTask[];
};

function buildEmptyWorkload(): AgentWorkload {
  return {
    openCount: 0,
    runningCount: 0,
    pendingCount: 0,
    reviewCount: 0,
    failedCount: 0,
    currentTasks: [],
  };
}

function workloadLabel(workload: AgentWorkload): string {
  if (workload.runningCount > 0) {
    return workload.runningCount === 1 ? 'Working on 1 live issue' : `Working on ${workload.runningCount} live issues`;
  }
  if (workload.openCount > 0) {
    return workload.openCount === 1 ? '1 open issue queued' : `${workload.openCount} open issues queued`;
  }
  return 'No active issues';
}

function statusChipTone(status: ResearchTask['status']): string {
  switch (status) {
    case 'running':
      return 'bg-blue-50 text-blue-700';
    case 'in_review':
      return 'bg-violet-50 text-violet-700';
    case 'failed':
      return 'bg-red-50 text-red-700';
    case 'pending':
      return 'bg-slate-100 text-slate-600';
    default:
      return 'bg-slate-100 text-slate-600';
  }
}

function taskPriorityOrder(status: ResearchTask['status']): number {
  switch (status) {
    case 'running':
      return 0;
    case 'failed':
      return 1;
    case 'in_review':
      return 2;
    case 'pending':
      return 3;
    default:
      return 4;
  }
}

function AgentWorkingIndicator({
  isWorking,
  runningCount,
}: {
  isWorking: boolean;
  runningCount: number;
}) {
  if (!isWorking) return null;

  return (
    <div className="mb-3 flex items-center gap-2 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2">
      <span className="relative flex h-3 w-3 flex-shrink-0 items-center justify-center">
        <span className="absolute inline-flex h-3 w-3 animate-ping rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex h-3 w-3 rounded-full border-2 border-white bg-blue-500" />
      </span>
      <span className="text-xs font-semibold text-blue-700">
        {runningCount === 1 ? 'Working on 1 issue now' : `Working on ${runningCount} issues now`}
      </span>
    </div>
  );
}

function WorkloadBar({ workload }: { workload: AgentWorkload }) {
  const total = workload.openCount;
  const segments =
    total > 0
      ? [
          { key: 'running', count: workload.runningCount, color: '#3B82F6' },
          { key: 'in_review', count: workload.reviewCount, color: '#8B5CF6' },
          { key: 'pending', count: workload.pendingCount, color: '#94A3B8' },
          { key: 'failed', count: workload.failedCount, color: '#EF4444' },
        ].filter((segment) => segment.count > 0)
      : [];

  return (
    <div className="mb-4 rounded-xl border border-slate-100 bg-slate-50/80 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Live workload</p>
          <p className="mt-1 text-sm font-medium text-slate-700">{workloadLabel(workload)}</p>
        </div>
        <div className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-500">
          {total} open
        </div>
      </div>

      <div className="h-2 overflow-hidden rounded-full bg-white">
        {segments.length === 0 ? (
          <div className="h-full w-full bg-slate-100" />
        ) : (
          <div className="flex h-full w-full">
            {segments.map((segment) => (
              <div
                key={segment.key}
                className="h-full"
                style={{
                  width: `${(segment.count / total) * 100}%`,
                  backgroundColor: segment.color,
                }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {workload.runningCount > 0 && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">
            {workload.runningCount} running
          </span>
        )}
        {workload.reviewCount > 0 && (
          <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700">
            {workload.reviewCount} in review
          </span>
        )}
        {workload.pendingCount > 0 && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
            {workload.pendingCount} pending
          </span>
        )}
        {workload.failedCount > 0 && (
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700">
            {workload.failedCount} failed
          </span>
        )}
      </div>

      <div className="mt-3 space-y-1.5">
        {workload.currentTasks.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <FileText className="h-3.5 w-3.5" />
            No issue is assigned right now.
          </div>
        ) : (
          workload.currentTasks.slice(0, 2).map((task) => (
            <div key={task.id} className="flex items-center justify-between gap-3 rounded-lg bg-white px-2.5 py-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-slate-700">{task.title}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">{displayTicker(task.ticker)}</p>
              </div>
              <span className={`flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusChipTone(task.status)}`}>
                {task.status.replace('_', ' ')}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function AgentCard({
  agent,
  workload,
  onDelete,
  onToggle,
  onRunNow,
}: {
  agent: ScheduledAgent;
  workload: AgentWorkload;
  onDelete: (id: string) => void;
  onToggle: (id: string, active: boolean) => void;
  onRunNow: (id: string) => void;
}) {
  const navigate = useNavigate();
  const meta = roleMetaForAgent(agent);
  const [running, setRunning] = useState(false);
  const showSubtitle = meta.displayTitle !== agent.name;
  const isWorking = workload.runningCount > 0;

  const handleRunNow = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setRunning(true);
    await onRunNow(agent.id);
    setTimeout(() => setRunning(false), 3000);
  };

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle(agent.id, !agent.is_active);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete(agent.id);
  };

  return (
    <div
      onClick={() => navigate(`/routines/${agent.id}`, { state: { from: '/' } })}
      className="group cursor-pointer rounded-2xl border border-slate-200 bg-white p-5 transition-all duration-200 hover:border-slate-300 hover:shadow-md"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-sm font-bold"
            style={{ background: meta.bg, color: meta.color }}
          >
            {meta.letter}
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-slate-900" style={{ letterSpacing: '-0.01em' }}>
              {agent.name}
            </h3>
            {showSubtitle && (
              <span className="text-xs font-medium" style={{ color: meta.color }}>
                {meta.displayTitle}
              </span>
            )}
            <p className="mt-0.5 text-xs text-slate-400">
              Reports to {agent.reports_to_label || 'CIO'}
            </p>
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-1.5">
          {isWorking ? (
            <>
              <span className="relative flex h-2.5 w-2.5 items-center justify-center">
                <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-blue-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-500" />
              </span>
              <span className="text-xs font-medium text-blue-600">Working</span>
            </>
          ) : (
            <>
              <div
                className={`h-2 w-2 rounded-full ${agent.is_active ? 'bg-emerald-400' : 'bg-slate-300'}`}
                style={agent.is_active ? { boxShadow: '0 0 0 3px #D1FAE5' } : {}}
              />
              <span className="text-xs text-slate-400">{agent.is_active ? 'Active' : 'Paused'}</span>
            </>
          )}
        </div>
      </div>

      {agent.tickers.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {agent.tickers.slice(0, 5).map((ticker) => (
            <span
              key={ticker}
              className="rounded-lg px-2 py-0.5 text-xs font-semibold"
              style={{ background: '#F1F5F9', color: '#475569' }}
            >
              {ticker}
            </span>
          ))}
          {agent.tickers.length > 5 && (
            <span className="text-xs text-slate-400">+{agent.tickers.length - 5}</span>
          )}
        </div>
      )}

      {agent.last_run_summary ? (
        <p className="mb-3 line-clamp-2 text-xs leading-relaxed text-slate-500">
          {stripMarkdown(agent.last_run_summary)}
        </p>
      ) : (
        <p className="mb-3 text-xs italic text-slate-400">No runs yet</p>
      )}

      <AgentWorkingIndicator isWorking={isWorking} runningCount={workload.runningCount} />

      <WorkloadBar workload={workload} />

      <div className="flex items-center justify-between border-t border-slate-100 pt-3">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock className="h-3.5 w-3.5" />
          <span className="text-xs">{SCHEDULE_LABELS[agent.schedule_label]}</span>
          {agent.last_run_at && (
            <>
              <span className="text-slate-300">·</span>
              <span className="text-xs">{formatRelativeApiTime(agent.last_run_at)}</span>
            </>
          )}
        </div>

        <div className="flex items-center gap-1 transition-opacity duration-150 group-hover:opacity-100 md:opacity-0">
          <button
            onClick={handleRunNow}
            className="rounded-lg p-1.5 text-slate-400 transition-colors duration-150 hover:bg-emerald-50 hover:text-emerald-600"
            title="Run now"
          >
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={handleToggle}
            className="rounded-lg p-1.5 text-slate-400 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-600"
            title={agent.is_active ? 'Pause' : 'Resume'}
          >
            {agent.is_active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={handleDelete}
            className="rounded-lg p-1.5 text-slate-400 transition-colors duration-150 hover:bg-red-50 hover:text-red-500"
            title="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>

        <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-300 transition-colors duration-150 group-hover:text-slate-500" />
      </div>
    </div>
  );
}

function LeaderCard({ workload }: { workload: AgentWorkload }) {
  const navigate = useNavigate();
  const isWorking = workload.runningCount > 0;

  return (
    <div
      onClick={() => navigate('/agents/ceo')}
      className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-5 transition-all duration-200 hover:border-slate-300 hover:shadow-md"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-900 text-sm font-bold text-white">
            C
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-slate-900" style={{ letterSpacing: '-0.01em' }}>
              CEO
            </h3>
            <span className="text-xs font-medium text-slate-700">Firm Lead</span>
            <p className="mt-0.5 text-xs text-slate-400">Persistent top-level orchestrator</p>
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-1.5">
          {isWorking ? (
            <>
              <span className="relative flex h-2.5 w-2.5 items-center justify-center">
                <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-blue-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-500" />
              </span>
              <span className="text-xs font-medium text-blue-600">Working</span>
            </>
          ) : (
            <>
              <div className="h-2 w-2 rounded-full bg-emerald-400" style={{ boxShadow: '0 0 0 3px #D1FAE5' }} />
              <span className="text-xs text-slate-400">Active</span>
            </>
          )}
        </div>
      </div>

      <p className="mb-3 text-xs leading-relaxed text-slate-500">
        Reviews new issues, decides whether to delegate existing work, and suggests new hires when the current team has a coverage gap.
      </p>

      <AgentWorkingIndicator isWorking={isWorking} runningCount={workload.runningCount} />

      <WorkloadBar workload={workload} />

      <div className="flex items-center justify-between border-t border-slate-100 pt-3">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock className="h-3.5 w-3.5" />
          <span className="text-xs">Always on</span>
        </div>

        <span className="text-xs font-medium text-slate-500">Open CEO</span>
      </div>
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2
      className="mb-4 text-sm font-semibold uppercase text-slate-400"
      style={{ letterSpacing: '0.08em', fontFamily: "'IBM Plex Mono', monospace" }}
    >
      {title}
    </h2>
  );
}

function ActivityRow({
  label,
  body,
  time,
  initials,
}: {
  label: string;
  body: string;
  time: string;
  initials: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-4 py-4 last:border-b-0">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-medium text-slate-600">
          {initials}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-900">{label}</p>
          <p className="mt-1 line-clamp-1 text-sm text-slate-500">{body}</p>
        </div>
      </div>
      <span className="flex-shrink-0 text-sm text-slate-400">{time}</span>
    </div>
  );
}

function TaskRow({ task }: { task: ResearchTask }) {
  const navigate = useNavigate();
  const statusColor = TASK_STATUS_TONE[task.status] || '#94A3B8';

  return (
    <button
      type="button"
      onClick={() => navigate(`/issues/${task.id}`)}
      className="flex w-full items-start justify-between gap-4 border-b border-slate-100 px-4 py-4 text-left transition hover:bg-slate-50 last:border-b-0"
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className="mt-0.5 h-6 w-6 flex-shrink-0 rounded-full border-2"
          style={{ borderColor: statusColor, boxShadow: `inset 0 0 0 4px ${statusColor}` }}
        />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
            <span className="font-mono text-xs uppercase tracking-wide text-slate-500">
              {displayTicker(task.ticker)}
            </span>
            <span>{formatRelativeApiTime(task.updated_at || task.created_at)}</span>
          </div>
          <p className="mt-1 truncate text-sm font-medium text-slate-900">{task.title}</p>
        </div>
      </div>
      <span
        className="flex-shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold capitalize"
        style={{ background: `${statusColor}14`, color: statusColor }}
      >
        {task.status.replace('_', ' ')}
      </span>
    </button>
  );
}

export default function AgentsDashboard() {
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [allTasks, setAllTasks] = useState<ResearchTask[]>([]);
  const [inboxItems, setInboxItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: 'error' | 'success' } | null>(null);

  const showToast = (msg: string, type: 'error' | 'success' = 'error') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const load = async () => {
    try {
      const [agentData, taskData, inboxData] = await Promise.all([
        getScheduledAgents(),
        listTasks({ limit: 200 }),
        getInbox(12),
      ]);
      setAgents(agentData);
      setAllTasks(taskData);
      setInboxItems(inboxData);
    } catch {
      showToast('Could not load dashboard state — backend may be offline.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this agent?')) return;
    try {
      await deleteScheduledAgent(id);
      setAgents((prev) => prev.filter((agent) => agent.id !== id));
    } catch {
      showToast('Failed to delete agent. Please try again.');
    }
  };

  const handleToggle = async (id: string, active: boolean) => {
    try {
      const updated = await updateScheduledAgent(id, { is_active: active });
      setAgents((prev) => prev.map((agent) => (agent.id === id ? updated : agent)));
    } catch {
      showToast('Failed to update agent status.');
    }
  };

  const handleRunNow = async (id: string) => {
    try {
      await triggerAgentRun(id);
      showToast('Run started — dashboard will refresh.', 'success');
      setTimeout(load, 1500);
    } catch {
      showToast('Failed to trigger run. Please try again.');
    }
  };

  const recentActivity = useMemo(() => {
    const runItems = inboxItems.filter((item): item is InboxItem & { item_type: 'agent_run'; agent_name: string } => item.item_type === 'agent_run');
    const rows = runItems.map((item) => ({
      id: item.id,
      label: item.agent_name,
      body:
        item.status === 'running'
          ? 'Run in progress'
          : item.findings_summary || item.error || 'Run completed',
      time: formatRelativeApiTime(item.started_at),
      initials: agentInitials(item.agent_name),
    }));

    if (rows.length >= 8) return rows.slice(0, 8);

    const supplemental = agents
      .filter((agent) => agent.is_active)
      .slice(0, 8 - rows.length)
      .map((agent) => ({
        id: `active-${agent.id}`,
        label: agent.name,
        body: agent.last_run_summary || 'Active and monitoring',
        time: formatRelativeApiTime(agent.updated_at),
        initials: agentInitials(agent.name),
      }));

    return [...rows, ...supplemental].slice(0, 8);
  }, [agents, inboxItems]);

  const activeCount = agents.filter((agent) => agent.is_active).length;
  const pausedCount = agents.filter((agent) => !agent.is_active).length;
  const recentTasks = useMemo(() => allTasks.slice(0, 10), [allTasks]);
  const agentWorkloads = useMemo(() => {
    const workloads = new Map<string, AgentWorkload>();
    agents.forEach((agent) => workloads.set(agent.id, buildEmptyWorkload()));
    for (const task of allTasks) {
      if (!ACTIVE_TASK_STATUSES.includes(task.status)) continue;
      const agentId = task.assigned_agent_id || task.owner_agent_id;
      if (!agentId || !workloads.has(agentId)) continue;
      const workload = workloads.get(agentId)!;
      workload.openCount += 1;
      if (task.status === 'running') workload.runningCount += 1;
      if (task.status === 'pending') workload.pendingCount += 1;
      if (task.status === 'in_review') workload.reviewCount += 1;
      if (task.status === 'failed') workload.failedCount += 1;
      workload.currentTasks.push(task);
    }
    for (const workload of workloads.values()) {
      workload.currentTasks.sort((left, right) => {
        const byStatus = taskPriorityOrder(left.status) - taskPriorityOrder(right.status);
        if (byStatus !== 0) return byStatus;
        return compareApiDatesDesc(left.updated_at || left.created_at, right.updated_at || right.created_at);
      });
    }
    return workloads;
  }, [agents, allTasks]);
  const ceoWorkload = useMemo(() => {
    const workload = buildEmptyWorkload();
    for (const task of allTasks) {
      if (!ACTIVE_TASK_STATUSES.includes(task.status)) continue;
      const isCeoTask =
        task.triggered_by === 'manual_pm_review' &&
        (task.assigned_agent_id === null || task.assigned_agent_id === undefined || task.assigned_agent_id === '');
      if (!isCeoTask) continue;
      workload.openCount += 1;
      if (task.status === 'running') workload.runningCount += 1;
      if (task.status === 'pending') workload.pendingCount += 1;
      if (task.status === 'in_review') workload.reviewCount += 1;
      if (task.status === 'failed') workload.failedCount += 1;
      workload.currentTasks.push(task);
    }
    workload.currentTasks.sort((left, right) => {
      const byStatus = taskPriorityOrder(left.status) - taskPriorityOrder(right.status);
      if (byStatus !== 0) return byStatus;
      return compareApiDatesDesc(left.updated_at || left.created_at, right.updated_at || right.created_at);
    });
    return workload;
  }, [allTasks]);

  return (
    <div className="min-h-screen bg-slate-50" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg transition-all duration-300 ${
            toast.type === 'error' ? 'bg-red-600' : 'bg-emerald-600'
          }`}
        >
          {toast.msg}
        </div>
      )}

      <div className="mx-auto w-full max-w-6xl px-6 py-12 lg:px-10">
        <div className="mb-10">
          <h1 className="mb-1 text-3xl font-bold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
            Dashboard
          </h1>
          <p className="text-sm text-slate-500">
            {agents.length === 0
              ? 'CEO seat is active · no analyst hires yet'
              : `${activeCount} active · ${pausedCount} paused`}
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <LeaderCard workload={ceoWorkload} />
              {agents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  workload={agentWorkloads.get(agent.id) || buildEmptyWorkload()}
                  onDelete={handleDelete}
                  onToggle={handleToggle}
                  onRunNow={handleRunNow}
                />
              ))}
            </div>

            <div className="mt-10 grid items-start gap-8 lg:grid-cols-2">
              <div className="min-w-0">
                <SectionHeader title="Recent Activity" />
                <div className="min-h-[360px] overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-sm">
                  {recentActivity.length === 0 ? (
                    <div className="px-4 py-12 text-center text-sm text-slate-500">
                      No agent activity yet.
                    </div>
                  ) : (
                    recentActivity.map((item) => (
                      <ActivityRow
                        key={item.id}
                        label={item.label}
                        body={item.body}
                        time={item.time}
                        initials={item.initials}
                      />
                    ))
                  )}
                </div>
              </div>

              <div className="min-w-0">
                <SectionHeader title="Recent Tasks" />
                <div className="min-h-[360px] overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-sm">
                  {recentTasks.length === 0 ? (
                    <div className="px-4 py-12 text-center text-sm text-slate-500">
                      No tasks yet.
                    </div>
                  ) : (
                    recentTasks.slice(0, 10).map((task) => (
                      <TaskRow key={task.id} task={task} />
                    ))
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
