import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  BrainCircuit,
  Loader2,
  Play,
  UserPlus,
  X,
} from 'lucide-react';
import {
  approveHireProposal,
  cioDelegate,
  cioReviewTask,
  getHireProposals,
  getProjects,
  getScheduledAgents,
  getTask,
  listTasks,
  rejectHireProposal,
  type CioAction,
  type ResearchTask,
} from '../api';
import { ROLE_META_BY_KEY } from '../agentRoles';
import type { HireProposal, ProjectSummary, ScheduledAgent } from '../types';

type ReviewActionState = 'idle' | 'loading' | 'done' | 'error' | 'rejected';

interface ReviewState {
  loading: boolean;
  message?: string;
  action?: CioAction | null;
  actionState?: ReviewActionState;
  actionResult?: string;
  error?: string;
}

const PRIORITY_TONE: Record<string, string> = {
  low: 'bg-slate-100 text-slate-600',
  medium: 'bg-blue-50 text-blue-700',
  high: 'bg-amber-50 text-amber-700',
  urgent: 'bg-red-50 text-red-700',
};

const STATUS_TONE: Record<string, string> = {
  pending: 'bg-slate-100 text-slate-700',
  running: 'bg-blue-100 text-blue-700',
  in_review: 'bg-amber-100 text-amber-700',
  done: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-slate-200 text-slate-600',
};

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market: 'Weekdays at 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly: 'Monthly',
};

const PRIORITY_RANK: Record<string, number> = {
  urgent: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function displayTicker(ticker: string): string {
  return ticker === 'GENERAL' ? 'General' : ticker;
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
  return `${days}d ago`;
}

function roleLabel(input: {
  role_key?: string | null;
  role_title?: string | null;
  template?: string | null;
}) {
  return (
    (input.role_key && ROLE_META_BY_KEY[input.role_key as keyof typeof ROLE_META_BY_KEY]?.title)
    || input.role_title
    || input.template
    || 'Role'
  );
}

function assigneeLabel(task: ResearchTask, agentsById: Map<string, ScheduledAgent>): string {
  if (task.assigned_agent_id && agentsById.has(task.assigned_agent_id)) {
    return agentsById.get(task.assigned_agent_id)!.name;
  }
  if (task.owner_agent_id && agentsById.has(task.owner_agent_id)) {
    return agentsById.get(task.owner_agent_id)!.name;
  }
  return 'PM / CIO';
}

function projectLabel(task: ResearchTask, projectsById: Map<string, ProjectSummary>): string {
  if (task.project_id && projectsById.has(task.project_id)) {
    return projectsById.get(task.project_id)!.title;
  }
  return 'No project';
}

function DelegateCard({
  action,
  state,
  result,
  onDelegate,
}: {
  action: CioAction;
  state: ReviewActionState;
  result?: string;
  onDelegate: () => void;
}) {
  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Delegate run</p>
          <p className="mt-1 truncate text-sm font-semibold text-slate-900">{action.agent_name}</p>
          {action.reason && <p className="mt-1 text-xs text-slate-500">{action.reason}</p>}
        </div>
        {state === 'idle' && (
          <button
            type="button"
            onClick={onDelegate}
            className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700"
          >
            <Play className="h-3 w-3" />
            Run now
          </button>
        )}
        {state === 'loading' && (
          <div className="inline-flex items-center gap-1.5 rounded-xl bg-blue-100 px-3 py-1.5 text-xs font-medium text-blue-700">
            <Loader2 className="h-3 w-3 animate-spin" />
            Running…
          </div>
        )}
        {state === 'done' && (
          <span className="rounded-xl bg-emerald-100 px-3 py-1.5 text-xs font-medium text-emerald-700">
            Dispatched
          </span>
        )}
        {state === 'error' && (
          <span className="rounded-xl bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700">
            Failed
          </span>
        )}
      </div>
      {result && <div className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500">{result}</div>}
    </div>
  );
}

function HireCard({
  action,
  state,
  result,
  onApprove,
  onReject,
}: {
  action: CioAction;
  state: ReviewActionState;
  result?: string;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-emerald-200 bg-emerald-50">
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Hire proposal</p>
            <p className="mt-1 text-sm font-semibold text-slate-900">{action.name}</p>
            {action.description && <p className="mt-1 text-xs text-slate-600">{action.description}</p>}
          </div>
          <div className="flex items-center gap-2">
            {state === 'idle' && (
              <>
                <button
                  type="button"
                  onClick={onReject}
                  className="rounded-lg p-1.5 text-slate-400 transition hover:bg-red-100 hover:text-red-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={onApprove}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700"
                >
                  <UserPlus className="h-3 w-3" />
                  Approve
                </button>
              </>
            )}
            {state === 'loading' && (
              <div className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-100 px-3 py-1.5 text-xs font-medium text-emerald-700">
                <Loader2 className="h-3 w-3 animate-spin" />
                Saving…
              </div>
            )}
            {state === 'done' && (
              <span className="rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white">
                Approved
              </span>
            )}
            {state === 'rejected' && (
              <span className="rounded-xl bg-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600">
                Declined
              </span>
            )}
            {state === 'error' && (
              <span className="rounded-xl bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700">
                Failed
              </span>
            )}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {(action.role_key || action.role_title || action.template) && (
            <span className="rounded-lg border border-emerald-200 bg-white px-2 py-0.5 text-xs font-medium text-emerald-700">
              {roleLabel(action)}
            </span>
          )}
          {action.schedule_label && (
            <span className="rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-600">
              {SCHEDULE_LABELS[action.schedule_label] || action.schedule_label}
            </span>
          )}
          {(action.tickers || []).map((ticker) => (
            <span key={ticker} className="rounded-lg border border-slate-200 bg-white px-2 py-0.5 font-mono text-xs text-slate-700">
              {ticker}
            </span>
          ))}
        </div>

        {action.instruction && (
          <p className="mt-3 rounded-xl border border-emerald-100 bg-white p-3 text-xs leading-relaxed text-slate-600">
            {action.instruction}
          </p>
        )}
      </div>
      {result && <div className="border-t border-emerald-100 px-4 py-2 text-xs text-slate-500">{result}</div>}
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
  return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Pending hire</p>
      <h3 className="mt-2 text-sm font-semibold text-slate-900">{proposal.name}</h3>
      <p className="mt-1 text-xs text-slate-600">
        {roleLabel(proposal)} · Reports to {proposal.reports_to_label || 'CIO'}
      </p>
      {proposal.description && <p className="mt-2 text-xs leading-relaxed text-slate-600">{proposal.description}</p>}
      {proposal.tickers.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {proposal.tickers.map((ticker) => (
            <span key={ticker} className="rounded-lg border border-slate-200 bg-white px-2 py-0.5 font-mono text-xs text-slate-700">
              {ticker}
            </span>
          ))}
        </div>
      )}
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onReject(proposal.id)}
          className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
        >
          Decline
        </button>
        <button
          type="button"
          onClick={() => onApprove(proposal.id)}
          className="rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700"
        >
          Approve
        </button>
      </div>
    </div>
  );
}

