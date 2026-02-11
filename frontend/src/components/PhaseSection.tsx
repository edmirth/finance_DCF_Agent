import { motion } from 'framer-motion';
import { ThinkingStep } from '../types';
import { Search, FileText, Calculator, Lightbulb, Loader2, Brain, CheckCircle2, Sparkles } from 'lucide-react';
import SearchQueryItem from './SearchQueryItem';
import SourceItem from './SourceItem';

interface PhaseSectionProps {
  phase: string;
  steps: ThinkingStep[];
  isActive?: boolean;
}

const phaseConfig: Record<string, { title: string; icon: any; color: string; bgColor: string; borderColor: string }> = {
  reasoning: {
    title: 'Thinking',
    icon: Brain,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  searching: {
    title: 'Searching',
    icon: Search,
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  gathering_data: {
    title: 'Gathering data',
    icon: FileText,
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
  },
  reviewing: {
    title: 'Reading sources',
    icon: FileText,
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-50',
    borderColor: 'border-indigo-200',
  },
  analyzing: {
    title: 'Analyzing',
    icon: Sparkles,
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
  },
  calculating: {
    title: 'Calculating',
    icon: Calculator,
    color: 'text-pink-600',
    bgColor: 'bg-pink-50',
    borderColor: 'border-pink-200',
  },
  synthesizing: {
    title: 'Synthesizing',
    icon: Lightbulb,
    color: 'text-teal-600',
    bgColor: 'bg-teal-50',
    borderColor: 'border-teal-200',
  },
  processing: {
    title: 'Processing',
    icon: Loader2,
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
  },
};

function PhaseSection({ phase, steps, isActive }: PhaseSectionProps) {
  const config = phaseConfig[phase] || phaseConfig.processing;

  // Extract different types of steps
  const searchQueries = steps.filter(s => s.type === 'search_query');
  const sources = steps.filter(s => s.type === 'source_review');
  const thoughts = steps.filter(s => s.type === 'agent_thought' || s.type === 'thinking_start');
  const tools = steps.filter(s => s.type === 'tool');
  
  // Get thinking text from thinking_start steps
  const thinkingText = thoughts.find(s => s.thinkingText)?.thinkingText || 
    thoughts.find(s => s.content)?.content || '';

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={`rounded-lg border ${config.borderColor} ${config.bgColor} p-3`}
    >
      {/* Phase Header */}
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-5 h-5 rounded-md flex items-center justify-center bg-white/60`}>
          {isActive ? (
            <Loader2 className={`w-3 h-3 ${config.color} animate-spin`} strokeWidth={2.5} />
          ) : (
            <CheckCircle2 className={`w-3 h-3 text-green-500`} strokeWidth={2.5} />
          )}
        </div>
        <h4 className={`text-sm font-semibold ${config.color}`}>
          {config.title}
        </h4>
        {(sources.length > 0 || tools.length > 0) && (
          <span className="text-xs text-gray-400">
            {sources.length > 0 ? `${sources.length} sources` : `${tools.length} tools`}
          </span>
        )}
      </div>

      {/* Phase Content */}
      <div className="space-y-2 ml-7">
        {/* Thinking Text */}
        {thinkingText && (
          <p className="text-sm text-gray-700 leading-relaxed">
            {thinkingText}
          </p>
        )}

        {/* Search Queries */}
        {searchQueries.length > 0 && (
          <div className="space-y-1">
            {searchQueries.map(step => (
              <SearchQueryItem key={step.id} query={step.searchQuery || step.content || ''} />
            ))}
          </div>
        )}

        {/* Sources */}
        {sources.length > 0 && (
          <div className="space-y-1">
            {sources.map(step => (
              <SourceItem key={step.id} source={step.source!} />
            ))}
          </div>
        )}

        {/* Tool executions */}
        {tools.length > 0 && (
          <div className="space-y-1">
            {tools.map(step => (
              <div key={step.id} className="flex items-center gap-2 text-xs text-gray-500">
                <CheckCircle2 className="w-3 h-3 text-green-500" />
                <span>{step.tool || step.content}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Progress Indicator */}
      {isActive && (
        <div className="mt-2 ml-7 flex items-center gap-2">
          <div className="flex gap-0.5">
            <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
            <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
            <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="text-xs text-gray-500">In progress...</span>
        </div>
      )}
    </motion.div>
  );
}

export default PhaseSection;
