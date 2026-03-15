import { useState, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ThinkingStep } from '../types';

interface ReasoningDisplayProps {
  steps: ThinkingStep[];
  isStreaming?: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  onCopy?: () => void;
}

/* ── Text utilities ── */

/** Strip markdown formatting to plain text for reasoning display */
function cleanText(text: string): string {
  if (!text) return '';
  return text
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^[-*]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim();
}

/**
 * Inline replacements for tool names that appear inside LLM thought sentences.
 * These are short noun phrases that read naturally mid-sentence,
 * e.g. "I should use the recent news tool" instead of "I should use the get_recent_news tool".
 */
const TOOL_INLINE: Record<string, string> = {
  get_stock_info:              'company overview tool',
  get_financial_metrics:       'financial metrics tool',
  search_web:                  'web search',
  perform_dcf_analysis:        'DCF valuation model',
  get_market_parameters:       'market parameters tool',
  get_dcf_comparison:          'DCF comparison tool',
  perform_multiples_valuation: 'multiples valuation model',
  format_dcf_report:           'report formatter',
  analyze_industry:            'industry analysis tool',
  analyze_competitors:         'competitor analysis tool',
  analyze_moat:                'moat analysis tool',
  analyze_management:          'management analysis tool',
  calculate_portfolio_metrics: 'portfolio metrics tool',
  analyze_diversification:     'diversification tool',
  identify_tax_loss_harvesting:'tax-loss harvesting tool',
  get_market_overview:         'market overview tool',
  get_sector_rotation:         'sector rotation tool',
  classify_market_regime:      'market regime classifier',
  get_market_news:             'market news tool',
  screen_stocks:               'stock screener',
  get_value_stocks:            'value stock finder',
  get_growth_stocks:           'growth stock finder',
  get_dividend_stocks:         'dividend stock finder',
  get_quarterly_earnings:      'quarterly earnings tool',
  get_analyst_estimates:       'analyst estimates tool',
  get_earnings_surprises:      'earnings surprises tool',
  analyze_earnings_guidance:   'earnings guidance tool',
  compare_peer_earnings:       'peer earnings comparison tool',
  get_price_targets:           'price targets tool',
  get_analyst_ratings:         'analyst ratings tool',
  get_earnings_call_insights:  'earnings call tool',
  get_sec_filings:             'SEC filings tool',
  analyze_sec_filing:          'SEC filing analyzer',
  get_sec_financials:          'SEC financials tool',
  get_quick_data:              'quick data tool',
  get_date_context:            'date context tool',
  calculate:                   'calculator',
  get_recent_news:             'recent news tool',
  compare_companies:           'company comparison tool',
  get_revenue_segments:        'revenue segments tool',
  compare_multiple_companies:  'multi-company comparison tool',
  get_company_context:         'company context tool',
};

/**
 * Replace any raw snake_case tool names embedded in LLM thought text with
 * natural inline phrases, so "I should use the get_recent_news tool" becomes
 * "I should use the recent news tool".
 */
function humanizeThought(text: string): string {
  if (!text) return text;
  let result = text;
  for (const [toolName, phrase] of Object.entries(TOOL_INLINE)) {
    // Match the tool name as a whole word (not part of a larger identifier)
    result = result.replace(new RegExp(`\\b${toolName}\\b`, 'g'), phrase);
  }
  return result;
}

/**
 * Human-readable labels for every tool the agents can call.
 * Used by cleanLabel() to produce natural sentences instead of snake_case names.
 */
