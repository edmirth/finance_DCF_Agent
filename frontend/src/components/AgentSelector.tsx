import { useState, useRef, useEffect } from 'react';
import { Agent } from '../types';
import { ChevronDown, Check } from 'lucide-react';

interface AgentSelectorProps {
  agents: Agent[];
  selectedAgent: Agent | null;
  onSelectAgent: (agent: Agent) => void;
}

function AgentSelector({ agents, selectedAgent, onSelectAgent }: AgentSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-3 px-4 py-2 bg-white border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
      >
        {selectedAgent && (
          <>
            <span className={`${selectedAgent.color} w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-sm`}>
              {selectedAgent.icon}
            </span>
            <div className="text-left">
              <p className="text-sm font-medium text-gray-900">{selectedAgent.name}</p>
              <p className="text-xs text-gray-500">Active Agent</p>
            </div>
            <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-20">
          <div className="p-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-3 py-2">
              Select Agent
            </p>
            {agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => {
                  onSelectAgent(agent);
                  setIsOpen(false);
                }}
                className="w-full flex items-start gap-3 px-3 py-3 hover:bg-gray-50 rounded-lg transition-colors text-left"
              >
                <span className={`${agent.color} w-10 h-10 rounded-lg flex items-center justify-center text-white flex-shrink-0 shadow-sm`}>
                  {agent.icon}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-medium text-gray-900">{agent.name}</p>
                    {selectedAgent?.id === agent.id && (
                      <Check className="w-4 h-4 text-green-600" />
                    )}
                  </div>
                  <p className="text-xs text-gray-500 line-clamp-2">{agent.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentSelector;
