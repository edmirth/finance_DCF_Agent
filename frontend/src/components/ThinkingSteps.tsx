import { ThinkingStep } from '../types';
import { Wrench, CheckCircle2, MessageSquare } from 'lucide-react';
import { cleanLabel } from './ReasoningDisplay';

interface ThinkingStepsProps {
  steps: ThinkingStep[];
}

function ThinkingSteps({ steps }: ThinkingStepsProps) {
  if (steps.length === 0) return null;

  return (
    <div className="mt-3 space-y-1.5">
      {steps.map((step, index) => {
        // Skip tool type if there's a matching thought right before it (avoid duplication)
        if (step.type === 'tool' && index > 0 && steps[index - 1].type === 'thought') {
          return null;
        }

        return (
          <div key={step.id} className="flex items-start gap-2 text-sm animate-in fade-in slide-in-from-bottom-2">
            {step.type === 'thought' && (
              <div className="flex items-start gap-2 text-blue-600">
                <MessageSquare className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <p className="leading-relaxed font-medium">{step.content}</p>
              </div>
            )}

            {step.type === 'tool' && (
              <div className="flex items-start gap-2 text-blue-600 opacity-70">
                <Wrench className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <div className="text-xs">
                  <span className="font-medium">{cleanLabel(step.tool || '')}</span>
                </div>
              </div>
            )}

            {step.type === 'tool_result' && (
              <div className="flex items-start gap-2 text-green-600">
                <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <p className="text-gray-500 text-xs leading-relaxed">{step.content}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default ThinkingSteps;
