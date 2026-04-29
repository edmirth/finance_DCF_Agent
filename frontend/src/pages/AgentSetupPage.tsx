import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Check, Plus, X, Zap } from 'lucide-react';
import { createScheduledAgent, triggerAgentRun } from '../api';
import { AgentTemplate, ScheduleLabel } from '../types';

// ── Template definitions ──────────────────────────────────────────────────────

const TEMPLATES: {
  id: AgentTemplate;
  label: string;
  description: string;
  color: string;
  bg: string;
  letter: string;
  requiresTickers: boolean;
  instructionPlaceholder: string;
  instructionHint: string;
}[] = [
  {
    id: 'earnings_watcher',
    label: 'Earnings Watcher',
    description: 'Deep earnings analysis before and after each report. EPS surprises, guidance, management tone, analyst reactions.',
    color: '#F59E0B',
    bg: '#FEF3C7',
    letter: 'E',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. I own AAPL at $175 avg cost. Focus on iPhone unit demand, Services margin expansion, and any change in buyback pace. Flag if gross margins drop below 44%.',
    instructionHint: 'What do you own, at what price, and what would change your view?',
  },
  {
    id: 'market_pulse',
    label: 'Market Pulse',
    description: 'Daily macro brief — indices, sector rotation, VIX, Fed signals, and what it all means for your portfolio.',
    color: '#3B82F6',
    bg: '#DBEAFE',
    letter: 'M',
    requiresTickers: false,
    instructionPlaceholder: 'e.g. I run a long/short tech portfolio. Focus on rate sensitivity, AI infrastructure themes, and any FOMC language shifts. Alert me if VIX spikes above 25.',
    instructionHint: 'What macro factors matter most to your strategy?',
  },
  {
    id: 'thesis_guardian',
    label: 'Thesis Guardian',
    description: 'Write your investment thesis. The agent monitors news, earnings, and macro data to tell you if it\'s holding or breaking.',
    color: '#10B981',
    bg: '#D1FAE5',
    letter: 'T',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. My thesis on NVDA: AI training compute demand stays elevated through 2026 driven by hyperscaler capex. Bull case breaks if data center revenue growth decelerates meaningfully or AMD closes the performance gap.',
    instructionHint: 'State your thesis and what would invalidate it.',
  },
  {
    id: 'portfolio_heartbeat',
    label: 'Portfolio Heartbeat',
    description: 'Weekly health check across all your holdings — concentration risk, material changes, anything worth reviewing.',
    color: '#8B5CF6',
    bg: '#EDE9FE',
    letter: 'P',
    requiresTickers: true,
    instructionPlaceholder: 'e.g. My portfolio is 40% mega-cap tech, 30% small-cap industrials, 30% cash. Flag any single-stock move >8%, earnings misses, or macro events that hurt small-cap sentiment.',
    instructionHint: 'Describe your portfolio composition and what to watch for.',
  },
];

const SCHEDULES: { id: ScheduleLabel; label: string; sub: string }[] = [
  { id: 'daily_morning', label: 'Daily',         sub: 'Every morning at 7am' },
  { id: 'pre_market',    label: 'Pre-market',    sub: 'Weekdays at 6:30am' },
  { id: 'weekly_monday', label: 'Weekly',         sub: 'Every Monday at 7am' },
  { id: 'weekly_friday', label: 'End of week',   sub: 'Every Friday at 4pm' },
  { id: 'monthly',       label: 'Monthly',        sub: '1st of each month' },
];

// ── Shared pieces ─────────────────────────────────────────────────────────────

