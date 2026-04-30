import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  FolderOpen,
  Loader2,
  Play,
  Radar,
  ShieldCheck,
} from 'lucide-react';
import { getProjects, getScheduledAgents, getTask, runTaskPipeline, type ResearchTask } from '../api';
import type { ProjectSummary, ScheduledAgent } from '../types';

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

export default function IssueDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<ResearchTask | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    try {
      const [taskRow, projectRows, agentRows] = await Promise.all([
        getTask(taskId),
        getProjects(),
        getScheduledAgents(),
      ]);
      setTask(taskRow);
      setProjects(projectRows);
      setAgents(agentRows);
    } catch {
      setError('Could not load this issue.');
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
  const canRunPipeline = !!task && task.ticker !== 'GENERAL' && selectedAgentCount > 0 && ['pending', 'failed'].includes(task.status);
  const findings = task?.findings ? Object.entries(task.findings) : [];

  const handleRun = async () => {
    if (!taskId || !canRunPipeline) return;
    setRunning(true);
    try {
      await runTaskPipeline(taskId);
      await load();
    } catch {
      setError('Failed to start the issue pipeline.');
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!task || error) {
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
      <div className="mx-auto max-w-5xl">
        <button
          type="button"
          onClick={() => navigate('/issues')}
          className="mb-6 inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to issues
        </button>

        <div className="rounded-[30px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex flex-col gap-5 border-b border-slate-100 pb-6 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusTone(task.status)}`}>
                  {task.status.replace('_', ' ')}
                </span>
                <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-500">
                  {displayTicker(task.ticker)}
                </span>
              </div>
              <h1 className="text-4xl font-semibold text-slate-900" style={{ letterSpacing: '-0.05em' }}>
                {task.title}
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-relaxed text-slate-600">
                {task.notes?.trim() || 'No issue description yet.'}
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
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

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Assignee</p>
              <p className="mt-2 text-sm font-medium text-slate-900">{assigneeLabel(task, agentsById)}</p>
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
              <p className="mt-2 text-sm font-medium text-slate-900">{formatDateTime(task.created_at)}</p>
            </div>
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-[1.3fr,0.7fr]">
            <div className="rounded-3xl border border-slate-200 p-5">
              <h2 className="text-lg font-semibold text-slate-900">Staffing state</h2>

              {selectedAgentCount === 0 ? (
                <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm text-slate-600">
                    This issue has not been staffed yet. Assign it to an existing agent or leave it unassigned until you decide who should own the work.
                  </p>
                </div>
              ) : (
                <div className="mt-4">
                  <p className="text-sm text-slate-600">
                    This issue is currently configured to use {selectedAgentCount} analyst{selectedAgentCount === 1 ? '' : 's'}.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {task.selected_agents.map((agentName) => (
                      <span key={agentName} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600">
                        {agentName}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {task.pm_synthesis && (
                <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Latest synthesis</p>
                  <p className="mt-2 text-sm leading-relaxed text-emerald-900">
                    {task.pm_synthesis.rationale || task.pm_synthesis.summary || 'Decision captured.'}
                  </p>
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-slate-200 p-5">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-slate-500" />
                <h2 className="text-lg font-semibold text-slate-900">Pipeline readiness</h2>
              </div>
              <div className="mt-4 space-y-3 text-sm text-slate-600">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                  <p className="font-medium text-slate-800">Ticker</p>
                  <p className="mt-1">{task.ticker === 'GENERAL' ? 'General issue — add a specific ticker before running the research pipeline.' : task.ticker}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                  <p className="font-medium text-slate-800">Analyst staffing</p>
                  <p className="mt-1">{selectedAgentCount > 0 ? `${selectedAgentCount} analyst engines selected.` : 'No analysts selected yet.'}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                  <p className="font-medium text-slate-800">Governance</p>
                  <p className="mt-1">Mandate: {task.mandate_check} · Risk: {task.risk_check} · Compliance: {task.compliance_check}</p>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 rounded-3xl border border-slate-200 p-5">
            <div className="flex items-center gap-2">
              <Radar className="h-4 w-4 text-slate-500" />
              <h2 className="text-lg font-semibold text-slate-900">Research findings</h2>
            </div>

            {findings.length === 0 ? (
              <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                No analyst findings yet.
              </div>
            ) : (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {findings.map(([agentName, finding]) => (
                  <div key={agentName} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-slate-900">{finding.title || agentName}</p>
                      <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-500">
                        {finding.sentiment}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-500">Confidence {Math.round((finding.confidence || 0) * 100)}%</p>
                    {finding.key_points?.length > 0 && (
                      <ul className="mt-3 space-y-2 text-sm text-slate-600">
                        {finding.key_points.slice(0, 4).map((point) => (
                          <li key={point} className="flex gap-2">
                            <span className="mt-[7px] h-1.5 w-1.5 flex-shrink-0 rounded-full bg-slate-400" />
                            <span>{point}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
