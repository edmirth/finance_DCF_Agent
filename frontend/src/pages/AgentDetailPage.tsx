import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowRight,
  FileText,
  Loader2,
  Pause,
  Play,
  Plus,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  getAgentRuns,
  getHeartbeatRuns,
  getScheduledAgent,
  listTasks,
  triggerAgentRun,
  updateScheduledAgent,
  type ResearchTask,
  type TaskPriority,
  type TaskStatus,
} from '../api';
import type { AgentRun, AlertLevel, HeartbeatRun, ScheduledAgent } from '../types';
import { ReportChart } from '../components/ReportChart';
import { roleMetaForAgent } from '../agentRoles';
import { compareApiDatesDesc, formatApiDateTime, formatRelativeApiTime, parseApiDate } from '../utils/time';
import { stripMarkdown } from '../utils/markdown';

type AgentTab = 'dashboard' | 'instructions' | 'system_prompt';

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market: 'Weekdays 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly: 'Monthly',
};

const STATUS_TONE: Record<TaskStatus, string> = {
  pending: 'bg-slate-100 text-slate-700',
  running: 'bg-blue-100 text-blue-700',
  in_review: 'bg-amber-100 text-amber-700',
  done: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-slate-200 text-slate-600',
};

const PRIORITY_TONE: Record<TaskPriority, string> = {
  low: 'bg-slate-100 text-slate-600',
  medium: 'bg-blue-50 text-blue-700',
  high: 'bg-amber-50 text-amber-700',
  urgent: 'bg-red-50 text-red-700',
};

const ALERT_CONFIG: Record<AlertLevel, { label: string; color: string; bg: string; Icon: any }> = {
  high: { label: 'Alert', color: '#EF4444', bg: '#FEE2E2', Icon: AlertTriangle },
  medium: { label: 'New', color: '#F59E0B', bg: '#FEF3C7', Icon: AlertTriangle },
  low: { label: 'Update', color: '#10B981', bg: '#D1FAE5', Icon: CheckCircle2 },
  none: { label: 'No change', color: '#94A3B8', bg: '#F1F5F9', Icon: CheckCircle2 },
};

