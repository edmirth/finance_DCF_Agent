import { Lightbulb } from 'lucide-react';

interface ReflectionItemProps {
  reflection: string;
}

function ReflectionItem({ reflection }: ReflectionItemProps) {
  return (
    <div className="flex items-start gap-2.5 text-sm">
      <div className="w-5 h-5 rounded-lg bg-purple-50 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Lightbulb className="w-3 h-3 text-purple-600" strokeWidth={2.5} />
      </div>
      <div className="flex-1">
        <p className="font-semibold text-purple-700 mb-1">Reflection</p>
        <p className="text-gray-700 leading-relaxed">{reflection}</p>
      </div>
    </div>
  );
}

export default ReflectionItem;
