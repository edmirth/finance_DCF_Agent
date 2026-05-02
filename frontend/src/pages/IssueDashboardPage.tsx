import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  Briefcase,
  ChevronDown,
  CircleDot,
  FilePlus2,
  FolderOpen,
  Loader2,
} from 'lucide-react';
import {
  createTask,
  getProjects,
  getScheduledAgents,
  getTaskBoardStats,
  listTasks,
  type CreateTaskBody,
  type ResearchTask,
  type TaskPriority,
  type TaskStatus,
  type TaskType,
} from '../api';
import type { ProjectSummary, ScheduledAgent } from '../types';

const STATUS_META: Record<string, { label: string; tone: string; dot: string }> = {
  pending: { label: 'Inbox', tone: 'bg-slate-100 text-slate-700', dot: 'bg-slate-400' },
  running: { label: 'Working', tone: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500' },
  in_review: { label: 'Review', tone: 'bg-amber-100 text-amber-700', dot: 'bg-amber-500' },
  closed: { label: 'Closed', tone: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-500' },
};

const PRIORITY_META: Record<TaskPriority, string> = {
  low: 'bg-slate-100 text-slate-600',
  medium: 'bg-blue-50 text-blue-700',
  high: 'bg-amber-50 text-amber-700',
  urgent: 'bg-red-50 text-red-700',
};

const TASK_TYPE_OPTIONS: Array<{ value: TaskType; label: string }> = [
  { value: 'ad_hoc', label: 'Ad hoc research' },
  { value: 'initiate_coverage', label: 'Initiate coverage' },
  { value: 'thesis_update', label: 'Thesis update' },
  { value: 'earnings', label: 'Earnings' },
  { value: 'risk_review', label: 'Risk review' },
  { value: 'sector_screen', label: 'Sector screen' },
];

const PRIORITY_OPTIONS: TaskPriority[] = ['low', 'medium', 'high', 'urgent'];

type AssigneeChoice =
  | { kind: 'none'; id: null; label: string; subtitle: string }
  | { kind: 'pm'; id: null; label: string; subtitle: string }
  | { kind: 'agent'; id: string; label: string; subtitle: string };

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

function taskProjectLabel(task: ResearchTask, projectsById: Map<string, ProjectSummary>): string {
  if (task.project_id && projectsById.has(task.project_id)) {
    return projectsById.get(task.project_id)!.title;
  }
  return 'No project';
}

function normalizeBoard(tasks: ResearchTask[]): Record<string, ResearchTask[]> {
  return {
    pending: tasks.filter((task) => task.status === 'pending'),
    running: tasks.filter((task) => task.status === 'running'),
    in_review: tasks.filter((task) => task.status === 'in_review'),
    closed: tasks.filter((task) => ['done', 'failed', 'cancelled'].includes(task.status)),
  };
}

function IssueCard({
  task,
  agentsById,
  projectsById,
}: {
  task: ResearchTask;
  agentsById: Map<string, ScheduledAgent>;
  projectsById: Map<string, ProjectSummary>;
}) {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => navigate(`/issues/${task.id}`)}
      className="w-full text-left rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${PRIORITY_META[task.priority]}`}>
              <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
              {task.priority}
            </span>
            <span className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500">
              {displayTicker(task.ticker)}
            </span>
          </div>
          <h3 className="text-sm font-semibold text-slate-900 leading-snug" style={{ letterSpacing: '-0.02em' }}>
            {task.title}
          </h3>
          <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-500">
            {task.notes?.trim() || 'No description yet.'}
          </p>
        </div>
        <ArrowRight className="h-4 w-4 flex-shrink-0 text-slate-300" />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-[11px] text-slate-500">
        <span>{assigneeLabel(task, agentsById)}</span>
        <span className="inline-flex items-center gap-1.5">
          <FolderOpen className="h-3.5 w-3.5 text-slate-400" />
          {taskProjectLabel(task, projectsById)}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <CircleDot className="h-3.5 w-3.5 text-slate-400" />
          {formatRelativeTime(task.updated_at || task.created_at)}
        </span>
      </div>
    </button>
  );
}

