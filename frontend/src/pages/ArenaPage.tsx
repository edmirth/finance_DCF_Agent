import { useState, useCallback, useRef, useEffect, KeyboardEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { streamMessage } from '../api';

// ─── Types ────────────────────────────────────────────────────────────────────

type ChatMsg =
  | { kind: 'user';      id: string; text: string }
  | { kind: 'system';    id: string; text: string }
  | { kind: 'signal';    id: string; agent: string; round: number; confidence: number; reasoning: string }
  | { kind: 'question';  id: string; from: string; to: string; question: string }
  | { kind: 'answer';    id: string; from: string; to: string; question: string; answer: string }
  | { kind: 'conflict';  id: string; round: number; description: string }
  | { kind: 'synthesis'; id: string; round: number; consensus: number; conviction: string; thesis: string }
  | { kind: 'decision';  id: string; decision: string; conviction: string; memo: string };

type QueryMode = 'full_ic' | 'quick_screen' | 'risk_check' | 'valuation' | 'macro_view';

// ─── Constants ────────────────────────────────────────────────────────────────

const MODES: { id: QueryMode; label: string; description: string }[] = [
  { id: 'full_ic',      label: 'Full IC',      description: 'All 5 analysts — deepest conviction' },
  { id: 'quick_screen', label: 'Quick Screen', description: 'Fast buy/pass signal' },
  { id: 'valuation',    label: 'Valuation',    description: 'Intrinsic value focus' },
  { id: 'risk_check',   label: 'Risk Check',   description: 'Downside & leverage deep-dive' },
  { id: 'macro_view',   label: 'Macro View',   description: 'Rates, cycle & sentiment' },
];

const AGENT: Record<string, { label: string; role: string; color: string; initials: string }> = {
  fundamental: { label: 'Fundamental', role: 'Valuation & Earnings Quality',  color: '#3B82F6', initials: 'FU' },
  risk:        { label: 'Risk',        role: 'Leverage & Liquidity',    color: '#EF4444', initials: 'RK' },
  quant:       { label: 'Quant',       role: 'Momentum & Factors',      color: '#8B5CF6', initials: 'QT' },
  macro:       { label: 'Macro',       role: 'Rates & Cycle',           color: '#F59E0B', initials: 'MC' },
  sentiment:   { label: 'Sentiment',   role: 'News & Analyst Flow',     color: '#10B981', initials: 'ST' },
  pm:          { label: 'PM',          role: 'Portfolio Manager',       color: '#1A1A1A', initials: 'PM' },
};


const SUGGESTIONS: { text: string; mode: QueryMode }[] = [
  { text: 'Is NVDA overvalued after the AI run-up?',           mode: 'valuation'    },
  { text: 'Full investment committee review on AAPL',          mode: 'full_ic'      },
  { text: "What are the key risks in TSLA right now?",         mode: 'risk_check'   },
  { text: 'Quick screen — is MSFT worth buying at this price?',mode: 'quick_screen' },
  { text: 'Macro outlook for semiconductor stocks',            mode: 'macro_view'   },
];

// ─── Avatar ───────────────────────────────────────────────────────────────────

function Avatar({ agentKey, size = 32 }: { agentKey: string; size?: number }) {
  const meta = AGENT[agentKey] || { color: '#6B7280', initials: agentKey.slice(0, 2).toUpperCase() };
  return (
    <div
      className="flex-shrink-0 flex items-center justify-center rounded-full font-semibold select-none"
      style={{
        width: size, height: size,
        background: `${meta.color}18`,
        color: meta.color,
        border: `1.5px solid ${meta.color}30`,
        fontSize: size * 0.34,
        letterSpacing: '0.02em',
        fontFamily: 'Inter, sans-serif',
      }}
    >
      {meta.initials}
    </div>
  );
}

// ─── Typing indicator ─────────────────────────────────────────────────────────

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-[3px] ml-1">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-current opacity-40"
          style={{ animation: `typingDot 1.2s ${i * 0.2}s ease-in-out infinite` }}
        />
      ))}
    </span>
  );
}

// ─── Message rows ─────────────────────────────────────────────────────────────