const TOOL_LABELS: Record<string, string> = {
  // DCF / valuation
  get_stock_info:              'Looking up company overview',
  get_financial_metrics:       'Pulling historical financials',
  search_web:                  'Searching the web for current data',
  perform_dcf_analysis:        'Running DCF valuation model',
  get_market_parameters:       'Fetching market parameters',
  get_dcf_comparison:          'Comparing DCF scenarios',
  perform_multiples_valuation: 'Running multiples-based valuation',
  format_dcf_report:           'Formatting valuation report',
  // Equity analyst
  analyze_industry:    'Analyzing industry dynamics',
  analyze_competitors: 'Mapping the competitive landscape',
  analyze_moat:        'Evaluating the competitive moat',
  analyze_management:  'Assessing management quality',
  // Portfolio
  calculate_portfolio_metrics:   'Calculating portfolio performance',
  analyze_diversification:       'Reviewing portfolio diversification',
  identify_tax_loss_harvesting:  'Scanning for tax-loss opportunities',
  // Market
  get_market_overview:     'Pulling market overview',
  get_sector_rotation:     'Analyzing sector rotation',
  classify_market_regime:  'Classifying market regime',
  get_market_news:         'Fetching market news',
  screen_stocks:           'Screening stocks by criteria',
  get_value_stocks:        'Identifying value opportunities',
  get_growth_stocks:       'Identifying growth candidates',
  get_dividend_stocks:     'Finding dividend opportunities',
  // Earnings
  get_quarterly_earnings:      'Pulling quarterly earnings history',
  get_analyst_estimates:       'Fetching analyst consensus estimates',
  get_earnings_surprises:      'Reviewing earnings surprises',
  analyze_earnings_guidance:   'Reviewing management guidance',
  compare_peer_earnings:       'Comparing peer earnings results',
  get_price_targets:           'Fetching analyst price targets',
  get_analyst_ratings:         'Checking analyst rating changes',
  get_earnings_call_insights:  'Analyzing earnings call transcript',
  // SEC / EDGAR
  get_sec_filings:    'Fetching SEC EDGAR filings',
  analyze_sec_filing: 'Reading SEC filing content',
  get_sec_financials: 'Pulling SEC XBRL financials',
  // Research assistant
  get_quick_data:             'Fetching quick financial snapshot',
  get_date_context:           'Checking time period context',
  calculate:                  'Running calculation',
  get_recent_news:            'Fetching recent news',
  compare_companies:          'Comparing companies',
  get_revenue_segments:       'Analyzing revenue breakdown',
  compare_multiple_companies: 'Running multi-company comparison',
  // Context / misc
  get_company_context: 'Loading company context',
};

/** Convert snake_case to Title Case as a last-resort fallback */
function snakeToNatural(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Return a natural-language label for a tool event, no matter how it arrives */
export function cleanLabel(text: string): string {
  if (!text) return 'Processing';

  // 1. Direct exact-match against known tool names (backend may send raw name)
  if (TOOL_LABELS[text.trim()]) return TOOL_LABELS[text.trim()];

  // 2. Extract raw tool name from "Using get_stock_info" or "🔍 Using get_stock_info"
  const usingMatch = text.match(/Using\s+([a-z][a-z_]+)/);
  if (usingMatch) {
    const toolName = usingMatch[1];
    return TOOL_LABELS[toolName] ?? snakeToNatural(toolName);
  }

  // 3. Strip [Action] bracket prefix that the backend adds (e.g. "[Getting] company info")
  //    and return just the description part, capitalized.
  const bracketMatch = text.match(/^\[([^\]]+)\]\s+(.+)/);
  if (bracketMatch) {
    const description = bracketMatch[2].trim();
    return description.charAt(0).toUpperCase() + description.slice(1);
  }

  // 4. Strip any leading emojis and return what remains
  const stripped = text
    .replace(/^[\u{1F300}-\u{1FAD6}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FEFF}\u{1F900}-\u{1F9FF}\u{200D}\u{20E3}\u{FE0F}\u{E0020}-\u{E007F}]+\s*/gu, '')
    .trim();

  // 5. If what remains looks like a raw snake_case tool name, humanize it
  if (/^[a-z][a-z_]+$/.test(stripped)) return snakeToNatural(stripped);

  return stripped || 'Processing';
}

