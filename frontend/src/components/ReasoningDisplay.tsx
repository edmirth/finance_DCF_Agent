import { motion, AnimatePresence } from 'framer-motion';
import { ThinkingStep } from '../types';
import ThinkingBubble from './ThinkingBubble';
import PhaseSection from './PhaseSection';
import { ChevronDown, ChevronUp, Loader2, CheckCircle2, Brain, Search, FileText, Calculator, Sparkles } from 'lucide-react';

interface ReasoningDisplayProps {
  steps: ThinkingStep[];
  isStreaming?: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  onCopy?: () => void;
}

// Phase configuration for Perplexity-style display
const phaseConfig: Record<string, { title: string; icon: any; color: string; bgColor: string }> = {
  reasoning: {
    title: 'Thinking',
    icon: Brain,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
  },
  gathering_data: {
    title: 'Gathering data',
    icon: FileText,
    color: 'text-green-600',
    bgColor: 'bg-green-50',
  },
  searching: {
    title: 'Searching',
    icon: Search,
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
  },
  reviewing: {
    title: 'Reading sources',
    icon: FileText,
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-50',
  },
  analyzing: {
    title: 'Analyzing',
    icon: Sparkles,
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
  },
  calculating: {
    title: 'Calculating',
    icon: Calculator,
    color: 'text-pink-600',
    bgColor: 'bg-pink-50',
  },
  synthesizing: {
    title: 'Synthesizing',
    icon: Sparkles,
    color: 'text-teal-600',
    bgColor: 'bg-teal-50',
  },
};

