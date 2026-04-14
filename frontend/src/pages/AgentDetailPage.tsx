import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Zap, Pause, Play, Trash2, Clock, AlertTriangle,
  CheckCircle, XCircle, Loader2, ChevronDown, ChevronUp
} from 'lucide-react';
import {
  getScheduledAgent, getAgentRuns, triggerAgentRun,
  updateScheduledAgent, deleteScheduledAgent
} from '../api';
import { ScheduledAgent, AgentRun, AlertLevel } from '../types';

const TEMPLATE_META: Record<string, { label: string; color: string; bg: string }> = {
  earnings_watcher:    { label: 'Earnings Watcher',    color: '#F59E0B', bg: '#FEF3C7' },
  market_pulse:        { label: 'Market Pulse',        color: '#3B82F6', bg: '#DBEAFE' },
  thesis_guardian:     { label: 'Thesis Guardian',     color: '#10B981', bg: '#D1FAE5' },
  portfolio_heartbeat: { label: 'Portfolio Heartbeat', color: '#8B5CF6', bg: '#EDE9FE' },
  arena_analyst:       { label: 'Arena Analyst',       color: '#EF4444', bg: '#FEE2E2' },
};

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market:    'Weekdays 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly:       'Monthly',
};

const ALERT_CONFIG: Record<AlertLevel, { label: string; color: string; bg: string; Icon: any }> = {
  high:   { label: 'Alert',     color: '#EF4444', bg: '#FEE2E2', Icon: AlertTriangle },
  medium: { label: 'New',       color: '#F59E0B', bg: '#FEF3C7', Icon: AlertTriangle },
  low:    { label: 'Update',    color: '#10B981', bg: '#D1FAE5', Icon: CheckCircle   },
  none:   { label: 'No change', color: '#9CA3AF', bg: '#F1F5F9', Icon: CheckCircle   },
};

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function formatDuration(startIso?: string, endIso?: string): string {
  if (!startIso || !endIso) return '—';
  const secs = Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function RunRow({ run }: { run: AgentRun }) {
  const [expanded, setExpanded] = useState(false);
  const alert = ALERT_CONFIG[run.alert_level as AlertLevel] || ALERT_CONFIG.none;
  const { Icon } = alert;

  return (
    <div className="border border-slate-200 rounded-2xl overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-4 px-5 py-4 bg-white hover:bg-slate-50 transition-colors duration-150 text-left"
      >
        {/* Status */}
        <div className="flex-shrink-0">
          {run.status === 'running' ? (
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
          ) : run.status === 'failed' ? (
            <XCircle className="w-4 h-4 text-red-500" />
          ) : (
            <Icon className="w-4 h-4" style={{ color: alert.color }} />
          )}
        </div>

        {/* Alert badge */}
        <span
          className="flex-shrink-0 text-xs font-semibold px-2 py-0.5 rounded-lg"
          style={{ background: alert.bg, color: alert.color }}
        >
          {alert.label}
        </span>

        {/* Summary */}
        <p className="flex-1 text-sm text-slate-700 truncate text-left">
          {run.findings_summary || run.error || 'Running…'}
        </p>

        {/* Meta */}
        <div className="flex items-center gap-4 flex-shrink-0 text-xs text-slate-400">
          {run.material_change && (
            <span className="text-amber-600 font-medium">Material change</span>
          )}
          <span>{formatDate(run.started_at)}</span>
          <span>{formatDuration(run.started_at, run.completed_at)}</span>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-slate-100 bg-white">
          {/* Meta row */}
          <div className="flex flex-wrap gap-4 pt-4 pb-3 text-xs text-slate-500">
            {run.tickers_analyzed?.length > 0 && (
              <span><span className="font-semibold text-slate-700">Tickers: </span>{run.tickers_analyzed.join(', ')}</span>
            )}
            {run.agents_used?.length > 0 && (
              <span><span className="font-semibold text-slate-700">Agents: </span>{run.agents_used.join(', ')}</span>
            )}
          </div>

          {/* Key findings */}
          {run.key_findings?.length > 0 && (
            <div className="mb-4 pb-4 border-b border-slate-100">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Key findings</p>
              <ul className="space-y-1.5">
                {run.key_findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="text-emerald-500 mt-0.5 flex-shrink-0">·</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Report / error / running */}
          {run.report ? (
            <div
              className="prose prose-sm max-w-none text-slate-700 leading-relaxed"
              style={{ fontSize: '13px', lineHeight: '1.65' }}
              dangerouslySetInnerHTML={{ __html: markdownToHtml(run.report) }}
            />
          ) : run.error ? (
            <div className="p-4 bg-red-50 rounded-xl text-sm text-red-700">
              <p className="font-semibold mb-1">Run failed</p>
              <p>{run.error}</p>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-slate-500 py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Research in progress — refreshing automatically…</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Minimal markdown → html (headings, bold, bullets, paragraphs)
function markdownToHtml(md: string): string {
  return md
    .replace(/^### (.+)$/gm, '<h3 style="font-size:14px;font-weight:700;color:#0F172A;margin:16px 0 6px;letter-spacing:-0.01em">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:15px;font-weight:700;color:#0F172A;margin:20px 0 8px;letter-spacing:-0.02em">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:17px;font-weight:700;color:#0F172A;margin:24px 0 10px;letter-spacing:-0.02em">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li style="margin-bottom:4px">$1</li>')
    .replace(/(<li.*<\/li>\n?)+/g, s => `<ul style="padding-left:20px;margin:8px 0">${s}</ul>`)
    .replace(/\n\n/g, '</p><p style="margin:10px 0">')
    .replace(/^(?!<[hul])(.+)$/gm, '$1')
    .replace(/\n/g, '<br>');
}

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();

  const [agent, setAgent] = useState<ScheduledAgent | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningNow, setRunningNow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (agentId) load(agentId);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [agentId]);

  // Start polling whenever a run is in "running" state; stop when all complete
  useEffect(() => {
    const hasRunning = runs.some(r => r.status === 'running');
    if (hasRunning && !pollRef.current && agentId) {
      pollRef.current = setInterval(() => load(agentId, true), 4000);
    } else if (!hasRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [runs, agentId]);

  const load = async (id: string, silent = false) => {
    try {
      const [a, r] = await Promise.all([getScheduledAgent(id), getAgentRuns(id, 20)]);
      setAgent(a);
      setRuns(r);
      if (!silent) setError(null);
    } catch {
      if (!silent) setError('Failed to load agent data.');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleRunNow = async () => {
    if (!agent) return;
    setRunningNow(true);
    try {
      await triggerAgentRun(agent.id);
      // Short delay then refresh — polling will take over if still running
      setTimeout(() => { load(agent.id, true); setRunningNow(false); }, 1500);
    } catch {
      setRunningNow(false);
      setError('Failed to trigger run.');
    }
  };

  const handleToggle = async () => {
    if (!agent) return;
    const updated = await updateScheduledAgent(agent.id, { is_active: !agent.is_active });
    setAgent(updated);
  };

  const handleDelete = async () => {
    if (!agent || !confirm(`Delete "${agent.name}"?`)) return;
    await deleteScheduledAgent(agent.id);
    navigate('/scheduled-agents');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 pl-20 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="min-h-screen bg-slate-50 pl-20 flex items-center justify-center">
        <p className="text-slate-500">{error || 'Agent not found.'}</p>
      </div>
    );
  }

  const meta = TEMPLATE_META[agent.template] || TEMPLATE_META.earnings_watcher;

  return (
    <div className="min-h-screen bg-slate-50 pl-20" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="max-w-3xl mx-auto px-8 py-12">

        {/* Back */}
        <button
          onClick={() => navigate('/scheduled-agents')}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-8 transition-colors duration-150"
        >
          <ChevronLeft className="w-4 h-4" />
          All agents
        </button>

        {/* Agent header */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center text-xl font-bold flex-shrink-0"
                style={{ background: meta.bg, color: meta.color }}
              >
                {meta.label[0]}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-0.5">
                  <h1 className="text-xl font-bold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
                    {agent.name}
                  </h1>
                  <div
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${agent.is_active ? 'bg-emerald-400' : 'bg-slate-300'}`}
                    style={agent.is_active ? { boxShadow: '0 0 0 3px #D1FAE5' } : {}}
                  />
                </div>
                <span className="text-sm font-medium" style={{ color: meta.color }}>{meta.label}</span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={handleRunNow}
                disabled={runningNow}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold bg-emerald-50 text-emerald-700 rounded-xl hover:bg-emerald-100 transition-colors duration-150 disabled:opacity-50"
              >
                {runningNow ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                Run now
              </button>
              <button
                onClick={handleToggle}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold bg-slate-100 text-slate-700 rounded-xl hover:bg-slate-200 transition-colors duration-150"
              >
                {agent.is_active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                {agent.is_active ? 'Pause' : 'Resume'}
              </button>
              <button
                onClick={handleDelete}
                className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors duration-150"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Config grid */}
          <div className="grid grid-cols-2 gap-4 mt-5 pt-5 border-t border-slate-100">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Schedule</p>
              <p className="text-sm text-slate-700 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                {SCHEDULE_LABELS[agent.schedule_label]}
              </p>
            </div>
            {agent.tickers.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Watching</p>
                <div className="flex flex-wrap gap-1.5">
                  {agent.tickers.map(t => (
                    <span key={t} className="text-xs font-semibold px-2 py-0.5 bg-slate-100 text-slate-600 rounded-lg">{t}</span>
                  ))}
                </div>
              </div>
            )}
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Last run</p>
              <p className="text-sm text-slate-700">{formatDate(agent.last_run_at)}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Next run</p>
              <p className="text-sm text-slate-700">{formatDate(agent.next_run_at)}</p>
            </div>
          </div>

          {/* Instruction */}
          {agent.instruction && (
            <div className="mt-5 pt-5 border-t border-slate-100">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Your instruction</p>
              <p className="text-sm text-slate-600 leading-relaxed">{agent.instruction}</p>
            </div>
          )}
        </div>

        {/* Run history */}
        <h2 className="text-base font-semibold text-slate-900 mb-4" style={{ letterSpacing: '-0.01em' }}>
          Run history
        </h2>

        {runs.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center">
            <p className="text-sm text-slate-400">No runs yet.</p>
            <button
              onClick={handleRunNow}
              className="mt-4 flex items-center gap-2 mx-auto px-4 py-2 text-sm font-semibold bg-slate-900 text-white rounded-xl hover:bg-slate-800 transition-colors duration-150"
            >
              <Zap className="w-4 h-4" />
              Trigger first run
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map(run => (
              <RunRow key={run.id} run={run} />
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
