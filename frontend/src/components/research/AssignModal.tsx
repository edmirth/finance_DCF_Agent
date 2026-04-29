import React, { useState, useEffect, useRef, useCallback } from 'react';

interface AssignModalProps {
  agentKey: string;
  agentTitle: string;
  onRun: (ticker: string, title: string, description: string) => void;
  onClose: () => void;
}

type Priority = 'low' | 'medium' | 'high';

const PRIORITY_CONFIG: Record<Priority, { label: string; color: string; bg: string; border: string }> = {
  low:    { label: 'Low',    color: '#6B7280', bg: '#F9FAFB',               border: '#E5E7EB' },
  medium: { label: 'Medium', color: '#D97706', bg: 'rgba(245,158,11,0.06)', border: 'rgba(245,158,11,0.3)' },
  high:   { label: 'High',   color: '#DC2626', bg: 'rgba(239,68,68,0.06)',  border: 'rgba(239,68,68,0.3)' },
};

const AssignModal: React.FC<AssignModalProps> = ({ agentTitle, onRun, onClose }) => {
  const [title, setTitle]               = useState('');
  const [ticker, setTicker]             = useState('');
  const [tickerEditing, setTickerEditing] = useState(false);
  const [tickerDraft, setTickerDraft]   = useState('');
  const [description, setDescription]   = useState('');
  const [priority, setPriority]         = useState<Priority | null>(null);
  const [showPriorityMenu, setShowPriorityMenu] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [attachments, setAttachments]   = useState<File[]>([]);

  const titleRef       = useRef<HTMLInputElement>(null);
  const tickerInputRef = useRef<HTMLInputElement>(null);
  const backdropRef    = useRef<HTMLDivElement>(null);
  const fileInputRef   = useRef<HTMLInputElement>(null);

  // Auto-focus title on open
  useEffect(() => { titleRef.current?.focus(); }, []);

  // Focus ticker input when editing starts
  useEffect(() => {
    if (tickerEditing) tickerInputRef.current?.focus();
  }, [tickerEditing]);

  // Keyboard shortcuts + close dropdowns on outside click
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showPriorityMenu) { setShowPriorityMenu(false); return; }
        if (showMoreMenu)     { setShowMoreMenu(false); return; }
        onClose();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSubmit();
      }
    };
    const clickHandler = () => { setShowPriorityMenu(false); setShowMoreMenu(false); };
    window.addEventListener('keydown', handler);
    window.addEventListener('click', clickHandler);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('click', clickHandler);
    };
  }, [ticker, title, description, showPriorityMenu, showMoreMenu]); // eslint-disable-line

  const openTickerEdit = useCallback(() => {
    setTickerDraft(ticker);
    setTickerEditing(true);
  }, [ticker]);

  const confirmTicker = useCallback(() => {
    const val = tickerDraft.trim().toUpperCase();
    setTicker(val);
    setTickerEditing(false);
    setTickerDraft('');
  }, [tickerDraft]);

  const handleTickerKey = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); confirmTicker(); }
    if (e.key === 'Escape') { setTickerEditing(false); setTickerDraft(''); }
  }, [confirmTicker]);

  const handleSubmit = useCallback(() => {
    if (!ticker) { openTickerEdit(); return; }
    onRun(ticker, title || `Analyze ${ticker}`, description);
  }, [ticker, title, description, onRun, openTickerEdit]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length) setAttachments(prev => [...prev, ...files]);
    // Reset so same file can be re-selected
    e.target.value = '';
  }, []);

  const removeAttachment = useCallback((idx: number) => {
    setAttachments(prev => prev.filter((_, i) => i !== idx));
  }, []);

  const clearForm = useCallback(() => {
    setTitle(''); setTicker(''); setDescription('');
    setPriority(null); setAttachments([]);
    setShowMoreMenu(false);
    titleRef.current?.focus();
  }, []);

  const canRun = ticker.length > 0;

  return (
    <>
      <style>{`
        @keyframes modalSlideIn {
          from { opacity: 0; transform: translateY(10px) scale(0.99); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes backdropIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        .assign-modal-ticker-pill {
          transition: background 0.1s ease, border-color 0.1s ease;
        }
        .assign-modal-ticker-pill:hover {
          background: #EBEBEB !important;
          border-color: #D1D5DB !important;
        }
        .assign-modal-discard:hover { color: #374151 !important; }
        .assign-modal-run:hover:not(:disabled) {
          background: #1e293b !important;
        }
        .assign-modal-close:hover { color: #0F172A !important; }
        .assign-modal-status-chip:hover {
          border-color: #D1D5DB !important;
          color: #6B7280 !important;
        }
        .assign-modal-title::placeholder { color: #D1D5DB; }
        .assign-modal-desc::placeholder  { color: #C4C4C4; }
        .assign-modal-ticker-input { caret-color: #10B981; }
        .assign-modal-ticker-input::placeholder { color: #C4C4C4; }
      `}</style>

      {/* ── Backdrop ─────────────────────────────────────────────────────── */}
      <div
        ref={backdropRef}
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          background: 'rgba(0,0,0,0.72)',
          backdropFilter: 'blur(4px)',
          WebkitBackdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          animation: 'backdropIn 0.18s ease-out',
          padding: '0 24px',
        }}
      >
        {/* ── Modal ──────────────────────────────────────────────────────── */}
        <div
          onClick={e => e.stopPropagation()}
          style={{
            width: '100%', maxWidth: 600,
            maxHeight: '88vh', overflowY: 'auto',
            background: '#FFFFFF',
            border: '1px solid #EEEEEE',
            borderRadius: 14,
            animation: 'modalSlideIn 0.18s ease-out',
            fontFamily: 'IBM Plex Sans, sans-serif',
            boxShadow: '0 8px 40px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
          }}
        >
          {/* ── Header ─────────────────────────────────────────────────── */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '13px 18px',
            borderBottom: '1px solid #F3F3F3',
          }}>
            {/* Breadcrumb */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                padding: '2px 8px', borderRadius: 6,
                background: '#F5F5F5', border: '1px solid #E5E7EB',
                fontSize: 10, fontWeight: 600, color: '#9CA3AF',
                fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '0.05em',
              }}>PHR</span>
              <span style={{ color: '#D1D5DB', fontSize: 13 }}>›</span>
              <span style={{ fontSize: 12, color: '#9CA3AF', fontFamily: 'IBM Plex Sans, sans-serif' }}>
                {agentTitle}
              </span>
            </div>

            {/* Header actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <button style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#BEBEBE', fontSize: 14, padding: '4px 6px', borderRadius: 6,
                lineHeight: 1, fontFamily: 'monospace',
              }} title="Expand">⤢</button>
              <button
                className="assign-modal-close"
                onClick={onClose}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: '#BEBEBE', fontSize: 18, padding: '2px 6px', borderRadius: 6,
                  lineHeight: 1, transition: 'color 0.12s ease',
                }}
              >×</button>
            </div>
          </div>

          {/* ── Title input ────────────────────────────────────────────── */}
          <div style={{ padding: '22px 26px 10px' }}>
            <input
              ref={titleRef}
              className="assign-modal-title"
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="What do you want to analyze?"
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'transparent', border: 'none', outline: 'none',
                fontSize: 24, fontWeight: 700, color: '#0F172A',
                fontFamily: 'IBM Plex Sans, sans-serif',
                letterSpacing: '-0.02em', lineHeight: 1.2,
              }}
            />
          </div>

          {/* ── Pill row ───────────────────────────────────────────────── */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
            padding: '8px 26px 14px',
            borderBottom: '1px solid #F3F3F3',
          }}>
            <span style={{ fontSize: 12, color: '#9CA3AF', fontFamily: 'IBM Plex Sans, sans-serif' }}>For</span>

            {/* Ticker pill / input */}
            {tickerEditing ? (
              <input
                ref={tickerInputRef}
                className="assign-modal-ticker-input"
                type="text"
                value={tickerDraft}
                onChange={e => setTickerDraft(e.target.value.toUpperCase())}
                onKeyDown={handleTickerKey}
                onBlur={confirmTicker}
                placeholder="AAPL"
                maxLength={10}
                style={{
                  background: '#F9FAFB', border: '1px solid #10B981',
                  borderRadius: 8, padding: '4px 10px',
                  fontSize: 12, fontFamily: 'IBM Plex Mono, monospace',
                  color: '#10B981', outline: 'none', width: 90,
                  letterSpacing: '0.04em', fontWeight: 600,
                }}
              />
            ) : (
              <button
                className="assign-modal-ticker-pill"
                onClick={openTickerEdit}
                style={{
                  background: '#F5F5F5', border: `1px solid ${ticker ? 'rgba(16,185,129,0.35)' : '#E5E7EB'}`,
                  borderRadius: 8, padding: '4px 10px',
                  fontSize: 12, fontFamily: 'IBM Plex Mono, monospace',
                  color: ticker ? '#10B981' : '#BEBEBE',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                  fontWeight: ticker ? 600 : 400, letterSpacing: ticker ? '0.04em' : 0,
                  transition: 'all 0.12s ease',
                }}
              >
                {ticker || 'Ticker'}
                <span style={{ color: '#C4C4C4', fontSize: 9, fontFamily: 'sans-serif' }}>▾</span>
              </button>
            )}

            <span style={{ fontSize: 12, color: '#9CA3AF', fontFamily: 'IBM Plex Sans, sans-serif' }}>in</span>

            {/* Agent pill — static */}
            <span style={{
              background: '#F5F5F5', border: '1px solid #E5E7EB',
              borderRadius: 8, padding: '4px 10px',
              fontSize: 12, fontFamily: 'IBM Plex Sans, sans-serif',
              color: '#9CA3AF', display: 'inline-flex', alignItems: 'center', gap: 5,
            }}>
              {agentTitle}
              <span style={{ color: '#C4C4C4', fontSize: 9, fontFamily: 'sans-serif' }}>▾</span>
            </span>

            {/* More options */}
            <button style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#BEBEBE', fontSize: 14, padding: '0 4px',
              letterSpacing: '0.1em', fontFamily: 'monospace',
            }}>···</button>
          </div>

          {/* ── Description textarea ───────────────────────────────────── */}
          <div style={{ padding: '0 26px' }}>
            <textarea
              className="assign-modal-desc"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Add description..."
              rows={5}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'transparent', border: 'none', outline: 'none',
                fontSize: 14, color: '#374151', resize: 'none',
                fontFamily: 'IBM Plex Sans, sans-serif', lineHeight: 1.65,
                padding: '16px 0',
              }}
            />
          </div>

          {/* ── Attachment chips (shown when files added) ──────────────── */}
          {attachments.length > 0 && (
            <div style={{ padding: '0 26px 10px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {attachments.map((file, idx) => (
                <span key={idx} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '3px 8px', borderRadius: 6,
                  background: '#F0FDF4', border: '1px solid rgba(16,185,129,0.25)',
                  fontSize: 11, color: '#059669', fontFamily: 'IBM Plex Mono, monospace',
                  maxWidth: 180, overflow: 'hidden',
                }}>
                  <span style={{ fontSize: 10 }}>📄</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {file.name}
                  </span>
                  <button
                    onClick={() => removeAttachment(idx)}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: '#10B981', fontSize: 12, padding: 0, lineHeight: 1, flexShrink: 0,
                    }}
                  >×</button>
                </span>
              ))}
            </div>
          )}

          {/* ── Status bar ─────────────────────────────────────────────── */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
            padding: '12px 26px 14px',
            borderTop: '1px solid #F3F3F3',
            position: 'relative',
          }}>

            {/* Priority */}
            <div style={{ position: 'relative' }}>
              <button
                className="assign-modal-status-chip"
                onClick={() => { setShowPriorityMenu(p => !p); setShowMoreMenu(false); }}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  background: priority ? PRIORITY_CONFIG[priority].bg : 'transparent',
                  border: `1px solid ${priority ? PRIORITY_CONFIG[priority].border : '#EEEEEE'}`,
                  borderRadius: 8, padding: '5px 10px',
                  fontSize: 11, color: priority ? PRIORITY_CONFIG[priority].color : '#BEBEBE',
                  cursor: 'pointer', fontFamily: 'IBM Plex Mono, monospace',
                  letterSpacing: '0.01em', transition: 'all 0.12s ease',
                }}
              >
                <span style={{ fontSize: 10 }}>⚑</span>
                {priority ? PRIORITY_CONFIG[priority].label : 'Priority'}
                {priority && (
                  <span
                    onClick={e => { e.stopPropagation(); setPriority(null); }}
                    style={{ fontSize: 11, opacity: 0.6, cursor: 'pointer', lineHeight: 1 }}
                  >×</span>
                )}
              </button>

              {showPriorityMenu && (
                <div
                  style={{
                    position: 'absolute', bottom: 'calc(100% + 6px)', left: 0,
                    background: '#FFFFFF', border: '1px solid #EEEEEE',
                    borderRadius: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
                    padding: '4px', zIndex: 100, minWidth: 130,
                  }}
                >
                  {(['low', 'medium', 'high'] as Priority[]).map(p => (
                    <button
                      key={p}
                      onClick={() => { setPriority(p); setShowPriorityMenu(false); }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                        padding: '7px 10px', border: 'none',
                        borderRadius: 7, cursor: 'pointer', textAlign: 'left',
                        fontSize: 12, fontFamily: 'IBM Plex Mono, monospace',
                        color: PRIORITY_CONFIG[p].color,
                        fontWeight: priority === p ? 600 : 400,
                        background: priority === p ? PRIORITY_CONFIG[p].bg : 'transparent',
                      } as React.CSSProperties}
                    >
                      <span style={{
                        width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                        background: PRIORITY_CONFIG[p].color,
                      }} />
                      {PRIORITY_CONFIG[p].label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Upload */}
            <button
              className="assign-modal-status-chip"
              onClick={() => fileInputRef.current?.click()}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: attachments.length ? 'rgba(16,185,129,0.05)' : 'transparent',
                border: `1px solid ${attachments.length ? 'rgba(16,185,129,0.3)' : '#EEEEEE'}`,
                borderRadius: 8, padding: '5px 10px',
                fontSize: 11, color: attachments.length ? '#059669' : '#BEBEBE',
                cursor: 'pointer', fontFamily: 'IBM Plex Mono, monospace',
                letterSpacing: '0.01em', transition: 'all 0.12s ease',
              }}
            >
              <span style={{ fontSize: 10 }}>⌘</span>
              Upload{attachments.length > 0 ? ` (${attachments.length})` : ''}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.csv,.xlsx,.xls,.txt,.docx,.doc,.png,.jpg"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />

            {/* ··· More options */}
            <div style={{ position: 'relative' }}>
              <button
                className="assign-modal-status-chip"
                onClick={() => { setShowMoreMenu(m => !m); setShowPriorityMenu(false); }}
                style={{
                  background: 'transparent', border: '1px solid #EEEEEE',
                  borderRadius: 8, padding: '5px 10px',
                  fontSize: 13, color: '#BEBEBE', cursor: 'pointer',
                  fontFamily: 'monospace', letterSpacing: '0.12em',
                  transition: 'all 0.12s ease',
                }}
              >···</button>

              {showMoreMenu && (
                <div
                  style={{
                    position: 'absolute', bottom: 'calc(100% + 6px)', left: 0,
                    background: '#FFFFFF', border: '1px solid #EEEEEE',
                    borderRadius: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
                    padding: '4px', zIndex: 100, minWidth: 160,
                  }}
                >
                  {[
                    { label: 'Clear form',       icon: '↺', action: clearForm },
                    { label: 'Save as template', icon: '◇', action: () => setShowMoreMenu(false) },
                  ].map(item => (
                    <button
                      key={item.label}
                      onClick={item.action}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                        padding: '7px 10px', background: 'none', border: 'none',
                        borderRadius: 7, cursor: 'pointer', textAlign: 'left',
                        fontSize: 12, fontFamily: 'IBM Plex Sans, sans-serif',
                        color: '#6B7280',
                      }}
                    >
                      <span style={{ fontSize: 11, color: '#BEBEBE' }}>{item.icon}</span>
                      {item.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Footer ─────────────────────────────────────────────────── */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 20px 16px',
            borderTop: '1px solid #F3F3F3',
          }}>
            <button
              className="assign-modal-discard"
              onClick={onClose}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#9CA3AF', fontSize: 13,
                fontFamily: 'IBM Plex Sans, sans-serif',
                transition: 'color 0.12s ease', padding: '4px 0',
              }}
            >
              Discard Draft
            </button>

            <button
              className="assign-modal-run"
              onClick={handleSubmit}
              disabled={!canRun}
              style={{
                background: canRun ? '#0F172A' : '#F3F4F6',
                color: canRun ? '#FFFFFF' : '#9CA3AF',
                border: 'none', borderRadius: 10,
                padding: '9px 20px',
                fontSize: 13, fontWeight: 700,
                fontFamily: 'IBM Plex Sans, sans-serif',
                cursor: canRun ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', gap: 7,
                letterSpacing: '-0.01em',
                transition: 'background 0.12s ease, color 0.12s ease',
              }}
            >
              <span style={{ fontSize: 11 }}>▶</span>
              Run Analysis
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default AssignModal;
