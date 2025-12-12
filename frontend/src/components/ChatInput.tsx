import { useState, KeyboardEvent } from 'react';
import { ArrowUp, Paperclip, Loader2, BarChart3, TrendingUp, Search, Globe } from 'lucide-react';
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
};

function ChatInput({ value, onChange, onSend, isLoading, placeholder, agents, selectedAgent, onSelectAgent }: ChatInputProps) {
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="bg-white/80 backdrop-blur-md rounded-full shadow-sm border border-gray-200/50 px-4 py-3 max-w-3xl mx-auto">
      <div className="flex items-center gap-2">
        {/* Agent Selector - Integrated */}
        {agents && selectedAgent && onSelectAgent && (
          <div className="flex items-center gap-1 pr-2 border-r border-gray-200">
            {agents.map((agent) => {
              const Icon = agentIcons[agent.id];
              const isSelected = selectedAgent.id === agent.id;
              return (
                <button
                  key={agent.id}
                  onClick={() => onSelectAgent(agent)}
                  className={`p-1.5 rounded-full transition-all ${
                    isSelected
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
                  }`}
                  title={agent.name}
                >
                  <Icon className="w-3.5 h-3.5" strokeWidth={2} />
                </button>
              );
            })}
          </div>
        )}

        <button
          className="text-gray-400 hover:text-gray-600 transition-colors p-1"
          disabled={isLoading}
        >
          <Paperclip className="w-4 h-4" />
        </button>

        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Ask about markets, stocks, or financial analysis..."}
          className="flex-1 resize-none outline-none text-gray-700 placeholder-gray-400 bg-transparent max-h-32 min-h-[24px]"
          rows={1}
          disabled={isLoading}
          style={{
            height: 'auto',
            minHeight: '24px',
          }}
          onInput={(e) => {
            const target = e.target as HTMLTextAreaElement;
            target.style.height = 'auto';
            target.style.height = target.scrollHeight + 'px';
          }}
        />

        <button
          onClick={onSend}
          disabled={!value.trim() || isLoading}
          className={`p-2.5 rounded-full transition-all ${
            value.trim() && !isLoading
              ? 'bg-gray-900 hover:bg-gray-800 text-white'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          }`}
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
          )}
        </button>
      </div>
    </div>
  );
}

export default ChatInput;
