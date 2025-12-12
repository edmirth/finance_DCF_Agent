import { Loader2 } from 'lucide-react';
import { ThinkingStep } from '../types';
import ThinkingSteps from './ThinkingSteps';

interface StatusIndicatorProps {
  status: string;
  isVisible: boolean;
  thinkingSteps?: ThinkingStep[];
}

function StatusIndicator({ status, isVisible, thinkingSteps = [] }: StatusIndicatorProps) {
  if (!isVisible) return null;

  return (
    <div className="flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2">
      <div className="bg-gray-900 w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm mt-1">
        <Loader2 className="w-3.5 h-3.5 text-white animate-spin" strokeWidth={2} />
      </div>
      <div className="flex flex-col max-w-3xl">
        <div className="px-5 py-3.5 bg-white border border-gray-200 text-gray-800 shadow-sm rounded-3xl">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1 h-1 bg-gray-400 rounded-full animate-pulse"></div>
            <p className="text-[15px] text-gray-600 font-medium">{status}</p>
          </div>
          <ThinkingSteps steps={thinkingSteps} />
        </div>
      </div>
    </div>
  );
}

export default StatusIndicator;
