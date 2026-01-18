import { MessageSquare } from 'lucide-react';

interface AgentThoughtItemProps {
  thought: string;
}

function AgentThoughtItem({ thought }: AgentThoughtItemProps) {
  return (
    <div className="flex items-start gap-2.5 text-sm">
      <div className="w-4 h-4 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0 mt-0.5">
        <MessageSquare className="w-2.5 h-2.5 text-blue-600" strokeWidth={2.5} />
      </div>
      <div className="flex-1">
        <p className="text-gray-700 leading-relaxed italic">{thought}</p>
      </div>
    </div>
  );
}

export default AgentThoughtItem;
