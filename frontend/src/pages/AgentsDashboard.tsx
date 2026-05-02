import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Pause, Trash2, ChevronRight, Clock, Loader2, Zap, FilePlus2 } from 'lucide-react';
import { getScheduledAgents, deleteScheduledAgent, updateScheduledAgent, triggerAgentRun, getHireProposals, approveHireProposal, rejectHireProposal } from '../api';
import { ScheduledAgent, HireProposal } from '../types';
import { getRoleMeta, roleMetaForAgent } from '../agentRoles';

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market:    'Weekdays 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly:       'Monthly',
};


function formatRelativeTime(iso?: string): string {
  if (!iso) return 'Never run';
  const diff = Date.now() - new Date(iso).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (mins < 1)   return 'Just now';
  if (mins < 60)  return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
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
      className="group bg-white border border-slate-200 rounded-2xl p-5 cursor-pointer hover:border-slate-300 hover:shadow-md transition-all duration-200"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-start gap-3 min-w-0">
          {/* Template badge */}
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 text-sm font-bold"
            style={{ background: meta.bg, color: meta.color }}
          >
            {meta.letter}
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-900 text-sm truncate" style={{ letterSpacing: '-0.01em' }}>
              {agent.name}
            </h3>
            <span
              className="text-xs font-medium"
              style={{ color: meta.color }}
            >
              {meta.displayTitle}
            </span>
            <p className="text-xs text-slate-400 mt-0.5">
              Reports to {agent.reports_to_label || 'CIO'}
            </p>
          </div>
        </div>

        {/* Status dot */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <div
            className={`w-2 h-2 rounded-full ${agent.is_active ? 'bg-emerald-400' : 'bg-slate-300'}`}
            style={agent.is_active ? { boxShadow: '0 0 0 3px #D1FAE5' } : {}}
          />
          <span className="text-xs text-slate-400">{agent.is_active ? 'Active' : 'Paused'}</span>
        </div>
      </div>

      {/* Tickers */}
      {agent.tickers.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {agent.tickers.slice(0, 5).map(t => (
            <span
              key={t}
              className="text-xs font-semibold px-2 py-0.5 rounded-lg"
              style={{ background: '#F1F5F9', color: '#475569' }}
            >
              {t}
            </span>
          ))}
          {agent.tickers.length > 5 && (
            <span className="text-xs text-slate-400">+{agent.tickers.length - 5}</span>
          )}
        </div>
      )}

      {/* Last run summary */}
      {agent.last_run_summary ? (
        <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-3">
          {agent.last_run_summary}
        </p>
      ) : (
        <p className="text-xs text-slate-400 italic mb-3">No runs yet</p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-100">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock className="w-3.5 h-3.5" />
          <span className="text-xs">{SCHEDULE_LABELS[agent.schedule_label]}</span>
          {agent.last_run_at && (
            <>
              <span className="text-slate-300">·</span>
              <span className="text-xs">{formatRelativeTime(agent.last_run_at)}</span>
            </>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <button
            onClick={handleRunNow}
            className="p-1.5 rounded-lg hover:bg-emerald-50 text-slate-400 hover:text-emerald-600 transition-colors duration-150"
            title="Run now"
          >
            {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleToggle}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors duration-150"
            title={agent.is_active ? 'Pause' : 'Resume'}
          >
            {agent.is_active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleDelete}
            className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors duration-150"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>

        <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-colors duration-150 flex-shrink-0" />
      </div>
    </div>
  );
}

function EmptyState() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg mb-5">
        <FilePlus2 className="w-8 h-8 text-white" />
      </div>
      <h2 className="text-xl font-semibold text-slate-900 mb-2" style={{ letterSpacing: '-0.02em' }}>
        No agents yet
      </h2>
      <p className="text-slate-500 text-sm max-w-xs mb-6 leading-relaxed">
        Open a new issue first. Agent cards will appear here as they are created and approved.
      </p>
      <button
        onClick={() => navigate('/issues?new=1')}
        className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-semibold rounded-xl hover:bg-slate-800 transition-colors duration-150"
      >
        <FilePlus2 className="w-4 h-4" />
        New Issue
      </button>
    </div>
  );
}

function PendingProposalCard({
  proposal,
  onApprove,
  onReject,
}: {
  proposal: HireProposal;
  onApprove: (proposalId: string) => void;
  onReject: (proposalId: string) => void;
}) {
  const meta = getRoleMeta({
    role_key: proposal.role_key,
    role_title: proposal.role_title,
    template: proposal.template,
  });

  return (
    <div className="bg-white border border-emerald-200 rounded-2xl p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 text-sm font-bold"
            style={{ background: meta.bg, color: meta.color }}
          >
            {meta.letter}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Pending Hire Proposal</p>
            <h3 className="font-semibold text-slate-900 text-sm truncate" style={{ letterSpacing: '-0.01em' }}>
              {proposal.name}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">{meta.displayTitle} · Reports to {proposal.reports_to_label || 'CIO'}</p>
            {proposal.description && (
              <p className="text-xs text-slate-500 mt-2 leading-relaxed">{proposal.description}</p>
            )}
            {proposal.tickers.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {proposal.tickers.map((ticker) => (
                  <span key={ticker} className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-slate-100 text-slate-700">
                    {ticker}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => onReject(proposal.id)}
            className="px-3 py-1.5 rounded-xl border border-slate-200 text-slate-600 text-xs font-medium hover:bg-slate-50 transition-colors"
          >
            Decline
          </button>
          <button
            onClick={() => onApprove(proposal.id)}
            className="px-3 py-1.5 rounded-xl bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 transition-colors"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AgentsDashboard() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [pendingProposals, setPendingProposals] = useState<HireProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: 'error' | 'success' } | null>(null);

  const showToast = (msg: string, type: 'error' | 'success' = 'error') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    try {
      const [agentData, proposalData] = await Promise.all([
        getScheduledAgents(),
        getHireProposals('pending'),
      ]);
      setAgents(agentData);
      setPendingProposals(proposalData);
    } catch {
      showToast('Could not load team state — backend may be offline.');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this agent?')) return;
    try {
      await deleteScheduledAgent(id);
      setAgents(prev => prev.filter(a => a.id !== id));
    } catch {
      showToast('Failed to delete agent. Please try again.');
    }
  };

  const handleToggle = async (id: string, active: boolean) => {
    try {
      const updated = await updateScheduledAgent(id, { is_active: active });
      setAgents(prev => prev.map(a => a.id === id ? updated : a));
    } catch {
      showToast('Failed to update agent status.');
    }
  };

  const handleRunNow = async (id: string) => {
    try {
      await triggerAgentRun(id);
      showToast('Run started — check Inbox for results.', 'success');
      setTimeout(load, 2000);
    } catch {
      showToast('Failed to trigger run. Please try again.');
    }
  };

  const handleApproveProposal = async (proposalId: string) => {
    try {
      const result = await approveHireProposal(proposalId);
      setPendingProposals(prev => prev.filter(p => p.id !== proposalId));
      showToast(`${result.agent.name} approved and added to the team.`, 'success');
      await load();
    } catch {
      showToast('Failed to approve hire proposal.');
    }
  };

  const handleRejectProposal = async (proposalId: string) => {
    try {
      await rejectHireProposal(proposalId);
      setPendingProposals(prev => prev.filter(p => p.id !== proposalId));
      showToast('Hire proposal declined.', 'success');
    } catch {
      showToast('Failed to decline hire proposal.');
    }
  };

  const activeCount  = agents.filter(a => a.is_active).length;
  const pausedCount  = agents.filter(a => !a.is_active).length;

  return (
    <div className="min-h-screen bg-slate-50" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium text-white transition-all duration-300 ${toast.type === 'error' ? 'bg-red-600' : 'bg-emerald-600'}`}>
          {toast.msg}
        </div>
      )}
      <div className="mx-auto w-full max-w-6xl px-6 py-12 lg:px-10">

        {/* Header */}
        <div className="flex items-center justify-between mb-10">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 mb-1" style={{ letterSpacing: '-0.03em' }}>
              Dashboard
            </h1>
            <p className="text-slate-500 text-sm">
              {agents.length === 0
                ? 'Agent cards and pending approvals'
                : `${activeCount} active · ${pausedCount} paused`}
            </p>
          </div>
          <button
            onClick={() => navigate('/issues?new=1')}
            className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-semibold rounded-xl hover:bg-slate-800 transition-colors duration-200 shadow-sm"
          >
            <FilePlus2 className="w-4 h-4" />
            New Issue
          </button>
        </div>

        {pendingProposals.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
                  Pending Agent Approvals
                </h2>
                <p className="text-sm text-slate-500">
                  Suggested agents waiting for approval.
                </p>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700">
                {pendingProposals.length} pending
              </span>
            </div>
            <div className="grid grid-cols-1 gap-4">
              {pendingProposals.map((proposal) => (
                <PendingProposalCard
                  key={proposal.id}
                  proposal={proposal}
                  onApprove={handleApproveProposal}
                  onReject={handleRejectProposal}
                />
              ))}
            </div>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
          </div>
        ) : agents.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            {/* Stats bar */}
            <div className="grid grid-cols-3 gap-4 mb-8">
              {[
                { label: 'Total agents', value: agents.length },
                { label: 'Active',       value: activeCount },
                { label: 'Last run',     value: formatRelativeTime(agents.filter(a => a.last_run_at).sort((a, b) => new Date(b.last_run_at!).getTime() - new Date(a.last_run_at!).getTime())[0]?.last_run_at) },
              ].map(stat => (
                <div key={stat.label} className="bg-white border border-slate-200 rounded-2xl px-5 py-4">
                  <p className="text-2xl font-bold text-slate-900 mb-0.5" style={{ letterSpacing: '-0.03em' }}>{stat.value}</p>
                  <p className="text-xs text-slate-500 font-medium">{stat.label}</p>
                </div>
              ))}
            </div>

            {/* Agent grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {agents.map(agent => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onDelete={handleDelete}
                  onToggle={handleToggle}
                  onRunNow={handleRunNow}
                />
              ))}
            </div>

            {/* Inbox link */}
            <div className="mt-8 text-center">
              <button
                onClick={() => navigate('/inbox')}
                className="text-sm text-emerald-600 hover:text-emerald-700 font-medium transition-colors duration-150"
              >
                View all run reports →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
