import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowLeft,
  FileText,
  FolderOpen,
  Loader2,
  MessageSquare,
  Pencil,
  Play,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import {
  cioReviewTask,
  createTaskChatTurn,
  createTaskDocument,
  deleteTaskDocument,
  getProjects,
  getScheduledAgents,
  getTask,
  getTaskRelatedWork,
  listTaskDocuments,
  listTaskMessages,
  runTaskPipeline,
  updateTaskDocument,
  type ResearchTask,
  type TaskDocument,
  type TaskMessage,
  type TaskRelatedWork,
} from '../api';
import type { ProjectSummary, ScheduledAgent } from '../types';

type IssueTab = 'chat' | 'activity' | 'related' | 'documents';
const LIVE_EXECUTION_STATUSES: Array<ResearchTask['status']> = ['pending', 'running', 'in_review'];

function displayTicker(ticker: string): string {
  return ticker === 'GENERAL' ? 'General' : ticker;
}

function statusTone(status: string): string {
  const tones: Record<string, string> = {
    pending: 'bg-slate-100 text-slate-700',
    running: 'bg-blue-100 text-blue-700',
    in_review: 'bg-amber-100 text-amber-700',
    done: 'bg-emerald-100 text-emerald-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-slate-200 text-slate-600',
  };
  return tones[status] || 'bg-slate-100 text-slate-700';
}

function assigneeLabel(task: ResearchTask, agentsById: Map<string, ScheduledAgent>): string {
  if (task.assigned_agent_id && agentsById.has(task.assigned_agent_id)) {
    return agentsById.get(task.assigned_agent_id)!.name;
  }
  if (task.owner_agent_id && agentsById.has(task.owner_agent_id)) {
    return agentsById.get(task.owner_agent_id)!.name;
  }
  if (task.triggered_by === 'manual_pm_review') {
    return 'PM / CIO';
  }
  return 'No assignee';
}

function formatDateTime(iso?: string | null): string {
  if (!iso) return 'Not yet';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
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

function executionProgressValue(status: ResearchTask['status']): number {
  switch (status) {
    case 'pending':
      return 18;
    case 'running':
      return 62;
    case 'in_review':
      return 88;
    case 'done':
      return 100;
    case 'failed':
    case 'cancelled':
      return 100;
    default:
      return 0;
  }
}

function executionHeadline(task: ResearchTask, assignee: string): string {
  switch (task.status) {
    case 'pending':
      return `${assignee} is queued to start this issue.`;
    case 'running':
      return `${assignee} is actively working this issue.`;
    case 'in_review':
      return `${assignee} finished a run and the issue is in review.`;
    case 'done':
      return `This issue is complete.`;
    case 'failed':
      return `${assignee} hit a failure on the last run.`;
    case 'cancelled':
      return `This issue has been cancelled.`;
    default:
      return `Current state is ${task.status}.`;
  }
}

function executionSubline(task: ResearchTask): string {
  if (task.status === 'running' && task.started_at) {
    return `Run started ${formatRelativeTime(task.started_at)}.`;
  }
  if (task.status === 'in_review' && task.completed_at) {
    return `Latest run finished ${formatRelativeTime(task.completed_at)}.`;
  }
  if (task.status === 'failed' && task.error) {
    return task.error;
  }
  return `Last issue update ${formatRelativeTime(task.updated_at || task.created_at)}.`;
}

function eventTone(message: TaskMessage): string {
  const event = String(message.metadata?.event || '');
  if (event.includes('failed')) return 'bg-red-50 text-red-700 border-red-100';
  if (event.includes('completed') || event.includes('saved')) return 'bg-emerald-50 text-emerald-700 border-emerald-100';
  if (event.includes('started') || event.includes('queued')) return 'bg-blue-50 text-blue-700 border-blue-100';
  return 'bg-slate-100 text-slate-600 border-slate-200';
}

function isArtifactThreadMessage(message: TaskMessage): boolean {
  const event = String(message.metadata?.event || '');
  return ['issue_plan_created', 'issue_run_completed', 'issue_run_failed'].includes(event);
}

function artifactThreadLabel(message: TaskMessage): string {
  const event = String(message.metadata?.event || '');
  if (event === 'issue_plan_created') return 'Plan saved';
  if (event === 'issue_run_completed') return 'Output ready';
  if (event === 'issue_run_failed') return 'Run failed';
  return 'Update';
}

function artifactThreadTone(message: TaskMessage): string {
  const event = String(message.metadata?.event || '');
  if (event === 'issue_run_failed') return 'border-red-200 bg-red-50';
  if (event === 'issue_run_completed') return 'border-emerald-200 bg-emerald-50';
  return 'border-blue-200 bg-blue-50';
}

function WorkspaceTabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`border-b-2 px-1 pb-3 text-sm font-semibold transition ${
        active
          ? 'border-slate-900 text-slate-900'
          : 'border-transparent text-slate-400 hover:text-slate-700'
      }`}
    >
      {label}
    </button>
  );
}

