import { KeyboardEvent, useState, useRef, useEffect } from 'react';
import { Loader2, Zap, Paperclip, SlidersHorizontal, ChevronDown, BarChart3, TrendingUp, Search, Globe, Briefcase, DollarSign } from 'lucide-react';
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
}

const agentIcons: Record<string, any> = {
  dcf: BarChart3,
  analyst: TrendingUp,
  research: Search,
  market: Globe,
  portfolio: Briefcase,
  earnings: DollarSign,
};

const agentLabels: Record<string, string> = {
  research: 'Research',
  analyst: 'Analyst',
  market: 'Market',
  dcf: 'DCF',
  portfolio: 'Portfolio',
  earnings: 'Earnings',
};

function ChatInput({ value, onChange, onSend, isLoading, placeholder, agents, selectedAgent, onSelectAgent }: ChatInputProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
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
    };
    if (showDropdown) {
      document.addEventListener('mousedown', handleClick);
    }
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showDropdown]);

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
          <button className="rogo-icon-btn" title="Quick prompts" disabled={isLoading}>
            <Zap className="w-4 h-4" />
          </button>
          <button className="rogo-icon-btn" title="Attach file" disabled={isLoading}>
            <Paperclip className="w-4 h-4" />
          </button>
          <button className="rogo-icon-btn" title="Settings" disabled={isLoading}>
            <SlidersHorizontal className="w-4 h-4" />
          </button>
        </div>

        {/* Right side: agent selector + send */}
        <div className="rogo-toolbar-right">
          {/* Agent selector dropdown */}
          {agents && selectedAgent && onSelectAgent && (
            <div className="relative" ref={dropdownRef}>
              <button
                className="agent-selector"
                onClick={() => setShowDropdown(!showDropdown)}
                disabled={isLoading}
              >
                <span>{agentLabels[selectedAgent.id] || selectedAgent.name}</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </button>

              {showDropdown && (
                <div className="agent-dropdown">
                  {agents.map((agent) => {
                    const Icon = agentIcons[agent.id];
                    const isActive = selectedAgent.id === agent.id;
                    return (
                      <button
                        key={agent.id}
                        className={`agent-dropdown-item ${isActive ? 'active' : ''}`}
                        onClick={() => {
                          onSelectAgent(agent);
                          setShowDropdown(false);
                        }}
                      >
                        <div className="agent-icon">
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <span>{agentLabels[agent.id] || agent.name}</span>
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
