import { ClipboardList, RefreshCw } from 'lucide-react';

interface PlanDisplayProps {
  plan: string[];
  isUpdated?: boolean;
}

function PlanDisplay({ plan, isUpdated = false }: PlanDisplayProps) {
  return (
    <div className="flex items-start gap-2.5 text-sm">
      <div className={`w-5 h-5 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${
        isUpdated ? 'bg-amber-50' : 'bg-blue-50'
      }`}>
        {isUpdated ? (
          <RefreshCw className="w-3 h-3 text-amber-600" strokeWidth={2.5} />
        ) : (
          <ClipboardList className="w-3 h-3 text-blue-600" strokeWidth={2.5} />
        )}
      </div>
      <div className="flex-1">
        <p className={`font-semibold mb-2 ${isUpdated ? 'text-amber-700' : 'text-blue-700'}`}>
          {isUpdated ? 'Updated Plan' : 'Execution Plan'}
        </p>
        <ol className="space-y-1.5 list-none">
          {plan.map((step, index) => (
            <li key={index} className="flex items-start gap-2">
              <span className={`font-semibold ${isUpdated ? 'text-amber-600' : 'text-blue-600'}`}>
                {index + 1}.
              </span>
              <span className="text-gray-700 leading-relaxed flex-1">{step}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export default PlanDisplay;
