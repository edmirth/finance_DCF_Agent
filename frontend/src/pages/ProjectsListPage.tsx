import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Archive,
  Calendar,
  FileText,
  FolderOpenDot,
  MessageSquare,
  Plus,
  Search,
  Sparkles,
} from 'lucide-react';
import { getProjects, createProject, deleteProject } from '../api';
import { ProjectSummary } from '../types';

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function ProjectCard({
  project,
  onArchive,
}: {
  project: ProjectSummary;
  onArchive: (id: string) => void;
}) {
  const navigate = useNavigate();
  const tickers = project.config?.tickers || [];

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/projects/${project.id}`)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          navigate(`/projects/${project.id}`);
        }
      }}
      style={{
        width: '100%',
        textAlign: 'left',
        background: 'rgba(255, 254, 250, 0.92)',
        border: '1px solid rgba(34, 27, 19, 0.08)',
        borderRadius: '24px',
        padding: '1.15rem 1.15rem 1.1rem',
        cursor: 'pointer',
        transition: 'transform 0.2s, box-shadow 0.2s, border-color 0.2s',
        boxShadow: '0 18px 48px rgba(28, 22, 14, 0.06)',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = '0 22px 56px rgba(28, 22, 14, 0.09)';
        e.currentTarget.style.borderColor = '#C9B897';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = '0 18px 48px rgba(28, 22, 14, 0.06)';
        e.currentTarget.style.borderColor = 'rgba(34, 27, 19, 0.08)';
      }}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                background: '#1F1A14',
                color: '#FFF8ED',
                borderRadius: '999px',
                padding: '0.35rem 0.75rem',
                fontFamily: 'IBM Plex Sans, sans-serif',
                fontSize: '0.72rem',
                fontWeight: 600,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              <FolderOpenDot size={13} />
              Active workspace
            </div>
            {tickers.slice(0, 3).map(ticker => (
              <span
                key={ticker}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  background: '#F2ECE2',
                  border: '1px solid #DED4C4',
                  borderRadius: '999px',
                  padding: '0.3rem 0.65rem',
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '0.72rem',
                  color: '#3A342C',
                }}
              >
                {ticker}
              </span>
            ))}
          </div>

          <h3
            style={{
              fontSize: '1.1rem',
              fontWeight: 700,
              color: '#1F1A14',
              fontFamily: 'IBM Plex Sans, sans-serif',
              letterSpacing: '-0.03em',
              margin: '0.85rem 0 0.45rem',
            }}
          >
            {project.title}
          </h3>

          <p
            style={{
              fontSize: '0.9rem',
              color: '#655E53',
              fontFamily: 'IBM Plex Sans, sans-serif',
              lineHeight: 1.65,
              margin: 0,
              maxWidth: '760px',
            }}
          >
            {project.thesis}
          </p>

          <div className="flex flex-wrap items-center gap-4 mt-4">
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontSize: '0.78rem',
                color: '#8F8577',
                fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            >
              <MessageSquare size={13} />
              {project.session_count} session{project.session_count !== 1 ? 's' : ''}
            </span>
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontSize: '0.78rem',
                color: '#8F8577',
                fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            >
              <FileText size={13} />
              {project.document_count} doc{project.document_count !== 1 ? 's' : ''}
            </span>
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontSize: '0.78rem',
                color: '#8F8577',
                fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            >
              <Calendar size={13} />
              Updated {formatDate(project.updated_at)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start">
          <button
            onClick={e => {
              e.stopPropagation();
              if (window.confirm(`Archive "${project.title}"?`)) onArchive(project.id);
            }}
            title="Archive project"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '38px',
              height: '38px',
              borderRadius: '999px',
              border: '1px solid #E6DCCB',
              background: '#FBF7EF',
              color: '#8E8679',
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            <Archive size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

function NewProjectForm({ onCancel, onCreated }: { onCancel: () => void; onCreated: (id: string) => void }) {
  const [title, setTitle] = useState('');
  const [thesis, setThesis] = useState('');
  const [tickers, setTickers] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !thesis.trim()) {
      setError('Title and thesis are required.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const tickerList = tickers
        .split(',')
        .map(t => t.trim().toUpperCase())
        .filter(Boolean);
      const project = await createProject(title.trim(), thesis.trim(), tickerList.length ? tickerList : undefined);
      onCreated(project.id);
    } catch {
      setError('Failed to create project. Please try again.');
    }
    setLoading(false);
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        background: 'rgba(255, 254, 250, 0.94)',
        border: '1px solid rgba(34, 27, 19, 0.08)',
        borderRadius: '28px',
        padding: '1.4rem',
        marginBottom: '1.5rem',
        boxShadow: '0 22px 56px rgba(28, 22, 14, 0.07)',
      }}
    >
      <div className="flex items-center gap-2 mb-6">
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '999px',
            background: '#1F1A14',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Sparkles size={16} color="#FFF8ED" />
        </div>
        <div>
          <h2
            style={{
              fontSize: '1.05rem',
              fontWeight: 700,
              color: '#1F1A14',
              fontFamily: 'IBM Plex Sans, sans-serif',
              letterSpacing: '-0.03em',
              margin: 0,
            }}
          >
            Create a new project workspace
          </h2>
          <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.82rem', color: '#847B6E', margin: '0.2rem 0 0' }}>
            Define the thesis once, then let the workspace build memory over time.
          </p>
        </div>
      </div>

      <div style={{ marginBottom: '0.95rem' }}>
        <label
          style={{
            display: 'block',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#464137',
            fontFamily: 'IBM Plex Sans, sans-serif',
            marginBottom: '0.45rem',
          }}
        >
          Project title
        </label>
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="e.g. European utilities rerating thesis"
          disabled={loading}
          style={{
            width: '100%',
            padding: '0.8rem 0.95rem',
            border: '1px solid #E2D8C8',
            borderRadius: '16px',
            fontSize: '0.92rem',
            fontFamily: 'IBM Plex Sans, sans-serif',
            color: '#1F1A14',
            outline: 'none',
            boxSizing: 'border-box',
            background: '#FFFCF6',
          }}
          onFocus={e => (e.target.style.borderColor = '#BEA777')}
          onBlur={e => (e.target.style.borderColor = '#E2D8C8')}
        />
      </div>

      <div style={{ marginBottom: '0.95rem' }}>
        <label
          style={{
            display: 'block',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#464137',
            fontFamily: 'IBM Plex Sans, sans-serif',
            marginBottom: '0.45rem',
          }}
        >
          Investment thesis
        </label>
        <textarea
          value={thesis}
          onChange={e => setThesis(e.target.value)}
          placeholder="e.g. Rate cuts and balance-sheet repair should re-rate the sector over the next 12-18 months."
          rows={4}
          disabled={loading}
          style={{
            width: '100%',
            padding: '0.8rem 0.95rem',
            border: '1px solid #E2D8C8',
            borderRadius: '16px',
            fontSize: '0.92rem',
            fontFamily: 'IBM Plex Sans, sans-serif',
            color: '#1F1A14',
            outline: 'none',
            resize: 'vertical',
            boxSizing: 'border-box',
            lineHeight: 1.65,
            background: '#FFFCF6',
          }}
          onFocus={e => (e.target.style.borderColor = '#BEA777')}
          onBlur={e => (e.target.style.borderColor = '#E2D8C8')}
        />
      </div>

      <div style={{ marginBottom: '1.15rem' }}>
        <label
          style={{
            display: 'block',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#464137',
            fontFamily: 'IBM Plex Sans, sans-serif',
            marginBottom: '0.45rem',
          }}
        >
          Tickers <span style={{ fontWeight: 400, color: '#8B8275' }}>(optional, comma-separated)</span>
        </label>
        <input
          type="text"
          value={tickers}
          onChange={e => setTickers(e.target.value)}
          placeholder="e.g. EQNR, XOM, CVX"
          disabled={loading}
          style={{
            width: '100%',
            padding: '0.8rem 0.95rem',
            border: '1px solid #E2D8C8',
            borderRadius: '16px',
            fontSize: '0.92rem',
            fontFamily: 'IBM Plex Sans, sans-serif',
            color: '#1F1A14',
            outline: 'none',
            boxSizing: 'border-box',
            background: '#FFFCF6',
          }}
          onFocus={e => (e.target.style.borderColor = '#BEA777')}
          onBlur={e => (e.target.style.borderColor = '#E2D8C8')}
        />
      </div>

      {error && (
        <p
          style={{
            fontSize: '0.8125rem',
            color: '#B14545',
            fontFamily: 'IBM Plex Sans, sans-serif',
            marginBottom: '0.9rem',
          }}
        >
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: '0.75rem 1.1rem',
            borderRadius: '999px',
            fontSize: '0.875rem',
            fontWeight: 600,
            fontFamily: 'IBM Plex Sans, sans-serif',
            background: '#1F1A14',
            color: '#FFF8ED',
            border: 'none',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? 'Creating...' : 'Create Project'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          style={{
            padding: '0.75rem 1.1rem',
            borderRadius: '999px',
            fontSize: '0.875rem',
            fontWeight: 600,
            fontFamily: 'IBM Plex Sans, sans-serif',
            background: '#F2ECE2',
            color: '#615A4E',
            border: '1px solid #E2D8C8',
            cursor: 'pointer',
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function ProjectsListPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await getProjects();
        setProjects(data.filter(p => p.status === 'active'));
      } catch {
        // ignore
      }
      setLoading(false);
    })();
  }, []);

  const filteredProjects = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter(project => {
      const tickers = (project.config?.tickers || []).join(' ').toLowerCase();
      return (
        project.title.toLowerCase().includes(needle) ||
        project.thesis.toLowerCase().includes(needle) ||
        tickers.includes(needle)
      );
    });
  }, [projects, query]);

  const handleArchive = async (id: string) => {
    try {
      await deleteProject(id);
      setProjects(prev => prev.filter(p => p.id !== id));
    } catch {
      // ignore
    }
  };

  const handleCreated = (id: string) => {
    navigate(`/projects/${id}`);
  };

  const totalSessions = projects.reduce((sum, project) => sum + project.session_count, 0);
  const totalDocs = projects.reduce((sum, project) => sum + project.document_count, 0);

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(180deg, #F5EFE4 0%, #FBF8F1 32%, #FFFFFF 68%)',
        paddingLeft: '80px',
      }}
    >
      <div className="mx-auto max-w-[1180px] px-4 sm:px-6 lg:px-8 py-8">
        <section
          style={{
            background: 'linear-gradient(135deg, rgba(255, 252, 245, 0.96) 0%, rgba(248, 241, 229, 0.94) 100%)',
            border: '1px solid rgba(31, 24, 16, 0.08)',
            borderRadius: '30px',
            padding: '1.5rem',
            boxShadow: '0 26px 80px rgba(32, 23, 12, 0.08)',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          <div
            style={{
              position: 'absolute',
              inset: '-40% auto auto 74%',
              width: '280px',
              height: '280px',
              borderRadius: '999px',
              background: 'radial-gradient(circle, rgba(166, 136, 83, 0.18) 0%, rgba(166, 136, 83, 0) 70%)',
              pointerEvents: 'none',
            }}
          />

          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  background: '#1F1A14',
                  color: '#FFF8ED',
                  borderRadius: '999px',
                  padding: '0.35rem 0.75rem',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                }}
              >
                <Sparkles size={13} />
                Project workspaces
              </div>
              <h1
                style={{
                  fontSize: 'clamp(2rem, 3vw, 2.8rem)',
                  fontWeight: 700,
                  color: '#1F1A14',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  letterSpacing: '-0.05em',
                  margin: '0.9rem 0 0.7rem',
                  lineHeight: 1,
                }}
              >
                Build thesis-driven analysis that compounds
              </h1>
              <p
                style={{
                  fontSize: '1rem',
                  color: '#655E53',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  lineHeight: 1.7,
                  margin: 0,
                  maxWidth: '760px',
                }}
              >
                Projects ground every conversation in an explicit investment view, then accumulate memory, uploaded evidence, and linked sessions around it.
              </p>
            </div>

            {!showForm && (
              <button
                onClick={() => setShowForm(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.8rem 1.1rem',
                  borderRadius: '999px',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  background: '#1F1A14',
                  color: '#FFF8ED',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <Plus size={15} />
                New Project
              </button>
            )}
          </div>

          <div className="grid gap-3 mt-6 sm:grid-cols-3">
            {[
              { label: 'Active projects', value: String(projects.length), hint: 'Live thesis workspaces' },
              { label: 'Linked sessions', value: String(totalSessions), hint: 'Conversation trails inside projects' },
              { label: 'Stored documents', value: String(totalDocs), hint: 'Embedded project materials' },
            ].map(stat => (
              <div
                key={stat.label}
                style={{
                  background: 'rgba(255, 252, 244, 0.82)',
                  border: '1px solid rgba(43, 35, 23, 0.08)',
                  borderRadius: '18px',
                  padding: '0.95rem 1rem',
                }}
              >
                <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.75rem', color: '#8C8376', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
                  {stat.label}
                </div>
                <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '1.45rem', fontWeight: 700, color: '#1F1A14', marginTop: '0.35rem', letterSpacing: '-0.04em' }}>
                  {stat.value}
                </div>
                <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.82rem', color: '#70695E', marginTop: '0.2rem' }}>
                  {stat.hint}
                </div>
              </div>
            ))}
          </div>
        </section>

        {showForm && (
          <div className="mt-6">
            <NewProjectForm
              onCancel={() => setShowForm(false)}
              onCreated={handleCreated}
            />
          </div>
        )}

        <section className="mt-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-4">
            <div>
              <h2
                style={{
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  fontSize: '1.05rem',
                  fontWeight: 700,
                  color: '#1F1A14',
                  letterSpacing: '-0.03em',
                  margin: 0,
                }}
              >
                Active workspaces
              </h2>
              <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.82rem', color: '#8A8174', margin: '0.25rem 0 0' }}>
                Search by title, thesis, or ticker.
              </p>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                background: 'rgba(255, 254, 250, 0.92)',
                border: '1px solid rgba(34, 27, 19, 0.08)',
                borderRadius: '999px',
                padding: '0.7rem 0.95rem',
                minWidth: 'min(100%, 340px)',
              }}
            >
              <Search size={16} color="#8E8679" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search projects..."
                style={{
                  width: '100%',
                  border: 'none',
                  outline: 'none',
                  background: 'transparent',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  fontSize: '0.9rem',
                  color: '#1F1A14',
                }}
              />
            </div>
          </div>

          {loading ? (
            <div className="text-center py-16">
              <p style={{ color: '#9A9081', fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.9rem' }}>
                Loading...
              </p>
            </div>
          ) : filteredProjects.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '72px 24px',
                border: '1px dashed #DACFBE',
                borderRadius: '28px',
                background: 'rgba(255, 254, 250, 0.86)',
              }}
            >
              <FolderOpenDot size={42} style={{ color: '#C2B7A6', margin: '0 auto 16px' }} />
              <p
                style={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  color: '#403A32',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  marginBottom: '0.4rem',
                }}
              >
                {projects.length === 0 ? 'No projects yet - create your first thesis workspace' : 'No matching projects'}
              </p>
              <p
                style={{
                  fontSize: '0.84rem',
                  color: '#978D7F',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  marginBottom: '1.1rem',
                }}
              >
                {projects.length === 0
                  ? 'Projects help every analysis session stay grounded in your evolving investment view.'
                  : 'Try a different title, thesis phrase, or ticker.'}
              </p>
              {!showForm && projects.length === 0 && (
                <button
                  onClick={() => setShowForm(true)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                    padding: '0.8rem 1.1rem',
                    borderRadius: '999px',
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    background: '#1F1A14',
                    color: '#FFF8ED',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  <Plus size={15} />
                  New Project
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredProjects.map(project => (
                <ProjectCard key={project.id} project={project} onArchive={handleArchive} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
