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

function ThreadMessage({ message }: { message: TaskMessage }) {
  const isUser = message.role === 'user';
  const bubbleClasses = isUser
    ? 'bg-slate-900 text-white'
    : message.role === 'assistant'
      ? 'bg-white text-slate-900 border border-slate-200'
      : 'bg-slate-100 text-slate-700 border border-slate-200';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-[24px] px-4 py-3 shadow-sm ${bubbleClasses}`}>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold">
          <span>{message.author_label}</span>
          <span className={isUser ? 'text-white/60' : 'text-slate-400'}>{formatRelativeTime(message.created_at)}</span>
        </div>
        <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : ''}`}>
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

  const load = async () => {
    if (!taskId) return;
    setLoading(true);
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
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [taskId]);

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
                      <ThreadMessage key={message.id} message={message} />
                    ))
                  )}
                </div>

                <div className="mt-6 rounded-[24px] border border-slate-200 bg-white p-4">
                  <textarea
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    placeholder={`Ask ${currentChatTargetLabel} to go deeper on this issue...`}
                    rows={4}
                    className="w-full resize-none border-none bg-transparent text-sm leading-7 text-slate-900 outline-none placeholder:text-slate-400"
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