function formatDuration(startIso?: string, endIso?: string): string {
  if (!startIso || !endIso) return '—';
  const start = parseApiDate(startIso)?.getTime();
  const end = parseApiDate(endIso)?.getTime();
  if (start == null || end == null) return '—';
  const secs = Math.round((end - start) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function displayTicker(ticker: string): string {
  return ticker === 'GENERAL' ? 'General' : ticker;
}

function markdownToHtml(md: string): string {
  return md
    .replace(/^### (.+)$/gm, '<h3 style="font-size:14px;font-weight:700;color:#0F172A;margin:16px 0 6px;letter-spacing:-0.01em">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:15px;font-weight:700;color:#0F172A;margin:20px 0 8px;letter-spacing:-0.02em">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:17px;font-weight:700;color:#0F172A;margin:24px 0 10px;letter-spacing:-0.02em">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li style="margin-bottom:4px">$1</li>')
    .replace(/(<li.*<\/li>\n?)+/g, (s) => `<ul style="padding-left:20px;margin:8px 0">${s}</ul>`)
    .replace(/\n\n/g, '</p><p style="margin:10px 0">')
    .replace(/^(?!<[hul])(.+)$/gm, '$1')
    .replace(/\n/g, '<br>');
}

function RecentIssueRow({ task }: { task: ResearchTask }) {
  return (
    <Link
      to={`/issues/${task.id}`}
      className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 transition hover:bg-slate-50"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_TONE[task.status]}`}>
            {task.status.replace('_', ' ')}
          </span>
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${PRIORITY_TONE[task.priority]}`}>
            {task.priority}
          </span>
          <span className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500">
            {displayTicker(task.ticker)}
          </span>
        </div>
        <p className="mt-3 text-base font-semibold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
          {task.title}
        </p>
        <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-slate-500">
          {task.notes?.trim() || 'No issue description provided.'}
        </p>
      </div>
      <div className="flex-shrink-0 text-right text-xs text-slate-400">
        <div>{formatRelativeApiTime(task.updated_at || task.created_at)}</div>
        <div className="mt-2 text-slate-500">
          {task.assigned_agent_id ? 'Assigned' : task.owner_agent_id ? 'Owned' : 'Tracked'}
        </div>
      </div>
    </Link>
  );
}

function MiniHeartbeatRow({ run }: { run: HeartbeatRun }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          {run.trigger_type}
        </span>
        <span className="text-xs text-slate-400">{formatRelativeApiTime(run.started_at)}</span>
      </div>
      <p className="mt-2 text-sm text-slate-700">
        {stripMarkdown(run.summary || run.error || 'Heartbeat wake-up recorded.')}
      </p>
    </div>
  );
}

function RunRow({ run }: { run: AgentRun }) {
  const [expanded, setExpanded] = useState(false);
  const alert = ALERT_CONFIG[run.alert_level as AlertLevel] || ALERT_CONFIG.none;
  const { Icon } = alert;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-4 bg-white px-5 py-4 text-left transition hover:bg-slate-50"
      >
        <div className="flex-shrink-0">
          {run.status === 'running' ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          ) : run.status === 'failed' ? (
            <XCircle className="h-4 w-4 text-red-500" />
          ) : (
            <Icon className="h-4 w-4" style={{ color: alert.color }} />
          )}
        </div>

        <span
          className="flex-shrink-0 rounded-lg px-2 py-0.5 text-xs font-semibold"
          style={{ background: alert.bg, color: alert.color }}
        >
          {alert.label}
        </span>

        <p className="flex-1 truncate text-left text-sm text-slate-700">
          {stripMarkdown(run.findings_summary || run.error || 'Running...')}
        </p>

        <div className="flex flex-shrink-0 items-center gap-4 text-xs text-slate-400">
          {run.material_change && <span className="font-medium text-amber-600">Material change</span>}
          <span>{formatApiDateTime(run.started_at)}</span>
          <span>{formatDuration(run.started_at, run.completed_at)}</span>
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 bg-white px-5 pb-5">
          <div className="flex flex-wrap gap-4 pb-3 pt-4 text-xs text-slate-500">
            {run.tickers_analyzed?.length > 0 && (
              <span><span className="font-semibold text-slate-700">Tickers: </span>{run.tickers_analyzed.join(', ')}</span>
            )}
            {run.agents_used?.length > 0 && (
              <span><span className="font-semibold text-slate-700">Engines: </span>{run.agents_used.join(', ')}</span>
            )}
          </div>

          {run.key_findings?.length > 0 && (
            <div className="mb-4 border-b border-slate-100 pb-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Key findings</p>
              <ul className="space-y-1.5">
                {run.key_findings.map((finding, index) => (
                  <li key={index} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="mt-0.5 flex-shrink-0 text-emerald-500">·</span>
                    {finding}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {run.report ? (
            <div
              className="prose prose-sm max-w-none text-slate-700"
              style={{ fontSize: '13px', lineHeight: '1.65' }}
              dangerouslySetInnerHTML={{ __html: markdownToHtml(run.report) }}
            />
          ) : run.error ? (
            <div className="rounded-xl bg-red-50 p-4 text-sm text-red-700">
              <p className="mb-1 font-semibold">Run failed</p>
              <p>{run.error}</p>
            </div>
          ) : (
            <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Research in progress.</span>
            </div>
          )}

          {run.chart_specs && (() => {
            try {
              const charts = JSON.parse(run.chart_specs);
              if (Array.isArray(charts) && charts.length > 0) {
                return (
                  <div className="mt-6 border-t border-slate-100 pt-6">
                    <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Charts</p>
                    <div className="grid gap-4 md:grid-cols-2">
                      {charts.map((chart: any) => (
                        <ReportChart key={chart.id} {...chart} />
                      ))}
                    </div>
                  </div>
                );
              }
            } catch {
              /* invalid JSON — silently skip */
            }
            return null;
          })()}
        </div>
      )}
    </div>
  );
}

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [tab, setTab] = useState<AgentTab>('dashboard');
  const [agent, setAgent] = useState<ScheduledAgent | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [heartbeatRuns, setHeartbeatRuns] = useState<HeartbeatRun[]>([]);
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningHeartbeat, setRunningHeartbeat] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [editingInstruction, setEditingInstruction] = useState(false);
  const [draftInstruction, setDraftInstruction] = useState('');
  const [savingInstruction, setSavingInstruction] = useState(false);
  const [editingSystemPrompt, setEditingSystemPrompt] = useState(false);
  const [draftSystemPrompt, setDraftSystemPrompt] = useState('');
  const [savingSystemPrompt, setSavingSystemPrompt] = useState(false);
  const [editingTickers, setEditingTickers] = useState(false);
  const [draftTickers, setDraftTickers] = useState<string[]>([]);
  const [tickerInput, setTickerInput] = useState('');
  const [savingTickers, setSavingTickers] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async (id: string, silent = false) => {
    try {
      const [agentData, runData, heartbeatData, taskData] = await Promise.all([
        getScheduledAgent(id),
        getAgentRuns(id, 20),
        getHeartbeatRuns(id, 10),
        listTasks({ agent_id: id, limit: 50 }),
      ]);
      setAgent(agentData);
      setRuns(runData);
      setHeartbeatRuns(heartbeatData);
      setTasks(taskData);
      if (!silent) setError(null);
    } catch {
      if (!silent) setError('Failed to load agent data.');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    if (agentId) load(agentId);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [agentId]);

  useEffect(() => {
    const hasRunning = runs.some((run) => run.status === 'running');
    if (hasRunning && !pollRef.current && agentId) {
      pollRef.current = setInterval(() => load(agentId, true), 4000);
    } else if (!hasRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [runs, agentId]);

  const recentTasks = useMemo(
    () =>
      [...tasks].sort((left, right) => {
        return compareApiDatesDesc(left.updated_at || left.created_at, right.updated_at || right.created_at);
      }),
    [tasks],
  );

  const completedRuns = runs.filter((run) => run.status === 'completed').length;
  const statusLabel = runs.some((run) => run.status === 'running')
    ? 'working'
    : agent?.is_active
      ? 'active'
      : 'paused';

  const handleRunHeartbeat = async () => {
    if (!agent) return;
    setRunningHeartbeat(true);
    setError(null);
    try {
      await triggerAgentRun(agent.id);
      setNotice('Heartbeat queued. Refreshing this agent as new activity arrives.');
      setTimeout(() => load(agent.id, true), 1200);
    } catch {
      setError('Failed to run the agent heartbeat.');
    } finally {
      setRunningHeartbeat(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!agent) return;
    setUpdatingStatus(true);
    setError(null);
    try {
      const updated = await updateScheduledAgent(agent.id, { is_active: !agent.is_active });
      setAgent(updated);
    } catch {
      setError('Failed to update agent status.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  const beginEditingInstruction = () => {
    setDraftInstruction(agent?.instruction || '');
    setEditingInstruction(true);
  };

  const cancelEditingInstruction = () => {
    setDraftInstruction('');
    setEditingInstruction(false);
  };

  const saveInstruction = async () => {
    if (!agent) return;
    setSavingInstruction(true);
    setError(null);
    try {
      const updated = await updateScheduledAgent(agent.id, { instruction: draftInstruction });
      setAgent(updated);
      setEditingInstruction(false);
      setNotice('Instruction updated.');
    } catch {
      setError('Failed to save the agent instruction.');
    } finally {
      setSavingInstruction(false);
    }
  };

  const beginEditingSystemPrompt = () => {
    setDraftSystemPrompt(agent?.system_prompt_override || '');
    setEditingSystemPrompt(true);
  };

  const cancelEditingSystemPrompt = () => {
    setDraftSystemPrompt('');
    setEditingSystemPrompt(false);
  };

  const saveSystemPrompt = async () => {
    if (!agent) return;
    setSavingSystemPrompt(true);
    setError(null);
    try {
      const updated = await updateScheduledAgent(agent.id, {
        system_prompt_override: draftSystemPrompt.trim() || null,
      });
      setAgent(updated);
      setEditingSystemPrompt(false);
      setNotice(draftSystemPrompt.trim() ? 'System prompt saved.' : 'System prompt cleared — using default.');
    } catch {
      setError('Failed to save the system prompt.');
    } finally {
      setSavingSystemPrompt(false);
    }
  };

  const beginEditingTickers = () => {
    setDraftTickers(agent?.tickers ?? []);
    setTickerInput('');
    setEditingTickers(true);
  };

  const cancelEditingTickers = () => {
    setDraftTickers([]);
    setTickerInput('');
    setEditingTickers(false);
  };

  const addDraftTicker = () => {
    const v = tickerInput.trim().toUpperCase();
    if (v && !draftTickers.includes(v)) setDraftTickers(prev => [...prev, v]);
    setTickerInput('');
  };

  const saveTickers = async () => {
    if (!agent) return;
    setSavingTickers(true);
    setError(null);
    try {
      const updated = await updateScheduledAgent(agent.id, { tickers: draftTickers });
      setAgent(updated);
      setEditingTickers(false);
      setNotice('Coverage tickers updated.');
    } catch {
      setError('Failed to save tickers.');
    } finally {
      setSavingTickers(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <p className="text-slate-500">{error || 'Agent not found.'}</p>
      </div>
    );
  }

  const meta = roleMetaForAgent(agent);
  const showSubtitle = meta.displayTitle !== agent.name;

  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-[1360px] px-6 py-10 lg:px-10">
        <div className="flex flex-col gap-6 border-b border-slate-200 pb-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl text-white"
              style={{ background: meta.color }}
            >
              <span className="text-xl font-bold">{meta.letter}</span>
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
                  {agent.name}
                </h1>
              </div>
              <p className="mt-2 text-sm text-slate-500">
                {showSubtitle ? `${meta.displayTitle} · ` : ''}Reports to {agent.reports_to_label || 'PM / CIO'}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Schedule: {SCHEDULE_LABELS[agent.schedule_label]}{agent.heartbeat_routine ? ` · ${agent.heartbeat_routine.timezone_name}` : ''}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              to={`/issues?new=1&assignee=${agent.id}`}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900"
            >
              <Plus className="h-4 w-4" />
              Assign Task
            </Link>
            <button
              type="button"
              onClick={handleRunHeartbeat}
              disabled={runningHeartbeat || !agent.is_active}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {runningHeartbeat ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run Heartbeat
            </button>
            <button
              type="button"
              onClick={handleToggleStatus}
              disabled={updatingStatus}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {updatingStatus ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : agent.is_active ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {agent.is_active ? 'Pause' : 'Resume'}
            </button>
            <span
              className={`inline-flex items-center rounded-full px-3 py-2 text-sm font-medium ${
                statusLabel === 'paused'
                  ? 'bg-slate-200 text-slate-700'
                  : statusLabel === 'working'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-emerald-100 text-emerald-700'
              }`}
            >
              {statusLabel}
            </span>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-6 border-b border-slate-200">
          {[
            ['dashboard', 'Dashboard'],
            ['instructions', 'Instructions'],
            ['system_prompt', 'System Prompt'],
          ].map(([key, label]) => {
            const isActive = tab === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key as AgentTab)}
                className="border-b-2 px-1 pb-3 text-base font-medium transition"
                style={{
                  borderColor: isActive ? '#0F172A' : 'transparent',
                  color: isActive ? '#0F172A' : '#6B7280',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {error && (
          <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {notice && (
          <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {notice}
          </div>
        )}

        {tab === 'dashboard' && (
          <div className="mt-8 space-y-8">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4">
                <p className="text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
                  {recentTasks.length}
                </p>
                <p className="mt-1 text-sm text-slate-500">Recent assigned issues</p>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4">
                <p className="text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
                  {completedRuns}
                </p>
                <p className="mt-1 text-sm text-slate-500">Completed runs</p>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4">
                <p className="text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
                  {agent.tickers.length || 1}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {agent.tickers.length > 0 ? 'Coverage tickers' : 'Coverage scope'}
                </p>
              </div>
            </div>

            <div className="grid gap-8 xl:grid-cols-[1.35fr,0.65fr]">
              <section className="rounded-[28px] border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                      Recent Activity
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Issues this agent has been assigned or asked to work through.
                    </p>
                  </div>
                  <Link to="/issues" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900">
                    See all
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>

                {recentTasks.length === 0 ? (
                  <div className="px-5 py-14 text-center text-sm text-slate-500">
                    No recent assigned issues yet.
                  </div>
                ) : (
                  <div>
                    {recentTasks.slice(0, 10).map((task) => (
                      <RecentIssueRow key={task.id} task={task} />
                    ))}
                  </div>
                )}
              </section>

              <section className="space-y-6">
                <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="border-b border-slate-100 pb-4">
                    <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                      Coverage
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Current scope and execution rhythm for this analyst seat.
                    </p>
                  </div>

                  <div className="mt-5 grid gap-4 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Watching</p>
                        {!editingTickers ? (
                          <button
                            onClick={beginEditingTickers}
                            className="text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors"
                          >
                            Edit
                          </button>
                        ) : (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={cancelEditingTickers}
                              className="text-xs font-medium text-slate-400 hover:text-slate-700 transition-colors"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={saveTickers}
                              disabled={savingTickers}
                              className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50 transition-colors"
                            >
                              {savingTickers && <Loader2 className="h-3 w-3 animate-spin" />}
                              Save
                            </button>
                          </div>
                        )}
                      </div>

                      {editingTickers ? (
                        <div className="mt-2 space-y-2">
                          <div className="flex flex-wrap gap-1.5">
                            {draftTickers.map(ticker => (
                              <span key={ticker} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 pl-2 pr-1 py-0.5 font-mono text-xs text-slate-700">
                                {ticker}
                                <button
                                  onClick={() => setDraftTickers(prev => prev.filter(t => t !== ticker))}
                                  className="text-slate-400 hover:text-red-500 transition-colors"
                                >
                                  ×
                                </button>
                              </span>
                            ))}
                          </div>
                          <div className="flex gap-1.5">
                            <input
                              value={tickerInput}
                              onChange={e => setTickerInput(e.target.value.toUpperCase())}
                              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addDraftTicker(); } }}
                              placeholder="Add ticker (e.g. AAPL)"
                              className="h-8 w-36 rounded-lg border border-slate-200 bg-white px-2.5 font-mono text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-400"
                            />
                            <button
                              onClick={addDraftTicker}
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
                            >
                              <Plus className="h-3 w-3" />
                              Add
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {(agent.tickers.length > 0 ? agent.tickers : ['GENERAL']).map((ticker: string) => (
                            <span key={ticker} className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-700">
                              {ticker}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Cadence</p>
                      <p className="mt-2 text-sm text-slate-700">{SCHEDULE_LABELS[agent.schedule_label]}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Last run</p>
                      <p className="mt-2 text-sm text-slate-700">{formatApiDateTime(agent.last_run_at)}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Next run</p>
                      <p className="mt-2 text-sm text-slate-700">{formatApiDateTime(agent.next_run_at)}</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="border-b border-slate-100 pb-4">
                    <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                      Recent Heartbeats
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">Latest wake-ups and execution context.</p>
                  </div>

                  {heartbeatRuns.length === 0 ? (
                    <div className="py-10 text-center text-sm text-slate-500">
                      No heartbeat log yet.
                    </div>
                  ) : (
                    <div className="mt-5 space-y-3">
                      {heartbeatRuns.slice(0, 4).map((run) => (
                        <MiniHeartbeatRow key={run.id} run={run} />
                      ))}
                    </div>
                  )}
                </div>
              </section>
            </div>

            <section className="rounded-[28px] border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-4">
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                  Recent Runs
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Latest research passes, findings, and run outcomes for this agent.
                </p>
              </div>

              <div className="p-5">
                {runs.length === 0 ? (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-12 text-center text-sm text-slate-500">
                    No runs yet.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {runs.map((run) => (
                      <RunRow key={run.id} run={run} />
                    ))}
                  </div>
                )}
              </div>
            </section>
          </div>
        )}

        {tab === 'instructions' && (
          <div className="mt-8 grid gap-6 xl:grid-cols-[280px,1fr]">
            <aside className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
              <div className="border-b border-slate-100 px-2 pb-3">
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                  Instructions
                </h2>
                <p className="mt-1 text-sm text-slate-500">This agent's editable operating brief.</p>
              </div>

              <div className="mt-3">
                <div
                  className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3"
                >
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Instruction</p>
                    <p className="mt-1 text-xs text-slate-500">INSTRUCTION.md</p>
                  </div>
                  <FileText className="h-4 w-4 text-slate-400" />
                </div>
              </div>
            </aside>

            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                    Instruction
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">INSTRUCTION.md</p>
                </div>
                {editingInstruction ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={cancelEditingInstruction}
                      disabled={savingInstruction}
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={saveInstruction}
                      disabled={savingInstruction}
                      className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingInstruction ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Save
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={beginEditingInstruction}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                  >
                    Edit
                  </button>
                )}
              </div>

              {editingInstruction ? (
                <div className="mt-6">
                  <textarea
                    value={draftInstruction}
                    onChange={(event) => setDraftInstruction(event.target.value)}
                    className="min-h-[560px] w-full rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4 font-mono text-sm leading-7 text-slate-800 outline-none transition focus:border-slate-300"
                    spellCheck={false}
                  />
                </div>
              ) : (
                <div className="prose prose-slate mt-6 max-w-none prose-headings:tracking-[-0.02em] prose-p:text-slate-700 prose-li:text-slate-700">
                  {agent.instruction?.trim() ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {agent.instruction}
                    </ReactMarkdown>
                  ) : (
                    <p className="text-sm text-slate-500">No instruction defined for this agent yet.</p>
                  )}
                </div>
              )}
            </section>
          </div>
        )}

        {tab === 'system_prompt' && (
          <div className="mt-8 grid gap-6 xl:grid-cols-[280px,1fr]">
            <aside className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
              <div className="border-b border-slate-100 px-2 pb-3">
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                  System Prompt
                </h2>
                <p className="mt-1 text-sm text-slate-500">Override the default role behaviour entirely.</p>
              </div>
              <div className="mt-3 space-y-2 px-2 text-sm text-slate-500">
                <p>
                  When set, this prompt <strong className="text-slate-700">replaces</strong> the built-in role lens, mandate, and focus
                  questions. The agent still receives live financial data and web research — your prompt controls how it reasons and
                  what it produces.
                </p>
                <p>Leave blank to use the default role behaviour.</p>
              </div>
            </aside>

            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                    System Prompt
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {agent?.system_prompt_override?.trim()
                      ? 'Custom prompt active — default role is overridden.'
                      : 'No override set — using default role.'}
                  </p>
                </div>
                {editingSystemPrompt ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={cancelEditingSystemPrompt}
                      disabled={savingSystemPrompt}
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={saveSystemPrompt}
                      disabled={savingSystemPrompt}
                      className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingSystemPrompt ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Save
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={beginEditingSystemPrompt}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                  >
                    {agent?.system_prompt_override?.trim() ? 'Edit' : 'Add override'}
                  </button>
                )}
              </div>

              {editingSystemPrompt ? (
                <div className="mt-6">
                  <p className="mb-3 text-xs text-slate-500">
                    Write your prompt as plain text or markdown. The agent will receive this followed by the ticker, company name, financial data, and web research. Clear the field and save to revert to the default role.
                  </p>
                  <textarea
                    value={draftSystemPrompt}
                    onChange={(e) => setDraftSystemPrompt(e.target.value)}
                    placeholder={`Example:\nYou are a forensic accounting specialist focused on earnings quality.\nFor every ticker, check for revenue recognition red flags, working capital deterioration, and accrual ratio trends.\nAlways produce a numeric accrual ratio and flag any YoY change greater than 3pp.`}
                    className="min-h-[480px] w-full rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4 font-mono text-sm leading-7 text-slate-800 outline-none transition focus:border-slate-300"
                    spellCheck={false}
                  />
                </div>
              ) : (
                <div className="mt-6">
                  {agent?.system_prompt_override?.trim() ? (
                    <pre className="whitespace-pre-wrap rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4 font-mono text-sm leading-7 text-slate-800">
                      {agent.system_prompt_override}
                    </pre>
                  ) : (
                    <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 px-5 py-10 text-center">
                      <p className="text-sm font-medium text-slate-500">No system prompt override set.</p>
                      <p className="mt-1 text-xs text-slate-400">This agent is using its built-in role definition.</p>
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
