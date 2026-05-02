import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowRight,
  Briefcase,
  Loader2,
  Plus,
  Pause,
  Play,
  UserPlus,
} from 'lucide-react';
import {
  approveHireProposal,
  getCeoAgentPage,
  rejectHireProposal,
  runCeoHeartbeat,
  updateCeoInstructionDoc,
  updateCeoAgentStatus,
  type CeoAgentPageData,
  type CeoInstructionDoc,
  type CeoRecentIssue,
  type TaskPriority,
  type TaskStatus,
} from '../api';
import { getRoleMeta } from '../agentRoles';
import type { HireProposal } from '../types';

type CeoTab = 'dashboard' | 'instructions';

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

function formatRelativeTime(iso?: string | null): string {
  if (!iso) return 'Just now';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

function displayTicker(ticker: string): string {
  return ticker === 'GENERAL' ? 'General' : ticker;
}

function RecentIssueRow({ issue }: { issue: CeoRecentIssue }) {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => navigate(`/issues/${issue.id}`)}
      className="flex w-full items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 text-left transition hover:bg-slate-50"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_TONE[issue.status]}`}>
            {issue.status.replace('_', ' ')}
          </span>
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${PRIORITY_TONE[issue.priority]}`}>
            {issue.priority}
          </span>
          <span className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500">
            {displayTicker(issue.ticker)}
          </span>
          {issue.project_title && (
            <span className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500">
              {issue.project_title}
            </span>
          )}
        </div>
        <p className="mt-3 text-base font-semibold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
          {issue.title}
        </p>
        <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-slate-500">
          {issue.notes?.trim() || 'No issue description provided.'}
        </p>
      </div>
      <div className="flex-shrink-0 text-right text-xs text-slate-400">
        <div>{formatRelativeTime(issue.updated_at || issue.created_at)}</div>
        <div className="mt-2 text-slate-500">{issue.triggered_by === 'manual_pm_review' ? 'CEO review' : 'Intake'}</div>
      </div>
    </button>
  );
}

