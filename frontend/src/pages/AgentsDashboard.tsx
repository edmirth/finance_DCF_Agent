import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronRight,
  Clock,
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

function formatRelativeTime(iso?: string | null): string {
  if (!iso) return 'Never run';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

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

function AgentCard({
  agent,
  onDelete,
  onToggle,
  onRunNow,
}: {
  agent: ScheduledAgent;
  onDelete: (id: string) => void;
  onToggle: (id: string, active: boolean) => void;
  onRunNow: (id: string) => void;
}) {
  const navigate = useNavigate();
  const meta = roleMetaForAgent(agent);
  const [running, setRunning] = useState(false);
  const showSubtitle = meta.displayTitle !== agent.name;

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
          <div
            className={`h-2 w-2 rounded-full ${agent.is_active ? 'bg-emerald-400' : 'bg-slate-300'}`}
            style={agent.is_active ? { boxShadow: '0 0 0 3px #D1FAE5' } : {}}
          />
          <span className="text-xs text-slate-400">{agent.is_active ? 'Active' : 'Paused'}</span>
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
          {agent.last_run_summary}
        </p>
      ) : (
        <p className="mb-3 text-xs italic text-slate-400">No runs yet</p>
      )}

      <div className="flex items-center justify-between border-t border-slate-100 pt-3">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock className="h-3.5 w-3.5" />
          <span className="text-xs">{SCHEDULE_LABELS[agent.schedule_label]}</span>
          {agent.last_run_at && (
            <>
              <span className="text-slate-300">·</span>
              <span className="text-xs">{formatRelativeTime(agent.last_run_at)}</span>
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

function LeaderCard() {
  const navigate = useNavigate();

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
          <div className="h-2 w-2 rounded-full bg-emerald-400" style={{ boxShadow: '0 0 0 3px #D1FAE5' }} />
          <span className="text-xs text-slate-400">Active</span>
        </div>
      </div>

      <p className="mb-3 text-xs leading-relaxed text-slate-500">
        Reviews new issues, decides whether to delegate existing work, and suggests new hires when the current team has a coverage gap.
      </p>

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
            <span>{formatRelativeTime(task.updated_at || task.created_at)}</span>
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
  const [recentTasks, setRecentTasks] = useState<ResearchTask[]>([]);
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
        listTasks({ limit: 12 }),
        getInbox(12),
      ]);
      setAgents(agentData);
      setRecentTasks(taskData);
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
      time: formatRelativeTime(item.started_at),
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
        time: formatRelativeTime(agent.updated_at),
        initials: agentInitials(agent.name),
      }));

    return [...rows, ...supplemental].slice(0, 8);
  }, [agents, inboxItems]);

  const activeCount = agents.filter((agent) => agent.is_active).length;
  const pausedCount = agents.filter((agent) => !agent.is_active).length;

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
              <LeaderCard />
              {agents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
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