function ReviewQueueCard({
  task,
  projectName,
  assigneeName,
  state,
  onReview,
  onOpen,
  onDelegate,
  onApproveHire,
  onRejectHire,
}: {
  task: ResearchTask;
  projectName: string;
  assigneeName: string;
  state?: ReviewState;
  onReview: () => void;
  onOpen: () => void;
  onDelegate: () => void;
  onApproveHire: () => void;
  onRejectHire: () => void;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${PRIORITY_TONE[task.priority] || PRIORITY_TONE.medium}`}>
              {task.priority}
            </span>
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_TONE[task.status] || STATUS_TONE.pending}`}>
              {task.status.replace('_', ' ')}
            </span>
            <span className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500">
              {displayTicker(task.ticker)}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
            {task.title}
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            {task.notes?.trim() || 'No issue description yet.'}
          </p>
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-500">
            <span>Project: {projectName}</span>
            <span>Owner: {assigneeName}</span>
            <span>Updated {formatRelativeTime(task.updated_at || task.created_at)}</span>
            <span>
              Staffing: {task.selected_agents.length > 0 ? task.selected_agents.join(', ') : 'Unstaffed'}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
          >
            Open issue
          </button>
          <button
            type="button"
            onClick={onReview}
            disabled={state?.loading}
            className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {state?.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BrainCircuit className="h-4 w-4" />}
            Run PM review
          </button>
        </div>
      </div>

      {state?.error && (
        <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {state.error}
        </div>
      )}

      {state?.message && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">PM view</p>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{state.message}</p>
        </div>
      )}

      {state?.action?.type === 'delegate' && state.actionState && state.actionState !== 'rejected' && (
        <DelegateCard
          action={state.action}
          state={state.actionState}
          result={state.actionResult}
          onDelegate={onDelegate}
        />
      )}

      {state?.action?.type === 'propose_hire' && state.actionState && (
        <HireCard
          action={state.action}
          state={state.actionState}
          result={state.actionResult}
          onApprove={onApproveHire}
          onReject={onRejectHire}
        />
      )}
    </div>
  );
}