function RelatedIssueRow({
  task,
  label,
}: {
  task: ResearchTask;
  label?: string;
}) {
  return (
    <Link
      to={`/issues/${task.id}`}
      className="flex items-start justify-between gap-4 border-b border-slate-100 px-4 py-4 transition hover:bg-slate-50"
    >
      <div className="min-w-0">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {label && (
            <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              {label}
            </span>
          )}
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${statusTone(task.status)}`}>
            {task.status.replace('_', ' ')}
          </span>
          <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-500">
            {displayTicker(task.ticker)}
          </span>
        </div>
        <p className="text-sm font-semibold text-slate-900">{task.title}</p>
        <p className="mt-1 line-clamp-1 text-xs text-slate-500">
          {task.notes?.trim() || 'No issue brief yet.'}
        </p>
      </div>
      <div className="flex-shrink-0 text-xs text-slate-400">{formatRelativeTime(task.updated_at || task.created_at)}</div>
    </Link>
  );
}

function ThreadMessage({
  message,
  onOpenDocument,
}: {
  message: TaskMessage;
  onOpenDocument: (documentId?: string | null) => void;
}) {
  const isUser = message.role === 'user';
  const isArtifactMessage = !isUser && isArtifactThreadMessage(message);
  const bubbleClasses = isUser
    ? 'bg-slate-900 text-white'
    : message.role === 'assistant'
      ? 'bg-white text-slate-900 border border-slate-200'
      : 'bg-slate-100 text-slate-700 border border-slate-200';

  if (isArtifactMessage) {
    const documentId = String(message.metadata?.document_id || '') || null;
    const documentTitle = String(message.metadata?.document_title || '') || null;
    return (
      <div className="flex justify-start">
        <div className={`w-full max-w-[88%] rounded-[24px] border px-5 py-4 shadow-sm ${artifactThreadTone(message)}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold">
                <span className="text-slate-900">{message.author_label}</span>
                <span className="text-slate-400">{formatRelativeTime(message.created_at)}</span>
              </div>
              <div className="mt-2 inline-flex items-center rounded-full border border-white/70 bg-white/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-600">
                {artifactThreadLabel(message)}
              </div>
            </div>
            {documentTitle && (
              <button
                type="button"
                onClick={() => onOpenDocument(documentId)}
                className="inline-flex items-center gap-2 rounded-2xl border border-white bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-900"
              >
                <FileText className="h-3.5 w-3.5" />
                Open {documentTitle}
              </button>
            )}
          </div>
          <div className="mt-4 prose prose-sm max-w-none prose-p:my-2 prose-p:leading-7 prose-ul:my-2 prose-ul:pl-5 prose-li:my-1 prose-li:text-slate-700 prose-strong:text-slate-900 prose-headings:text-slate-900">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-[24px] px-4 py-3 shadow-sm ${bubbleClasses}`}>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold">
          <span>{message.author_label}</span>
          <span className={isUser ? 'text-white/60' : 'text-slate-400'}>{formatRelativeTime(message.created_at)}</span>
        </div>
        <div className={`prose prose-sm max-w-none prose-p:my-2 prose-p:leading-7 prose-ul:my-2 prose-ul:pl-5 prose-li:my-1 ${isUser ? 'prose-invert' : 'prose-strong:text-slate-900 prose-headings:text-slate-900'}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function IssueDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();

  const [tab, setTab] = useState<IssueTab>('chat');
  const [task, setTask] = useState<ResearchTask | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [chatMessages, setChatMessages] = useState<TaskMessage[]>([]);
  const [activityMessages, setActivityMessages] = useState<TaskMessage[]>([]);
  const [documents, setDocuments] = useState<TaskDocument[]>([]);
  const [relatedWork, setRelatedWork] = useState<TaskRelatedWork | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [documentDraftTitle, setDocumentDraftTitle] = useState('');
  const [documentDraftContent, setDocumentDraftContent] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [sendingChat, setSendingChat] = useState(false);
  const [savingDocument, setSavingDocument] = useState(false);
  const [creatingDocument, setCreatingDocument] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (showSpinner = true) => {
    if (!taskId) return;
    if (showSpinner) {
      setLoading(true);
    }
    setError(null);
    try {
      const [
        taskRow,
        projectRows,
        agentRows,
        chatRows,
        activityRows,
        documentRows,
        relatedRows,
      ] = await Promise.all([
        getTask(taskId),
        getProjects(),
        getScheduledAgents(),
        listTaskMessages(taskId, 'chat'),
        listTaskMessages(taskId, 'activity'),
        listTaskDocuments(taskId),
        getTaskRelatedWork(taskId),
      ]);
      setTask(taskRow);
      setProjects(projectRows);
      setAgents(agentRows);
      setChatMessages(chatRows);
      setActivityMessages(activityRows);
      setDocuments(documentRows);
      setRelatedWork(relatedRows);
      setSelectedDocumentId((current) => current || documentRows[0]?.id || null);
    } catch {
      setError('Could not load this issue workspace.');
    } finally {
      if (showSpinner) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    load();
  }, [taskId]);

  useEffect(() => {
    if (!taskId || !task || !LIVE_EXECUTION_STATUSES.includes(task.status)) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void load(false);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [taskId, task?.status]);

  const agentsById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);
  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);
  const project = task?.project_id ? projectsById.get(task.project_id) || null : null;
  const selectedAgentCount = task?.selected_agents.length || 0;
  const canRunPipeline =
    !!task &&
    task.ticker !== 'GENERAL' &&
    selectedAgentCount > 0 &&
    ['pending', 'failed'].includes(task.status);
  const selectedDocument = documents.find((doc) => doc.id === selectedDocumentId) || null;
  const currentChatTargetLabel = task ? assigneeLabel(task, agentsById) : 'Agent';
  const latestActivityMessage = activityMessages.length > 0 ? activityMessages[activityMessages.length - 1] : null;
  const recentExecutionEvents = useMemo(() => activityMessages.slice(-5).reverse(), [activityMessages]);
  const latestPlanDocument = useMemo(
    () => documents.find((document) => document.document_type === 'plan') || null,
    [documents],
  );
  const latestOutputDocument = useMemo(
    () => documents.find((document) => document.document_type === 'analysis') || null,
    [documents],
  );

  useEffect(() => {
    if (!selectedDocument) {
      setEditingDocumentId(null);
      setDocumentDraftTitle('');
      setDocumentDraftContent('');
      return;
    }
    if (editingDocumentId === selectedDocument.id) {
      return;
    }
    setDocumentDraftTitle(selectedDocument.title);
    setDocumentDraftContent(selectedDocument.content_md);
  }, [selectedDocumentId, selectedDocument, editingDocumentId]);

  const handleRun = async () => {
    if (!taskId || !canRunPipeline) return;
    setRunning(true);
    setError(null);
    try {
      await runTaskPipeline(taskId);
      await load();
    } catch {
      setError('Failed to start the issue pipeline.');
    } finally {
      setRunning(false);
    }
  };

  const handleCioReview = async () => {
    if (!taskId) return;
    setReviewing(true);
    setError(null);
    try {
      const review = await cioReviewTask(taskId);
      await load();
      if (review.action?.type === 'propose_hire' && review.action.proposal_id) {
        navigate('/inbox');
      }
    } catch {
      setError('Failed to request CEO review.');
    } finally {
      setReviewing(false);
    }
  };

  const handleSendChat = async () => {
    if (!taskId || !task || !chatInput.trim()) return;
    setSendingChat(true);
    setError(null);
    try {
      const response = await createTaskChatTurn(taskId, {
        content: chatInput,
        agent_id: task.assigned_agent_id || undefined,
      });
      setChatMessages((current) => [...current, response.user_message, response.assistant_message]);
      setChatInput('');
      const freshActivity = await listTaskMessages(taskId, 'activity');
      setActivityMessages(freshActivity);
    } catch {
      setError('Failed to send the issue follow-up.');
    } finally {
      setSendingChat(false);
    }
  };

  const handleCreateDocument = async () => {
    if (!taskId) return;
    setCreatingDocument(true);
    setError(null);
    try {
      const created = await createTaskDocument(taskId, {
        title: 'Untitled document',
        content_md: '# Untitled document\n\nStart drafting here.',
        document_type: 'analysis',
        created_by_agent_id: task?.assigned_agent_id || undefined,
      });
      setDocuments((current) => [created, ...current]);
      setSelectedDocumentId(created.id);
      setEditingDocumentId(created.id);
      setDocumentDraftTitle(created.title);
      setDocumentDraftContent(created.content_md);
      const freshActivity = await listTaskMessages(taskId, 'activity');
      setActivityMessages(freshActivity);
      setTab('documents');
    } catch {
      setError('Failed to create a new issue document.');
    } finally {
      setCreatingDocument(false);
    }
  };

  const handleSaveDocument = async () => {
    if (!taskId || !selectedDocument) return;
    setSavingDocument(true);
    setError(null);
    try {
      const updated = await updateTaskDocument(taskId, selectedDocument.id, {
        title: documentDraftTitle.trim(),
        content_md: documentDraftContent,
      });
      setDocuments((current) => current.map((doc) => (doc.id === updated.id ? updated : doc)));
      setEditingDocumentId(null);
      const freshActivity = await listTaskMessages(taskId, 'activity');
      setActivityMessages(freshActivity);
    } catch {
      setError('Failed to save the issue document.');
    } finally {
      setSavingDocument(false);
    }
  };

  const handleDeleteDocument = async () => {
    if (!taskId || !selectedDocument) return;
    setSavingDocument(true);
    setError(null);
    try {
      await deleteTaskDocument(taskId, selectedDocument.id);
      const remaining = documents.filter((doc) => doc.id !== selectedDocument.id);
      setDocuments(remaining);
      setSelectedDocumentId(remaining[0]?.id || null);
      setEditingDocumentId(null);
      const freshActivity = await listTaskMessages(taskId, 'activity');
      setActivityMessages(freshActivity);
    } catch {
      setError('Failed to delete the issue document.');
    } finally {
      setSavingDocument(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!task || error && !task) {
    return (
      <div className="min-h-screen bg-slate-50 px-6 py-10">
        <div className="mx-auto max-w-4xl rounded-3xl border border-slate-200 bg-white p-8 text-center">
          <p className="text-sm text-red-600">{error || 'Issue not found.'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-7xl">
        <button
          type="button"
          onClick={() => navigate('/issues')}
          className="mb-6 inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to issues
        </button>

        <div className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex flex-col gap-5 border-b border-slate-100 pb-6 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusTone(task!.status)}`}>
                  {task!.status.replace('_', ' ')}
                </span>
                <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-500">
                  {displayTicker(task!.ticker)}
                </span>
                {project && (
                  <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-500">
                    {project.title}
                  </span>
                )}
              </div>
              <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
                {task!.title}
              </h1>
              <p className="mt-4 max-w-4xl text-sm leading-relaxed text-slate-600">
                {task!.notes?.trim() || 'No issue description yet.'}
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleCreateDocument}
                disabled={creatingDocument}
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creatingDocument ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                New document
              </button>
              <button
                type="button"
                onClick={handleCioReview}
                disabled={reviewing}
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {reviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                Send to CEO
              </button>
              <button
                type="button"
                onClick={handleRun}
                disabled={!canRunPipeline || running}
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run pipeline
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Assignee</p>
              <p className="mt-2 text-sm font-medium text-slate-900">{assigneeLabel(task!, agentsById)}</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Project</p>
              <p className="mt-2 text-sm font-medium text-slate-900">
                {project ? (
                  <Link to={`/projects/${project.id}`} className="inline-flex items-center gap-1.5 text-slate-900 hover:text-emerald-700">
                    <FolderOpen className="h-4 w-4 text-slate-400" />
                    {project.title}
                  </Link>
                ) : (
                  'No project'
                )}
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Created</p>
              <p className="mt-2 text-sm font-medium text-slate-900">{formatDateTime(task!.created_at)}</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Selected engines</p>
              <p className="mt-2 text-sm font-medium text-slate-900">
                {task!.selected_agents.length > 0 ? task!.selected_agents.join(', ') : 'None'}
              </p>
            </div>
          </div>

          {error && (
            <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="mt-8 border-b border-slate-100">
            <div className="flex flex-wrap gap-6">
              <WorkspaceTabButton label="Chat" active={tab === 'chat'} onClick={() => setTab('chat')} />
              <WorkspaceTabButton label="Activity" active={tab === 'activity'} onClick={() => setTab('activity')} />
              <WorkspaceTabButton label="Related work" active={tab === 'related'} onClick={() => setTab('related')} />
              <WorkspaceTabButton label="Documents" active={tab === 'documents'} onClick={() => setTab('documents')} />
            </div>
          </div>

          {tab === 'chat' && (
            <div className="mt-6 grid gap-6 lg:grid-cols-[1fr,320px]">
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-4">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Issue thread</p>
                    <p className="mt-1 text-sm text-slate-500">Follow up directly inside this issue workspace.</p>
                  </div>
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-500">
                    Target: {currentChatTargetLabel}
                  </span>
                </div>

                <div className="space-y-4">
                  {chatMessages.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
                      No issue discussion yet. Start the thread with a follow-up for {currentChatTargetLabel}.
                    </div>
                  ) : (
                    chatMessages.map((message) => (
                      <ThreadMessage
                        key={message.id}
                        message={message}
                        onOpenDocument={(documentId) => {
                          if (documentId) {
                            setSelectedDocumentId(documentId);
                          }
                          setTab('documents');
                        }}
                      />
                    ))
                  )}
                </div>

                <div className="mt-6 rounded-[24px] border border-slate-200 bg-white p-4 focus-within:outline-none focus-within:ring-0">
                  <textarea
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    placeholder={`Ask ${currentChatTargetLabel} to go deeper on this issue...`}
                    rows={4}
                    className="w-full resize-none border-none bg-transparent text-sm leading-7 text-slate-900 outline-none focus:outline-none focus:ring-0 placeholder:text-slate-400"
                  />
                  <div className="mt-4 flex items-center justify-between gap-4">
                    <div className="text-xs text-slate-400">
                      This thread stays attached to the issue.
                    </div>
                    <button
                      type="button"
                      onClick={handleSendChat}
                      disabled={sendingChat || !chatInput.trim()}
                      className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {sendingChat ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
                      Send
                    </button>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div className="rounded-[28px] border border-slate-200 bg-white p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Live execution</p>
                      <p className="mt-2 text-sm font-semibold text-slate-900">{executionHeadline(task!, currentChatTargetLabel)}</p>
                      <p className="mt-1 text-sm text-slate-500">{executionSubline(task!)}</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone(task!.status)}`}>
                      {task!.status.replace('_', ' ')}
                    </span>
                  </div>

                  <div className="mt-4">
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={`h-full rounded-full ${
                          task!.status === 'failed'
                            ? 'bg-red-500'
                            : task!.status === 'done'
                              ? 'bg-emerald-500'
                              : task!.status === 'in_review'
                                ? 'bg-amber-500'
                                : 'bg-blue-500'
                        }`}
                        style={{ width: `${executionProgressValue(task!.status)}%` }}
                      />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                      <span>Queued</span>
                      <span>Running</span>
                      <span>Review</span>
                      <span>Done</span>
                    </div>
                  </div>

                  <div className="mt-4 space-y-3 border-t border-slate-100 pt-4 text-sm text-slate-600">
                    <div className="flex items-center justify-between gap-3">
                      <span>Assignee</span>
                      <span className="font-medium text-slate-900">{currentChatTargetLabel}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Run ID</span>
                      <span className="max-w-[180px] truncate font-medium text-slate-900">{task!.run_id || 'Not started'}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Plan</span>
                      <span className="max-w-[180px] truncate font-medium text-slate-900">
                        {latestPlanDocument ? `rev ${latestPlanDocument.revision}` : 'Not saved'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Output</span>
                      <span className="max-w-[180px] truncate font-medium text-slate-900">
                        {latestOutputDocument ? `rev ${latestOutputDocument.revision}` : 'Not saved'}
                      </span>
                    </div>
                  </div>

                  {(latestActivityMessage || recentExecutionEvents.length > 0) && (
                    <div className="mt-4 border-t border-slate-100 pt-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">What it is doing</p>
                      {latestActivityMessage && (
                        <p className="mt-2 text-sm leading-relaxed text-slate-700">{latestActivityMessage.content}</p>
                      )}
                      <div className="mt-3 space-y-2">
                        {recentExecutionEvents.map((message) => (
                          <div key={message.id} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                            <div className="mb-1 flex items-center justify-between gap-3">
                              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${eventTone(message)}`}>
                                {message.author_label}
                              </span>
                              <span className="text-[11px] text-slate-400">{formatRelativeTime(message.created_at)}</span>
                            </div>
                            <p className="line-clamp-2 text-xs leading-relaxed text-slate-600">{message.content}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="rounded-[28px] border border-slate-200 bg-white p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Current state</p>
                  <div className="mt-4 space-y-3 text-sm text-slate-600">
                    <div className="flex items-center justify-between gap-3">
                      <span>Status</span>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone(task!.status)}`}>
                        {task!.status.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Documents</span>
                      <span className="font-medium text-slate-900">{documents.length}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Sub-issues</span>
                      <span className="font-medium text-slate-900">{relatedWork?.sub_issues.length || 0}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Last update</span>
                      <span className="font-medium text-slate-900">{formatRelativeTime(task!.updated_at || task!.created_at)}</span>
                    </div>
                  </div>
                </div>

                {task!.pm_synthesis?.rationale && (
                  <div className="rounded-[28px] border border-emerald-200 bg-emerald-50 p-5">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Latest synthesis</p>
                    <p className="mt-3 text-sm leading-relaxed text-emerald-900">
                      {task!.pm_synthesis.rationale}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'activity' && (
            <div className="mt-6 rounded-[28px] border border-slate-200 bg-white">
              {activityMessages.length === 0 ? (
                <div className="px-6 py-10 text-center text-sm text-slate-500">
                  No activity recorded for this issue yet.
                </div>
              ) : (
                activityMessages.map((message) => (
                  <div key={message.id} className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 last:border-b-0">
                    <div className="min-w-0">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                          {message.author_label}
                        </span>
                        <span className="text-xs text-slate-400">{message.kind}</span>
                      </div>
                      <p className="text-sm leading-relaxed text-slate-800">{message.content}</p>
                    </div>
                    <span className="flex-shrink-0 text-xs text-slate-400">{formatRelativeTime(message.created_at)}</span>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === 'related' && (
            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <div className="rounded-[28px] border border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Sub-issues</p>
                    <p className="mt-1 text-sm text-slate-500">Break deeper work into linked follow-up issues.</p>
                  </div>
                  <Link
                    to={`/issues?new=1&parent=${task!.id}${task!.project_id ? `&project=${task!.project_id}` : ''}`}
                    className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300"
                  >
                    <Plus className="h-4 w-4" />
                    New sub-issue
                  </Link>
                </div>
                {relatedWork?.parent_task && (
                  <RelatedIssueRow task={relatedWork.parent_task} label="Parent issue" />
                )}
                {relatedWork?.sub_issues.length ? (
                  relatedWork.sub_issues.map((relatedTask) => (
                    <RelatedIssueRow key={relatedTask.id} task={relatedTask} />
                  ))
                ) : (
                  <div className="px-5 py-10 text-center text-sm text-slate-500">No sub-issues yet.</div>
                )}
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-white">
                <div className="border-b border-slate-100 px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Same project</p>
                  <p className="mt-1 text-sm text-slate-500">Other issue work linked to the same thesis workspace.</p>
                </div>
                {relatedWork?.same_project_issues.length ? (
                  relatedWork.same_project_issues.map((relatedTask) => (
                    <RelatedIssueRow key={relatedTask.id} task={relatedTask} />
                  ))
                ) : (
                  <div className="px-5 py-10 text-center text-sm text-slate-500">
                    {task!.project_id ? 'No other project-linked issues yet.' : 'This issue is not attached to a project.'}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'documents' && (
            <div className="mt-6 grid gap-6 lg:grid-cols-[320px,1fr]">
              <div className="rounded-[28px] border border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Documents</p>
                    <p className="mt-1 text-sm text-slate-500">Issue-native deliverables and drafts.</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleCreateDocument}
                    disabled={creatingDocument}
                    className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {creatingDocument ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                    New
                  </button>
                </div>
                {documents.length === 0 ? (
                  <div className="px-5 py-10 text-center text-sm text-slate-500">
                    No issue documents yet.
                  </div>
                ) : (
                  documents.map((document) => (
                    <button
                      key={document.id}
                      type="button"
                      onClick={() => setSelectedDocumentId(document.id)}
                      className={`w-full border-b border-slate-100 px-5 py-4 text-left transition last:border-b-0 hover:bg-slate-50 ${
                        selectedDocumentId === document.id ? 'bg-slate-50' : 'bg-white'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">{document.title}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            rev {document.revision} · {formatRelativeTime(document.updated_at)}
                          </p>
                        </div>
                        <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                          {document.document_type}
                        </span>
                      </div>
                    </button>
                  ))
                )}
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-white">
                {!selectedDocument ? (
                  <div className="px-6 py-16 text-center text-sm text-slate-500">
                    Select a document or create a new one for this issue.
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-slate-400" />
                          {editingDocumentId === selectedDocument.id ? (
                            <input
                              value={documentDraftTitle}
                              onChange={(event) => setDocumentDraftTitle(event.target.value)}
                              className="w-full border-none bg-transparent text-lg font-semibold text-slate-900 outline-none"
                            />
                          ) : (
                            <h2 className="truncate text-lg font-semibold text-slate-900">{selectedDocument.title}</h2>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-slate-500">
                          rev {selectedDocument.revision} · updated {formatRelativeTime(selectedDocument.updated_at)}
                        </p>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {editingDocumentId === selectedDocument.id ? (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingDocumentId(null);
                                setDocumentDraftTitle(selectedDocument.title);
                                setDocumentDraftContent(selectedDocument.content_md);
                              }}
                              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-300"
                            >
                              <X className="h-4 w-4" />
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={handleSaveDocument}
                              disabled={savingDocument || !documentDraftTitle.trim()}
                              className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {savingDocument ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                              Save
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingDocumentId(selectedDocument.id);
                                setDocumentDraftTitle(selectedDocument.title);
                                setDocumentDraftContent(selectedDocument.content_md);
                              }}
                              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300"
                            >
                              <Pencil className="h-4 w-4" />
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={handleDeleteDocument}
                              disabled={savingDocument}
                              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 transition hover:border-red-300 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              <Trash2 className="h-4 w-4" />
                              Delete
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="px-6 py-5">
                      {editingDocumentId === selectedDocument.id ? (
                        <textarea
                          value={documentDraftContent}
                          onChange={(event) => setDocumentDraftContent(event.target.value)}
                          rows={22}
                          className="min-h-[640px] w-full resize-none rounded-[24px] border border-slate-200 bg-slate-50 p-5 font-mono text-sm leading-7 text-slate-900 outline-none"
                        />
                      ) : (
                        <div className="prose prose-slate max-w-none">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {selectedDocument.content_md || 'No document content yet.'}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