function PickerButton({
  label,
  value,
  active,
  onClick,
}: {
  label: string;
  value: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex h-10 items-center gap-2 rounded-[14px] border px-3.5 text-left transition focus:outline-none focus-visible:outline-none ${
        active
          ? 'border-white/20 bg-[#1a1a1a]'
          : 'border-white/10 bg-[#121212] hover:border-white/20 hover:bg-[#171717]'
      }`}
    >
      <span className="text-[13px] text-slate-500">{label}</span>
      <span className="text-[13px] font-medium text-slate-200">{value}</span>
      <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
    </button>
  );
}

function NewIssueModal({
  agents,
  projects,
  initialAssigneeId,
  initialProjectId,
  initialParentTaskId,
  onClose,
  onCreated,
}: {
  agents: ScheduledAgent[];
  projects: ProjectSummary[];
  initialAssigneeId?: string | null;
  initialProjectId?: string | null;
  initialParentTaskId?: string | null;
  onClose: () => void;
  onCreated: (task: ResearchTask, options?: { redirectToInbox?: boolean }) => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [ticker, setTicker] = useState('');
  const [taskType, setTaskType] = useState<TaskType>('ad_hoc');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [assigneeOpen, setAssigneeOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [assigneeQuery, setAssigneeQuery] = useState('');
  const [projectQuery, setProjectQuery] = useState('');
  const [selectedAssignee, setSelectedAssignee] = useState<AssigneeChoice>({
    kind: 'pm',
    id: null,
    label: 'PM / CIO',
    subtitle: 'Route this issue to the PM for triage and delegation',
  });
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(initialProjectId || null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeProjects = useMemo(
    () => projects.filter((project) => project.status === 'active'),
    [projects],
  );

  const assigneeOptions = useMemo<AssigneeChoice[]>(() => {
    const normalizedQuery = assigneeQuery.trim().toLowerCase();
    const baseOptions: AssigneeChoice[] = [
      { kind: 'pm', id: null, label: 'PM / CIO', subtitle: 'Route this issue to the PM for triage and delegation' },
      { kind: 'none', id: null, label: 'No assignee', subtitle: 'Create the issue without routing it yet' },
      ...agents.map((agent) => ({
        kind: 'agent' as const,
        id: agent.id,
        label: agent.name,
        subtitle: agent.role_title || agent.template.replace(/_/g, ' '),
      })),
    ];

    if (!normalizedQuery) return baseOptions;
    return baseOptions.filter((option) =>
      `${option.label} ${option.subtitle}`.toLowerCase().includes(normalizedQuery),
    );
  }, [agents, assigneeQuery]);

  const projectOptions = useMemo(() => {
    const normalizedQuery = projectQuery.trim().toLowerCase();
    const baseOptions = [
      { id: null as string | null, title: 'No project', subtitle: 'Keep this issue outside a thesis workspace' },
      ...activeProjects.map((project) => ({
        id: project.id,
        title: project.title,
        subtitle: project.thesis || 'Investment project',
      })),
    ];
    if (!normalizedQuery) return baseOptions;
    return baseOptions.filter((option) =>
      `${option.title} ${option.subtitle}`.toLowerCase().includes(normalizedQuery),
    );
  }, [activeProjects, projectQuery]);

  const selectedProject = activeProjects.find((project) => project.id === selectedProjectId) || null;

  useEffect(() => {
    if (!initialAssigneeId) return;
    const matchedAgent = agents.find((agent) => agent.id === initialAssigneeId);
    if (!matchedAgent) return;
    setSelectedAssignee({
      kind: 'agent',
      id: matchedAgent.id,
      label: matchedAgent.name,
      subtitle: matchedAgent.role_title || matchedAgent.template.replace(/_/g, ' '),
    });
  }, [agents, initialAssigneeId]);

  useEffect(() => {
    if (!initialProjectId) return;
    setSelectedProjectId(initialProjectId);
  }, [initialProjectId]);

  const handleSubmit = async () => {
    if (!title.trim()) {
      setError('Issue title required.');
      return;
    }

    setCreating(true);
    setError(null);

    const body: CreateTaskBody = {
      ticker: ticker.trim() ? ticker.trim().toUpperCase() : undefined,
      title: title.trim(),
      task_type: taskType,
      priority,
      project_id: selectedProjectId || undefined,
      parent_task_id: initialParentTaskId || undefined,
      notes: description.trim() || undefined,
      triggered_by:
        selectedAssignee.kind === 'agent'
          ? 'manual_assignment'
          : selectedAssignee.kind === 'pm'
            ? 'manual_pm_review'
            : 'manual',
      assigned_agent_id: selectedAssignee.kind === 'agent' ? selectedAssignee.id : undefined,
    };

    try {
      const task = await createTask(body);
      onCreated(task);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to create issue.');
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-[690px] overflow-hidden rounded-[24px] border border-slate-800/20 bg-[#0a0a0a] text-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-white/10 px-2.5 py-1 font-mono text-[11px] font-semibold tracking-wide text-slate-200">
              PHR
            </div>
            <span className="text-base font-medium text-slate-200">New issue</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/5 hover:text-white focus:outline-none focus-visible:outline-none"
          >
            <span className="sr-only">Close</span>
            ×
          </button>
        </div>

        <div className="px-5 py-4">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Issue title"
            className="w-full border-none bg-transparent px-0 py-0.5 text-[24px] font-semibold tracking-[-0.025em] text-white outline-none placeholder:text-slate-600 focus:outline-none focus-visible:outline-none"
          />

          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <span className="text-sm text-slate-400">For</span>
            <div className="relative">
              <PickerButton
                label=""
                value={selectedAssignee.label}
                active={assigneeOpen}
                onClick={() => {
                  setAssigneeOpen((open) => !open);
                  setProjectOpen(false);
                }}
              />
              {assigneeOpen && (
                <div className="absolute left-0 top-[calc(100%+8px)] z-10 w-[320px] rounded-2xl border border-white/10 bg-[#151515] p-3 shadow-2xl">
                  <input
                    autoFocus
                    value={assigneeQuery}
                    onChange={(event) => setAssigneeQuery(event.target.value)}
                    placeholder="Search assignees..."
                    className="mb-3 w-full rounded-xl border border-white/10 bg-[#0f0f0f] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:outline-none focus-visible:outline-none"
                  />
                  <div className="max-h-64 overflow-y-auto">
                    {assigneeOptions.map((option) => (
                      <button
                        key={`${option.kind}:${option.id ?? option.label}`}
                        type="button"
                        onClick={() => {
                          setSelectedAssignee(option);
                          setAssigneeOpen(false);
                          setAssigneeQuery('');
                        }}
                        className="flex w-full items-start justify-between rounded-xl px-3 py-2 text-left transition hover:bg-white/5"
                      >
                        <div>
                          <div className="text-sm font-medium text-white">{option.label}</div>
                          <div className="text-xs text-slate-500">{option.subtitle}</div>
                        </div>
                        {selectedAssignee.kind === option.kind && selectedAssignee.id === option.id && (
                          <span className="text-sm text-slate-300">✓</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <span className="text-sm text-slate-400">in</span>
            <div className="relative">
              <PickerButton
                label=""
                value={selectedProject?.title || 'Project'}
                active={projectOpen}
                onClick={() => {
                  setProjectOpen((open) => !open);
                  setAssigneeOpen(false);
                }}
              />
              {projectOpen && (
                <div className="absolute left-0 top-[calc(100%+8px)] z-10 w-[340px] rounded-2xl border border-white/10 bg-[#151515] p-3 shadow-2xl">
                  <input
                    autoFocus
                    value={projectQuery}
                    onChange={(event) => setProjectQuery(event.target.value)}
                    placeholder="Search projects..."
                    className="mb-3 w-full rounded-xl border border-white/10 bg-[#0f0f0f] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:outline-none focus-visible:outline-none"
                  />
                  <div className="max-h-64 overflow-y-auto">
                    {projectOptions.map((project) => (
                      <button
                        key={project.id || 'none'}
                        type="button"
                        onClick={() => {
                          setSelectedProjectId(project.id);
                          setProjectOpen(false);
                          setProjectQuery('');
                        }}
                        className="flex w-full items-start justify-between rounded-xl px-3 py-2 text-left transition hover:bg-white/5"
                      >
                        <div>
                          <div className="text-sm font-medium text-white">{project.title}</div>
                          <div className="line-clamp-1 text-xs text-slate-500">{project.subtitle}</div>
                        </div>
                        {selectedProjectId === project.id && <span className="text-sm text-slate-300">✓</span>}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 border-t border-white/10 pt-4">
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Add description..."
              rows={3}
              className="min-h-[116px] w-full resize-none border-none bg-transparent text-[15px] leading-7 text-slate-200 outline-none placeholder:text-slate-600 focus:outline-none focus-visible:outline-none"
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-2.5 border-t border-white/10 pt-3.5">
            <div className="flex h-10 items-center gap-2 rounded-[14px] border border-white/10 bg-white/5 px-3.5 text-sm text-slate-300">
              <CircleDot className="h-3.5 w-3.5 text-blue-400" />
              <select
                value={taskType}
                onChange={(event) => setTaskType(event.target.value as TaskType)}
                className="bg-transparent text-[13px] outline-none focus:outline-none focus-visible:outline-none"
              >
                {TASK_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value} className="bg-slate-900">
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex h-10 items-center gap-2 rounded-[14px] border border-white/10 bg-white/5 px-3.5 text-sm text-slate-300">
              <Briefcase className="h-3.5 w-3.5 text-slate-400" />
              <select
                value={priority}
                onChange={(event) => setPriority(event.target.value as TaskPriority)}
                className="bg-transparent text-[13px] capitalize outline-none focus:outline-none focus-visible:outline-none"
              >
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option} value={option} className="bg-slate-900 capitalize">
                    {option}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex h-10 min-w-[200px] flex-1 items-center gap-2 rounded-[14px] border border-white/10 bg-white/5 px-3.5">
              <FolderOpen className="h-3.5 w-3.5 text-slate-400" />
              <input
                value={ticker}
                onChange={(event) => setTicker(event.target.value)}
                placeholder="Ticker / company (optional)"
                className="w-full bg-transparent text-[13px] text-slate-200 outline-none placeholder:text-slate-500 focus:outline-none focus-visible:outline-none"
              />
            </div>
          </div>

          {error && (
            <p className="mt-4 text-sm text-red-300">{error}</p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/10 px-5 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-medium text-slate-500 transition hover:text-slate-300 focus:outline-none focus-visible:outline-none"
          >
            Discard draft
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={creating}
            className="inline-flex min-w-[156px] items-center justify-center rounded-2xl bg-white px-5 py-2.5 text-base font-semibold text-slate-900 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:outline-none"
          >
            {creating ? <Loader2 className="h-5 w-5 animate-spin" /> : 'Create Issue'}
          </button>
        </div>
      </div>
    </div>
  );
}

function EmptyBoard({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-[28px] border border-dashed border-slate-300 bg-white px-8 py-16 text-center">
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-white">
        <FilePlus2 className="h-6 w-6" />
      </div>
      <h2 className="text-xl font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
        Open the first issue
      </h2>
      <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-slate-500">
        Start by defining the work. Issues live here separately from the agent dashboard and inbox.
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
      >
        <FilePlus2 className="h-4 w-4" />
        New Issue
      </button>
    </div>
  );
}

export default function IssueDashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [stats, setStats] = useState<Record<TaskStatus, number> | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const showComposer = searchParams.get('new') === '1';
  const preselectedAssigneeId = searchParams.get('assignee');
  const preselectedProjectId = searchParams.get('project');
  const parentTaskId = searchParams.get('parent');

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskRows, boardStats, projectRows, agentRows] = await Promise.all([
        listTasks({ limit: 200 }),
        getTaskBoardStats(),
        getProjects(),
        getScheduledAgents(),
      ]);
      setTasks(taskRows);
      setStats(boardStats);
      setProjects(projectRows);
      setAgents(agentRows);
    } catch {
      setError('Could not load the issue board.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const board = useMemo(() => normalizeBoard(tasks), [tasks]);
  const liveCount = useMemo(
    () => (stats?.pending || 0) + (stats?.running || 0) + (stats?.in_review || 0),
    [stats],
  );
  const agentsById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);
  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);

  const openComposer = () => {
    setSearchParams({ new: '1' });
  };

  const closeComposer = () => {
    setSearchParams({});
  };

  const handleCreated = (task: ResearchTask, options?: { redirectToInbox?: boolean }) => {
    closeComposer();
    navigate(options?.redirectToInbox ? '/inbox' : `/issues/${task.id}`);
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-6 py-10 lg:px-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500 shadow-sm ring-1 ring-slate-200">
              <span className="h-2 w-2 rounded-full bg-blue-500" />
              {liveCount} live
            </div>
            <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
              Issues
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-500">
              Create and track work items here. The dashboard is for agent cards, while this tab is for the issue queue itself.
            </p>
          </div>

          <button
            type="button"
            onClick={openComposer}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            <FilePlus2 className="h-4 w-4" />
            New Issue
          </button>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <div className="rounded-3xl border border-slate-200 bg-white p-5">
            <p className="text-sm font-medium text-slate-500">Open issues</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
              {liveCount}
            </p>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white p-5">
            <p className="text-sm font-medium text-slate-500">Active projects</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
              {projects.filter((project) => project.status === 'active').length}
            </p>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white p-5">
            <p className="text-sm font-medium text-slate-500">Approved analysts</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900" style={{ letterSpacing: '-0.04em' }}>
              {agents.length}
            </p>
          </div>
        </div>

        <div className="mt-10 rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900" style={{ letterSpacing: '-0.03em' }}>
                Issue board
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Each issue is the unit of work. Click through to review assignment, task state, and findings.
              </p>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : error ? (
            <div className="py-20 text-center text-sm text-red-600">{error}</div>
          ) : tasks.length === 0 ? (
            <div className="pt-8">
              <EmptyBoard onCreate={openComposer} />
            </div>
          ) : (
            <div className="mt-6 grid gap-5 xl:grid-cols-4">
              {Object.entries(board).map(([key, columnTasks]) => (
                <div key={key} className="rounded-3xl bg-slate-50 p-4">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${STATUS_META[key].dot}`} />
                      <h3 className="text-sm font-semibold text-slate-800">{STATUS_META[key].label}</h3>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_META[key].tone}`}>
                      {columnTasks.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {columnTasks.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-xs text-slate-400">
                        No issues
                      </div>
                    ) : (
                      columnTasks.map((task) => (
                        <IssueCard
                          key={task.id}
                          task={task}
                          agentsById={agentsById}
                          projectsById={projectsById}
                        />
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showComposer && (
            <NewIssueModal
              agents={agents}
              projects={projects}
              initialAssigneeId={preselectedAssigneeId}
              initialProjectId={preselectedProjectId}
              initialParentTaskId={parentTaskId}
              onClose={closeComposer}
              onCreated={handleCreated}
            />
      )}
    </div>
  );
}