export default function CioPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [pendingProposals, setPendingProposals] = useState<HireProposal[]>([]);
  const [linkedIssue, setLinkedIssue] = useState<ResearchTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewStates, setReviewStates] = useState<Record<string, ReviewState>>({});

  const issueId = searchParams.get('issue');

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskRows, projectRows, agentRows, proposalRows] = await Promise.all([
        listTasks({ limit: 200 }),
        getProjects(),
        getScheduledAgents(),
        getHireProposals('pending'),
      ]);
      setTasks(taskRows);
      setProjects(projectRows);
      setAgents(agentRows);
      setPendingProposals(proposalRows);
    } catch {
      setError('Could not load the PM desk.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const loadLinkedIssue = async () => {
      if (!issueId) {
        setLinkedIssue(null);
        return;
      }
      try {
        const task = await getTask(issueId);
        setLinkedIssue(task);
      } catch {
        setLinkedIssue(null);
      }
    };
    loadLinkedIssue();
  }, [issueId]);

  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);
  const agentsById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);

  const reviewQueue = useMemo(() => {
    const openTasks = tasks.filter((task) => !['done', 'cancelled'].includes(task.status));
    const deduped = new Map<string, ResearchTask>();
    if (linkedIssue) {
      deduped.set(linkedIssue.id, linkedIssue);
    }
    for (const task of openTasks) {
      if (
        task.status === 'pending'
        || task.status === 'in_review'
        || task.selected_agents.length === 0
        || task.id === issueId
      ) {
        deduped.set(task.id, task);
      }
    }

    return Array.from(deduped.values()).sort((left, right) => {
      if (left.id === issueId) return -1;
      if (right.id === issueId) return 1;
      const leftRank = PRIORITY_RANK[left.priority] ?? 99;
      const rightRank = PRIORITY_RANK[right.priority] ?? 99;
      if (leftRank !== rightRank) return leftRank - rightRank;
      return new Date(right.updated_at || right.created_at || 0).getTime() - new Date(left.updated_at || left.created_at || 0).getTime();
    });
  }, [issueId, linkedIssue, tasks]);

  const activeTeam = useMemo(
    () => agents.filter((agent) => agent.is_active).sort((left, right) => left.name.localeCompare(right.name)),
    [agents],
  );

  const runReview = async (task: ResearchTask) => {
    setReviewStates((current) => ({
      ...current,
      [task.id]: { loading: true },
    }));

    try {
      const response = await cioReviewTask(task.id);
      setReviewStates((current) => ({
        ...current,
        [task.id]: {
          loading: false,
          message: response.message,
          action: response.action ?? null,
          actionState: !response.action
            ? undefined
            : response.action.proposal_status === 'approved'
              ? 'done'
              : response.action.proposal_status === 'rejected'
                ? 'rejected'
                : 'idle',
        },
      }));
      if (response.action?.type === 'propose_hire') {
        const proposals = await getHireProposals('pending');
        setPendingProposals(proposals);
      }
    } catch {
      setReviewStates((current) => ({
        ...current,
        [task.id]: {
          loading: false,
          error: 'PM review failed. Please try again.',
        },
      }));
    }
  };

  const handleDelegate = async (taskId: string) => {
    const review = reviewStates[taskId];
    if (!review?.action?.agent_id) return;

    setReviewStates((current) => ({
      ...current,
      [taskId]: { ...current[taskId], actionState: 'loading' },
    }));

    try {
      const result = await cioDelegate(review.action.agent_id);
      setReviewStates((current) => ({
        ...current,
        [taskId]: {
          ...current[taskId],
          actionState: 'done',
          actionResult: `Run started — ID: ${result.run_id}. Check Inbox for results.`,
        },
      }));
    } catch {
      setReviewStates((current) => ({
        ...current,
        [taskId]: {
          ...current[taskId],
          actionState: 'error',
          actionResult: 'Failed to dispatch agent run.',
        },
      }));
    }
  };

  const handleApproveFromReview = async (taskId: string) => {
    const review = reviewStates[taskId];
    if (!review?.action?.proposal_id) return;

    setReviewStates((current) => ({
      ...current,
      [taskId]: { ...current[taskId], actionState: 'loading' },
    }));

    try {
      const result = await approveHireProposal(review.action.proposal_id);
      setReviewStates((current) => ({
        ...current,
        [taskId]: {
          ...current[taskId],
          actionState: 'done',
          actionResult: `${result.agent.name} approved and added to the team.`,
        },
      }));
      await load();
    } catch {
      setReviewStates((current) => ({
        ...current,
        [taskId]: {
          ...current[taskId],
          actionState: 'error',
          actionResult: 'Failed to approve the hire proposal.',
        },
      }));
    }
  };

  const handleRejectFromReview = async (taskId: string) => {
    const review = reviewStates[taskId];
    if (!review?.action?.proposal_id) return;

    setReviewStates((current) => ({
      ...current,
      [taskId]: { ...current[taskId], actionState: 'loading' },
    }));

    try {
      await rejectHireProposal(review.action.proposal_id);
      setReviewStates((current) => ({
        ...current,
        [taskId]: {
          ...current[taskId],
          actionState: 'rejected',
          actionResult: 'Hire proposal declined.',
        },
      }));
      const proposals = await getHireProposals('pending');
      setPendingProposals(proposals);
    } catch {
      setReviewStates((current) => ({
        ...current,
        [taskId]: {
          ...current[taskId],
          actionState: 'error',
          actionResult: 'Failed to update the hire proposal.',
        },
      }));
    }
  };

  const handleApproveProposal = async (proposalId: string) => {
    try {
      await approveHireProposal(proposalId);
      await load();
    } catch {
      setError('Failed to approve the hire proposal.');
    }
  };

  const handleRejectProposal = async (proposalId: string) => {
    try {
      await rejectHireProposal(proposalId);
      const proposals = await getHireProposals('pending');
      setPendingProposals(proposals);
    } catch {
      setError('Failed to decline the hire proposal.');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-6 py-10 lg:px-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500 shadow-sm ring-1 ring-slate-200">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              PM desk
            </div>
            <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
              PM Workflow
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-500">
              Issues arrive here first. The PM reviews the card, decides whether to delegate to the current team or propose a hire, and then pushes the work forward. No chat step.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center">
              <p className="text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>{reviewQueue.length}</p>
              <p className="text-xs text-slate-500">Queue</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center">
              <p className="text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>{pendingProposals.length}</p>
              <p className="text-xs text-slate-500">Pending hires</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center">
              <p className="text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>{activeTeam.length}</p>
              <p className="text-xs text-slate-500">Active team</p>
            </div>
          </div>
        </div>

        {linkedIssue && (
          <div className="mt-8 rounded-[28px] border border-emerald-200 bg-emerald-50 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Linked issue</p>
                <h2 className="mt-2 text-2xl font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                  {linkedIssue.title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  {linkedIssue.notes || 'No issue description provided.'}
                </p>
                <p className="mt-3 text-xs text-slate-500">
                  {displayTicker(linkedIssue.ticker)} · {projectLabel(linkedIssue, projectsById)} · {linkedIssue.priority}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => navigate(`/issues/${linkedIssue.id}`)}
                  className="rounded-2xl border border-emerald-200 bg-white px-4 py-2 text-sm font-medium text-emerald-700 transition hover:border-emerald-300"
                >
                  Open issue
                </button>
                <button
                  type="button"
                  onClick={() => runReview(linkedIssue)}
                  disabled={reviewStates[linkedIssue.id]?.loading}
                  className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {reviewStates[linkedIssue.id]?.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BrainCircuit className="h-4 w-4" />}
                  Run PM review
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="mt-8 grid gap-6 xl:grid-cols-[1.25fr,0.75fr]">
          <div className="space-y-6">
            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                    Review queue
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Unstaffed, pending, or in-review issues that need PM direction.
                  </p>
                </div>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                </div>
              ) : reviewQueue.length === 0 ? (
                <div className="py-16 text-center">
                  <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
                    <BrainCircuit className="h-5 w-5" />
                  </div>
                  <p className="text-sm text-slate-500">No issues currently need PM review.</p>
                </div>
              ) : (
                <div className="mt-6 space-y-4">
                  {reviewQueue.map((task) => (
                    <ReviewQueueCard
                      key={task.id}
                      task={task}
                      projectName={projectLabel(task, projectsById)}
                      assigneeName={assigneeLabel(task, agentsById)}
                      state={reviewStates[task.id]}
                      onReview={() => runReview(task)}
                      onOpen={() => navigate(`/issues/${task.id}`)}
                      onDelegate={() => handleDelegate(task.id)}
                      onApproveHire={() => handleApproveFromReview(task.id)}
                      onRejectHire={() => handleRejectFromReview(task.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                    Pending hires
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">Approvals waiting on your decision.</p>
                </div>
                <Link to="/team" className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800">
                  Team
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>

              {pendingProposals.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  No pending hire proposals.
                </div>
              ) : (
                <div className="mt-6 space-y-4">
                  {pendingProposals.map((proposal) => (
                    <PendingProposalCard
                      key={proposal.id}
                      proposal={proposal}
                      onApprove={handleApproveProposal}
                      onReject={handleRejectProposal}
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="border-b border-slate-100 pb-4">
                <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                  Active team
                </h2>
                <p className="mt-1 text-sm text-slate-500">Current analysts available for delegation.</p>
              </div>

              {activeTeam.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  No approved active agents yet.
                </div>
              ) : (
                <div className="mt-6 space-y-3">
                  {activeTeam.slice(0, 8).map((agent) => (
                    <div key={agent.id} className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900">{agent.name}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {roleLabel(agent)} · Reports to {agent.reports_to_label || 'CIO'}
                        </p>
                      </div>
                      <Link to={`/scheduled-agents/${agent.id}`} className="text-xs font-medium text-emerald-700 hover:text-emerald-800">
                        Open
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
