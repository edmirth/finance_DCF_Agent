import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Loader2, BrainCircuit, Play, UserPlus, ChevronDown, ChevronUp, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { cioChat, cioDelegate, cioHire, CioMessage, CioAction } from '../api';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChatEntry {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: CioAction | null;
  actionState?: 'idle' | 'loading' | 'done' | 'error';
  actionResult?: string;
}

// ── Action Cards ──────────────────────────────────────────────────────────────

function DelegateCard({
  action,
  state,
  result,
  onDelegate,
}: {
  action: CioAction;
  state: 'idle' | 'loading' | 'done' | 'error';
  result?: string;
  onDelegate: () => void;
}) {
  return (
    <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden">
      <div className="px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-blue-100 flex items-center justify-center flex-shrink-0">
            <Play className="w-3.5 h-3.5 text-blue-600" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800" style={{ letterSpacing: '-0.01em' }}>
              {action.agent_name}
            </p>
            {action.reason && (
              <p className="text-xs text-slate-500 truncate mt-0.5">{action.reason}</p>
            )}
          </div>
        </div>
        {state === 'idle' && (
          <button
            onClick={onDelegate}
            className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-xl transition-colors duration-200"
          >
            <Play className="w-3 h-3" />
            Run now
          </button>
        )}
        {state === 'loading' && (
          <div className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-blue-100 text-blue-600 text-xs font-medium rounded-xl">
            <Loader2 className="w-3 h-3 animate-spin" />
            Running…
          </div>
        )}
        {state === 'done' && (
          <span className="flex-shrink-0 px-3 py-1.5 bg-emerald-100 text-emerald-700 text-xs font-medium rounded-xl">
            Dispatched
          </span>
        )}
        {state === 'error' && (
          <span className="flex-shrink-0 px-3 py-1.5 bg-red-100 text-red-600 text-xs font-medium rounded-xl">
            Failed
          </span>
        )}
      </div>
      {result && (
        <div className="px-4 pb-3 text-xs text-slate-500 border-t border-slate-200 pt-2">
          {result}
        </div>
      )}
    </div>
  );
}

const TEMPLATE_LABELS: Record<string, string> = {
  earnings_watcher: 'Earnings Watcher',
  market_pulse: 'Market Pulse',
  thesis_guardian: 'Thesis Guardian',
  portfolio_heartbeat: 'Portfolio Heartbeat',
  arena_analyst: 'Arena Analyst',
};

const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily at 7am',
  pre_market: 'Weekdays at 6:30am',
  weekly_monday: 'Every Monday',
  weekly_friday: 'Every Friday',
  monthly: 'Monthly',
};