function PendingHireRow({
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
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Pending hire</p>
          <h3 className="mt-2 text-sm font-semibold text-slate-900">{proposal.name}</h3>
          <p className="mt-1 text-xs text-slate-600">
            {meta.displayTitle} · Reports to {proposal.reports_to_label || 'CEO'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onReject(proposal.id)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
          >
            Decline
          </button>
          <button
            type="button"
            onClick={() => onApprove(proposal.id)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700"
          >
            <UserPlus className="h-3.5 w-3.5" />
            Approve
          </button>
        </div>
      </div>
      {proposal.rationale && (
        <p className="mt-3 text-xs leading-relaxed text-slate-600">{proposal.rationale}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {proposal.tickers.map((ticker) => (
          <span key={ticker} className="rounded-lg border border-slate-200 bg-white px-2 py-0.5 font-mono text-xs text-slate-700">
            {ticker}
          </span>
        ))}
      </div>
      {proposal.source_task_id && proposal.source_task_title && (
        <Link
          to={`/issues/${proposal.source_task_id}`}
          className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-700 hover:text-emerald-800"
        >
          Source issue
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </div>
  );
}

export default function CioPage() {
  const [tab, setTab] = useState<CeoTab>('dashboard');
  const [data, setData] = useState<CeoAgentPageData | null>(null);
  const [selectedDocKey, setSelectedDocKey] = useState<string>('system');
  const [editingDocKey, setEditingDocKey] = useState<string | null>(null);
  const [draftContent, setDraftContent] = useState<string>('');
  const [savingDocKey, setSavingDocKey] = useState<string | null>(null);
  const [runningHeartbeat, setRunningHeartbeat] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [heartbeatNotice, setHeartbeatNotice] = useState<{
    message: string;
    taskId: string | null;
    taskTitle: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getCeoAgentPage(20);
      setData(result);
      if (!result.instructions.some((doc) => doc.key === selectedDocKey) && result.instructions.length > 0) {
        setSelectedDocKey(result.instructions[0].key);
      }
    } catch {
      setError('Could not load the CEO page.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const selectedDoc = useMemo<CeoInstructionDoc | null>(() => {
    if (!data) return null;
    return data.instructions.find((doc) => doc.key === selectedDocKey) || data.instructions[0] || null;
  }, [data, selectedDocKey]);

  const beginEditingInstruction = () => {
    if (!selectedDoc) return;
    setEditingDocKey(selectedDoc.key);
    setDraftContent(selectedDoc.content);
  };

  const cancelEditingInstruction = () => {
    setEditingDocKey(null);
    setDraftContent('');
  };

  const saveInstruction = async () => {
    if (!selectedDoc || editingDocKey !== selectedDoc.key) return;
    setSavingDocKey(selectedDoc.key);
    setError(null);
    try {
      const updated = await updateCeoInstructionDoc(selectedDoc.key, draftContent);
      setData((current) => {
        if (!current) return current;
        return {
          ...current,
          instructions: current.instructions.map((doc) =>
            doc.key === updated.key ? updated : doc,
          ),
        };
      });
      setEditingDocKey(null);
      setDraftContent('');
    } catch {
      setError('Failed to save the CEO instruction file.');
    } finally {
      setSavingDocKey(null);
    }
  };

  const handleApprove = async (proposalId: string) => {
    try {
      await approveHireProposal(proposalId);
      await load();
    } catch {
      setError('Failed to approve the hire proposal.');
    }
  };

  const handleReject = async (proposalId: string) => {
    try {
      await rejectHireProposal(proposalId);
      await load();
    } catch {
      setError('Failed to decline the hire proposal.');
    }
  };

  const handleRunHeartbeat = async () => {
    setRunningHeartbeat(true);
    setError(null);
    try {
      const result = await runCeoHeartbeat();
      setHeartbeatNotice({
        message: result.message,
        taskId: result.task_id,
        taskTitle: result.task_title,
      });
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to run the CEO heartbeat.');
    } finally {
      setRunningHeartbeat(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!data) return;
    setUpdatingStatus(true);
    setError(null);
    try {
      const nextStatus = data.agent.status === 'paused' ? 'idle' : 'paused';
      const updated = await updateCeoAgentStatus(nextStatus);
      setData((current) =>
        current
          ? {
              ...current,
              agent: {
                ...current.agent,
                status: updated.status,
                last_heartbeat_at: updated.last_heartbeat_at,
                last_heartbeat_message: updated.last_heartbeat_message,
                last_reviewed_task_id: updated.last_reviewed_task_id,
              },
            }
          : current,
      );
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update CEO status.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-[1360px] px-6 py-10 lg:px-10">
        <div className="flex flex-col gap-6 border-b border-slate-200 pb-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-white">
              <Briefcase className="h-6 w-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
                  CEO
                </h1>
              </div>
              <p className="mt-2 text-sm text-slate-500">
                Firm lead · aliases: {data?.agent.aliases.join(', ') || 'CIO, PM / CIO'}
              </p>
              {data?.agent.model && (
                <p className="mt-1 text-xs text-slate-400">Model: {data.agent.model}</p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              to="/issues?new=1"
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900"
            >
              <Plus className="h-4 w-4" />
              Assign Task
            </Link>
            <button
              type="button"
              onClick={handleRunHeartbeat}
              disabled={runningHeartbeat || data?.agent.status === 'paused'}
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
              ) : data?.agent.status === 'paused' ? (
                <Play className="h-4 w-4" />
              ) : (
                <Pause className="h-4 w-4" />
              )}
              {data?.agent.status === 'paused' ? 'Resume' : 'Pause'}
            </button>
            <span
              className={`inline-flex items-center rounded-full px-3 py-2 text-sm font-medium ${
                data?.agent.status === 'paused'
                  ? 'bg-slate-200 text-slate-700'
                  : 'bg-amber-100 text-amber-700'
              }`}
            >
              {data?.agent.status || 'idle'}
            </span>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-6 border-b border-slate-200">
          {[
            ['dashboard', 'Dashboard'],
            ['instructions', 'Instructions'],
          ].map(([key, label]) => {
            const isActive = tab === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key as CeoTab)}
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

        {heartbeatNotice && (
          <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <div>{heartbeatNotice.message}</div>
            {heartbeatNotice.taskId && heartbeatNotice.taskTitle && (
              <Link
                to={`/issues/${heartbeatNotice.taskId}`}
                className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800"
              >
                Open reviewed issue: {heartbeatNotice.taskTitle}
                <ArrowRight className="h-4 w-4" />
              </Link>
            )}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        )}

        {!loading && data && tab === 'dashboard' && (
          <div className="mt-8 space-y-8">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4">
                <p className="text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
                  {data.stats.recent_issue_count}
                </p>
                <p className="mt-1 text-sm text-slate-500">Recent CEO issues</p>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4">
                <p className="text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
                  {data.stats.pending_hire_count}
                </p>
                <p className="mt-1 text-sm text-slate-500">Pending hire suggestions</p>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4">
                <p className="text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
                  {data.stats.active_team_count}
                </p>
                <p className="mt-1 text-sm text-slate-500">Active analysts</p>
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
                      Recent issues the CEO has reviewed or is responsible for routing.
                    </p>
                  </div>
                  <Link to="/issues" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900">
                    See all
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>

                {data.recent_issues.length === 0 ? (
                  <div className="px-5 py-14 text-center text-sm text-slate-500">
                    No recent CEO activity yet.
                  </div>
                ) : (
                  <div>
                    {data.recent_issues.slice(0, 10).map((issue) => (
                      <RecentIssueRow key={issue.id} issue={issue} />
                    ))}
                  </div>
                )}
              </section>

              <section className="space-y-6">
                <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                      <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                        Pending Hires
                      </h2>
                      <p className="mt-1 text-sm text-slate-500">Suggestions waiting for approval.</p>
                    </div>
                    <Link to="/inbox" className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800">
                      Inbox
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </div>

                  {data.pending_hire_proposals.length === 0 ? (
                    <div className="py-10 text-center text-sm text-slate-500">
                      No pending hire suggestions.
                    </div>
                  ) : (
                    <div className="mt-6 space-y-4">
                      {data.pending_hire_proposals.slice(0, 3).map((proposal) => (
                        <PendingHireRow
                          key={proposal.id}
                          proposal={proposal}
                          onApprove={handleApprove}
                          onReject={handleReject}
                        />
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="border-b border-slate-100 pb-4">
                    <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                      Profile Path
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">This is the current repo-backed CEO instruction directory.</p>
                  </div>
                  <p className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-xs text-slate-600">
                    {data.agent.profile_path}
                  </p>
                </div>
              </section>
            </div>
          </div>
        )}

        {!loading && data && tab === 'instructions' && (
          <div className="mt-8 grid gap-6 xl:grid-cols-[280px,1fr]">
            <aside className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
              <div className="border-b border-slate-100 px-2 pb-3">
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                  Instructions
                </h2>
                <p className="mt-1 text-sm text-slate-500">Repo-backed markdown files for the CEO seat.</p>
              </div>

              <div className="mt-3 space-y-1">
                {data.instructions.map((doc) => {
                  const isActive = selectedDoc?.key === doc.key;
                  return (
                    <button
                      key={doc.key}
                      type="button"
                      onClick={() => {
                        setSelectedDocKey(doc.key);
                        if (editingDocKey && editingDocKey !== doc.key) {
                          setEditingDocKey(null);
                          setDraftContent('');
                        }
                      }}
                      className="flex w-full items-center justify-between rounded-2xl px-3 py-3 text-left transition"
                      style={{
                        background: isActive ? '#F8FAFC' : 'transparent',
                        border: isActive ? '1px solid #E2E8F0' : '1px solid transparent',
                      }}
                    >
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{doc.title}</p>
                        <p className="mt-1 text-xs text-slate-500">{doc.filename}</p>
                      </div>
                      <Briefcase className="h-4 w-4 text-slate-400" />
                    </button>
                  );
                })}
              </div>
            </aside>

            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              {selectedDoc ? (
                <>
                  <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-4">
                    <div>
                      <h2 className="text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                        {selectedDoc.title}
                      </h2>
                      <p className="mt-1 text-sm text-slate-500">{selectedDoc.filename}</p>
                    </div>
                    {editingDocKey === selectedDoc.key ? (
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={cancelEditingInstruction}
                          disabled={savingDocKey === selectedDoc.key}
                          className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={saveInstruction}
                          disabled={savingDocKey === selectedDoc.key}
                          className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {savingDocKey === selectedDoc.key ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
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
                  {editingDocKey === selectedDoc.key ? (
                    <div className="mt-6">
                      <textarea
                        value={draftContent}
                        onChange={(event) => setDraftContent(event.target.value)}
                        className="min-h-[560px] w-full rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4 font-mono text-sm leading-7 text-slate-800 outline-none transition focus:border-slate-300"
                        spellCheck={false}
                      />
                    </div>
                  ) : (
                    <div className="markdown-content mt-6">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {selectedDoc.content}
                      </ReactMarkdown>
                    </div>
                  )}
                </>
              ) : (
                <div className="py-12 text-center text-sm text-slate-500">
                  No instruction file loaded.
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