function UserBubble({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex justify-end py-3"
    >
      <div
        className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-br-sm text-sm leading-relaxed"
        style={{
          background: '#1A1A1A',
          color: '#FFFFFF',
          fontFamily: 'Inter, sans-serif',
        }}
      >
        {text}
      </div>
    </motion.div>
  );
}

function SystemRow({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex justify-center py-3"
    >
      <span
        className="text-xs px-3 py-1 rounded-full"
        style={{
          color: '#9CA3AF',
          background: '#F9FAFB',
          border: '1px solid #E5E7EB',
          fontFamily: 'Inter, sans-serif',
          letterSpacing: '0.01em',
        }}
      >
        {text}
      </span>
    </motion.div>
  );
}

function ThinkingRow({ agentKey }: { agentKey: string }) {
  const meta = AGENT[agentKey] || AGENT.fundamental;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey={agentKey} />
      <div className="flex flex-col">
        <div className="flex items-baseline gap-1.5 mb-1">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif', letterSpacing: '-0.01em' }}>
            {meta.label}
          </span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
            {meta.role}
          </span>
        </div>
        <div
          className="inline-flex items-center px-3 py-2 rounded-2xl rounded-tl-sm"
          style={{ background: '#F9FAFB', border: '1px solid #E5E7EB' }}
        >
          <span className="text-sm" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
            Writing
          </span>
          <TypingDots />
        </div>
      </div>
    </motion.div>
  );
}

function SignalRow({ msg }: { msg: Extract<ChatMsg, { kind: 'signal' }> }) {
  const meta = AGENT[msg.agent] || AGENT.fundamental;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey={msg.agent} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5 mb-1.5">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif', letterSpacing: '-0.01em' }}>
            {meta.label}
          </span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
            {meta.role}
          </span>
          {msg.round > 1 && (
            <span className="text-xs px-1.5 py-0.5 rounded-md" style={{ color: '#9CA3AF', background: '#F3F4F6', fontFamily: 'Inter, sans-serif' }}>
              Round {msg.round}
            </span>
          )}
        </div>
        <div
          className="rounded-2xl rounded-tl-sm p-3.5"
          style={{ background: '#FAFAFA', border: '1px solid #EFEFEF' }}
        >
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="text-sm leading-relaxed mb-1.5 last:mb-0" style={{ color: '#374151', fontFamily: 'Inter, sans-serif' }}>{children}</p>,
              strong: ({ children }) => <strong className="font-semibold" style={{ color: '#1A1A1A' }}>{children}</strong>,
              ul: ({ children }) => <ul className="space-y-1 mt-1.5 pl-0">{children}</ul>,
              li: ({ children }) => (
                <li className="flex gap-2 text-sm leading-relaxed" style={{ color: '#374151', listStyle: 'none' }}>
                  <span style={{ color: '#10B981', flexShrink: 0 }}>•</span>
                  <span>{children}</span>
                </li>
              ),
            }}
          >
            {msg.reasoning}
          </ReactMarkdown>
        </div>
      </div>
    </motion.div>
  );
}

