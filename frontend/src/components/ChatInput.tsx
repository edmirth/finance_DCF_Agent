import { KeyboardEvent, useState, useRef, useEffect } from 'react';
import { Loader2, Zap, Paperclip, ChevronDown, BarChart3, TrendingUp, Search, Globe, Briefcase, DollarSign, AlertTriangle, Sparkles } from 'lucide-react';
import { Agent } from '../types';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  isLoading: boolean;
  placeholder?: string;
  agents?: Agent[];
  selectedAgent?: Agent;
  onSelectAgent?: (agent: Agent) => void;
  onQuickPromptSend?: (text: string) => void;
  onPaperclipClick?: () => void;
  attachedFileCount?: number;
}

const quickPrompts = [
  { icon: TrendingUp, label: 'Fair Value Analysis', prompt: 'What\'s the fair value and investment rating for AAPL?' },
  { icon: DollarSign, label: 'Earnings Deep Dive', prompt: 'Analyze the latest earnings for NVDA' },
  { icon: Globe, label: 'Market Regime', prompt: 'What\'s the current market regime and sector rotation?' },
  { icon: BarChart3, label: 'Stock Comparison', prompt: 'Compare AAPL vs MSFT: which is the better investment?' },
  { icon: AlertTriangle, label: 'Risk Assessment', prompt: 'What are the biggest risks of investing in TSLA?' },
];

const agentIcons: Record<string, any> = {
  auto: Sparkles,
  analyst: TrendingUp,
  research: Search,
  market: Globe,
  portfolio: Briefcase,
  earnings: DollarSign,
};

const agentLabels: Record<string, string> = {
  auto: 'Auto',
  research: 'Finance Q&A',
  analyst: 'Analyst',
  market: 'Market',
  portfolio: 'Portfolio',
  earnings: 'Earnings',
};

const agentDescriptions: Record<string, string> = {
  auto: 'Picks the right agent for you',
  research: 'Q&A, company info, financial data',
  analyst: 'Deep equity analysis, valuation',
  market: 'Market conditions, macro trends',
  earnings: 'Earnings trends, estimates, calls',
};

function ChatInput({ value, onChange, onSend, isLoading, placeholder, agents, selectedAgent, onSelectAgent, onQuickPromptSend, onPaperclipClick, attachedFileCount }: ChatInputProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [showQuickPrompts, setShowQuickPrompts] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const quickPromptsRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  // Auto-resize textarea
  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 128) + 'px';
    }
  };

  // Close dropdown on click outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
      if (quickPromptsRef.current && !quickPromptsRef.current.contains(e.target as Node)) {
        setShowQuickPrompts(false);
      }
    };
    if (showDropdown || showQuickPrompts) {
      document.addEventListener('mousedown', handleClick);
    }
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showDropdown, showQuickPrompts]);

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <div className="rogo-input-box">
      {/* Textarea area */}
      <div className="input-area">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            handleInput();
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Ask Phronesis anything..."}
          rows={1}
          disabled={isLoading}
        />
      </div>

      {/* Bottom toolbar */}
      <div className="toolbar">
        {/* Left icons */}
        <div className="rogo-toolbar-left">
          <div className="relative" ref={quickPromptsRef}>
            <button
              className={`rogo-icon-btn ${showQuickPrompts ? 'active' : ''}`}
              title="Quick prompts"
              disabled={isLoading}
              onClick={() => setShowQuickPrompts(!showQuickPrompts)}
            >
              <Zap className="w-4 h-4" />
            </button>

            {showQuickPrompts && (
              <div className="quick-prompts-popover">
                <div className="quick-prompts-header">Quick Prompts</div>
                {quickPrompts.map(({ icon: Icon, label, prompt }) => (
                  <button
                    key={label}
                    className="quick-prompt-item"
                    onClick={() => {
                      if (onQuickPromptSend) {
                        onQuickPromptSend(prompt);
                      } else {
                        onChange(prompt);
                      }
                      setShowQuickPrompts(false);
                    }}
                  >
                    <div className="quick-prompt-icon">
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <div className="quick-prompt-text">
                      <span className="quick-prompt-label">{label}</span>
                      <span className="quick-prompt-preview">{prompt}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            className="rogo-icon-btn"
            title="Attach file"
            disabled={isLoading}
            onClick={onPaperclipClick}
            style={{ position: 'relative' }}
          >
            <Paperclip className="w-4 h-4" />
            {(attachedFileCount ?? 0) > 0 && (
              <span
                style={{
                  position: 'absolute',
                  top: 2,
                  right: 2,
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: '#10B981',
                }}
              />
            )}
          </button>
        </div>

        {/* Right side: agent selector + send */}
        <div className="rogo-toolbar-right">
          {/* Agent selector dropdown */}
          {agents && selectedAgent && onSelectAgent && (
            <div className="relative" ref={dropdownRef}>
              <button
                className={`agent-selector ${selectedAgent.id === 'auto' ? 'agent-selector-auto' : ''}`}
                onClick={() => setShowDropdown(!showDropdown)}
                disabled={isLoading}
              >
                {selectedAgent.id === 'auto' ? (
                  <Sparkles className="w-3.5 h-3.5" style={{ color: '#10B981' }} />
                ) : null}
                <span>{agentLabels[selectedAgent.id] || selectedAgent.name}</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </button>

              {showDropdown && (
                <div className="agent-dropdown">
                  {agents.map((agent) => {
                    const Icon = agentIcons[agent.id] || Sparkles;
                    const isActive = selectedAgent.id === agent.id;
                    const isAuto = agent.id === 'auto';
                    return (
                      <button
                        key={agent.id}
                        className={`agent-dropdown-item ${isActive ? 'active' : ''} ${isAuto ? 'agent-dropdown-auto' : ''}`}
                        onClick={() => {
                          onSelectAgent(agent);
                          setShowDropdown(false);
                        }}
                      >
                        <div className={`agent-icon ${isAuto ? 'agent-icon-auto' : ''}`}>
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', textAlign: 'left' }}>
                          <span>{agentLabels[agent.id] || agent.name}</span>
                          {agentDescriptions[agent.id] && (
                            <span style={{ fontSize: '10px', color: '#9CA3AF', fontWeight: 400 }}>
                              {agentDescriptions[agent.id]}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Send button */}
          <button
            onClick={onSend}
            disabled={!canSend}
            className={`rogo-send-btn ${canSend ? 'active' : 'disabled'}`}
            aria-label="Send message"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 8H13M13 8L8.5 3.5M13 8L8.5 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatInput;
