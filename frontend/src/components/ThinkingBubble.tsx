import { motion } from 'framer-motion';
import { Brain, Lightbulb, Loader2 } from 'lucide-react';
import { useStreamingText } from '../hooks/useTypewriter';

interface ThinkingBubbleProps {
  text: string;
  isStreaming: boolean;
  phase?: 'reasoning' | 'analyzing' | 'reflecting';
  type?: 'thinking' | 'reflection';
}

/**
 * ThinkingBubble - Displays streaming reasoning text in a Perplexity-like style
 * 
 * Shows the agent's thought process with a typing animation and phase indicator.
 */
function ThinkingBubble({ text, isStreaming, phase = 'reasoning', type = 'thinking' }: ThinkingBubbleProps) {
  const isReflection = type === 'reflection';
  
  // Phase configurations
  const phaseConfig = {
    reasoning: {
      label: 'Thinking',
      icon: Brain,
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-100',
      iconColor: 'text-blue-500',
      textColor: 'text-blue-900',
      labelColor: 'text-blue-600',
    },
    analyzing: {
      label: 'Analyzing',
      icon: Brain,
      bgColor: 'bg-purple-50',
      borderColor: 'border-purple-100',
      iconColor: 'text-purple-500',
      textColor: 'text-purple-900',
      labelColor: 'text-purple-600',
    },
    reflecting: {
      label: 'Reflecting',
      icon: Lightbulb,
      bgColor: 'bg-amber-50',
      borderColor: 'border-amber-100',
      iconColor: 'text-amber-500',
      textColor: 'text-amber-900',
      labelColor: 'text-amber-600',
    },
  };

  const config = isReflection ? phaseConfig.reflecting : phaseConfig[phase];
  const Icon = config.icon;
  
  // Use streaming text hook for smooth display
  const displayedText = useStreamingText(text, isStreaming);

  if (!text && !isStreaming) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className={`rounded-xl p-4 ${config.bgColor} border ${config.borderColor}`}
    >
      {/* Header with phase indicator */}
      <div className="flex items-center gap-2 mb-2">
        {isStreaming ? (
          <Loader2 className={`w-4 h-4 ${config.iconColor} animate-spin`} />
        ) : (
          <Icon className={`w-4 h-4 ${config.iconColor}`} />
        )}
        <span className={`text-xs font-semibold uppercase tracking-wider ${config.labelColor}`}>
          {config.label}
        </span>
        {isStreaming && (
          <span className="flex items-center gap-1">
            <span className="w-1 h-1 bg-current rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
            <span className="w-1 h-1 bg-current rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
            <span className="w-1 h-1 bg-current rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
          </span>
        )}
      </div>

      {/* Streaming text content */}
      <div className={`text-sm leading-relaxed ${config.textColor}`}>
        <p className="whitespace-pre-wrap">
          {displayedText}
          {isStreaming && (
            <span className="inline-block w-0.5 h-4 ml-0.5 bg-current animate-pulse" />
          )}
        </p>
      </div>
    </motion.div>
  );
}

export default ThinkingBubble;