function ReasoningDisplay({ steps, isStreaming, isCollapsed = false, onToggleCollapse }: ReasoningDisplayProps) {
  if (steps.length === 0) return null;

  // Extract thinking text from steps (accumulated from thinking_chunk events)
  const thinkingSteps = steps.filter(s => 
    s.type === 'thinking_start' || s.type === 'thinking_chunk' || s.type === 'thinking_end' ||
    s.type === 'agent_thought'
  );
  
  // Get the current accumulated thinking text
  const currentThinkingStep = thinkingSteps.find(s => s.thinkingText) || 
    steps.find(s => s.type === 'agent_thought');
  const thinkingText = currentThinkingStep?.thinkingText || currentThinkingStep?.content || '';
  
  // Check if we're currently in a thinking stream
  const isThinking = steps.some(s => s.type === 'thinking_start' && !steps.some(e => e.type === 'thinking_end'));
  
  // Extract reflection text
  const reflectionSteps = steps.filter(s => 
    s.type === 'reflection_start' || s.type === 'reflection_chunk' || s.type === 'reflection_end' ||
    s.type === 'reflection'
  );
  const currentReflectionStep = reflectionSteps.find(s => s.reflectionText) ||
    reflectionSteps.find(s => s.type === 'reflection');
  const reflectionText = currentReflectionStep?.reflectionText || currentReflectionStep?.content || '';
  const isReflecting = steps.some(s => s.type === 'reflection_start' && !steps.some(e => e.type === 'reflection_end'));

  // Get the most recent plan
  const latestPlan = steps.filter(s => s.type === 'plan_created' || s.type === 'plan_updated').pop();

  // Get current phase
  const phaseSteps = steps.filter(s => s.type === 'phase_start');
  const currentPhase = phaseSteps[phaseSteps.length - 1]?.phase || 'reasoning';
  const phaseInfo = phaseConfig[currentPhase] || phaseConfig.reasoning;
  const PhaseIcon = phaseInfo.icon;

  // Get tool execution steps for the current phase
  const toolSteps = steps.filter(s => s.type === 'tool' || s.type === 'tool_result');
  const currentTool = toolSteps[toolSteps.length - 1];
  
  // Count total steps for history toggle
  const historyStepsCount = steps.filter(s => 
    !['thinking_chunk', 'reflection_chunk'].includes(s.type)
  ).length;

  // Group steps by phase for history display
  const groupedPhases = groupStepsByPhase(steps);

  return (
    <div className="my-3">
      {/* Main Container - Perplexity-style card */}
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isStreaming ? (
                <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-green-500" />
              )}
              <span className="text-sm font-medium text-gray-700">
                {isStreaming ? 'Thinking...' : 'Complete'}
              </span>
              {isStreaming && (
                <div className="flex gap-0.5">
                  <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
                  <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
                  <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
                </div>
              )}
            </div>

            {/* History toggle */}
            {historyStepsCount > 1 && (
              <button
                onClick={onToggleCollapse}
                className="flex items-center gap-1.5 px-2.5 py-1 hover:bg-gray-100 rounded-lg transition-colors text-xs font-medium text-gray-500"
              >
                <span>{historyStepsCount} steps</span>
                {isCollapsed ? (
                  <ChevronDown className="w-3.5 h-3.5" />
                ) : (
                  <ChevronUp className="w-3.5 h-3.5" />
                )}
              </button>
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="p-4 space-y-4">
          
          {/* Current Phase Indicator */}
          <div className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded-lg flex items-center justify-center ${phaseInfo.bgColor}`}>
              {isStreaming ? (
                <Loader2 className={`w-3.5 h-3.5 ${phaseInfo.color} animate-spin`} />
              ) : (
                <PhaseIcon className={`w-3.5 h-3.5 ${phaseInfo.color}`} />
              )}
            </div>
            <span className={`text-sm font-semibold ${phaseInfo.color}`}>
              {phaseInfo.title}
            </span>
          </div>

          {/* Plan Display (if exists) */}
          {latestPlan && latestPlan.plan && latestPlan.plan.length > 0 && (
            <div className="bg-indigo-50 rounded-xl p-4 border border-indigo-100">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-4 h-4 text-indigo-600" />
                <span className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">
                  Plan
                </span>
              </div>
              <ol className="space-y-1.5 ml-1">
                {latestPlan.plan.map((step, idx) => (
                  <li key={idx} className="text-sm text-indigo-900 leading-relaxed flex gap-2">
                    <span className="font-semibold text-indigo-600 min-w-[1.25rem]">{idx + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Thinking Bubble - Shows streaming thoughts */}
          {(thinkingText || isThinking) && (
            <ThinkingBubble
              text={thinkingText}
              isStreaming={isThinking || !!isStreaming}
              phase="reasoning"
              type="thinking"
            />
          )}

          {/* Current Tool Execution */}
          {currentTool && currentTool.type === 'tool' && isStreaming && (
            <motion.div
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-3 text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2"
            >
              <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
              <span>{currentTool.tool || currentTool.content}</span>
            </motion.div>
          )}

          {/* Reflection Bubble - Shows after tool results */}
          {(reflectionText || isReflecting) && (
            <ThinkingBubble
              text={reflectionText}
              isStreaming={isReflecting}
              phase="reflecting"
              type="reflection"
            />
          )}
        </div>

        {/* Collapsible History */}
        <AnimatePresence initial={false}>
          {!isCollapsed && groupedPhases.length > 1 && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeInOut' }}
              className="overflow-hidden border-t border-gray-100"
            >
              <div className="p-4 bg-gray-50/70 space-y-3">
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  History
                </div>
                
                {/* Previous phases */}
                {groupedPhases.slice(0, -1).map((group, index) => (
                  <motion.div
                    key={`${group.phase}-${index}`}
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15, delay: index * 0.03 }}
                  >
                    <PhaseSection
                      phase={group.phase}
                      steps={group.steps}
                      isActive={false}
                    />
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// Helper function to group steps by phase
function groupStepsByPhase(steps: ThinkingStep[]) {
  const groups: { phase: string; steps: ThinkingStep[] }[] = [];
  let currentGroup: { phase: string; steps: ThinkingStep[] } | null = null;

  for (const step of steps) {
    // Skip chunk events in grouping
    if (['thinking_chunk', 'reflection_chunk'].includes(step.type)) {
      continue;
    }
    
    if (step.type === 'phase_start' && step.phase) {
      currentGroup = {
        phase: step.phase,
        steps: [step]
      };
      groups.push(currentGroup);
    } else if (step.type === 'thinking_start') {
      currentGroup = {
        phase: 'reasoning',
        steps: [step]
      };
      groups.push(currentGroup);
    } else if (currentGroup) {
      currentGroup.steps.push(step);
    } else {
      currentGroup = { phase: 'processing', steps: [step] };
      groups.push(currentGroup);
    }
  }

  return groups;
}

export default ReasoningDisplay;
