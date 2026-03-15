import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import Chat from '../components/Chat';
import ToastNotification from '../components/ToastNotification';
import { Agent, Message, ProjectDetail, ProjectDocument, SessionSummary } from '../types';
import {
  getAgents, getProject, getProjectSessions, getSession,
  getProjectMemory, patchProjectMemory, getProjectDocuments,
  deleteProjectDocument, uploadProjectDocument,
} from '../api';

const AUTO_AGENT: Agent = {
  id: 'auto',
  name: 'Auto',
  description: 'Automatically routes to the best agent for your question',
  example: 'Ask anything about stocks, markets, or portfolio analysis',
  icon: '✨',
  color: 'bg-gray-500',
};

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx', '.csv'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

type PanelTab = 'memory' | 'documents' | 'sessions';

type ThesisStatus = 'STRONG' | 'WEAKENING' | 'CHALLENGED' | 'INVALIDATED' | 'Not assessed';

interface ThesisHealth {
  status: ThesisStatus;
  rationale: string;
}

const THESIS_STATUS_STYLES: Record<ThesisStatus, { bg: string; color: string; border: string }> = {
  STRONG: { bg: '#D1FAE5', color: '#065F46', border: '#6EE7B7' },
  WEAKENING: { bg: '#FEF9C3', color: '#854D0E', border: '#FDE047' },
  CHALLENGED: { bg: '#FFEDD5', color: '#9A3412', border: '#FED7AA' },
  INVALIDATED: { bg: '#FEE2E2', color: '#991B1B', border: '#FECACA' },
  'Not assessed': { bg: '#F3F4F6', color: '#6B7280', border: '#E5E7EB' },
};