/** Extract ticker/query tags from tool input strings */
function extractTags(input: string | undefined): string[] {
  if (!input) return [];
  const tags: string[] = [];
  const tickerMatches = input.match(/ticker[s]?\s*=\s*([A-Z]{1,5})/gi);
  if (tickerMatches) {
    tickerMatches.forEach(m => {
      const val = m.split('=')[1]?.trim().toUpperCase();
      if (val) tags.push(val);
    });
  }
  const queryMatch = input.match(/query\s*=\s*(.+?)(?:,|$)/i);
  if (queryMatch?.[1]) {
    const q = queryMatch[1].trim().replace(/^['"]|['"]$/g, '');
    if (q.length > 3 && q.length < 60) tags.push(q);
  }
  return [...new Set(tags)].slice(0, 6);
}

/**
 * Guard: detect content that looks like a final response rather than reasoning.
 * If the text contains heavy markdown formatting or numbered analysis points,
 * it's likely the agent's answer leaking into reasoning events.
 */
function looksLikeFinalAnswer(text: string): boolean {
  if (!text || text.length < 80) return false;
  const markdownHeavy = (text.match(/\*\*/g) || []).length >= 4;
  const manyNumberedLines = (text.match(/^\d+\.\s/gm) || []).length >= 4;
  const hasHeadings = (text.match(/^#{1,3}\s/gm) || []).length >= 2;
  const hasSections = (text.match(/\*[A-Z][a-z]+.*:\*\*/gm) || []).length >= 3;
  return (markdownHeavy && manyNumberedLines) || hasHeadings || hasSections;
}

/** Truncate text to a max length with ellipsis */
function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).replace(/\s+\S*$/, '') + '...';
}

/* ── Source type colors ── */
const SOURCE_COLORS: Record<string, string> = {
  financial_data: '#3B82F6',
  web_search: '#10B981',
  news: '#F59E0B',
  calculation: '#8B5CF6',
};

/* ── Timeline model ── */

type TimelineItem =
  | { kind: 'thinking'; text: string; isLive: boolean }
  | { kind: 'phase'; label: string }
  | { kind: 'activity'; label: string; tags: string[]; isActive: boolean }
  | { kind: 'search_group'; queries: string[] }
  | { kind: 'source_group'; sources: Array<{ title: string; domain: string; type?: string }> }
  | { kind: 'plan'; planSteps: string[] }
  | { kind: 'reflection'; text: string };

function buildTimeline(steps: ThinkingStep[], isStreaming: boolean): TimelineItem[] {
  const timeline: TimelineItem[] = [];
  let searchBuf: string[] = [];
  let sourceBuf: Array<{ title: string; domain: string; type?: string }> = [];

  const flushSearch = () => {
    if (searchBuf.length > 0) {
      timeline.push({ kind: 'search_group', queries: [...searchBuf] });
      searchBuf = [];
    }
  };
  const flushSources = () => {
    if (sourceBuf.length > 0) {
      timeline.push({ kind: 'source_group', sources: [...sourceBuf] });
      sourceBuf = [];
    }
  };

  steps.forEach((step, i) => {
    switch (step.type) {
      case 'thinking_start':
        flushSearch(); flushSources();
        if (step.thinkingText && step.thinkingText.length > 0 && !looksLikeFinalAnswer(step.thinkingText)) {
          timeline.push({ kind: 'thinking', text: truncate(humanizeThought(cleanText(step.thinkingText)), 300), isLive: !!step.isStreaming });
        }
        break;
      case 'agent_thought':
        flushSearch(); flushSources();
        if (step.content && step.content.length > 5 && !looksLikeFinalAnswer(step.content)) {
          timeline.push({ kind: 'thinking', text: truncate(humanizeThought(cleanText(step.content)), 300), isLive: false });
        }
        break;
      case 'phase_start':
        flushSearch(); flushSources();
        if (step.content) timeline.push({ kind: 'phase', label: step.content });
        break;
      case 'thought': {
        if (!step.content) break;
        // Skip thought if the next step is a tool (they duplicate)
        if (steps[i + 1]?.type === 'tool') break;
        // Guard against final answer leaking
        if (looksLikeFinalAnswer(step.content)) break;
        flushSearch(); flushSources();
        timeline.push({ kind: 'activity', label: cleanLabel(step.content), tags: [], isActive: false });
        break;
      }
      case 'tool':
        flushSearch(); flushSources();
        timeline.push({
          kind: 'activity',
          label: cleanLabel(step.tool || step.content || 'Processing'),
          tags: extractTags(step.input),
          isActive: false,
        });
        break;
      case 'search_query':
        flushSources();
        if (step.searchQuery || step.content) searchBuf.push(step.searchQuery || step.content || '');
        break;
      case 'source_review':
        flushSearch();
        if (step.source) sourceBuf.push({ title: step.source.title, domain: step.source.domain, type: step.source.type });
        break;
      case 'plan_created':
      case 'plan_updated':
        flushSearch(); flushSources();
        // Cap plan steps at 8 to avoid rendering full analyses
        if (step.plan?.length) {
          timeline.push({ kind: 'plan', planSteps: step.plan.slice(0, 8) });
        }
        break;
      case 'reflection':
        flushSearch(); flushSources();
        if (step.content && !looksLikeFinalAnswer(step.content)) {
          timeline.push({ kind: 'reflection', text: truncate(humanizeThought(cleanText(step.content)), 200) });
        }
        break;
      case 'reflection_start':
        flushSearch(); flushSources();
        if (step.reflectionText && !looksLikeFinalAnswer(step.reflectionText)) {
          timeline.push({ kind: 'reflection', text: truncate(humanizeThought(cleanText(step.reflectionText)), 200) });
        }
        break;
    }
  });

  flushSearch();
  flushSources();

  // Mark the last activity as active during streaming
  if (isStreaming) {
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (timeline[i].kind === 'activity') {
        (timeline[i] as any).isActive = true;
        break;
      }
    }
  }

  return timeline;
}

/* ── Animations ── */

const itemVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, delay: i * 0.04, ease: [0.25, 0.1, 0.25, 1] as const },
  }),
};

