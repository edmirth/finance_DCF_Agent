import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CalendarClock,
  ChevronRight,
  FilePlus2,
  Inbox,
  Loader2,
  Mail,
  Pause,
  Play,
  Repeat,
  Zap,
} from 'lucide-react';
import { getScheduledAgents, triggerAgentRun, updateScheduledAgent } from '../api';
import type { ScheduledAgent } from '../types';
import { roleMetaForAgent } from '../agentRoles';

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market: 'Weekdays 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly: 'Monthly',
};

type RoutineFilter = 'all' | 'active' | 'paused';

function formatDateTime(iso?: string | null): string {
  if (!iso) return 'Not scheduled';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function formatRelativeTime(iso?: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

function isDueToday(iso?: string | null): boolean {
  if (!iso) return false;
  const next = new Date(iso);
  const now = new Date();
  return (
    next.getFullYear() === now.getFullYear() &&
    next.getMonth() === now.getMonth() &&
    next.getDate() === now.getDate()
  );
}

function EmptyState() {
  const navigate = useNavigate();

  return (
    <div className="rounded-[28px] border border-dashed border-slate-300 bg-white px-8 py-16 text-center">
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-white">
        <Repeat className="h-6 w-6" />
      </div>
      <h2 className="text-xl font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
        No routines yet
      </h2>
      <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-slate-500">
        Routines are recurring workflows for your agent desks. Create one to wake an analyst on a schedule and send findings into Inbox.
      </p>
      <button
        type="button"
        onClick={() => navigate('/routines/new')}
        className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
      >
        <FilePlus2 className="h-4 w-4" />
        New Routine
      </button>
    </div>
  );
}

function RoutineCard({
  agent,
  onToggle,
  onRunNow,
}: {
  agent: ScheduledAgent;
  onToggle: (agent: ScheduledAgent) => void;
  onRunNow: (agent: ScheduledAgent) => Promise<void>;
}) {
  const navigate = useNavigate();
  const meta = roleMetaForAgent(agent);
  const [runningNow, setRunningNow] = useState(false);

  const handleRunNow = async (event: React.MouseEvent) => {
    event.stopPropagation();
    setRunningNow(true);
    try {
      await onRunNow(agent);
    } finally {
      setTimeout(() => setRunningNow(false), 1200);
    }
  };

  const handleToggle = (event: React.MouseEvent) => {
    event.stopPropagation();
    onToggle(agent);
  };

  return (
    <button
      type="button"
      onClick={() => navigate(`/routines/${agent.id}`, { state: { from: '/routines' } })}
      className="w-full rounded-[28px] border border-slate-200 bg-white p-6 text-left transition hover:border-slate-300 hover:shadow-sm"
    >
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-4">
            <div
              className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl text-base font-bold"
              style={{ background: meta.bg, color: meta.color }}
            >
              {meta.letter}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
                  {agent.name}
                </h2>
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${agent.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                  {agent.is_active ? 'Active' : 'Paused'}
                </span>
                {agent.last_run_status === 'failed' && (
                  <span className="rounded-full bg-red-100 px-2.5 py-1 text-[11px] font-semibold text-red-700">
                    Last run failed
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm font-medium" style={{ color: meta.color }}>
                {meta.displayTitle}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                {agent.description?.trim() || agent.instruction?.trim() || 'No routine brief yet.'}
              </p>
            </div>
          </div>

          {agent.tickers.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {agent.tickers.slice(0, 6).map((ticker) => (
                <span key={ticker} className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                  {ticker}
                </span>
              ))}
              {agent.tickers.length > 6 && (
                <span className="rounded-lg bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-400">
                  +{agent.tickers.length - 6}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-row items-start justify-between gap-4 lg:flex-col lg:items-end">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunNow}
              className="rounded-xl border border-emerald-200 bg-emerald-50 p-2.5 text-emerald-700 transition hover:bg-emerald-100"
              title="Run now"
            >
              {runningNow ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={handleToggle}
              className="rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-slate-600 transition hover:bg-slate-100"
              title={agent.is_active ? 'Pause routine' : 'Resume routine'}
            >
              {agent.is_active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
          </div>
          <ChevronRight className="hidden h-5 w-5 text-slate-300 lg:block" />
        </div>
      </div>

      <div className="mt-5 grid gap-3 border-t border-slate-100 pt-5 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Schedule</p>
          <p className="mt-1 text-sm font-medium text-slate-800">{SCHEDULE_LABELS[agent.schedule_label]}</p>
          {agent.heartbeat_routine?.timezone_name && (
            <p className="mt-1 text-xs text-slate-400">{agent.heartbeat_routine.timezone_name}</p>
          )}
        </div>
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Next wake-up</p>
          <p className="mt-1 text-sm font-medium text-slate-800">{formatDateTime(agent.next_run_at || agent.heartbeat_routine?.next_run_at)}</p>
          <p className="mt-1 text-xs text-slate-400">
            {isDueToday(agent.next_run_at || agent.heartbeat_routine?.next_run_at) ? 'Due today' : 'Upcoming'}
          </p>
        </div>
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Last run</p>
          <p className="mt-1 text-sm font-medium text-slate-800">{formatRelativeTime(agent.last_run_at)}</p>
          <p className="mt-1 text-xs text-slate-400">{formatDateTime(agent.last_run_at)}</p>
        </div>
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Delivery</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm font-medium text-slate-800">
            {agent.delivery_inapp && (
              <span className="inline-flex items-center gap-1.5">
                <Inbox className="h-3.5 w-3.5 text-slate-400" />
                Inbox
              </span>
            )}
            {agent.delivery_email && (
              <span className="inline-flex items-center gap-1.5">
                <Mail className="h-3.5 w-3.5 text-slate-400" />
                Email
              </span>
            )}
            {!agent.delivery_inapp && !agent.delivery_email && (
              <span className="text-slate-400">No delivery channel</span>
            )}
          </div>
          <p className="mt-1 text-xs text-slate-400">{agent.reports_to_label || 'CIO'}</p>
        </div>
      </div>
    </button>
  );
}

export default function RoutinesPage() {
  const navigate = useNavigate();
  const [routines, setRoutines] = useState<ScheduledAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<RoutineFilter>('all');
  const [toast, setToast] = useState<{ msg: string; tone: 'error' | 'success' } | null>(null);

  const showToast = (msg: string, tone: 'error' | 'success' = 'error') => {
    setToast({ msg, tone });
    setTimeout(() => setToast(null), 3500);
  };

  const load = async () => {
    setLoading(true);
    try {
      const data = await getScheduledAgents();
      setRoutines(data);
    } catch {
      showToast('Could not load routines.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filteredRoutines = useMemo(() => {
    if (filter === 'active') return routines.filter((routine) => routine.is_active);
    if (filter === 'paused') return routines.filter((routine) => !routine.is_active);
    return routines;
  }, [filter, routines]);

  const activeCount = routines.filter((routine) => routine.is_active).length;
  const pausedCount = routines.filter((routine) => !routine.is_active).length;
  const dueTodayCount = routines.filter((routine) => isDueToday(routine.next_run_at || routine.heartbeat_routine?.next_run_at)).length;
  const failedCount = routines.filter((routine) => routine.last_run_status === 'failed').length;

  const handleToggle = async (routine: ScheduledAgent) => {
    try {
      const updated = await updateScheduledAgent(routine.id, { is_active: !routine.is_active });
      setRoutines((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      showToast('Failed to update routine state.', 'error');
    }
  };

  const handleRunNow = async (routine: ScheduledAgent) => {
    try {
      await triggerAgentRun(routine.id);
      showToast('Routine run started. Watch Inbox for results.', 'success');
      setTimeout(load, 1200);
    } catch {
      showToast('Failed to trigger routine.', 'error');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${toast.tone === 'error' ? 'bg-red-600' : 'bg-emerald-600'}`}>
          {toast.msg}
        </div>
      )}

      <div className="mx-auto w-full max-w-6xl px-6 py-12 lg:px-10">
        <div className="flex flex-col gap-5 border-b border-slate-200 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
              Routines
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-500">
              Recurring workflows that wake up agent desks, run on a schedule, and deliver findings to your Inbox. {activeCount} active · {pausedCount} paused.
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/routines/new')}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            <FilePlus2 className="h-4 w-4" />
            New Routine
          </button>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <p className="text-3xl font-semibold text-slate-900">{routines.length}</p>
            <p className="mt-1 text-sm text-slate-500">Total routines</p>
          </div>
          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <p className="text-3xl font-semibold text-slate-900">{activeCount}</p>
            <p className="mt-1 text-sm text-slate-500">Active right now</p>
          </div>
          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <p className="text-3xl font-semibold text-slate-900">{dueTodayCount}</p>
            <p className="mt-1 text-sm text-slate-500">Due today</p>
          </div>
          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <p className="text-3xl font-semibold text-slate-900">{failedCount}</p>
            <p className="mt-1 text-sm text-slate-500">Need attention</p>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-2">
          {([
            { id: 'all', label: 'All routines' },
            { id: 'active', label: 'Active' },
            { id: 'paused', label: 'Paused' },
          ] as Array<{ id: RoutineFilter; label: string }>).map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setFilter(option.id)}
              className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
                filter === option.id
                  ? 'bg-slate-900 text-white'
                  : 'border border-slate-200 bg-white text-slate-600 hover:border-slate-300'
              }`}
            >
              {option.label}
            </button>
          ))}
          {failedCount > 0 && (
            <span className="ml-auto inline-flex items-center gap-1.5 rounded-xl bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
              <AlertTriangle className="h-4 w-4" />
              {failedCount} failed recently
            </span>
          )}
        </div>

        <div className="mt-8">
          {loading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : filteredRoutines.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-4">
              {filteredRoutines.map((routine) => (
                <RoutineCard
                  key={routine.id}
                  agent={routine}
                  onToggle={handleToggle}
                  onRunNow={handleRunNow}
                />
              ))}
            </div>
          )}
        </div>

        {!loading && routines.length > 0 && (
          <div className="mt-8 rounded-[24px] border border-slate-200 bg-white p-5">
            <div className="flex items-start gap-3">
              <CalendarClock className="mt-0.5 h-5 w-5 text-slate-400" />
              <div>
                <p className="text-sm font-semibold text-slate-900">How routines work</p>
                <p className="mt-1 text-sm leading-relaxed text-slate-500">
                  Each routine is attached to an agent desk. The heartbeat scheduler wakes it up, records the wake-up cycle, and sends findings into Inbox or email.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