function HireCard({
  action,
  state,
  result,
  onHire,
  onDismiss,
}: {
  action: CioAction;
  state: 'idle' | 'loading' | 'done' | 'error';
  result?: string;
  onHire: () => void;
  onDismiss: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-3 rounded-2xl border border-emerald-200 bg-emerald-50 overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
              <UserPlus className="w-3.5 h-3.5 text-emerald-600" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide" style={{ letterSpacing: '0.04em' }}>
                Proposal — Hire New Agent
              </p>
              <p className="text-sm font-semibold text-slate-800 mt-0.5" style={{ letterSpacing: '-0.01em' }}>
                {action.name}
              </p>
              {action.description && (
                <p className="text-xs text-slate-500 mt-1">{action.description}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {state === 'idle' && (
              <>
                <button
                  onClick={onDismiss}
                  className="p-1.5 rounded-lg hover:bg-emerald-100 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onHire}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-xl transition-colors duration-200"
                >
                  <UserPlus className="w-3 h-3" />
                  Hire
                </button>
              </>
            )}
            {state === 'loading' && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-100 text-emerald-600 text-xs font-medium rounded-xl">
                <Loader2 className="w-3 h-3 animate-spin" />
                Hiring…
              </div>
            )}
            {state === 'done' && (
              <span className="px-3 py-1.5 bg-emerald-600 text-white text-xs font-medium rounded-xl">
                Hired
              </span>
            )}
            {state === 'error' && (
              <span className="px-3 py-1.5 bg-red-100 text-red-600 text-xs font-medium rounded-xl">
                Failed
              </span>
            )}
          </div>
        </div>

        {/* Meta pills */}
        <div className="flex flex-wrap gap-1.5 mt-3 ml-11">
          {action.template && (
            <span className="px-2 py-0.5 bg-white border border-emerald-200 text-emerald-700 text-xs rounded-lg font-medium">
              {TEMPLATE_LABELS[action.template] || action.template}
            </span>
          )}
          {action.schedule_label && (
            <span className="px-2 py-0.5 bg-white border border-slate-200 text-slate-600 text-xs rounded-lg">
              {SCHEDULE_LABELS[action.schedule_label] || action.schedule_label}
            </span>
          )}
          {(action.tickers || []).map(t => (
            <span key={t} className="px-2 py-0.5 bg-white border border-slate-200 text-slate-700 text-xs rounded-lg font-mono">
              {t}
            </span>
          ))}
        </div>

        {/* Expand instruction */}
        {action.instruction && (
          <button
            onClick={() => setExpanded(e => !e)}
            className="mt-3 ml-11 flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? 'Hide' : 'Show'} instructions
          </button>
        )}
        {expanded && action.instruction && (
          <p className="mt-2 ml-11 text-xs text-slate-600 leading-relaxed bg-white rounded-xl p-3 border border-emerald-100">
            {action.instruction}
          </p>
        )}
      </div>

      {result && (
        <div className="px-4 pb-3 text-xs text-slate-500 border-t border-emerald-100 pt-2">
          {result}
        </div>
      )}
    </div>
  );
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({
  entry,
  onDelegate,
  onHire,
  onDismissAction,
}: {
  entry: ChatEntry;
  onDelegate: (entryId: string) => void;
  onHire: (entryId: string) => void;
  onDismissAction: (entryId: string) => void;
}) {
  const isUser = entry.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center flex-shrink-0 mr-3 mt-0.5 shadow-sm">
          <BrainCircuit className="w-4 h-4 text-white" />
        </div>
      )}
      <div className={`max-w-[75%] ${isUser ? 'max-w-[60%]' : ''}`}>
        {isUser ? (
          <div className="px-4 py-3 bg-slate-900 text-white rounded-2xl rounded-tr-sm text-sm leading-relaxed">
            {entry.content}
          </div>
        ) : (
          <div>
            <div className="text-sm text-slate-800 leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1">
              <ReactMarkdown>{entry.content}</ReactMarkdown>
            </div>
            {entry.action?.type === 'delegate' && entry.actionState !== undefined && (
              <DelegateCard
                action={entry.action}
                state={entry.actionState}
                result={entry.actionResult}
                onDelegate={() => onDelegate(entry.id)}
              />
            )}
            {entry.action?.type === 'propose_hire' && entry.actionState !== undefined && (
              <HireCard
                action={entry.action}
                state={entry.actionState}
                result={entry.actionResult}
                onHire={() => onHire(entry.id)}
                onDismiss={() => onDismissAction(entry.id)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Suggested prompts ──────────────────────────────────────────────────────────

const SUGGESTIONS = [
  "What's the current state of my research team?",
  "Run an earnings analysis on NVDA",
  "Hire an agent to monitor my AAPL thesis",
  "What are the latest findings from my agents?",
  "Set up a weekly market pulse report",
];

// ── Main page ──────────────────────────────────────────────────────────────────

export default function CioPage() {
  const navigate = useNavigate();
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries]);

  const buildHistory = (): CioMessage[] =>
    entries.map(e => ({ role: e.role, content: e.content }));

  const send = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userEntry: ChatEntry = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
    };
    setEntries(prev => [...prev, userEntry]);
    setInput('');
    setIsLoading(true);

    try {
      const history = [...buildHistory(), { role: 'user' as const, content: text.trim() }];
      const res = await cioChat(history);

      const assistantEntry: ChatEntry = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: res.message,
        action: res.action ?? null,
        actionState: res.action ? 'idle' : undefined,
      };
      setEntries(prev => [...prev, assistantEntry]);
    } catch {
      setEntries(prev => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Something went wrong. Please try again.',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelegate = async (entryId: string) => {
    const entry = entries.find(e => e.id === entryId);
    if (!entry?.action?.agent_id) return;

    setEntries(prev =>
      prev.map(e => e.id === entryId ? { ...e, actionState: 'loading' } : e)
    );

    try {
      const result = await cioDelegate(entry.action.agent_id);
      setEntries(prev =>
        prev.map(e =>
          e.id === entryId
            ? { ...e, actionState: 'done', actionResult: `Run started — ID: ${result.run_id}. Check Inbox for results.` }
            : e
        )
      );
    } catch {
      setEntries(prev =>
        prev.map(e =>
          e.id === entryId
            ? { ...e, actionState: 'error', actionResult: 'Failed to dispatch agent run.' }
            : e
        )
      );
    }
  };

  const handleHire = async (entryId: string) => {
    const entry = entries.find(e => e.id === entryId);
    if (!entry?.action) return;

    setEntries(prev =>
      prev.map(e => e.id === entryId ? { ...e, actionState: 'loading' } : e)
    );

    try {
      const result = await cioHire(entry.action);
      setEntries(prev =>
        prev.map(e =>
          e.id === entryId
            ? {
                ...e,
                actionState: 'done',
                actionResult: `${result.name} hired and scheduled. View in Agents dashboard.`,
              }
            : e
        )
      );
    } catch {
      setEntries(prev =>
        prev.map(e =>
          e.id === entryId
            ? { ...e, actionState: 'error', actionResult: 'Failed to hire agent.' }
            : e
        )
      );
    }
  };

  const handleDismissAction = (entryId: string) => {
    setEntries(prev =>
      prev.map(e => e.id === entryId ? { ...e, action: null, actionState: undefined } : e)
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const isEmpty = entries.length === 0;

  return (
    <div className="flex flex-col h-screen bg-white" style={{ paddingLeft: '80px' }}>
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-100 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-sm">
            <BrainCircuit className="w-4.5 h-4.5 text-white" strokeWidth={2} />
          </div>
          <div>
            <h1 className="text-base font-semibold text-slate-900" style={{ letterSpacing: '-0.02em' }}>
              Chief Investment Officer
            </h1>
            <p className="text-xs text-slate-400 font-light">Your persistent investment advisor</p>
          </div>
        </div>
        <button
          onClick={() => navigate('/scheduled-agents')}
          className="text-xs text-slate-500 hover:text-slate-700 px-3 py-1.5 rounded-xl hover:bg-slate-50 transition-colors flex items-center gap-1.5"
        >
          View team →
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full px-8 pb-16">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg mb-6">
              <BrainCircuit className="w-8 h-8 text-white" strokeWidth={1.5} />
            </div>
            <h2 className="text-2xl font-semibold text-slate-900 mb-2" style={{ letterSpacing: '-0.03em' }}>
              Your CIO is ready
            </h2>
            <p className="text-slate-500 text-sm text-center max-w-sm mb-10 font-light leading-relaxed">
              Ask anything about your portfolio, delegate to your research team, or hire new agents.
            </p>
            <div className="flex flex-col gap-2 w-full max-w-md">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left px-4 py-3 rounded-2xl border border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-sm text-slate-700 transition-all duration-200 font-light"
                  style={{ letterSpacing: '-0.01em' }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto px-6 py-8">
            {entries.map(entry => (
              <MessageBubble
                key={entry.id}
                entry={entry}
                onDelegate={handleDelegate}
                onHire={handleHire}
                onDismissAction={handleDismissAction}
              />
            ))}
            {isLoading && (
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center flex-shrink-0 shadow-sm">
                  <BrainCircuit className="w-4 h-4 text-white" />
                </div>
                <div className="flex items-center gap-1.5 px-4 py-3 rounded-2xl bg-slate-50">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-slate-100 px-8 py-5">
        <div className="max-w-2xl mx-auto">
          <div className="relative flex items-end gap-3 p-3 rounded-2xl border border-slate-200 focus-within:border-slate-400 transition-colors bg-white shadow-sm">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask your CIO anything…"
              rows={1}
              className="flex-1 resize-none outline-none text-sm text-slate-900 placeholder-slate-400 leading-relaxed max-h-36 bg-transparent py-1 px-1 font-light"
              style={{ letterSpacing: '-0.01em' }}
              onInput={e => {
                const el = e.currentTarget;
                el.style.height = 'auto';
                el.style.height = `${el.scrollHeight}px`;
              }}
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || isLoading}
              className="flex-shrink-0 w-8 h-8 rounded-xl bg-slate-900 hover:bg-slate-700 disabled:bg-slate-200 text-white disabled:text-slate-400 flex items-center justify-center transition-all duration-200 mb-0.5"
            >
              {isLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
          <p className="text-center text-xs text-slate-400 mt-2 font-light">
            Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
}