function QuestionRow({ msg }: { msg: Extract<ChatMsg, { kind: 'question' }> }) {
  const fromMeta = AGENT[msg.from] || AGENT.fundamental;
  const toMeta   = AGENT[msg.to]   || AGENT.risk;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey={msg.from} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5 mb-1.5">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif', letterSpacing: '-0.01em' }}>
            {fromMeta.label}
          </span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
            asking {toMeta.label}
          </span>
        </div>
        <div
          className="rounded-2xl rounded-tl-sm px-3.5 py-2.5"
          style={{ background: `${fromMeta.color}08`, border: `1px solid ${fromMeta.color}20` }}
        >
          <p className="text-sm leading-relaxed" style={{ color: '#374151', fontFamily: 'Inter, sans-serif' }}>
            <span style={{ color: fromMeta.color, fontWeight: 600 }}>@{toMeta.label}</span>
            {' '}{msg.question}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

function AnswerRow({ msg }: { msg: Extract<ChatMsg, { kind: 'answer' }> }) {
  const fromMeta = AGENT[msg.from] || AGENT.fundamental;
  const toMeta   = AGENT[msg.to]   || AGENT.risk;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey={msg.from} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5 mb-1.5">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif', letterSpacing: '-0.01em' }}>
            {fromMeta.label}
          </span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
            replying to {toMeta.label}
          </span>
        </div>
        <div
          className="mb-1.5 px-3 py-1.5 rounded-xl text-xs italic border-l-2"
          style={{ color: '#9CA3AF', background: '#F9FAFB', borderLeftColor: toMeta.color, fontFamily: 'Inter, sans-serif' }}
        >
          {msg.question}
        </div>
        <div
          className="rounded-2xl rounded-tl-sm px-3.5 py-2.5"
          style={{ background: `${fromMeta.color}08`, border: `1px solid ${fromMeta.color}20` }}
        >
          <p className="text-sm leading-relaxed" style={{ color: '#374151', fontFamily: 'Inter, sans-serif' }}>
            {msg.answer}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

function ConflictRow({ msg }: { msg: Extract<ChatMsg, { kind: 'conflict' }> }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey="pm" />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5 mb-1.5">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}>PM</span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>Portfolio Manager</span>
        </div>
        <div
          className="rounded-2xl rounded-tl-sm px-3.5 py-2.5"
          style={{ background: '#FFFBEB', border: '1px solid #FDE68A' }}
        >
          <div className="flex items-center gap-1.5 mb-1">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
              <path d="M7 1.5L13 12.5H1L7 1.5Z" stroke="#D97706" strokeWidth="1.4" strokeLinejoin="round"/>
              <path d="M7 6V8.5" stroke="#D97706" strokeWidth="1.4" strokeLinecap="round"/>
              <circle cx="7" cy="10.5" r="0.6" fill="#D97706"/>
            </svg>
            <span className="text-xs font-semibold" style={{ color: '#92400E', fontFamily: 'Inter, sans-serif' }}>
              Conflict flagged — Round {msg.round}
            </span>
          </div>
          <p className="text-sm" style={{ color: '#B45309', fontFamily: 'Inter, sans-serif' }}>
            {msg.description}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

function SynthesisRow({ msg }: { msg: Extract<ChatMsg, { kind: 'synthesis' }> }) {
  const pct = Math.round(msg.consensus * 100);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey="pm" />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5 mb-1.5">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}>PM</span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
            Round {msg.round} · {pct}% consensus
          </span>
        </div>
        <div
          className="rounded-2xl rounded-tl-sm px-4 py-3.5 prose prose-sm max-w-none"
          style={{ background: '#F9FAFB', border: '1px solid #E5E7EB', fontFamily: 'Inter, sans-serif', color: '#374151' }}
        >
          <ReactMarkdown
            components={{
              h1: ({ children }) => <p className="text-sm font-semibold mb-2" style={{ color: '#1A1A1A' }}>{children}</p>,
              h2: ({ children }) => <p className="text-sm font-semibold mb-1.5 mt-3" style={{ color: '#1A1A1A' }}>{children}</p>,
              h3: ({ children }) => <p className="text-xs font-semibold uppercase mb-1 mt-3" style={{ color: '#9CA3AF', letterSpacing: '0.05em' }}>{children}</p>,
              p: ({ children }) => <p className="text-sm leading-relaxed mb-2 last:mb-0" style={{ color: '#374151' }}>{children}</p>,
              strong: ({ children }) => <strong className="font-semibold" style={{ color: '#1A1A1A' }}>{children}</strong>,
              ul: ({ children }) => <ul className="space-y-1 mb-2 pl-0">{children}</ul>,
              li: ({ children }) => (
                <li className="flex gap-2 text-sm leading-relaxed" style={{ color: '#374151', listStyle: 'none' }}>
                  <span style={{ color: '#10B981', flexShrink: 0 }}>•</span>
                  <span>{children}</span>
                </li>
              ),
            }}
          >
            {msg.thesis}
          </ReactMarkdown>
        </div>
      </div>
    </motion.div>
  );
}

function DecisionRow({ msg }: { msg: Extract<ChatMsg, { kind: 'decision' }> }) {
  // Clean the raw memo: strip separator lines, header, and convert ALL-CAPS
  // section headings into markdown ## headings so ReactMarkdown renders them.
  const cleanedMemo = msg.memo
    .split('\n')
    .filter(line => {
      const t = line.trim();
      return (
        !t.match(/^={3,}/) &&                      // strip === separators
        !t.match(/^INVESTMENT COMMITTEE MEMO/) &&   // strip header
        !t.match(/^DECISION:/) &&                   // strip — shown at top already
        !t.match(/^CONSENSUS:/) &&                  // strip — shown at top already
        !t.match(/^ANALYST SIGNALS:/)               // strip raw signals block heading
      );
    })
    .filter((line, i, arr) => {
      // Collapse runs of blank lines down to a single blank line
      if (line.trim() === '' && arr[i - 1]?.trim() === '') return false;
      return true;
    })
    .map(line => {
      const t = line.trim();
      // Agent signal lines like "  FUNDAMENTAL  BEARISH  conf:68% ..." — skip them
      if (/^\s+(FUNDAMENTAL|RISK|MACRO|QUANT|SENTIMENT)\s+/.test(line)) return null;
      // Convert standalone ALL-CAPS headings to ## markdown
      if (t.length > 3 && t === t.toUpperCase() && /^[A-Z][A-Z\s&:()/]+$/.test(t)) {
        return `## ${t}`;
      }
      return line;
    })
    .filter((line): line is string => line !== null)
    .join('\n')
    .trim();

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="flex items-start gap-3 py-2.5"
    >
      <Avatar agentKey="pm" />
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-baseline gap-1.5 mb-1.5">
          <span className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}>PM</span>
          <span className="text-xs" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>Investment memo</span>
        </div>

        {/* Memo card */}
        <div
          className="rounded-2xl rounded-tl-sm px-5 py-4"
          style={{ background: '#FAFAFA', border: '1px solid #EFEFEF' }}
        >
          {/* Full memo rendered */}
          <ReactMarkdown
            components={{
              h2: ({ children }) => (
                <h2 className="text-xs font-semibold uppercase mt-5 mb-2 first:mt-0" style={{ color: '#9CA3AF', letterSpacing: '0.06em', fontFamily: 'Inter, sans-serif' }}>
                  {children}
                </h2>
              ),
              p: ({ children }) => (
                <p className="text-sm leading-relaxed mb-3 last:mb-0" style={{ color: '#374151', fontFamily: 'Inter, sans-serif' }}>
                  {children}
                </p>
              ),
              strong: ({ children }) => (
                <strong className="font-semibold" style={{ color: '#1A1A1A' }}>{children}</strong>
              ),
              ul: ({ children }) => <ul className="space-y-1.5 mb-3 pl-0">{children}</ul>,
              li: ({ children }) => (
                <li className="flex gap-2 text-sm leading-relaxed" style={{ color: '#374151', listStyle: 'none' }}>
                  <span style={{ color: '#10B981', flexShrink: 0, marginTop: 1 }}>•</span>
                  <span>{children}</span>
                </li>
              ),
            }}
          >
            {cleanedMemo}
          </ReactMarkdown>
        </div>
      </div>
    </motion.div>
  );
}


// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({
  queryMode,
  onModeChange,
  onSuggest,
}: {
  queryMode: QueryMode;
  onModeChange: (m: QueryMode) => void;
  onSuggest: (text: string, mode: QueryMode) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] animate-fade-in">
      {/* Badge */}
      <div className="inline-flex items-center gap-2 mb-5 px-3 py-1.5 rounded-full" style={{ background: '#F0FDF4', border: '1px solid #A7F3D0' }}>
        <div className="flex -space-x-1">
          {['fundamental', 'risk', 'quant'].map(a => (
            <div key={a} className="w-4 h-4 rounded-full border-2 border-white" style={{ background: AGENT[a].color }} />
          ))}
        </div>
        <span className="text-xs font-semibold" style={{ color: '#059669', letterSpacing: '0.04em', textTransform: 'uppercase', fontFamily: 'Inter, sans-serif' }}>
          Investment Committee
        </span>
      </div>

      {/* Title */}
      <h1 className="text-2xl sm:text-[2.5rem] font-semibold text-[#1A1A1A] mb-3 text-center" style={{ fontFamily: 'Inter, sans-serif', letterSpacing: '-0.03em' }}>
        Agent Arena
      </h1>
      <p className="text-base sm:text-lg text-center max-w-sm mb-6 sm:mb-8 px-4" style={{ color: '#6B7280', fontFamily: 'Inter, sans-serif', lineHeight: 1.6 }}>
        Ask anything about a stock. Five AI analysts debate it live and deliver a conviction-rated verdict.
      </p>

      {/* Mode pills */}
      <div className="flex flex-wrap justify-center gap-2 mb-2 max-w-[520px] px-4">
        {MODES.map(m => (
          <button
            key={m.id}
            onClick={() => onModeChange(m.id)}
            className="px-3.5 py-1.5 rounded-full text-sm font-medium transition-all duration-200"
            style={{
              fontFamily: 'Inter, sans-serif',
              background: queryMode === m.id ? '#1A1A1A' : '#F9FAFB',
              color: queryMode === m.id ? '#FFFFFF' : '#6B7280',
              border: `1px solid ${queryMode === m.id ? '#1A1A1A' : '#E5E5E5'}`,
            }}
          >
            {m.label}
          </button>
        ))}
      </div>
      <p className="text-xs mb-8 text-center" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
        {MODES.find(m => m.id === queryMode)?.description}
      </p>

      {/* Suggestions */}
      <div className="flex flex-col gap-2 w-full max-w-[480px] px-4">
        <p className="text-xs mb-1 text-center" style={{ color: '#C4C4C4', fontFamily: 'Inter, sans-serif' }}>
          Try asking…
        </p>
        {SUGGESTIONS.map(s => (
          <button
            key={s.text}
            onClick={() => onSuggest(s.text, s.mode)}
            className="text-left px-4 py-3 rounded-xl text-sm transition-all duration-200"
            style={{ fontFamily: 'Inter, sans-serif', color: '#374151', background: '#F9FAFB', border: '1px solid #EFEFEF' }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = '#10B981';
              e.currentTarget.style.background = '#F0FDF4';
              e.currentTarget.style.color = '#1A1A1A';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = '#EFEFEF';
              e.currentTarget.style.background = '#F9FAFB';
              e.currentTarget.style.color = '#374151';
            }}
          >
            {s.text}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Input bar ────────────────────────────────────────────────────────────────

const MENTION_AGENTS = [
  { key: 'fundamental', label: 'Fundamental', role: 'Valuation & Earnings Quality',  color: '#3B82F6', initials: 'FU' },
  { key: 'risk',        label: 'Risk',        role: 'Leverage & Liquidity',    color: '#EF4444', initials: 'RK' },
  { key: 'quant',       label: 'Quant',       role: 'Momentum & Factors',      color: '#8B5CF6', initials: 'QT' },
  { key: 'macro',       label: 'Macro',       role: 'Rates & Cycle',           color: '#F59E0B', initials: 'MC' },
  { key: 'sentiment',   label: 'Sentiment',   role: 'News & Analyst Flow',     color: '#10B981', initials: 'ST' },
];

function InputBar({
  value,
  onChange,
  onSubmit,
  disabled,
  queryMode,
  onModeChange,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  queryMode: QueryMode;
  onModeChange: (m: QueryMode) => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [value]);

  const filteredAgents = MENTION_AGENTS.filter(a =>
    a.label.toLowerCase().startsWith(mentionFilter.toLowerCase()) ||
    a.key.startsWith(mentionFilter.toLowerCase())
  );

  const insertMention = (agent: typeof MENTION_AGENTS[0]) => {
    const el = textareaRef.current;
    const cursor = el?.selectionStart ?? value.length;
    const before = value.slice(0, cursor).replace(/@\w*$/, `@${agent.label} `);
    const after = value.slice(cursor);
    onChange(before + after);
    setMentionOpen(false);
    setMentionFilter('');
    setTimeout(() => {
      el?.focus();
      const pos = before.length;
      el?.setSelectionRange(pos, pos);
    }, 0);
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    const cursor = e.target.selectionStart;
    const before = val.slice(0, cursor);
    const match = before.match(/@(\w*)$/);
    if (match) {
      setMentionFilter(match[1]);
      setMentionIndex(0);
      setMentionOpen(true);
    } else {
      setMentionOpen(false);
    }
    onChange(val);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen && filteredAgents.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setMentionIndex(i => Math.min(i + 1, filteredAgents.length - 1)); return; }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setMentionIndex(i => Math.max(i - 1, 0)); return; }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); insertMention(filteredAgents[mentionIndex]); return; }
      if (e.key === 'Escape')    { setMentionOpen(false); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) onSubmit();
    }
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div
      className="fixed bottom-0 left-0 md:left-[60px] lg:left-[240px] right-0 pb-4 sm:pb-6 pt-4 z-50 transition-all duration-300"
      style={{ background: 'linear-gradient(to top, #FFFFFF 60%, transparent)' }}
    >
      <div className="max-w-[720px] mx-auto px-4 sm:px-6">
        {/* @mention picker — floats above the input */}
        {mentionOpen && filteredAgents.length > 0 && (
          <div
            className="mb-2 rounded-xl overflow-hidden"
            style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }}
          >
            {filteredAgents.map((agent, i) => (
              <button
                key={agent.key}
                onMouseDown={e => { e.preventDefault(); insertMention(agent); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors"
                style={{ background: i === mentionIndex ? '#F9FAFB' : 'transparent' }}
                onMouseEnter={() => setMentionIndex(i)}
              >
                <div
                  className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-semibold"
                  style={{ background: `${agent.color}18`, color: agent.color, border: `1.5px solid ${agent.color}30` }}
                >
                  {agent.initials}
                </div>
                <div>
                  <span className="text-sm font-medium" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}>
                    @{agent.label}
                  </span>
                  <span className="text-xs ml-2" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
                    {agent.role}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}

        <div className="rogo-input-box">
          {/* Textarea */}
          <div className="input-area">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask the committee anything… or type @ to call a specific agent"
              rows={1}
              disabled={disabled}
            />
          </div>

          {/* Toolbar */}
          <div className="toolbar">
            {/* Mode pills on the left - horizontal scroll on mobile */}
            <div className="rogo-toolbar-left overflow-x-auto scrollbar-hide" style={{ gap: '0.375rem' }}>
              {MODES.map(m => (
                <button
                  key={m.id}
                  onClick={() => onModeChange(m.id)}
                  disabled={disabled}
                  className="flex-shrink-0 transition-all duration-150"
                  style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    padding: '0.25rem 0.75rem',
                    borderRadius: '9999px',
                    background: queryMode === m.id ? '#1A1A1A' : '#F3F4F6',
                    color: queryMode === m.id ? '#FFFFFF' : '#9CA3AF',
                    border: 'none',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {/* Send button on the right */}
            <div className="rogo-toolbar-right">
              <button
                onClick={onSubmit}
                disabled={!canSend}
                className={`rogo-send-btn ${canSend ? 'active' : 'disabled'}`}
                aria-label="Send"
              >
                {disabled ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="animate-spin">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="28" strokeDashoffset="10" />
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M3 8H13M13 8L8.5 3.5M13 8L8.5 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ArenaPage() {
  const [query, setQuery] = useState('');
  const [queryMode, setQueryMode] = useState<QueryMode>('full_ic');
  const [isRunning, setIsRunning] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [threadTitle, setThreadTitle] = useState('');

  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [thinkingAgent, setThinkingAgent] = useState<string | null>(null);
  const [memoBuffer, setMemoBuffer] = useState('');
  const [finalDecision, setFinalDecision] = useState('');
  const [done, setDone] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const push = useCallback((msg: ChatMsg) => setMessages(prev => [...prev, msg]), []);

  // Timer
  useEffect(() => {
    if (isRunning) {
      setElapsedTime(0);
      timerRef.current = setInterval(() => setElapsedTime(p => p + 1), 1000);
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isRunning]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, thinkingAgent]);

  const formatTime = (s: number) => s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;

  const runArena = useCallback(async (overrideQuery?: string, overrideMode?: QueryMode) => {
    const userQuery = (overrideQuery ?? query).trim();
    const mode = overrideMode ?? queryMode;
    if (!userQuery) return;

    // Build the query sent to backend — append mode annotation so backend respects the UI selection
    const backendQuery = `${userQuery} query_mode=${mode}`;

    // Reset thread
    setIsRunning(true);
    setDone(false);
    setMessages([{ kind: 'user', id: 'user-query', text: userQuery }]);
    setThinkingAgent(null);
    setMemoBuffer('');
    setFinalDecision('');
    setThreadTitle(userQuery.length > 60 ? userQuery.slice(0, 57) + '…' : userQuery);
    setQuery('');

    let localMemo = '';

    try {
      await streamMessage(
        { message: backendQuery, agent_type: 'arena', model: 'claude-sonnet-4-6', session_id: `arena-${Date.now()}` },
        (event) => {

          if (event.type === 'arena_dispatch') {
            const agents: string[] = event.agents || [];
            const modeMeta = MODES.find(m => m.id === (event.query_mode as QueryMode));
            push({
              kind: 'system',
              id: 'sys-dispatch',
              text: `Investment committee convened · ${modeMeta?.label || 'Full IC'} · ${agents.length} analysts`,
            });

          } else if (event.type === 'arena_agent_start') {
            setThinkingAgent(event.agent || null);

          } else if (event.type === 'arena_agent_done') {
            setThinkingAgent(null);
            push({
              kind: 'signal',
              id: `signal-${event.agent}-${event.round ?? 1}`,
              agent: event.agent || '',
              round: event.round ?? 1,
              confidence: event.confidence || 0,
              reasoning: event.reasoning || '',
            });

          } else if (event.type === 'arena_question') {
            push({
              kind: 'question',
              id: `q-${event.from_agent}-${Date.now()}`,
              from: event.from_agent || '',
              to: event.to_agent || '',
              question: event.question || '',
            });

          } else if (event.type === 'arena_answer') {
            push({
              kind: 'answer',
              id: `a-${event.from_agent}-${Date.now()}`,
              from: event.from_agent || '',
              to: event.to_agent || '',
              question: event.question || '',
              answer: event.answer || '',
            });

          } else if (event.type === 'arena_conflict') {
            push({
              kind: 'conflict',
              id: `conflict-${event.round}-${Date.now()}`,
              round: event.round || 0,
              description: event.description || '',
            });

          } else if (event.type === 'arena_synthesis') {
            // Only show mid-debate synthesis; the final memo covers the concluding synthesis
            if (event.next_action !== 'finalise') {
              push({
                kind: 'synthesis',
                id: `synth-${event.round}-${Date.now()}`,
                round: event.round || 0,
                consensus: event.consensus_score || 0,
                conviction: event.conviction_level || 'low',
                thesis: event.thesis_summary || '',
              });
            }

          } else if (event.type === 'content' && event.content) {
            localMemo += event.content;
            setMemoBuffer(localMemo);

          } else if (event.type === 'end') {
            const decisionMatch = localMemo.match(/DECISION:\s*(.+)/);
            const convMatch = localMemo.match(/high conviction|medium conviction|low conviction/i);
            const dec = decisionMatch ? decisionMatch[1].replace(/ — .* conviction$/i, '').trim() : '';
            const conv = convMatch ? convMatch[0].replace(' conviction', '').trim() : 'medium';
            setFinalDecision(dec);
            if (localMemo && dec) {
              push({ kind: 'decision', id: 'final-decision', decision: dec, conviction: conv, memo: localMemo });
            }
            setThinkingAgent(null);
            setIsRunning(false);
            setDone(true);

          } else if (event.type === 'error') {
            console.error('Arena error:', event.error);
            push({ kind: 'system', id: `err-${Date.now()}`, text: `Error: ${event.error}` });
            setIsRunning(false);
          }
        },
        (error) => {
          console.error('Stream error:', error);
          setIsRunning(false);
        }
      );
    } catch (err) {
      console.error('Arena error:', err);
      setIsRunning(false);
    }
  }, [query, queryMode, push]);

  const hasStarted = messages.length > 0 || isRunning;

  const handleSuggest = useCallback((text: string, mode: QueryMode) => {
    setQueryMode(mode);
    runArena(text, mode);
  }, [runArena]);

  return (
    <>
      <style>{`
        @keyframes typingDot {
          0%, 60%, 100% { opacity: 0.2; transform: translateY(0); }
          30% { opacity: 1; transform: translateY(-3px); }
        }
      `}</style>

      {/* Main scrollable content — padded bottom for fixed input bar */}
      <div className="earnings-page" style={{ paddingBottom: 140 }}>
        <a href="#main-content" className="skip-link">Skip to main content</a>

        <main id="main-content" tabIndex={-1} className="flex justify-center items-start min-h-screen">
          <div className="w-full max-w-[720px] px-4 sm:px-6 py-6 sm:py-8 mx-auto">

            {/* Empty state */}
            {!hasStarted && (
              <EmptyState
                queryMode={queryMode}
                onModeChange={setQueryMode}
                onSuggest={handleSuggest}
              />
            )}

            {/* Chat thread */}
            {hasStarted && (
              <div className="animate-fade-in">
                {/* Thread header */}
                <div className="flex items-center justify-between mb-6">
                  <div className="min-w-0 flex-1">
                    <h2
                      className="text-lg font-semibold truncate"
                      style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif', letterSpacing: '-0.02em' }}
                      title={threadTitle}
                    >
                      {threadTitle}
                    </h2>
                    <p className="text-sm mt-0.5" style={{ color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
                      {isRunning ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
                          Debate in progress · {formatTime(elapsedTime)}
                        </span>
                      ) : done ? (
                        `Completed in ${formatTime(elapsedTime)}`
                      ) : ''}
                    </p>
                  </div>
                  {done && (
                    <button
                      onClick={() => {
                        setMessages([]);
                        setDone(false);
                        setFinalDecision('');
                        setMemoBuffer('');
                        setThreadTitle('');
                      }}
                      className="ml-4 flex-shrink-0 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200"
                      style={{ fontFamily: 'Inter, sans-serif', color: '#6B7280', background: '#F9FAFB', border: '1px solid #E5E5E5' }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = '#10B981'; e.currentTarget.style.color = '#1A1A1A'; e.currentTarget.style.background = '#F0FDF4'; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = '#E5E5E5'; e.currentTarget.style.color = '#6B7280'; e.currentTarget.style.background = '#F9FAFB'; }}
                    >
                      New analysis
                    </button>
                  )}
                </div>

                <div style={{ height: 1, background: '#F3F4F6', marginBottom: '1.5rem' }} />

                {/* Messages */}
                <div className="pb-4">
                  <AnimatePresence mode="sync">
                    {messages.map(msg => {
                      if (msg.kind === 'user')      return <UserBubble   key={msg.id} text={msg.text} />;
                      if (msg.kind === 'system')    return <SystemRow    key={msg.id} text={msg.text} />;
                      if (msg.kind === 'signal')    return <SignalRow    key={msg.id} msg={msg} />;
                      if (msg.kind === 'question')  return <QuestionRow  key={msg.id} msg={msg} />;
                      if (msg.kind === 'answer')    return <AnswerRow    key={msg.id} msg={msg} />;
                      if (msg.kind === 'conflict')  return <ConflictRow  key={msg.id} msg={msg} />;
                      if (msg.kind === 'synthesis') return <SynthesisRow key={msg.id} msg={msg} />;
                      if (msg.kind === 'decision')  return <DecisionRow  key={msg.id} msg={msg} />;
                      return null;
                    })}

                    {/* Live typing indicator */}
                    {thinkingAgent && (
                      <ThinkingRow key={`thinking-${thinkingAgent}`} agentKey={thinkingAgent} />
                    )}

                    {/* PM writing the memo */}
                    {isRunning && memoBuffer.length > 0 && !finalDecision && (
                      <ThinkingRow key="pm-writing" agentKey="pm" />
                    )}
                  </AnimatePresence>

                  <div ref={bottomRef} />
                </div>
              </div>
            )}

          </div>
        </main>
      </div>

      {/* Fixed input bar — always visible */}
      <InputBar
        value={query}
        onChange={setQuery}
        onSubmit={() => runArena()}
        disabled={isRunning}
        queryMode={queryMode}
        onModeChange={setQueryMode}
      />
    </>
  );
}
