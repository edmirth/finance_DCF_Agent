import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  BrainCircuit,
  Clock3,
  FileStack,
  MessagesSquare,
  Orbit,
  Sparkles,
  Target,
  UploadCloud,
} from 'lucide-react';
import Chat from '../components/Chat';
import ToastNotification from '../components/ToastNotification';
import { Agent, Message, ProjectDetail, ProjectDocument, SessionSummary } from '../types';
import {
  getProject,
  getProjectSessions,
  getSession,
  getProjectMemory,
  patchProjectMemory,
  getProjectDocuments,
  deleteProjectDocument,
  uploadProjectDocument,
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
  STRONG: { bg: '#DFF4E7', color: '#17603A', border: '#9FD2B4' },
  WEAKENING: { bg: '#F8EFCB', color: '#8B660A', border: '#E8D06B' },
  CHALLENGED: { bg: '#F9E3CF', color: '#9E4A17', border: '#F1BC8C' },
  INVALIDATED: { bg: '#F6DCDC', color: '#962C2C', border: '#E8AFAF' },
  'Not assessed': { bg: '#EFEEE8', color: '#6E6A61', border: '#D7D2C7' },
};

const PANEL_META: Record<PanelTab, { label: string; description: string; icon: React.ComponentType<any> }> = {
  memory: {
    label: 'Memory',
    description: 'Track thesis health and accumulated learnings.',
    icon: BrainCircuit,
  },
  documents: {
    label: 'Documents',
    description: 'Upload filings, research, and supporting material.',
    icon: FileStack,
  },
  sessions: {
    label: 'Sessions',
    description: 'Jump between linked project conversations.',
    icon: MessagesSquare,
  },
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

function formatRelativeTime(iso: string): string {
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) return 'Updated recently';

  const diffMs = Date.now() - timestamp;
  const diffMinutes = Math.round(diffMs / (1000 * 60));

  if (diffMinutes < 1) return 'Updated just now';
  if (diffMinutes < 60) return `Updated ${diffMinutes}m ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `Updated ${diffHours}h ago`;

  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `Updated ${diffDays}d ago`;

  return `Updated ${formatDate(iso)}`;
}

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

const SECTION_ICON: Record<string, string> = {
  Thesis: 'T',
  'Key Assumptions': 'A',
  'Violated or Revised Assumptions': 'R',
  'Thesis Health': 'H',
  'Key Companies & Tickers': 'C',
  'Accumulated Conclusions': 'C',
  'Open Questions': 'Q',
  'Uploaded Document Summaries': 'D',
  'Live Data Snapshots': 'S',
};

function SectionCard({ title, children, accent }: { title: string; children: React.ReactNode; accent?: string }) {
  return (
    <div
      style={{
        border: '1px solid rgba(30, 24, 16, 0.08)',
        borderRadius: '16px',
        padding: '1rem',
        marginBottom: '0.75rem',
        background: '#FFFEFB',
        boxShadow: '0 8px 24px rgba(32, 24, 14, 0.04)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          marginBottom: '0.75rem',
        }}
      >
        <div
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '999px',
            background: accent || '#EFE9DE',
            color: accent ? '#FFFFFF' : '#6B675D',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.6875rem',
            fontWeight: 700,
            fontFamily: 'IBM Plex Mono, monospace',
          }}
        >
          {SECTION_ICON[title]}
        </div>
        <div>
          <div
            style={{
              fontFamily: 'IBM Plex Sans, sans-serif',
              fontSize: '0.75rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: '#8A8376',
              fontWeight: 600,
            }}
          >
            {title}
          </div>
        </div>
      </div>
      {children}
    </div>
  );
}

function EmptyPlaceholder({ label }: { label: string }) {
  return (
    <div
      style={{
        border: '1px dashed #DDD4C6',
        borderRadius: '12px',
        padding: '0.875rem 1rem',
        textAlign: 'center',
        background: '#FBF7EF',
      }}
    >
      <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', color: '#A19788' }}>{label}</span>
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
      <SectionCard title="Thesis" accent="#1B5D4B">
        {thesis ? (
          <div
            style={{
              fontFamily: 'IBM Plex Sans, sans-serif',
              fontSize: '0.9375rem',
              color: '#221E17',
              lineHeight: 1.7,
              fontStyle: 'italic',
              padding: '0.25rem 0.25rem 0.25rem 0.85rem',
              borderLeft: '3px solid #B9D7CC',
            }}
          >
            {thesis}
          </div>
        ) : <EmptyPlaceholder label="No thesis defined yet" />}
      </SectionCard>

      <SectionCard title="Thesis Health" accent="#242018">
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.75rem',
            background: healthStyle.bg,
            border: `1px solid ${healthStyle.border}`,
            borderRadius: '12px',
            padding: '0.875rem',
          }}
        >
          <div
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: healthStyle.color,
              flexShrink: 0,
              marginTop: '5px',
            }}
          />
          <div>
            <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', fontWeight: 700, color: healthStyle.color }}>
              {thesisHealth.status}
            </div>
            {thesisHealth.rationale && (
              <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', color: healthStyle.color, marginTop: '0.25rem', lineHeight: 1.5 }}>
                {thesisHealth.rationale}
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Key Companies & Tickers" accent="#3E6C80">
        {tickers.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {tickers.map((t, i) => (
              <div
                key={i}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.375rem',
                  background: '#F4F7F8',
                  border: '1px solid #D7E2E8',
                  borderRadius: '999px',
                  padding: '0.3125rem 0.75rem',
                }}
              >
                {t.ticker && (
                  <span
                    style={{
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontSize: '0.6875rem',
                      fontWeight: 600,
                      color: '#25566A',
                      background: '#DCEAF0',
                      borderRadius: '999px',
                      padding: '0.125rem 0.4rem',
                    }}
                  >
                    {t.ticker}
                  </span>
                )}
                <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', color: '#3C3A34' }}>{t.label}</span>
              </div>
            ))}
          </div>
        ) : <EmptyPlaceholder label="Companies will appear after analysis" />}
      </SectionCard>

      <SectionCard title="Key Assumptions" accent="#1B5D4B">
        {assumptions.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {assumptions.map((a, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.625rem', alignItems: 'flex-start' }}>
                <span style={{ color: '#1B5D4B', fontSize: '0.875rem', marginTop: '1px', flexShrink: 0 }}>+</span>
                <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#403C34', lineHeight: 1.55 }}>{a}</span>
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Assumptions will populate after analysis" />}
      </SectionCard>

      <SectionCard title="Violated or Revised Assumptions" accent="#B85D2B">
        {violated.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {violated.map((v, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.625rem', alignItems: 'flex-start' }}>
                <span style={{ color: '#B85D2B', fontSize: '0.875rem', marginTop: '1px', flexShrink: 0 }}>!</span>
                <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#7E4723', lineHeight: 1.55 }}>{v}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.875rem', color: '#1B5D4B' }}>+</span>
            <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', color: '#6E6A61' }}>No violations detected</span>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Accumulated Conclusions" accent="#5C4AB2">
        {conclusions.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
            {conclusions.map((c, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.625rem', alignItems: 'flex-start' }}>
                <span style={{ color: '#5C4AB2', fontSize: '0.75rem', marginTop: '4px', flexShrink: 0 }}>o</span>
                <div style={{ minWidth: 0 }}>
                  {c.date && (
                    <span
                      style={{
                        fontFamily: 'IBM Plex Mono, monospace',
                        fontSize: '0.6875rem',
                        color: '#9F9688',
                        display: 'block',
                        marginBottom: '2px',
                      }}
                    >
                      {c.date}
                    </span>
                  )}
                  <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#403C34', lineHeight: 1.55 }}>{c.content}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Conclusions accumulate after each session" />}
      </SectionCard>

      <SectionCard title="Open Questions" accent="#2D4E76">
        {questions.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {questions.map((q, i) => (
              <li key={i} style={{ display: 'flex', gap: '0.625rem', alignItems: 'flex-start' }}>
                <span
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    background: '#E8EFF6',
                    border: '1px solid #C6D7E7',
                    flexShrink: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.625rem',
                    color: '#2D4E76',
                    fontWeight: 700,
                    marginTop: '1px',
                  }}
                >
                  ?
                </span>
                <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#403C34', lineHeight: 1.55 }}>{q}</span>
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Questions will surface during analysis" />}
      </SectionCard>

      <SectionCard title="Uploaded Document Summaries" accent="#6A5A3A">
        {docSummaries ? (
          <div
            style={{
              fontFamily: 'IBM Plex Sans, sans-serif',
              fontSize: '0.875rem',
              color: '#403C34',
              lineHeight: 1.65,
              whiteSpace: 'pre-wrap',
            }}
          >
            {docSummaries}
          </div>
        ) : <EmptyPlaceholder label="Upload docs in the Documents tab" />}
      </SectionCard>

      <SectionCard title="Live Data Snapshots" accent="#3E6C80">
        {snapshots.length > 0 ? (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {snapshots.map((s, i) => (
              <li
                key={i}
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '0.75rem',
                  color: '#324452',
                  background: '#F4F7F8',
                  border: '1px solid #D7E2E8',
                  borderRadius: '10px',
                  padding: '0.5rem 0.625rem',
                }}
              >
                {s}
              </li>
            ))}
          </ul>
        ) : <EmptyPlaceholder label="Data snapshots appear after analysis runs" />}
      </SectionCard>
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ComponentType<any>;
}) {
  return (
    <div
      style={{
        background: 'rgba(255, 252, 244, 0.82)',
        border: '1px solid rgba(43, 35, 23, 0.08)',
        borderRadius: '18px',
        padding: '0.95rem 1rem',
        minHeight: '116px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
        <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.75rem', color: '#8C8376', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {label}
        </span>
        <Icon size={16} color="#575247" />
      </div>
      <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '1.4rem', fontWeight: 700, color: '#1E1A13', letterSpacing: '-0.03em' }}>
        {value}
      </div>
      <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', color: '#70695E', marginTop: '0.25rem', lineHeight: 1.45 }}>
        {hint}
      </div>
    </div>
  );
}

function ProjectWorkspace() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<Agent>(AUTO_AGENT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [restoredSessionId, setRestoredSessionId] = useState<string | undefined>(undefined);
  const [restoredMessages, setRestoredMessages] = useState<Message[] | undefined>(undefined);
  const [chatKey, setChatKey] = useState(0);

  const [projectSessions, setProjectSessions] = useState<SessionSummary[]>([]);
  const [activeTab, setActiveTab] = useState<PanelTab>('memory');

  const [memoryDoc, setMemoryDoc] = useState<string>('');
  const [memoryUpdatedAt, setMemoryUpdatedAt] = useState<string>('');
  const [thesisHealth, setThesisHealth] = useState<ThesisHealth>({ status: 'Not assessed', rationale: '' });
  const [editingMemory, setEditingMemory] = useState(false);
  const [editedMemoryDoc, setEditedMemoryDoc] = useState('');
  const [savingMemory, setSavingMemory] = useState(false);
  const memoryIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [showToast, setShowToast] = useState(false);
  const [toastMessage, setToastMessage] = useState('Workspace updated');

  useEffect(() => {
    if (!projectId) return;
    loadData(projectId);
  }, [projectId]);

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

  useEffect(() => {
    const sessionId = searchParams.get('session');
    if (sessionId) {
      restoreSession(sessionId);
    }
  }, [searchParams]);

  useEffect(() => {
    const handler = () => {
      if (projectId) loadProjectSessions(projectId);
    };
    window.addEventListener('sessionSaved', handler);
    return () => window.removeEventListener('sessionSaved', handler);
  }, [projectId]);

  useEffect(() => {
    setThesisHealth(parseThesisHealth(memoryDoc));
  }, [memoryDoc]);

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
      const proj = await getProject(id);
      setProject(proj);
      setSelectedAgent(AUTO_AGENT);
      setMemoryDoc(proj.memory_doc || '');
      setMemoryUpdatedAt(proj.updated_at);
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
      const response = await getProjectMemory(id);
      setMemoryDoc(response.memory_doc);
      setMemoryUpdatedAt(response.updated_at);
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

  const handleSaveMemory = async () => {
    if (!projectId) return;
    setSavingMemory(true);
    try {
      const updated = await patchProjectMemory(projectId, editedMemoryDoc);
      setMemoryDoc(updated.memory_doc);
      setMemoryUpdatedAt(updated.updated_at);
      setEditingMemory(false);
      setToastMessage('Project memory updated');
      setShowToast(true);
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
      setToastMessage('Document removed from workspace');
      setShowToast(true);
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
          <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', color: '#8E8679', fontSize: '0.95rem' }}>
            Loading project workspace...
          </p>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex items-center justify-center h-screen pl-20">
        <div
          className="text-center max-w-md px-6 py-8"
          style={{
            background: '#FFFCF4',
            border: '1px solid rgba(36, 30, 21, 0.08)',
            borderRadius: '24px',
            boxShadow: '0 18px 50px rgba(20, 16, 10, 0.06)',
          }}
        >
          <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', color: '#635E55', margin: 0 }}>
            {error || 'Project not found'}
          </p>
          <button
            onClick={() => navigate('/projects')}
            style={{
              marginTop: '1rem',
              fontFamily: 'IBM Plex Sans, sans-serif',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: '#201B14',
              background: '#F3EBDD',
              border: '1px solid #E2D8C8',
              borderRadius: '999px',
              padding: '0.625rem 1rem',
              cursor: 'pointer',
            }}
          >
            Back to Projects
          </button>
        </div>
      </div>
    );
  }

  const projectTickers = project.config?.tickers || [];
  const activeSessionId = searchParams.get('session');

  return (
    <div
      className="pl-20 min-h-screen"
      style={{
        background: 'linear-gradient(180deg, #F5EFE4 0%, #FBF8F1 28%, #FFFFFF 62%)',
      }}
    >
      <div className="mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 py-6">
        <section
          style={{
            background: 'linear-gradient(135deg, rgba(255, 252, 245, 0.96) 0%, rgba(248, 241, 229, 0.94) 100%)',
            border: '1px solid rgba(31, 24, 16, 0.08)',
            borderRadius: '30px',
            padding: '1.5rem',
            boxShadow: '0 26px 80px rgba(32, 23, 12, 0.08)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute',
              inset: '-35% auto auto 68%',
              width: '320px',
              height: '320px',
              borderRadius: '999px',
              background: 'radial-gradient(circle, rgba(166, 136, 83, 0.18) 0%, rgba(166, 136, 83, 0) 70%)',
              pointerEvents: 'none',
            }}
          />

          <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-4xl">
              <button
                onClick={() => navigate('/projects')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  background: 'rgba(255,255,255,0.7)',
                  border: '1px solid rgba(35, 28, 20, 0.08)',
                  borderRadius: '999px',
                  padding: '0.45rem 0.85rem',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  fontSize: '0.8125rem',
                  color: '#665E51',
                  cursor: 'pointer',
                }}
              >
                <ArrowLeft size={14} />
                All projects
              </button>

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                    background: '#1F1A14',
                    color: '#FFF9F0',
                    borderRadius: '999px',
                    padding: '0.375rem 0.8rem',
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}
                >
                  <Orbit size={14} />
                  Auto-orchestrated workspace
                </div>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    background: THESIS_STATUS_STYLES[thesisHealth.status].bg,
                    color: THESIS_STATUS_STYLES[thesisHealth.status].color,
                    border: `1px solid ${THESIS_STATUS_STYLES[thesisHealth.status].border}`,
                    borderRadius: '999px',
                    padding: '0.35rem 0.75rem',
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}
                >
                  <Target size={13} />
                  {thesisHealth.status}
                </div>
              </div>

              <h1
                style={{
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  fontSize: 'clamp(1.9rem, 3vw, 2.8rem)',
                  lineHeight: 1,
                  letterSpacing: '-0.05em',
                  color: '#1F1A14',
                  margin: '1rem 0 0.75rem',
                }}
              >
                {project.title}
              </h1>

              <p
                style={{
                  fontFamily: 'IBM Plex Sans, sans-serif',
                  fontSize: '1rem',
                  color: '#675F54',
                  lineHeight: 1.7,
                  margin: 0,
                  maxWidth: '860px',
                }}
              >
                {project.thesis}
              </p>

              <div className="mt-5 flex flex-wrap gap-2">
                {projectTickers.length > 0 ? projectTickers.map(ticker => (
                  <span
                    key={ticker}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      background: '#F2ECE2',
                      border: '1px solid #DED4C4',
                      borderRadius: '999px',
                      padding: '0.4rem 0.8rem',
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontSize: '0.75rem',
                      color: '#3B362E',
                    }}
                  >
                    {ticker}
                  </span>
                )) : (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      background: '#F8F3E9',
                      border: '1px dashed #DDD0BA',
                      borderRadius: '999px',
                      padding: '0.4rem 0.8rem',
                      fontFamily: 'IBM Plex Sans, sans-serif',
                      fontSize: '0.75rem',
                      color: '#8A8376',
                    }}
                  >
                    Add tickers to sharpen routing
                  </span>
                )}
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                    background: 'rgba(255,255,255,0.75)',
                    border: '1px solid rgba(36, 29, 21, 0.08)',
                    borderRadius: '999px',
                    padding: '0.5rem 0.85rem',
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: '0.8125rem',
                    color: '#60594D',
                  }}
                >
                  <Sparkles size={14} />
                  Every question uses thesis, memory, and uploaded materials.
                </div>
                {memoryUpdatedAt && (
                  <div
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.45rem',
                      background: 'rgba(255,255,255,0.75)',
                      border: '1px solid rgba(36, 29, 21, 0.08)',
                      borderRadius: '999px',
                      padding: '0.5rem 0.85rem',
                      fontFamily: 'IBM Plex Sans, sans-serif',
                      fontSize: '0.8125rem',
                      color: '#60594D',
                    }}
                  >
                    <Clock3 size={14} />
                    {formatRelativeTime(memoryUpdatedAt)}
                  </div>
                )}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 xl:w-[460px]">
              <MetricCard
                label="Sessions"
                value={String(projectSessions.length)}
                hint={activeSessionId ? 'Jumping between linked analysis threads.' : 'Start a thread and it stays attached here.'}
                icon={MessagesSquare}
              />
              <MetricCard
                label="Documents"
                value={String(documents.length)}
                hint={documents.length > 0 ? 'Embedded into project context for future questions.' : 'Upload filings, notes, or research to ground answers.'}
                icon={FileStack}
              />
              <MetricCard
                label="Memory"
                value={thesisHealth.status === 'Not assessed' ? 'Cold' : thesisHealth.status}
                hint={thesisHealth.rationale || 'The workspace will accumulate conclusions over time.'}
                icon={BrainCircuit}
              />
            </div>
          </div>
        </section>

        <div className="mt-6 flex flex-col gap-6 xl:flex-row">
          <div className="min-w-0 flex-1">
            <section
              style={{
                background: '#FFFEFA',
                border: '1px solid rgba(31, 24, 16, 0.08)',
                borderRadius: '28px',
                boxShadow: '0 24px 72px rgba(28, 22, 14, 0.06)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  padding: '1rem 1.25rem 1.1rem',
                  borderBottom: '1px solid rgba(31, 24, 16, 0.08)',
                  background: 'linear-gradient(180deg, rgba(250, 245, 236, 0.9) 0%, rgba(255, 254, 250, 0.92) 100%)',
                }}
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div
                      style={{
                        fontFamily: 'IBM Plex Sans, sans-serif',
                        fontSize: '0.75rem',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        color: '#8E8477',
                        fontWeight: 600,
                      }}
                    >
                      Project Copilot
                    </div>
                    <div
                      style={{
                        fontFamily: 'IBM Plex Sans, sans-serif',
                        fontSize: '1.15rem',
                        fontWeight: 700,
                        color: '#1F1A14',
                        marginTop: '0.2rem',
                      }}
                    >
                      Ask, test, and evolve the thesis in one place
                    </div>
                    <div
                      style={{
                        fontFamily: 'IBM Plex Sans, sans-serif',
                        fontSize: '0.875rem',
                        color: '#686155',
                        marginTop: '0.35rem',
                      }}
                    >
                      This workspace routes across the right finance agents automatically, then folds results back into project memory.
                    </div>
                  </div>

                  <button
                    onClick={handleNewSession}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '0.5rem',
                      fontFamily: 'IBM Plex Sans, sans-serif',
                      fontSize: '0.875rem',
                      fontWeight: 600,
                      color: '#FFFAF2',
                      background: '#1F1A14',
                      border: 'none',
                      borderRadius: '999px',
                      padding: '0.7rem 1rem',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <Sparkles size={14} />
                    New session
                  </button>
                </div>

                {projectSessions.length > 0 && (
                  <div className="mt-4">
                    <div
                      style={{
                        fontFamily: 'IBM Plex Sans, sans-serif',
                        fontSize: '0.75rem',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        color: '#9B9182',
                        fontWeight: 600,
                        marginBottom: '0.65rem',
                      }}
                    >
                      Recent sessions
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {projectSessions.slice(0, 6).map(s => (
                        <button
                          key={s.id}
                          onClick={() => setSearchParams({ session: s.id })}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.45rem',
                            maxWidth: '240px',
                            background: activeSessionId === s.id ? '#1F1A14' : '#FFFFFF',
                            color: activeSessionId === s.id ? '#FFF8ED' : '#5E574C',
                            border: activeSessionId === s.id ? '1px solid #1F1A14' : '1px solid #E4DAC9',
                            borderRadius: '999px',
                            padding: '0.5rem 0.8rem',
                            cursor: 'pointer',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontFamily: 'IBM Plex Sans, sans-serif',
                            fontSize: '0.8125rem',
                          }}
                        >
                          <MessagesSquare size={14} />
                          {s.title || new Date(s.created_at).toLocaleDateString()}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="px-2 sm:px-4">
                <Chat
                  key={chatKey}
                  agent={selectedAgent}
                  agents={[AUTO_AGENT]}
                  onSelectAgent={setSelectedAgent}
                  sessionId={restoredSessionId}
                  initialMessages={restoredMessages}
                  projectId={projectId}
                />
              </div>
            </section>
          </div>

          <aside className="w-full xl:w-[390px] xl:flex-shrink-0">
            <section
              style={{
                background: '#FFFEFA',
                border: '1px solid rgba(31, 24, 16, 0.08)',
                borderRadius: '28px',
                boxShadow: '0 24px 72px rgba(28, 22, 14, 0.06)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  padding: '1rem 1rem 0.9rem',
                  borderBottom: '1px solid rgba(31, 24, 16, 0.08)',
                  background: 'linear-gradient(180deg, rgba(250, 245, 236, 0.9) 0%, rgba(255, 254, 250, 0.92) 100%)',
                }}
              >
                <div
                  style={{
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: '0.75rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: '#8E8477',
                    fontWeight: 600,
                  }}
                >
                  Workspace sidecar
                </div>
                <div
                  style={{
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: '1.1rem',
                    fontWeight: 700,
                    color: '#1F1A14',
                    marginTop: '0.2rem',
                  }}
                >
                  Memory, materials, and threads
                </div>
                <p
                  style={{
                    fontFamily: 'IBM Plex Sans, sans-serif',
                    fontSize: '0.875rem',
                    color: '#686155',
                    margin: '0.35rem 0 0',
                    lineHeight: 1.6,
                  }}
                >
                  Keep the thesis state visible while you work so every answer compounds.
                </p>

                <div className="grid grid-cols-3 gap-2 mt-4">
                  {(['memory', 'documents', 'sessions'] as PanelTab[]).map(tab => {
                    const meta = PANEL_META[tab];
                    const Icon = meta.icon;
                    const active = activeTab === tab;
                    return (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'flex-start',
                          gap: '0.45rem',
                          padding: '0.75rem 0.8rem',
                          borderRadius: '16px',
                          textAlign: 'left',
                          border: active ? '1px solid #1F1A14' : '1px solid #E6DCCB',
                          background: active ? '#1F1A14' : '#FFFFFF',
                          color: active ? '#FFF8ED' : '#2C261E',
                          cursor: 'pointer',
                        }}
                      >
                        <Icon size={16} />
                        <div>
                          <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', fontWeight: 600 }}>
                            {meta.label}
                          </div>
                          <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.6875rem', lineHeight: 1.4, opacity: active ? 0.82 : 0.72 }}>
                            {meta.description}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div style={{ padding: '1rem' }}>
                {activeTab === 'memory' && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.9rem' }}>
                      <span style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8125rem', color: '#8E8679' }}>
                        {memoryUpdatedAt ? formatRelativeTime(memoryUpdatedAt) : 'Not yet updated'}
                      </span>
                      {editingMemory ? (
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button
                            onClick={() => setEditingMemory(false)}
                            style={{
                              fontFamily: 'IBM Plex Sans, sans-serif',
                              fontSize: '0.75rem',
                              color: '#615A4E',
                              background: '#F4EEE3',
                              border: '1px solid #E3D8C8',
                              borderRadius: '999px',
                              padding: '0.38rem 0.8rem',
                              cursor: 'pointer',
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            onClick={handleSaveMemory}
                            disabled={savingMemory}
                            style={{
                              fontFamily: 'IBM Plex Sans, sans-serif',
                              fontSize: '0.75rem',
                              color: '#FFF9F0',
                              background: savingMemory ? '#928B80' : '#1F1A14',
                              border: 'none',
                              borderRadius: '999px',
                              padding: '0.38rem 0.8rem',
                              cursor: savingMemory ? 'default' : 'pointer',
                            }}
                          >
                            {savingMemory ? 'Saving...' : 'Save'}
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            setEditedMemoryDoc(memoryDoc);
                            setEditingMemory(true);
                          }}
                          style={{
                            fontFamily: 'IBM Plex Sans, sans-serif',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            color: '#1F1A14',
                            background: '#F4EEE3',
                            border: '1px solid #E3D8C8',
                            borderRadius: '999px',
                            padding: '0.38rem 0.8rem',
                            cursor: 'pointer',
                          }}
                        >
                          Edit memory
                        </button>
                      )}
                    </div>

                    {editingMemory ? (
                      <textarea
                        value={editedMemoryDoc}
                        onChange={e => setEditedMemoryDoc(e.target.value)}
                        style={{
                          width: '100%',
                          minHeight: '65vh',
                          fontFamily: 'IBM Plex Mono, monospace',
                          fontSize: '0.75rem',
                          color: '#1F1A14',
                          border: '1px solid #E3D8C8',
                          borderRadius: '18px',
                          padding: '0.9rem',
                          resize: 'vertical',
                          lineHeight: 1.65,
                          background: '#FBF7EF',
                        }}
                      />
                    ) : memoryDoc ? (
                      <MemoryDashboard memoryDoc={memoryDoc} thesisHealth={thesisHealth} />
                    ) : (
                      <div style={{ textAlign: 'center', marginTop: '3rem' }}>
                        <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>[]</div>
                        <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#958C7E', margin: 0 }}>
                          Memory builds automatically after your first analysis session.
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'documents' && (
                  <div>
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      onDragOver={e => e.preventDefault()}
                      onDrop={e => {
                        e.preventDefault();
                        handleFileSelect(e.dataTransfer.files);
                      }}
                      style={{
                        border: '1.5px dashed #D7CCBA',
                        borderRadius: '18px',
                        padding: '1.35rem',
                        textAlign: 'center',
                        cursor: uploadingDoc ? 'default' : 'pointer',
                        background: uploadingDoc ? '#F7F2E8' : '#FBF7EF',
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
                      <UploadCloud size={24} color="#7F7567" style={{ margin: '0 auto 0.7rem' }} />
                      {uploadingDoc ? (
                        <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#8E8679', margin: 0 }}>
                          Uploading...
                        </p>
                      ) : (
                        <>
                          <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#625B4F', margin: 0 }}>
                            Drop a file or click to upload
                          </p>
                          <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.75rem', color: '#9A9081', marginTop: '0.35rem', marginBottom: 0 }}>
                            PDF, DOCX, XLSX, PPTX, CSV - max 10 MB
                          </p>
                        </>
                      )}
                    </div>

                    {docError && (
                      <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.75rem', color: '#B14545', marginBottom: '0.9rem' }}>
                        {docError}
                      </p>
                    )}

                    {docsLoading ? (
                      <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#8E8679', textAlign: 'center' }}>Loading...</p>
                    ) : documents.length === 0 ? (
                      <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#958C7E', textAlign: 'center', marginTop: '1rem', lineHeight: 1.6 }}>
                        No documents yet. Upload 10-Ks, notes, research reports, or expert transcripts to ground the workspace.
                      </p>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                        {documents.map(doc => (
                          <div
                            key={doc.id}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: '0.75rem',
                              padding: '0.8rem 0.9rem',
                              border: '1px solid #E6DCCB',
                              borderRadius: '16px',
                              background: '#FFFEFA',
                            }}
                          >
                            <div style={{ minWidth: 0 }}>
                              <p
                                style={{
                                  fontFamily: 'IBM Plex Sans, sans-serif',
                                  fontSize: '0.875rem',
                                  color: '#1F1A14',
                                  fontWeight: 600,
                                  margin: 0,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                  maxWidth: '220px',
                                }}
                              >
                                {doc.filename}
                              </p>
                              <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.75rem', color: '#948A7B', margin: '0.25rem 0 0' }}>
                                {doc.chunk_count} chunks - {formatDate(doc.uploaded_at)}
                              </p>
                            </div>
                            <button
                              onClick={() => handleDeleteDocument(doc.id)}
                              style={{
                                fontFamily: 'IBM Plex Sans, sans-serif',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                color: '#B14545',
                                background: '#F8ECEC',
                                border: '1px solid #E9CACA',
                                borderRadius: '999px',
                                cursor: 'pointer',
                                padding: '0.38rem 0.8rem',
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

                {activeTab === 'sessions' && (
                  <div>
                    {projectSessions.length === 0 ? (
                      <p style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.875rem', color: '#958C7E', textAlign: 'center', marginTop: '1rem' }}>
                        No sessions yet. Start a chat to create your first linked thread.
                      </p>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                        {projectSessions.map(s => (
                          <button
                            key={s.id}
                            onClick={() => setSearchParams({ session: s.id })}
                            style={{
                              display: 'block',
                              width: '100%',
                              textAlign: 'left',
                              padding: '0.85rem 0.95rem',
                              border: activeSessionId === s.id ? '1px solid #1F1A14' : '1px solid #E6DCCB',
                              borderRadius: '16px',
                              background: activeSessionId === s.id ? '#1F1A14' : '#FFFEFA',
                              cursor: 'pointer',
                            }}
                          >
                            <p
                              style={{
                                fontFamily: 'IBM Plex Sans, sans-serif',
                                fontSize: '0.875rem',
                                color: activeSessionId === s.id ? '#FFF8ED' : '#1F1A14',
                                fontWeight: 600,
                                margin: 0,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {s.title || 'Untitled session'}
                            </p>
                            <p
                              style={{
                                fontFamily: 'IBM Plex Sans, sans-serif',
                                fontSize: '0.75rem',
                                color: activeSessionId === s.id ? 'rgba(255, 248, 237, 0.72)' : '#948A7B',
                                margin: '0.25rem 0 0',
                              }}
                            >
                              {formatDate(s.created_at)}
                            </p>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          </aside>
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