function ProgressBar({ step, total }: { step: number; total: number }) {
  return (
    <div className="flex items-center gap-1.5 mb-10">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-1 rounded-full transition-all duration-300 ${i < step ? 'bg-slate-900' : 'bg-slate-200'}`}
          style={{ flex: i < step ? 2 : 1 }}
        />
      ))}
      <span className="text-xs text-slate-400 ml-1 flex-shrink-0">{step}/{total}</span>
    </div>
  );
}

function TickerInput({ tickers, onChange }: { tickers: string[]; onChange: (t: string[]) => void }) {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim().toUpperCase().replace(/[^A-Z.]/g, '');
    if (v && !tickers.includes(v)) onChange([...tickers, v]);
    setInput('');
  };

  return (
    <div>
      <div className="flex gap-2 mb-2.5">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder="e.g. NVDA"
          className="flex-1 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:border-slate-400 bg-white font-mono uppercase placeholder:normal-case placeholder:font-sans"
        />
        <button
          onClick={add}
          className="px-3 py-2 bg-slate-900 text-white rounded-xl hover:bg-slate-800 transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
      {tickers.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tickers.map(t => (
            <span key={t} className="flex items-center gap-1 px-2.5 py-1 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold font-mono">
              {t}
              <button onClick={() => onChange(tickers.filter(x => x !== t))} className="text-slate-400 hover:text-red-500 transition-colors ml-0.5">
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Wizard state ──────────────────────────────────────────────────────────────

interface WizardState {
  template: AgentTemplate | null;
  name: string;
  tickers: string[];
  topics: string[];
  instruction: string;
  schedule_label: ScheduleLabel;
  delivery_email: string;
  delivery_inapp: boolean;
  run_after_create: boolean;
}

const DEFAULT: WizardState = {
  template: null,
  name: '',
  tickers: [],
  topics: [],
  instruction: '',
  schedule_label: 'weekly_monday',
  delivery_email: '',
  delivery_inapp: true,
  run_after_create: false,
};

// ── Step 1: Template ──────────────────────────────────────────────────────────

function Step1({ state, set }: { state: WizardState; set: (p: Partial<WizardState>) => void }) {
  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-1" style={{ letterSpacing: '-0.03em' }}>
        What type of agent?
      </h2>
      <p className="text-slate-500 text-sm mb-7">Pick the template that matches what you want monitored.</p>

      <div className="space-y-2.5">
        {TEMPLATES.map(t => {
          const selected = state.template === t.id;
          return (
            <button
              key={t.id}
              onClick={() => set({ template: t.id, name: state.name || t.label })}
              className={`w-full flex items-start gap-4 text-left px-4 py-4 rounded-2xl border-2 transition-all duration-150 ${
                selected ? 'border-slate-900 bg-white shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm flex-shrink-0 mt-0.5"
                style={{ background: t.bg, color: t.color }}
              >
                {t.letter}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm text-slate-900">{t.label}</span>
                  {selected && (
                    <span className="w-4 h-4 bg-slate-900 rounded-full flex items-center justify-center flex-shrink-0">
                      <Check className="w-2.5 h-2.5 text-white" />
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{t.description}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Step 2: Configure ─────────────────────────────────────────────────────────

function Step2({ state, set }: { state: WizardState; set: (p: Partial<WizardState>) => void }) {
  const tmpl = TEMPLATES.find(t => t.id === state.template)!;
  const instructionWords = state.instruction.trim().split(/\s+/).filter(Boolean).length;
  const instructionTooShort = state.instruction.trim().length > 0 && instructionWords < 10;

  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-1" style={{ letterSpacing: '-0.03em' }}>
        Configure the agent
      </h2>
      <p className="text-slate-500 text-sm mb-7">Name it, set its scope, and write your instruction.</p>

      <div className="space-y-5">
        {/* Name */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Agent name
          </label>
          <input
            value={state.name}
            onChange={e => set({ name: e.target.value })}
            placeholder={tmpl.label}
            className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:border-slate-400 bg-white"
          />
        </div>

        {/* Tickers */}
        {tmpl.requiresTickers && (
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
              Tickers to watch
            </label>
            <TickerInput tickers={state.tickers} onChange={tickers => set({ tickers })} />
          </div>
        )}

        {/* Topics */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-0.5">
            Focus themes
            <span className="text-slate-400 font-normal normal-case ml-1 tracking-normal">— optional</span>
          </label>
          <p className="text-xs text-slate-400 mb-1.5">Comma-separated topics the agent should prioritise.</p>
          <input
            value={state.topics.join(', ')}
            onChange={e => set({ topics: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
            placeholder="e.g. AI infrastructure, margins, guidance"
            className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:border-slate-400 bg-white"
          />
        </div>

        {/* Instruction */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-0.5">
            Your instruction
          </label>
          <p className="text-xs text-slate-400 mb-1.5">{tmpl.instructionHint}</p>
          <textarea
            value={state.instruction}
            onChange={e => set({ instruction: e.target.value })}
            placeholder={tmpl.instructionPlaceholder}
            rows={5}
            className={`w-full px-3.5 py-3 border rounded-2xl text-sm focus:outline-none bg-white resize-none leading-relaxed transition-colors ${
              instructionTooShort ? 'border-amber-300 focus:border-amber-400' : 'border-slate-200 focus:border-slate-400'
            }`}
          />
          <div className="flex items-center justify-between mt-1">
            {instructionTooShort ? (
              <p className="text-xs text-amber-600">Add more detail — the more specific, the better the findings.</p>
            ) : (
              <span />
            )}
            <p className="text-xs text-slate-400 ml-auto">{state.instruction.length} chars</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step 3: Schedule + delivery ───────────────────────────────────────────────

function Step3({ state, set }: { state: WizardState; set: (p: Partial<WizardState>) => void }) {
  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-1" style={{ letterSpacing: '-0.03em' }}>
        Schedule &amp; delivery
      </h2>
      <p className="text-slate-500 text-sm mb-7">When should it run, and how should findings reach you?</p>

      {/* Schedule */}
      <div className="mb-6">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Run schedule
        </label>
        <div className="grid grid-cols-1 gap-2">
          {SCHEDULES.map(s => {
            const selected = state.schedule_label === s.id;
            return (
              <button
                key={s.id}
                onClick={() => set({ schedule_label: s.id })}
                className={`flex items-center justify-between px-4 py-3 rounded-xl border-2 transition-all duration-150 text-left ${
                  selected ? 'border-slate-900 bg-white' : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div>
                  <span className="text-sm font-semibold text-slate-900">{s.label}</span>
                  <span className="text-xs text-slate-400 ml-2">{s.sub}</span>
                </div>
                {selected && (
                  <div className="w-4 h-4 bg-slate-900 rounded-full flex items-center justify-center flex-shrink-0">
                    <Check className="w-2.5 h-2.5 text-white" />
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Delivery */}
      <div className="space-y-4 mb-6">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Delivery
        </label>

        {/* In-app toggle */}
        <label className="flex items-center gap-3 cursor-pointer">
          <button
            type="button"
            onClick={() => set({ delivery_inapp: !state.delivery_inapp })}
            className={`w-10 h-5 rounded-full transition-colors duration-200 flex-shrink-0 ${state.delivery_inapp ? 'bg-slate-900' : 'bg-slate-200'}`}
          >
            <div className={`w-4 h-4 bg-white rounded-full m-0.5 shadow transition-transform duration-200 ${state.delivery_inapp ? 'translate-x-5' : 'translate-x-0'}`} />
          </button>
          <div>
            <p className="text-sm font-medium text-slate-800">In-app inbox</p>
            <p className="text-xs text-slate-400">Findings appear in your Inbox tab</p>
          </div>
        </label>

        {/* Email */}
        <div>
          <label className="block text-sm font-medium text-slate-800 mb-1">
            Email reports
            <span className="text-xs text-slate-400 font-normal ml-1">— optional, requires SMTP config</span>
          </label>
          <input
            type="email"
            value={state.delivery_email}
            onChange={e => set({ delivery_email: e.target.value })}
            placeholder="you@email.com"
            className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:border-slate-400 bg-white"
          />
        </div>
      </div>

      {/* Run now option */}
      <label className="flex items-center gap-3 cursor-pointer p-4 rounded-2xl border-2 border-slate-200 hover:border-slate-300 transition-colors">
        <button
          type="button"
          onClick={() => set({ run_after_create: !state.run_after_create })}
          className={`w-10 h-5 rounded-full transition-colors duration-200 flex-shrink-0 ${state.run_after_create ? 'bg-emerald-600' : 'bg-slate-200'}`}
        >
          <div className={`w-4 h-4 bg-white rounded-full m-0.5 shadow transition-transform duration-200 ${state.run_after_create ? 'translate-x-5' : 'translate-x-0'}`} />
        </button>
        <div>
          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-emerald-600" />
            <p className="text-sm font-medium text-slate-800">Run immediately after creating</p>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">Don't wait for the schedule — get your first findings now</p>
        </div>
      </label>
    </div>
  );
}

// ── Main wizard ───────────────────────────────────────────────────────────────

export default function AgentSetupPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [state, setState] = useState<WizardState>(DEFAULT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const set = (patch: Partial<WizardState>) => setState(prev => ({ ...prev, ...patch }));

  const canAdvance = (): boolean => {
    if (step === 1) return !!state.template;
    if (step === 2) {
      const tmpl = TEMPLATES.find(t => t.id === state.template)!;
      const hasName = !!state.name.trim();
      const hasTickers = !tmpl.requiresTickers || state.tickers.length > 0;
      return hasName && hasTickers;
    }
    return true;
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError('');
    try {
      const agent = await createScheduledAgent({
        name: state.name,
        template: state.template!,
        tickers: state.tickers,
        topics: state.topics,
        instruction: state.instruction,
        schedule_label: state.schedule_label,
        delivery_email: state.delivery_email || undefined,
        delivery_inapp: state.delivery_inapp,
      });

      if (state.run_after_create) {
        try { await triggerAgentRun(agent.id); } catch { /* non-fatal */ }
      }

      navigate(`/scheduled-agents/${agent.id}`);
    } catch {
      setError('Failed to create agent. Please try again.');
      setSubmitting(false);
    }
  };

  const TOTAL_STEPS = 3;

  return (
    <div className="min-h-screen bg-slate-50 pl-20 flex items-center justify-center py-12" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="w-full max-w-lg px-6">

        {/* Back / cancel */}
        <button
          onClick={() => step > 1 ? setStep(s => s - 1) : navigate('/scheduled-agents')}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-8 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          {step > 1 ? 'Back' : 'Cancel'}
        </button>

        {/* Card */}
        <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
          <ProgressBar step={step} total={TOTAL_STEPS} />

          {step === 1 && <Step1 state={state} set={set} />}
          {step === 2 && <Step2 state={state} set={set} />}
          {step === 3 && <Step3 state={state} set={set} />}

          {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

          {/* Footer nav */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-slate-100">
            {step > 1 ? (
              <button
                onClick={() => setStep(s => s - 1)}
                className="text-sm font-medium text-slate-500 hover:text-slate-800 transition-colors"
              >
                Back
              </button>
            ) : <div />}

            {step < TOTAL_STEPS ? (
              <button
                onClick={() => setStep(s => s + 1)}
                disabled={!canAdvance()}
                className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-semibold rounded-xl hover:bg-slate-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Continue <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 text-white text-sm font-semibold rounded-xl hover:bg-emerald-700 transition-colors disabled:opacity-50"
              >
                {submitting ? 'Creating…' : state.run_after_create ? 'Create & run' : 'Create agent'}
                {!submitting && (state.run_after_create ? <Zap className="w-4 h-4" /> : <Check className="w-4 h-4" />)}
              </button>
            )}
          </div>
        </div>

        {/* Step label */}
        <p className="text-center text-xs text-slate-400 mt-4">
          {step === 1 && 'Choose the type of monitoring you need'}
          {step === 2 && 'The more specific your instruction, the better the findings'}
          {step === 3 && 'You can change the schedule anytime from the agent page'}
        </p>
      </div>
    </div>
  );
}
