import { useState, useRef, useEffect } from 'react';
import {
  Send, Loader2, BrainCircuit, Play, UserPlus,
  ChevronDown, ChevronUp, X, Zap,
} from 'lucide-react';
import { cioChat, cioDelegate, cioHire, CioMessage, CioAction } from '../api';

// ── Persistence ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'cio_conversation_v1';

interface ChatEntry {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: CioAction | null;
  actionState?: 'idle' | 'loading' | 'done' | 'error';
  actionResult?: string;
}

function loadHistory(): ChatEntry[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
}
function saveHistory(entries: ChatEntry[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-60)));
}

// ── Labels ────────────────────────────────────────────────────────────────────

const TEMPLATE_LABELS: Record<string, string> = {
  earnings_watcher: 'Earnings Watcher', market_pulse: 'Market Pulse',
  thesis_guardian: 'Thesis Guardian', portfolio_heartbeat: 'Portfolio Heartbeat',
};
const SCHEDULE_LABELS: Record<string, string> = {
  daily_morning: 'Daily 7am', pre_market: 'Weekdays 6:30am',
  weekly_monday: 'Every Monday', weekly_friday: 'Every Friday', monthly: 'Monthly',
};

// ── Inline action cards ───────────────────────────────────────────────────────

function DelegateCard({ action, state, result, onRun }: {
  action: CioAction; state: 'idle' | 'loading' | 'done' | 'error';
  result?: string; onRun: () => void;
}) {
  return (
    <div className="mt-2.5 flex items-center gap-3 px-3 py-2.5 rounded-xl bg-slate-50 border border-slate-200">
      <Play className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700 truncate">{action.agent_name}</p>
        {action.reason && <p className="text-xs text-slate-400 truncate mt-0.5">{action.reason}</p>}
        {result && <p className="text-xs text-slate-400 mt-0.5">{result}</p>}
      </div>
      {state === 'idle' && (
        <button onClick={onRun} className="flex-shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors">
          <Zap className="w-2.5 h-2.5" /> Run
        </button>
      )}
      {state === 'loading' && <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400 flex-shrink-0" />}
      {state === 'done' && <span className="flex-shrink-0 text-xs font-medium text-emerald-600">Dispatched</span>}
      {state === 'error' && <span className="flex-shrink-0 text-xs text-red-500">Failed</span>}
    </div>
  );
}

function HireCard({ action, state, result, onHire, onDismiss }: {
  action: CioAction; state: 'idle' | 'loading' | 'done' | 'error';
  result?: string; onHire: () => void; onDismiss: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2.5 px-3 py-2.5 rounded-xl bg-emerald-50 border border-emerald-200">
      <div className="flex items-start gap-3">
        <UserPlus className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-xs text-emerald-600 font-medium mb-0.5">Proposal</p>
          <p className="text-sm font-medium text-slate-800">{action.name}</p>
          {action.description && <p className="text-xs text-slate-500 mt-0.5">{action.description}</p>}
          <div className="flex flex-wrap gap-1 mt-1.5">
            {action.template && (
              <span className="text-xs px-1.5 py-0.5 bg-white border border-emerald-200 text-emerald-700 rounded-md font-medium">
                {TEMPLATE_LABELS[action.template] || action.template}
              </span>
            )}
            {action.schedule_label && (
              <span className="text-xs px-1.5 py-0.5 bg-white border border-slate-200 text-slate-500 rounded-md">
                {SCHEDULE_LABELS[action.schedule_label] || action.schedule_label}
              </span>
            )}
            {(action.tickers || []).map(t => (
              <span key={t} className="text-xs px-1.5 py-0.5 bg-white border border-slate-200 text-slate-700 rounded-md font-mono font-semibold">{t}</span>
            ))}
          </div>
          {action.instruction && (
            <button onClick={() => setOpen(v => !v)} className="flex items-center gap-1 mt-1.5 text-xs text-slate-400 hover:text-slate-600 transition-colors">
              {open ? <ChevronUp className="w-2.5 h-2.5" /> : <ChevronDown className="w-2.5 h-2.5" />}
              {open ? 'Hide' : 'View'} instructions
            </button>
          )}
          {open && action.instruction && (
            <p className="mt-1.5 text-xs text-slate-600 leading-relaxed bg-white rounded-lg p-2.5 border border-emerald-100">{action.instruction}</p>
          )}
          {result && <p className="text-xs text-slate-400 mt-1.5">{result}</p>}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {state === 'idle' && (
            <>
              <button onClick={onDismiss} className="p-1 rounded-lg hover:bg-emerald-100 text-slate-400 hover:text-slate-500 transition-colors"><X className="w-3 h-3" /></button>
              <button onClick={onHire} className="flex items-center gap-1 px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors">
                <UserPlus className="w-2.5 h-2.5" /> Hire
              </button>
            </>
          )}
          {state === 'loading' && <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-500" />}
          {state === 'done' && <span className="text-xs font-medium text-emerald-600">Hired ✓</span>}
          {state === 'error' && <span className="text-xs text-red-500">Failed</span>}
        </div>
      </div>
    </div>
  );
}

// ── Message row ───────────────────────────────────────────────────────────────

function MessageRow({ entry, onDelegate, onHire, onDismiss }: {
  entry: ChatEntry;
  onDelegate: (id: string) => void;
  onHire: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const isUser = entry.role === 'user';
  return (
    <div className={`flex gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-5 h-5 rounded-md bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center flex-shrink-0 mt-0.5">
          <BrainCircuit className="w-2.5 h-2.5 text-white" />
        </div>
      )}
      <div className={isUser ? 'max-w-[70%]' : 'flex-1'}>
        {isUser ? (
          <div className="inline-block px-3.5 py-2 bg-slate-900 text-white rounded-2xl rounded-tr-sm text-sm leading-relaxed">
            {entry.content}
          </div>
        ) : (
          <div>
            <p className="text-sm text-slate-700 leading-relaxed">{entry.content}</p>
            {entry.action?.type === 'delegate' && entry.actionState !== undefined && (
              <DelegateCard action={entry.action} state={entry.actionState} result={entry.actionResult} onRun={() => onDelegate(entry.id)} />
            )}
            {entry.action?.type === 'propose_hire' && entry.actionState !== undefined && (
              <HireCard action={entry.action} state={entry.actionState} result={entry.actionResult} onHire={() => onHire(entry.id)} onDismiss={() => onDismiss(entry.id)} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Suggestions ───────────────────────────────────────────────────────────────

const SUGGESTIONS = [
  "What did my agents find this week?",
  "Run my earnings watcher now",
  "Hire an agent to watch NVDA",
  "Brief me on my team",
];

// ── Main card ─────────────────────────────────────────────────────────────────

export default function CioCard({ onAgentHired }: { onAgentHired?: () => void }) {
  const [entries, setEntries] = useState<ChatEntry[]>(() => loadHistory());
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { saveHistory(entries); }, [entries]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [entries]);

  const send = async (text: string) => {
    if (!text.trim() || isLoading) return;
    const userEntry: ChatEntry = { id: crypto.randomUUID(), role: 'user', content: text.trim() };
    setEntries(prev => [...prev, userEntry]);
    setInput('');
    setIsLoading(true);
    if (inputRef.current) inputRef.current.style.height = 'auto';

    try {
      const history: CioMessage[] = [
        ...entries.map(e => ({ role: e.role, content: e.content })),
        { role: 'user', content: text.trim() },
      ];
      const res = await cioChat(history);
      setEntries(prev => [...prev, {
        id: crypto.randomUUID(), role: 'assistant', content: res.message,
        action: res.action ?? null, actionState: res.action ? 'idle' : undefined,
      }]);
    } catch {
      setEntries(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: 'Something went wrong. Please try again.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelegate = async (entryId: string) => {
    const entry = entries.find(e => e.id === entryId);
    if (!entry?.action?.agent_id) return;
    setEntries(prev => prev.map(e => e.id === entryId ? { ...e, actionState: 'loading' as const } : e));
    try {
      const result = await cioDelegate(entry.action.agent_id);
      setEntries(prev => prev.map(e => e.id === entryId
        ? { ...e, actionState: 'done' as const, actionResult: `Dispatched · check Inbox (run ${result.run_id.slice(0, 8)}…)` } : e));
    } catch {
      setEntries(prev => prev.map(e => e.id === entryId ? { ...e, actionState: 'error' as const } : e));
    }
  };

  const handleHire = async (entryId: string) => {
    const entry = entries.find(e => e.id === entryId);
    if (!entry?.action) return;
    setEntries(prev => prev.map(e => e.id === entryId ? { ...e, actionState: 'loading' as const } : e));
    try {
      const result = await cioHire(entry.action);
      setEntries(prev => prev.map(e => e.id === entryId
        ? { ...e, actionState: 'done' as const, actionResult: `${result.name} hired and scheduled.` } : e));
      onAgentHired?.();
    } catch {
      setEntries(prev => prev.map(e => e.id === entryId ? { ...e, actionState: 'error' as const } : e));
    }
  };

  const handleDismiss = (entryId: string) => {
    setEntries(prev => prev.map(e => e.id === entryId ? { ...e, action: null, actionState: undefined } : e));
  };

  const isEmpty = entries.length === 0;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden mb-8">

      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-sm">
            <BrainCircuit className="w-3.5 h-3.5 text-white" strokeWidth={2} />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold text-slate-900" style={{ letterSpacing: '-0.01em' }}>CIO</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
            </div>
            <p className="text-xs text-slate-400" style={{ fontSize: '0.65rem' }}>Chief Investment Officer · knows your team</p>
          </div>
        </div>
        {entries.length > 0 && (
          <button
            onClick={() => { if (confirm('Clear conversation?')) setEntries([]); }}
            className="text-xs text-slate-400 hover:text-slate-600 transition-colors px-2 py-1 rounded-lg hover:bg-slate-50"
          >
            Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <div
        className="px-5 py-4 space-y-4 overflow-y-auto"
        style={{ maxHeight: isEmpty ? undefined : '320px' }}
      >
        {isEmpty ? (
          <div>
            <p className="text-xs text-slate-400 mb-2.5">Ask anything — get a briefing, delegate a task, or hire a new agent:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-xs px-3 py-1.5 rounded-xl border border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-600 transition-all duration-150"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {entries.map(entry => (
              <MessageRow
                key={entry.id}
                entry={entry}
                onDelegate={handleDelegate}
                onHire={handleHire}
                onDismiss={handleDismiss}
              />
            ))}
            {isLoading && (
              <div className="flex items-center gap-2.5">
                <div className="w-5 h-5 rounded-md bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center flex-shrink-0">
                  <BrainCircuit className="w-2.5 h-2.5 text-white" />
                </div>
                <div className="flex items-center gap-1 px-3 py-2 rounded-xl bg-slate-50">
                  <span className="w-1 h-1 rounded-full bg-slate-300 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1 h-1 rounded-full bg-slate-300 animate-bounce" style={{ animationDelay: '120ms' }} />
                  <span className="w-1 h-1 rounded-full bg-slate-300 animate-bounce" style={{ animationDelay: '240ms' }} />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="px-5 py-3 border-t border-slate-100 bg-slate-50">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
            placeholder="Ask your CIO…"
            rows={1}
            className="flex-1 resize-none outline-none text-sm text-slate-800 placeholder-slate-400 leading-relaxed bg-transparent max-h-24 py-0.5"
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
            className="flex-shrink-0 w-7 h-7 rounded-lg bg-slate-900 hover:bg-slate-700 disabled:bg-slate-200 text-white disabled:text-slate-400 flex items-center justify-center transition-colors mb-0.5"
          >
            {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
          </button>
        </div>
      </div>
    </div>
  );
}
