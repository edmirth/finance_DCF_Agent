import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Folder, Plus, Archive, ChevronRight, FileText, MessageSquare, Calendar } from 'lucide-react';
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

  return (
    <div
      onClick={() => navigate(`/projects/${project.id}`)}
      style={{
        background: '#FFFFFF',
        border: '1px solid #E5E7EB',
        borderRadius: '12px',
        padding: '20px',
        cursor: 'pointer',
        transition: 'box-shadow 0.2s, border-color 0.2s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.08)';
        e.currentTarget.style.borderColor = '#10B981';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = 'none';
        e.currentTarget.style.borderColor = '#E5E7EB';
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              background: '#F0FDF4',
              border: '1px solid #BBF7D0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginTop: '2px',
            }}
          >
            <Folder size={16} color="#10B981" />
          </div>
          <div className="flex-1 min-w-0">
            <h3
              style={{
                fontSize: '1rem',
                fontWeight: 700,
                color: '#1A1A1A',
                fontFamily: 'Inter, sans-serif',
                letterSpacing: '-0.01em',
                margin: '0 0 6px',
              }}
            >
              {project.title}
            </h3>
            <p
              style={{
                fontSize: '0.8125rem',
                color: '#6B7280',
                fontFamily: 'Inter, sans-serif',
                lineHeight: 1.55,
                margin: '0 0 12px',
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
              }}
            >
              {project.thesis.slice(0, 120)}{project.thesis.length > 120 ? '…' : ''}
            </p>
            <div className="flex items-center gap-4 flex-wrap">
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.75rem',
                  color: '#9CA3AF',
                  fontFamily: 'Inter, sans-serif',
                }}
              >
                <MessageSquare size={11} />
                {project.session_count} session{project.session_count !== 1 ? 's' : ''}
              </span>
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.75rem',
                  color: '#9CA3AF',
                  fontFamily: 'Inter, sans-serif',
                }}
              >
                <FileText size={11} />
                {project.document_count} doc{project.document_count !== 1 ? 's' : ''}
              </span>
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.75rem',
                  color: '#9CA3AF',
                  fontFamily: 'Inter, sans-serif',
                }}
              >
                <Calendar size={11} />
                Updated {formatDate(project.updated_at)}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={e => {
              e.stopPropagation();
              if (window.confirm(`Archive "${project.title}"?`)) onArchive(project.id);
            }}
            title="Archive project"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              border: '1px solid #E5E7EB',
              background: '#F9FAFB',
              color: '#9CA3AF',
              cursor: 'pointer',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = '#FCA5A5';
              e.currentTarget.style.color = '#EF4444';
              e.currentTarget.style.background = '#FFF5F5';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = '#E5E7EB';
              e.currentTarget.style.color = '#9CA3AF';
              e.currentTarget.style.background = '#F9FAFB';
            }}
          >
            <Archive size={14} />
          </button>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '32px',
              height: '32px',
              color: '#D1D5DB',
            }}
          >
            <ChevronRight size={16} />
          </div>
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
        background: '#FFFFFF',
        border: '1px solid #10B981',
        borderRadius: '12px',
        padding: '24px',
        marginBottom: '24px',
        boxShadow: '0 4px 16px rgba(16, 185, 129, 0.08)',
      }}
    >
      <h2
        style={{
          fontSize: '1rem',
          fontWeight: 700,
          color: '#1A1A1A',
          fontFamily: 'Inter, sans-serif',
          letterSpacing: '-0.01em',
          margin: '0 0 20px',
        }}
      >
        New Investment Project
      </h2>

      <div style={{ marginBottom: '14px' }}>
        <label
          style={{
            display: 'block',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#374151',
            fontFamily: 'Inter, sans-serif',
            marginBottom: '6px',
          }}
        >
          Project Title
        </label>
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="e.g. Equinor Oil Cycle Analysis"
          disabled={loading}
          style={{
            width: '100%',
            padding: '9px 12px',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontFamily: 'Inter, sans-serif',
            color: '#1A1A1A',
            outline: 'none',
            boxSizing: 'border-box',
          }}
          onFocus={e => (e.target.style.borderColor = '#10B981')}
          onBlur={e => (e.target.style.borderColor = '#E5E7EB')}
        />
      </div>

      <div style={{ marginBottom: '14px' }}>
        <label
          style={{
            display: 'block',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#374151',
            fontFamily: 'Inter, sans-serif',
            marginBottom: '6px',
          }}
        >
          Investment Thesis
        </label>
        <textarea
          value={thesis}
          onChange={e => setThesis(e.target.value)}
          placeholder="e.g. Equinor is overvalued given the oil cycle; Brent crude will fall below $70 in H2 2026 as OPEC+ discipline breaks down."
          rows={3}
          disabled={loading}
          style={{
            width: '100%',
            padding: '9px 12px',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontFamily: 'Inter, sans-serif',
            color: '#1A1A1A',
            outline: 'none',
            resize: 'vertical',
            boxSizing: 'border-box',
            lineHeight: 1.55,
          }}
          onFocus={e => (e.target.style.borderColor = '#10B981')}
          onBlur={e => (e.target.style.borderColor = '#E5E7EB')}
        />
      </div>

      <div style={{ marginBottom: '20px' }}>
        <label
          style={{
            display: 'block',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#374151',
            fontFamily: 'Inter, sans-serif',
            marginBottom: '6px',
          }}
        >
          Tickers{' '}
          <span style={{ fontWeight: 400, color: '#9CA3AF' }}>(optional, comma-separated)</span>
        </label>
        <input
          type="text"
          value={tickers}
          onChange={e => setTickers(e.target.value)}
          placeholder="e.g. EQNR, XOM, CVX"
          disabled={loading}
          style={{
            width: '100%',
            padding: '9px 12px',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontFamily: 'Inter, sans-serif',
            color: '#1A1A1A',
            outline: 'none',
            boxSizing: 'border-box',
          }}
          onFocus={e => (e.target.style.borderColor = '#10B981')}
          onBlur={e => (e.target.style.borderColor = '#E5E7EB')}
        />
      </div>

      {error && (
        <p
          style={{
            fontSize: '0.8125rem',
            color: '#EF4444',
            fontFamily: 'Inter, sans-serif',
            marginBottom: '14px',
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
            padding: '9px 20px',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontWeight: 600,
            fontFamily: 'Inter, sans-serif',
            background: '#1A1A1A',
            color: '#FFFFFF',
            border: 'none',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? 'Creating…' : 'Create Project'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          style={{
            padding: '9px 20px',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontWeight: 600,
            fontFamily: 'Inter, sans-serif',
            background: '#F3F4F6',
            color: '#6B7280',
            border: 'none',
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const showForm = searchParams.get('new') === '1';

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

  const openForm = () => {
    const next = new URLSearchParams(searchParams);
    next.set('new', '1');
    setSearchParams(next);
  };

  const closeForm = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('new');
    setSearchParams(next);
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#FAFAFA',
      }}
    >
      <div style={{ maxWidth: '800px', margin: '0 auto', padding: '40px 24px' }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: '#1A1A1A',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Folder size={18} color="#FFFFFF" />
            </div>
            <div>
              <h1
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 700,
                  color: '#1A1A1A',
                  fontFamily: 'Inter, sans-serif',
                  letterSpacing: '-0.02em',
                  margin: 0,
                }}
              >
                Investment Projects
              </h1>
              <p
                style={{
                  fontSize: '0.8125rem',
                  color: '#9CA3AF',
                  fontFamily: 'Inter, sans-serif',
                  margin: 0,
                }}
              >
                {projects.length} active {projects.length === 1 ? 'project' : 'projects'}
              </p>
            </div>
          </div>

          {!showForm && (
            <button
              onClick={openForm}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '9px 16px',
                borderRadius: '8px',
                fontSize: '0.875rem',
                fontWeight: 600,
                fontFamily: 'Inter, sans-serif',
                background: '#1A1A1A',
                color: '#FFFFFF',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <Plus size={15} />
              New Project
            </button>
          )}
        </div>

        {/* New project form */}
        {showForm && (
          <NewProjectForm
            onCancel={closeForm}
            onCreated={handleCreated}
          />
        )}

        {/* Content */}
        {loading ? (
          <div className="text-center py-16">
            <p style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif', fontSize: '0.875rem' }}>
              Loading…
            </p>
          </div>
        ) : projects.length === 0 ? (
          <div
            style={{
              textAlign: 'center',
              padding: '64px 24px',
              border: '1px dashed #E5E7EB',
              borderRadius: '12px',
              background: '#FFFFFF',
            }}
          >
            <Folder size={40} style={{ color: '#D1D5DB', margin: '0 auto 16px' }} />
            <p
              style={{
                fontSize: '1rem',
                fontWeight: 600,
                color: '#374151',
                fontFamily: 'Inter, sans-serif',
                marginBottom: '8px',
              }}
            >
              No projects yet — create your first investment thesis
            </p>
            <p
              style={{
                fontSize: '0.8125rem',
                color: '#9CA3AF',
                fontFamily: 'Inter, sans-serif',
                marginBottom: '20px',
              }}
            >
              Projects ground every analysis session in your thesis and accumulate memory across sessions.
            </p>
            {!showForm && (
              <button
                onClick={openForm}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '9px 20px',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  fontFamily: 'Inter, sans-serif',
                  background: '#1A1A1A',
                  color: '#FFFFFF',
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
          <div className="space-y-3">
            {projects.map(project => (
              <ProjectCard key={project.id} project={project} onArchive={handleArchive} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
