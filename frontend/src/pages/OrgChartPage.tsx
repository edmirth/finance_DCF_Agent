import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Loader2, Minus, Plus, RefreshCcw } from 'lucide-react';
import { getScheduledAgents } from '../api';
import { roleMetaForAgent } from '../agentRoles';
import type { ScheduledAgent } from '../types';

type OrgNode = ScheduledAgent & { reports: OrgNode[]; synthetic?: boolean };

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily',
  pre_market: 'Pre-market',
  weekly_monday: 'Weekly',
  weekly_friday: 'Friday',
  monthly: 'Monthly',
};

function sortAgents(agents: ScheduledAgent[]): ScheduledAgent[] {
  return agents.slice().sort((a, b) => {
    if (a.is_active !== b.is_active) return Number(b.is_active) - Number(a.is_active);
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
}

function buildOrgForest(agents: ScheduledAgent[]): OrgNode[] {
  const sortedAgents = sortAgents(agents);
  const nodes = new Map<string, OrgNode>();

  for (const agent of sortedAgents) {
    nodes.set(agent.id, { ...agent, reports: [] });
  }

  const roots: OrgNode[] = [];

  for (const agent of sortedAgents) {
    const node = nodes.get(agent.id)!;
    const managerId = agent.manager_agent_id || null;
    if (managerId && nodes.has(managerId)) {
      nodes.get(managerId)!.reports.push(node);
    } else {
      roots.push(node);
    }
  }

  const sortTree = (node: OrgNode) => {
    node.reports.sort((a, b) => {
      if (a.is_active !== b.is_active) return Number(b.is_active) - Number(a.is_active);
      return a.name.localeCompare(b.name);
    });
    node.reports.forEach(sortTree);
  };

  roots.sort((a, b) => {
    if (a.is_active !== b.is_active) return Number(b.is_active) - Number(a.is_active);
    return a.name.localeCompare(b.name);
  });
  roots.forEach(sortTree);
  if (roots.length === 0) return [];

  const syntheticRoot: OrgNode = {
    id: 'synthetic-pm-cio-root',
    name: 'PM / CIO',
    description: 'Top-level orchestrator',
    template: 'market_pulse',
    role_key: null,
    role_title: 'Portfolio Manager / CIO',
    role_family: 'leadership',
    tickers: [],
    topics: [],
    instruction: '',
    schedule_label: 'weekly_monday',
    manager_agent_id: null,
    manager_agent_name: null,
    reports_to_label: undefined,
    delivery_email: undefined,
    delivery_inapp: true,
    is_active: true,
    last_run_at: undefined,
    next_run_at: undefined,
    last_run_status: undefined,
    last_run_summary: undefined,
    heartbeat_routine: null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    reports: roots,
    synthetic: true,
  };

  return [syntheticRoot];
}

function exportCompany(agents: ScheduledAgent[]) {
  const payload = {
    exported_at: new Date().toISOString(),
    agents: agents.map((agent) => ({
      id: agent.id,
      name: agent.name,
      description: agent.description || '',
      role_key: agent.role_key || null,
      role_title: agent.role_title || null,
      role_family: agent.role_family || null,
      template: agent.template,
      tickers: agent.tickers,
      topics: agent.topics,
      instruction: agent.instruction,
      schedule_label: agent.schedule_label,
      manager_agent_id: agent.manager_agent_id || null,
      is_active: agent.is_active,
    })),
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `phronesis-org-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function OrgNodeCard({
  node,
  onSelect,
}: {
  node: OrgNode;
  onSelect: (node: OrgNode) => void;
}) {
  const meta = roleMetaForAgent(node);
  const isSynthetic = Boolean(node.synthetic);
  const managerLabel = isSynthetic
    ? 'Top-level orchestrator'
    : node.manager_agent_id
      ? node.reports_to_label || 'Unknown manager'
      : 'Reports to PM / CIO';

  return (
    <button
      type="button"
      onClick={() => {
        onSelect(node);
      }}
      className={`w-[250px] rounded-2xl border p-4 text-left shadow-[0_12px_30px_rgba(15,23,42,0.08)] transition ${
        isSynthetic
          ? 'cursor-default border-slate-200 bg-white text-slate-900'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-[0_16px_34px_rgba(15,23,42,0.12)]'
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl text-sm font-bold"
          style={isSynthetic ? { background: '#F1F5F9', color: '#0F172A' } : { background: meta.bg, color: meta.color }}
        >
          {isSynthetic ? 'P' : meta.letter}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-[15px] font-semibold text-slate-900">{node.name}</h3>
            <span
              className={`h-2 w-2 flex-shrink-0 rounded-full ${isSynthetic ? 'bg-amber-400' : node.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}
              title={isSynthetic ? 'Leader' : node.is_active ? 'Active' : 'Paused'}
            />
          </div>
          <p className="mt-0.5 text-xs font-medium" style={{ color: isSynthetic ? '#475569' : meta.color }}>
            {isSynthetic ? 'Firm lead' : meta.displayTitle}
          </p>
          <p className={`mt-1 text-xs ${isSynthetic ? 'text-slate-500' : 'text-slate-400'}`}>{managerLabel}</p>
        </div>
      </div>

      {!isSynthetic && node.tickers.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {node.tickers.slice(0, 4).map((ticker) => (
            <span key={ticker} className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
              {ticker}
            </span>
          ))}
          {node.tickers.length > 4 && (
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-400">
              +{node.tickers.length - 4}
            </span>
          )}
        </div>
      )}

      <div className={`mt-3 flex items-center justify-between text-[11px] ${isSynthetic ? 'text-slate-500' : 'text-slate-400'}`}>
        <span>{node.reports.length} direct report{node.reports.length === 1 ? '' : 's'}</span>
        <span>{isSynthetic ? 'Leadership' : SCHEDULE_LABELS[node.schedule_label] || node.schedule_label}</span>
      </div>
    </button>
  );
}

function OrgTree({
  nodes,
  onSelect,
}: {
  nodes: OrgNode[];
  onSelect: (node: OrgNode) => void;
}) {
  if (nodes.length === 0) return null;

  return (
    <ul className="org-tree-root">
      {nodes.map((node) => (
        <li key={node.id}>
          <OrgNodeCard node={node} onSelect={onSelect} />
          {node.reports.length > 0 && <OrgTree nodes={node.reports} onSelect={onSelect} />}
        </li>
      ))}
    </ul>
  );
}

export default function OrgChartPage() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<ScheduledAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const suppressClickRef = useRef(false);
  const panRef = useRef({ x: 0, y: 0 });
  const dragRef = useRef({
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    startPanX: 0,
    startPanY: 0,
  });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await getScheduledAgents();
      setAgents(rows);
    } catch {
      setError('Could not load the org chart.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setPan({ x: 0, y: 0 });
    panRef.current = { x: 0, y: 0 };
  }, [agents.length]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!dragRef.current.active) return;
      const dx = event.clientX - dragRef.current.startX;
      const dy = event.clientY - dragRef.current.startY;
      if (!dragRef.current.moved && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
        dragRef.current.moved = true;
        suppressClickRef.current = true;
      }
      const nextPan = {
        x: dragRef.current.startPanX + dx,
        y: dragRef.current.startPanY + dy,
      };
      panRef.current = nextPan;
      setPan(nextPan);
    };

    const handleMouseUp = () => {
      const moved = dragRef.current.moved;
      dragRef.current.active = false;
      dragRef.current.moved = false;
      setIsDragging(false);
      document.body.style.userSelect = '';
      if (moved) {
        window.setTimeout(() => {
          suppressClickRef.current = false;
        }, 0);
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
    };
  }, []);

  const forest = useMemo(() => buildOrgForest(agents), [agents]);

  const handleCanvasMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    suppressClickRef.current = false;
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      startPanX: panRef.current.x,
      startPanY: panRef.current.y,
    };
    setIsDragging(true);
    document.body.style.userSelect = 'none';
  };

  const handleCanvasWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const nextPan = {
      x: panRef.current.x - event.deltaX,
      y: panRef.current.y - event.deltaY,
    };
    panRef.current = nextPan;
    setPan(nextPan);
  };

  const handleNodeSelect = (node: OrgNode) => {
    if (node.synthetic || suppressClickRef.current) return;
    navigate(`/routines/${node.id}`, { state: { from: '/org' } });
  };

  const handleResetView = () => {
    setZoom(1);
    const nextPan = { x: 0, y: 0 };
    panRef.current = nextPan;
    setPan(nextPan);
  };

  return (
    <div className="h-[calc(100dvh-56px)] overflow-hidden bg-slate-50 text-slate-900 md:h-dvh" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <style>{`
        .org-tree-root,
        .org-tree-root ul {
          display: flex;
          justify-content: center;
          margin: 0;
          padding: 0;
          list-style: none;
        }

        .org-tree-root ul {
          position: relative;
          padding-top: 36px;
        }

        .org-tree-root ul::before {
          content: "";
          position: absolute;
          top: 0;
          left: 50%;
          width: 0;
          height: 36px;
          border-left: 1px solid rgba(148, 163, 184, 0.45);
        }

        .org-tree-root li {
          position: relative;
          padding: 36px 14px 0;
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .org-tree-root li::before,
        .org-tree-root li::after {
          content: "";
          position: absolute;
          top: 0;
          width: 50%;
          height: 36px;
          border-top: 1px solid rgba(148, 163, 184, 0.45);
        }

        .org-tree-root li::before {
          right: 50%;
        }

        .org-tree-root li::after {
          left: 50%;
          border-left: 1px solid rgba(148, 163, 184, 0.45);
        }

        .org-tree-root li:only-child::before,
        .org-tree-root li:only-child::after {
          display: none;
        }

        .org-tree-root li:only-child {
          padding-top: 0;
        }

        .org-tree-root li:first-child::before,
        .org-tree-root li:last-child::after {
          border: 0;
        }

        .org-tree-root li:last-child::before {
          border-right: 1px solid rgba(148, 163, 184, 0.45);
          border-radius: 0 10px 0 0;
        }

        .org-tree-root li:first-child::after {
          border-radius: 10px 0 0 0;
        }
      `}</style>

      <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col px-6 py-8 lg:px-10">
        <div className="flex flex-shrink-0 items-center justify-between border-b border-slate-200 pb-4">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Org Chart</p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => exportCompany(agents)}
              disabled={agents.length === 0}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download className="h-4 w-4" />
              Export company
            </button>
          </div>
        </div>

        <div className="relative mt-4 min-h-0 flex-1 overflow-hidden rounded-[28px] border border-slate-200 bg-white">
          <div className="absolute right-4 top-4 z-10 flex flex-col gap-2">
            <button
              type="button"
              onClick={() => setZoom((current) => Math.min(1.6, Number((current + 0.1).toFixed(2))))}
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              aria-label="Zoom in"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom((current) => Math.max(0.6, Number((current - 0.1).toFixed(2))))}
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              aria-label="Zoom out"
            >
              <Minus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={handleResetView}
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              aria-label="Reset zoom"
            >
              <RefreshCcw className="h-4 w-4" />
            </button>
          </div>

          <div
            ref={canvasRef}
            onMouseDownCapture={handleCanvasMouseDown}
            onWheel={handleCanvasWheel}
            onDragStart={(event) => event.preventDefault()}
            className={`h-full overflow-hidden ${isDragging ? 'cursor-grabbing select-none' : 'cursor-grab'}`}
          >
            {loading ? (
              <div className="flex h-full min-h-[420px] items-center justify-center">
                <Loader2 className="h-7 w-7 animate-spin text-slate-300" />
              </div>
            ) : error ? (
              <div className="flex h-full min-h-[420px] items-center justify-center">
                <p className="text-sm text-red-500">{error}</p>
              </div>
            ) : agents.length === 0 ? (
              <div className="flex h-full min-h-[420px] flex-col items-center justify-center text-center">
                <div className="h-10 w-10 rounded-2xl border border-slate-200 bg-slate-50" />
                <p className="mt-4 text-base font-medium text-slate-700">No agent structure yet</p>
                <p className="mt-2 max-w-md text-sm text-slate-500">
                  Hire agents first. Once reporting lines exist, the org chart will show how they are orchestrated.
                </p>
              </div>
            ) : (
              <div className="flex h-full min-h-[420px] min-w-full items-start justify-center overflow-hidden px-8 py-10">
                <div className="will-change-transform" style={{ transform: `translate3d(${pan.x}px, ${pan.y}px, 0)` }}>
                  <div className="min-w-max pb-8 transition-transform duration-150" style={{ transform: `scale(${zoom})`, transformOrigin: 'top center' }}>
                    <OrgTree nodes={forest} onSelect={handleNodeSelect} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