const collapseTransition = { duration: 0.3, ease: [0.16, 1, 0.3, 1] as const };

/* ── Component ── */

function ReasoningDisplay({ steps, isStreaming, isCollapsed = false, onToggleCollapse, onCopy }: ReasoningDisplayProps) {
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  useEffect(() => {
    if (isStreaming) {
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isStreaming]);

  if (steps.length === 0) return null;

  const timeline = buildTimeline(steps, !!isStreaming);
  const fmt = (s: number) => s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;

  const handleCopy = () => {
    if (onCopy) onCopy();
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rd-root">
      {/* ── Header bar ── */}
      <div className="rd-header-bar">
        <button onClick={onToggleCollapse} className="rd-toggle" aria-expanded={!isCollapsed}>
          {/* Animated chevron */}
          <svg
            width="16" height="16" viewBox="0 0 16 16" fill="none"
            className="rd-chevron"
            style={{ transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}
          >
            <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>

          {/* Status indicator */}
          {isStreaming && <span className="rd-pulse" />}

          <span className="rd-header-label">
            {isStreaming ? 'Reasoning' : `Reasoned for ${fmt(elapsed)}`}
          </span>
        </button>

        {/* Copy button (only when not streaming) */}
        {!isStreaming && onCopy && (
          <button onClick={handleCopy} className="rd-copy-btn" title="Copy reasoning">
            {copied ? (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 7.5L6 10.5L11 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M9.5 4.5V3a1.5 1.5 0 0 0-1.5-1.5H3A1.5 1.5 0 0 0 1.5 3v5A1.5 1.5 0 0 0 3 9.5h1.5" stroke="currentColor" strokeWidth="1.2"/>
              </svg>
            )}
          </button>
        )}
      </div>

      {/* ── Collapsible timeline ── */}
      <AnimatePresence initial={false}>
        {!isCollapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={collapseTransition}
            className="rd-collapse-wrapper"
          >
            <div className="rd-timeline">
              {/* Vertical line */}
              <div className="rd-line" />

              {timeline.map((item, idx) => {
                const hasDot = item.kind === 'thinking' || item.kind === 'activity';
                const isLargeDot = item.kind === 'thinking';
                const isActiveDot = item.kind === 'activity' && (item as any).isActive && isStreaming;

                return (
                  <motion.div
                    key={idx}
                    custom={idx}
                    initial="hidden"
                    animate="visible"
                    variants={itemVariants}
                    className="rd-item"
                  >
                    {/* Dot */}
                    {hasDot && (
                      <div className={`rd-dot ${isLargeDot ? 'rd-dot--lg' : 'rd-dot--sm'} ${isActiveDot ? 'rd-dot--active' : ''}`} />
                    )}

                    {/* THINKING */}
                    {item.kind === 'thinking' && (
                      <p className="rd-thinking">
                        {item.text}
                        {item.isLive && <span className="rd-cursor" />}
                      </p>
                    )}

                    {/* PHASE */}
                    {item.kind === 'phase' && (
                      <span className="rd-phase">{item.label}</span>
                    )}

                    {/* ACTIVITY */}
                    {item.kind === 'activity' && (
                      <div>
                        <p className={`rd-activity ${item.isActive ? 'rd-activity--live' : ''}`}>
                          {item.label}
                        </p>
                        {item.tags.length > 0 && (
                          <div className="rd-tags">
                            {item.tags.map((tag, ti) => (
                              <span key={ti} className="rd-tag">{tag}</span>
                            ))}
                          </div>
                        )}
                        {item.isActive && isStreaming && item.tags.length === 0 && (
                          <div className="rd-loading-dots">
                            <span className="loading-dot" />
                            <span className="loading-dot" />
                            <span className="loading-dot" />
                          </div>
                        )}
                      </div>
                    )}

                    {/* SEARCH GROUP */}
                    {item.kind === 'search_group' && (
                      <div>
                        <span className="rd-phase">Searching</span>
                        <div className="rd-tags" style={{ marginTop: 6 }}>
                          {item.queries.map((q, qi) => (
                            <span key={qi} className="rd-search-chip">
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="rd-search-icon">
                                <circle cx="5.2" cy="5.2" r="3.5" stroke="currentColor" strokeWidth="1.3"/>
                                <line x1="7.8" y1="7.8" x2="10.5" y2="10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                              </svg>
                              <span>{q}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* SOURCE GROUP */}
                    {item.kind === 'source_group' && (
                      <div>
                        <span className="rd-phase">Reviewing sources</span>
                        <div className="rd-source-card">
                          {item.sources.map((src, si) => (
                            <div key={si} className="rd-source-row">
                              <div className="rd-source-left">
                                <div
                                  className="rd-source-dot"
                                  style={{ background: SOURCE_COLORS[src.type || 'web_search'] || '#9CA3AF' }}
                                />
                                <span className="rd-source-title">{src.title}</span>
                              </div>
                              <span className="rd-source-domain">{src.domain}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* PLAN */}
                    {item.kind === 'plan' && (
                      <div className="rd-plan">
                        {item.planSteps.map((s, si) => (
                          <div key={si} className="rd-plan-step">
                            <span className="rd-plan-num">{si + 1}</span>
                            <span className="rd-plan-text">{truncate(cleanText(s), 120)}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* REFLECTION */}
                    {item.kind === 'reflection' && (
                      <p className="rd-reflection">{item.text}</p>
                    )}
                  </motion.div>
                );
              })}

              {/* Empty streaming placeholder */}
              {isStreaming && timeline.length === 0 && (
                <div className="rd-item">
                  <div className="rd-dot rd-dot--lg rd-dot--active" />
                  <span className="rd-activity rd-activity--live">Analyzing...</span>
                </div>
              )}

              {/* Completion marker */}
              {!isStreaming && steps.length > 0 && (
                <motion.div
                  className="rd-item"
                  initial={{ opacity: 0, scale: 0.92 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] as const }}
                >
                  <div className="rd-dot rd-dot--done">
                    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                      <path d="M1.5 4L3.5 6L6.5 2" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <span className="rd-done">Analysis complete</span>
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default ReasoningDisplay;