function parseThesisHealth(memoryDoc: string): ThesisHealth {
  const sectionMatch = memoryDoc.match(/## Thesis Health\s*([\s\S]*?)(?=\n## |\n# |$)/);
  if (!sectionMatch) return { status: 'Not assessed', rationale: '' };

  const section = sectionMatch[1];
  const statusMatch = section.match(/\*\*Status\*\*:\s*(STRONG|WEAKENING|CHALLENGED|INVALIDATED)/);
  const rationaleMatch = section.match(/\*\*Rationale\*\*:\s*(.+)/);

  if (!statusMatch) return { status: 'Not assessed', rationale: '' };

  return {
    status: statusMatch[1] as ThesisStatus,
    rationale: rationaleMatch ? rationaleMatch[1].trim() : '',
  };
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── Memory doc parsers ──────────────────────────────────────────────────────

function parseSection(memoryDoc: string, header: string): string {
  const escaped = header.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = memoryDoc.match(new RegExp(`## ${escaped}\\n([\\s\\S]*?)(?=\\n## |\\n# |$)`));
  const raw = match ? match[1].trim() : '';
  return raw === '(to be populated)' || raw === '(none yet)' ? '' : raw;
}

function parseBullets(content: string): string[] {
  if (!content) return [];
  return content.split('\n').filter(l => l.trim().startsWith('- ')).map(l => l.trim().slice(2).trim()).filter(Boolean);
}

function parseConclusion(text: string): { date: string; content: string } {
  const m = text.match(/^\[(\d{4}-\d{2}-\d{2})[^\]]*\]\s*(.+)$/);
  return m ? { date: m[1], content: m[2] } : { date: '', content: text };
}

function parseTickers(content: string): Array<{ label: string; ticker: string }> {
  if (!content) return [];
  return parseBullets(content).map(b => {
    const m = b.match(/^(.+?)\s*\(([A-Z]{1,6})\)/);
    return m ? { label: m[1].trim(), ticker: m[2] } : { label: b, ticker: '' };
  });
}

// ── Memory section card ────────────────────────────────────────────────────

const SECTION_ICON: Record<string, string> = {
  'Thesis': '💡',
  'Key Assumptions': '✓',
  'Violated or Revised Assumptions': '⚠',
  'Thesis Health': '❤',
  'Key Companies & Tickers': '🏢',
  'Accumulated Conclusions': '📌',
  'Open Questions': '?',
  'Uploaded Document Summaries': '📄',
  'Live Data Snapshots': '📊',
};

function SectionCard({ title, children, accent }: { title: string; children: React.ReactNode; accent?: string }) {
  return (
    <div style={{
      border: '1px solid #F0F0F0',
      borderRadius: '10px',
      padding: '0.875rem 1rem',
      marginBottom: '0.5rem',
      background: '#FFFFFF',
      borderLeft: accent ? `3px solid ${accent}` : '1px solid #F0F0F0',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.375rem',
        marginBottom: '0.625rem',
      }}>
        <span style={{ fontSize: '0.6875rem' }}>{SECTION_ICON[title]}</span>
        <span style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.6875rem',
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: '#9CA3AF',
        }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function EmptyPlaceholder({ label }: { label: string }) {
  return (
    <div style={{
      border: '1.5px dashed #E5E7EB',
      borderRadius: '6px',
      padding: '0.625rem 0.875rem',
      textAlign: 'center',
    }}>
      <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#D1D5DB' }}>{label}</span>
    </div>
  );
}

function MemoryDashboard({ memoryDoc, thesisHealth }: { memoryDoc: string; thesisHealth: ThesisHealth }) {
  const thesis = parseSection(memoryDoc, 'Thesis');
  const assumptions = parseBullets(parseSection(memoryDoc, 'Key Assumptions'));
  const violated = parseBullets(parseSection(memoryDoc, 'Violated or Revised Assumptions'));
  const tickers = parseTickers(parseSection(memoryDoc, 'Key Companies & Tickers'));
  const conclusions = parseBullets(parseSection(memoryDoc, 'Accumulated Conclusions')).map(parseConclusion);
  const questions = parseBullets(parseSection(memoryDoc, 'Open Questions'));
  const docSummaries = parseSection(memoryDoc, 'Uploaded Document Summaries');
  const snapshots = parseBullets(parseSection(memoryDoc, 'Live Data Snapshots'));

  const healthStyle = THESIS_STATUS_STYLES[thesisHealth.status];

  return (
    <div>
      {/* Thesis */}
      <SectionCard title="Thesis" accent="#10B981">
        {thesis ? (
          <div style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.875rem',
            color: '#1A1A1A',
            lineHeight: 1.6,
            fontStyle: 'italic',
            borderLeft: '2px solid #D1FAE5',
            paddingLeft: '0.75rem',
          }}>{thesis}</div>
        ) : <EmptyPlaceholder label="No thesis defined yet" />}
      </SectionCard>

      {/* Thesis Health */}
      <SectionCard title="Thesis Health">
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.75rem',
          background: healthStyle.bg,
          border: `1px solid ${healthStyle.border}`,
          borderRadius: '8px',
          padding: '0.75rem',
        }}>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: healthStyle.color,
            flexShrink: 0,
            marginTop: '5px',
          }} />
          <div>
            <div style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', fontWeight: 700, color: healthStyle.color }}>
              {thesisHealth.status}
            </div>
            {thesisHealth.rationale && (
              <div style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: healthStyle.color, marginTop: '0.25rem', opacity: 0.85 }}>
                {thesisHealth.rationale}
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      {/* Key Companies & Tickers */}
      <SectionCard title="Key Companies & Tickers">
        {tickers.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
            {tickers.map((t, i) => (
              <div key={i} style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.375rem',
                background: '#F9FAFB',
                border: '1px solid #E5E7EB',
                borderRadius: '999px',
                padding: '0.25rem 0.625rem',
              }}>
                {t.ticker && (
                  <span style={{
                    fontFamily: 'IBM Plex Mono, monospace',
                    fontSize: '0.6875rem',
                    fontWeight: 600,
                    color: '#10B981',
                    background: '#ECFDF5',
                    borderRadius: '4px',
                    padding: '0 0.25rem',
                  }}>{t.ticker}</span>
                )}
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#374151' }}>{t.label}</span>
              </div>
            ))}
          </div>
        ) : <EmptyPlaceholder label="Companies will appear after analysis" />}
      </SectionCard>

      {/* Key Assumptions */}
      <SectionCard title="Key Assumptions" accent="#10B981">
        {assumptions.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {assumptions.map((a, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                <span style={{ color: '#10B981', fontSize: '0.75rem', marginTop: '2px', flexShrink: 0 }}>✓</span>
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#374151', lineHeight: 1.5 }}>{a}</span>
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Assumptions will populate after analysis" />}
      </SectionCard>

      {/* Violated / Revised Assumptions */}
      <SectionCard title="Violated or Revised Assumptions" accent="#F59E0B">
        {violated.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {violated.map((v, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                <span style={{ color: '#F59E0B', fontSize: '0.75rem', marginTop: '2px', flexShrink: 0 }}>⚠</span>
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#92400E', lineHeight: 1.5 }}>{v}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.75rem', color: '#10B981' }}>✓</span>
            <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#6B7280' }}>No violations detected</span>
          </div>
        )}
      </SectionCard>

      {/* Accumulated Conclusions */}
      <SectionCard title="Accumulated Conclusions" accent="#6366F1">
        {conclusions.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {conclusions.map((c, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                <span style={{ color: '#6366F1', fontSize: '0.625rem', marginTop: '4px', flexShrink: 0 }}>●</span>
                <div style={{ minWidth: 0 }}>
                  {c.date && (
                    <span style={{
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontSize: '0.625rem',
                      color: '#9CA3AF',
                      display: 'block',
                      marginBottom: '1px',
                    }}>{c.date}</span>
                  )}
                  <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#374151', lineHeight: 1.5 }}>{c.content}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Conclusions accumulate after each session" />}
      </SectionCard>

      {/* Open Questions */}
      <SectionCard title="Open Questions">
        {questions.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {questions.map((q, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                <span style={{
                  width: '16px',
                  height: '16px',
                  borderRadius: '50%',
                  background: '#F3F4F6',
                  border: '1px solid #E5E7EB',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.5625rem',
                  color: '#9CA3AF',
                  fontWeight: 700,
                  marginTop: '1px',
                }}>?</span>
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#374151', lineHeight: 1.5 }}>{q}</span>
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Questions will surface during analysis" />}
      </SectionCard>

      {/* Uploaded Document Summaries */}
      <SectionCard title="Uploaded Document Summaries">
        {docSummaries ? (
          <div style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#374151', lineHeight: 1.6 }}>
            {docSummaries}
          </div>
        ) : <EmptyPlaceholder label="Upload docs in the Documents tab" />}
      </SectionCard>

      {/* Live Data Snapshots */}
      <SectionCard title="Live Data Snapshots">
        {snapshots.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {snapshots.map((s, i) => (
              <li key={i} style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '0.75rem',
                color: '#374151',
                background: '#F9FAFB',
                borderRadius: '4px',
                padding: '0.25rem 0.5rem',
              }}>{s}</li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Data snapshots appear after analysis runs" />}
      </SectionCard>
    </div>
  );
}


function ProjectWorkspace() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent>(AUTO_AGENT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Session restore
  const [restoredSessionId, setRestoredSessionId] = useState<string | undefined>(undefined);
  const [restoredMessages, setRestoredMessages] = useState<Message[] | undefined>(undefined);
  const [chatKey, setChatKey] = useState(0);

  // Project sessions list
  const [projectSessions, setProjectSessions] = useState<SessionSummary[]>([]);

  // Right panel
  const [activeTab, setActiveTab] = useState<PanelTab>('memory');

  // Memory tab state
  const [memoryDoc, setMemoryDoc] = useState<string>('');
  const [memoryUpdatedAt, setMemoryUpdatedAt] = useState<string>('');
  const [thesisHealth, setThesisHealth] = useState<ThesisHealth>({ status: 'Not assessed', rationale: '' });
  const [editingMemory, setEditingMemory] = useState(false);
  const [editedMemoryDoc, setEditedMemoryDoc] = useState('');
  const [savingMemory, setSavingMemory] = useState(false);
  const memoryIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Documents tab state
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Toast
  const [showToast, setShowToast] = useState(false);
  const [toastMessage, setToastMessage] = useState('Analysis saved to library');

  useEffect(() => {
    if (!projectId) return;
    loadData(projectId);
  }, [projectId]);

  // Update URL when a new session is saved
  useEffect(() => {
    const handler = (e: Event) => {
      const sid = (e as CustomEvent).detail?.sessionId;
      if (sid && !searchParams.get('session')) {
        setSearchParams({ session: sid }, { replace: true });
      }
    };
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, [searchParams, setSearchParams]);

  // Session restore from URL
  useEffect(() => {
    const sessionId = searchParams.get('session');
    if (sessionId) {
      restoreSession(sessionId);
    }
  }, [searchParams]);

  // Reload project sessions after a session is saved
  useEffect(() => {
    const handler = () => {
      if (projectId) loadProjectSessions(projectId);
    };
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, [projectId]);

  // Update thesis health badge whenever memory doc changes
  useEffect(() => {
    setThesisHealth(parseThesisHealth(memoryDoc));
  }, [memoryDoc]);

  // Memory auto-refresh every 10s
  useEffect(() => {
    if (!projectId) return;
    memoryIntervalRef.current = setInterval(() => {
      if (!editingMemory) {
        loadMemory(projectId);
      }
    }, 10000);
    return () => {
      if (memoryIntervalRef.current) clearInterval(memoryIntervalRef.current);
    };
  }, [projectId, editingMemory]);

  const loadData = async (id: string) => {
    try {
      const [proj, fetchedAgents] = await Promise.all([
        getProject(id),
        getAgents(),
      ]);
      setProject(proj);
      setMemoryDoc(proj.memory_doc || '');
      setMemoryUpdatedAt(proj.updated_at);
      const chatAgents = [AUTO_AGENT, ...fetchedAgents.filter(a => a.id !== 'portfolio' && a.id !== 'dcf')];
      setAgents(chatAgents);
      await Promise.all([
        loadProjectSessions(id),
        loadDocuments(id),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project');
    } finally {
      setLoading(false);
    }
  };

  const loadProjectSessions = async (id: string) => {
    try {
      const sessions = await getProjectSessions(id);
      setProjectSessions(sessions);
    } catch {
      // non-fatal
    }
  };

  const loadMemory = async (id: string) => {
    try {
      const doc = await getProjectMemory(id);
      setMemoryDoc(doc);
      setMemoryUpdatedAt(new Date().toISOString());
    } catch {
      // non-fatal
    }
  };

  const loadDocuments = async (id: string) => {
    setDocsLoading(true);
    try {
      const docs = await getProjectDocuments(id);
      setDocuments(docs);
    } catch {
      // non-fatal
    } finally {
      setDocsLoading(false);
    }
  };

  const restoreSession = async (sessionId: string) => {
    try {
      const session = await getSession(sessionId);
      setRestoredSessionId(sessionId);
      const msgs: Message[] = session.messages.map(m => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: new Date(m.created_at),
        agentType: m.agent_type ?? undefined,
        ticker: m.ticker ?? undefined,
        followUps: m.follow_ups,
        thinkingSteps: [],
      }));
      setRestoredMessages(msgs);
      setChatKey(k => k + 1);
    } catch {
      setSearchParams({});
    }
  };

  const handleNewSession = useCallback(() => {
    setRestoredSessionId(undefined);
    setRestoredMessages(undefined);
    setSearchParams({});
    setChatKey(k => k + 1);
  }, [setSearchParams]);

  const handleAnalysisSaved = useCallback(() => {
    setToastMessage('Analysis saved to library');
    setShowToast(true);
  }, []);

  const handleSaveMemory = async () => {
    if (!projectId) return;
    setSavingMemory(true);
    try {
      await patchProjectMemory(projectId, editedMemoryDoc);
      setMemoryDoc(editedMemoryDoc);
      setMemoryUpdatedAt(new Date().toISOString());
      setEditingMemory(false);
    } catch {
      // non-fatal, stay in edit mode
    } finally {
      setSavingMemory(false);
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!projectId) return;
    try {
      await deleteProjectDocument(projectId, docId);
      setDocuments(docs => docs.filter(d => d.id !== docId));
    } catch {
      // non-fatal
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || !projectId) return;
    const file = files[0];
    if (!file) return;

    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setDocError(`Unsupported file type. Accepted: ${ACCEPTED_EXTENSIONS.join(', ')}`);
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setDocError('File exceeds 10MB limit.');
      return;
    }

    setDocError(null);
    setUploadingDoc(true);
    try {
      const doc = await uploadProjectDocument(projectId, file);
      setDocuments(docs => [doc, ...docs]);
      setToastMessage('Document uploaded and embedded');
      setShowToast(true);
      // Refresh memory after upload (summary gets added)
      loadMemory(projectId);
    } catch (err) {
      setDocError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploadingDoc(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen pl-20">
        <div className="text-center">
          <div className="flex justify-center gap-2 mb-4">
            <span className="loading-dot" />
            <span className="loading-dot" />
            <span className="loading-dot" />
          </div>
          <p style={{ fontFamily: 'Inter, sans-serif', color: '#9CA3AF', fontSize: '0.875rem' }}>
            Loading project...
          </p>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex items-center justify-center h-screen pl-20">
        <div className="text-center max-w-md px-6">
          <p style={{ fontFamily: 'Inter, sans-serif', color: '#6B7280' }}>
            {error || 'Project not found'}
          </p>
          <button
            onClick={() => navigate('/projects')}
            style={{
              marginTop: '1rem',
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.875rem',
              color: '#1A1A1A',
              background: 'none',
              border: '1px solid #E5E7EB',
              borderRadius: '0.5rem',
              padding: '0.5rem 1rem',
              cursor: 'pointer',
            }}
          >
            Back to Projects
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="pl-20 min-h-screen flex flex-col" style={{ background: '#FFFFFF' }}>
      {/* Project header */}
      <div
        style={{
          borderBottom: '1px solid #F3F4F6',
          padding: '1rem 1.5rem',
          background: '#FAFAFA',
          flexShrink: 0,
        }}
      >
        <div className="flex items-start justify-between max-w-[1400px] mx-auto">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <button
                onClick={() => navigate('/projects')}
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.8125rem',
                  color: '#9CA3AF',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                Projects
              </button>
              <span style={{ color: '#D1D5DB', fontSize: '0.8125rem' }}>/</span>
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#6B7280' }}>
                {project.title}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', flexWrap: 'wrap' }}>
              <h1 style={{ fontFamily: 'Inter, sans-serif', fontSize: '1.125rem', fontWeight: 600, color: '#1A1A1A', margin: 0 }}>
                {project.title}
              </h1>
              {/* Thesis health badge */}
              <div
                title={thesisHealth.rationale || thesisHealth.status}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '0.1875rem 0.625rem',
                  borderRadius: '999px',
                  fontSize: '0.6875rem',
                  fontFamily: 'Inter, sans-serif',
                  fontWeight: 600,
                  letterSpacing: '0.03em',
                  background: THESIS_STATUS_STYLES[thesisHealth.status].bg,
                  color: THESIS_STATUS_STYLES[thesisHealth.status].color,
                  border: `1px solid ${THESIS_STATUS_STYLES[thesisHealth.status].border}`,
                  cursor: thesisHealth.rationale ? 'help' : 'default',
                  userSelect: 'none',
                  whiteSpace: 'nowrap',
                }}
              >
                {thesisHealth.status}
              </div>
            </div>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.875rem', color: '#6B7280', marginTop: '0.25rem', maxWidth: '600px' }}>
              {project.thesis.length > 160 ? project.thesis.slice(0, 160) + '…' : project.thesis}
            </p>
          </div>
          <button
            onClick={handleNewSession}
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.8125rem',
              fontWeight: 500,
              color: '#FFFFFF',
              background: '#1A1A1A',
              border: 'none',
              borderRadius: '0.5rem',
              padding: '0.5rem 1rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            New session
          </button>
        </div>

        {/* Past sessions row */}
        {projectSessions.length > 0 && (
          <div className="max-w-[1400px] mx-auto" style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {projectSessions.slice(0, 8).map(s => (
              <button
                key={s.id}
                onClick={() => setSearchParams({ session: s.id })}
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.75rem',
                  color: '#6B7280',
                  background: searchParams.get('session') === s.id ? '#F3F4F6' : '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: '1rem',
                  padding: '0.25rem 0.75rem',
                  cursor: 'pointer',
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {s.title || new Date(s.created_at).toLocaleDateString()}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main content: chat (2/3) + right panel (1/3) */}
      <div className="flex flex-1 max-w-[1400px] mx-auto w-full" style={{ minHeight: 0 }}>
        {/* Chat panel */}
        <div className="flex-1 flex justify-center items-start" style={{ minWidth: 0 }}>
          <div className="w-full max-w-[720px] px-6 mx-auto">
            <Chat
              key={chatKey}
              agent={selectedAgent}
              agents={agents}
              onSelectAgent={setSelectedAgent}
              sessionId={restoredSessionId}
              initialMessages={restoredMessages}
              onAnalysisSaved={handleAnalysisSaved}
              projectId={projectId}
            />
          </div>
        </div>

        {/* Right panel */}
        <div
          style={{
            width: '360px',
            flexShrink: 0,
            borderLeft: '1px solid #F3F4F6',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 'calc(100vh - 120px)',
          }}
        >
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #F3F4F6', flexShrink: 0 }}>
            {(['memory', 'documents', 'sessions'] as PanelTab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  flex: 1,
                  padding: '0.625rem 0.5rem',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.8125rem',
                  fontWeight: activeTab === tab ? 600 : 400,
                  color: activeTab === tab ? '#1A1A1A' : '#9CA3AF',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === tab ? '2px solid #1A1A1A' : '2px solid transparent',
                  cursor: 'pointer',
                  textTransform: 'capitalize',
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>

            {/* ── Memory Tab ── */}
            {activeTab === 'memory' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                  <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#9CA3AF' }}>
                    {memoryUpdatedAt ? `Updated ${formatDate(memoryUpdatedAt)}` : 'Not yet updated'}
                  </span>
                  {editingMemory ? (
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        onClick={() => setEditingMemory(false)}
                        style={{
                          fontFamily: 'Inter, sans-serif',
                          fontSize: '0.75rem',
                          color: '#6B7280',
                          background: 'none',
                          border: '1px solid #E5E7EB',
                          borderRadius: '0.375rem',
                          padding: '0.25rem 0.625rem',
                          cursor: 'pointer',
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSaveMemory}
                        disabled={savingMemory}
                        style={{
                          fontFamily: 'Inter, sans-serif',
                          fontSize: '0.75rem',
                          color: '#FFFFFF',
                          background: savingMemory ? '#9CA3AF' : '#1A1A1A',
                          border: 'none',
                          borderRadius: '0.375rem',
                          padding: '0.25rem 0.625rem',
                          cursor: savingMemory ? 'default' : 'pointer',
                        }}
                      >
                        {savingMemory ? 'Saving…' : 'Save'}
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setEditedMemoryDoc(memoryDoc);
                        setEditingMemory(true);
                      }}
                      style={{
                        fontFamily: 'Inter, sans-serif',
                        fontSize: '0.75rem',
                        color: '#6B7280',
                        background: 'none',
                        border: '1px solid #E5E7EB',
                        borderRadius: '0.375rem',
                        padding: '0.25rem 0.625rem',
                        cursor: 'pointer',
                      }}
                    >
                      Edit
                    </button>
                  )}
                </div>

                {editingMemory ? (
                  <textarea
                    value={editedMemoryDoc}
                    onChange={e => setEditedMemoryDoc(e.target.value)}
                    style={{
                      width: '100%',
                      minHeight: '60vh',
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontSize: '0.75rem',
                      color: '#1A1A1A',
                      border: '1px solid #E5E7EB',
                      borderRadius: '0.5rem',
                      padding: '0.75rem',
                      resize: 'vertical',
                      lineHeight: 1.6,
                      background: '#FAFAFA',
                    }}
                  />
                ) : memoryDoc ? (
                  <MemoryDashboard memoryDoc={memoryDoc} thesisHealth={thesisHealth} />
                ) : (
                  <div style={{ textAlign: 'center', marginTop: '3rem' }}>
                    <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>🧠</div>
                    <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#9CA3AF', margin: 0 }}>
                      Memory builds automatically after your first analysis session.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* ── Documents Tab ── */}
            {activeTab === 'documents' && (
              <div>
                {/* Upload area */}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => {
                    e.preventDefault();
                    handleFileSelect(e.dataTransfer.files);
                  }}
                  style={{
                    border: '1.5px dashed #D1D5DB',
                    borderRadius: '0.625rem',
                    padding: '1.25rem',
                    textAlign: 'center',
                    cursor: uploadingDoc ? 'default' : 'pointer',
                    background: uploadingDoc ? '#F9FAFB' : '#FFFFFF',
                    marginBottom: '1rem',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ACCEPTED_EXTENSIONS.join(',')}
                    style={{ display: 'none' }}
                    onChange={e => handleFileSelect(e.target.files)}
                  />
                  {uploadingDoc ? (
                    <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#9CA3AF' }}>
                      Uploading…
                    </p>
                  ) : (
                    <>
                      <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#6B7280', margin: 0 }}>
                        Drop a file or click to upload
                      </p>
                      <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#9CA3AF', marginTop: '0.25rem', marginBottom: 0 }}>
                        PDF, DOCX, XLSX, PPTX, CSV · max 10 MB
                      </p>
                    </>
                  )}
                </div>

                {docError && (
                  <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#EF4444', marginBottom: '0.75rem' }}>
                    {docError}
                  </p>
                )}

                {docsLoading ? (
                  <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#9CA3AF', textAlign: 'center' }}>Loading…</p>
                ) : documents.length === 0 ? (
                  <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#9CA3AF', textAlign: 'center', marginTop: '1rem' }}>
                    No documents yet. Upload 10-Ks, research reports, or news articles.
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {documents.map(doc => (
                      <div
                        key={doc.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.625rem 0.75rem',
                          border: '1px solid #F3F4F6',
                          borderRadius: '0.5rem',
                          background: '#FAFAFA',
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <p style={{
                            fontFamily: 'Inter, sans-serif',
                            fontSize: '0.8125rem',
                            color: '#1A1A1A',
                            fontWeight: 500,
                            margin: 0,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: '200px',
                          }}>
                            {doc.filename}
                          </p>
                          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.6875rem', color: '#9CA3AF', margin: 0, marginTop: '0.125rem' }}>
                            {doc.chunk_count} chunks · {formatDate(doc.uploaded_at)}
                          </p>
                        </div>
                        <button
                          onClick={() => handleDeleteDocument(doc.id)}
                          style={{
                            fontFamily: 'Inter, sans-serif',
                            fontSize: '0.75rem',
                            color: '#EF4444',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            padding: '0.25rem 0.5rem',
                            flexShrink: 0,
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Sessions Tab ── */}
            {activeTab === 'sessions' && (
              <div>
                {projectSessions.length === 0 ? (
                  <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8125rem', color: '#9CA3AF', textAlign: 'center', marginTop: '1rem' }}>
                    No sessions yet. Start a chat to create your first session.
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {projectSessions.map(s => (
                      <button
                        key={s.id}
                        onClick={() => navigate(`/?session=${s.id}`)}
                        style={{
                          display: 'block',
                          width: '100%',
                          textAlign: 'left',
                          padding: '0.625rem 0.75rem',
                          border: '1px solid #F3F4F6',
                          borderRadius: '0.5rem',
                          background: '#FAFAFA',
                          cursor: 'pointer',
                        }}
                      >
                        <p style={{
                          fontFamily: 'Inter, sans-serif',
                          fontSize: '0.8125rem',
                          color: '#1A1A1A',
                          fontWeight: 500,
                          margin: 0,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {s.title || 'Untitled session'}
                        </p>
                        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.6875rem', color: '#9CA3AF', margin: 0, marginTop: '0.125rem' }}>
                          {formatDate(s.created_at)}
                        </p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>
        </div>
      </div>

      <ToastNotification
        message={toastMessage}
        visible={showToast}
        onDismiss={() => setShowToast(false)}
      />
    </div>
  );
}

export default ProjectWorkspace;
