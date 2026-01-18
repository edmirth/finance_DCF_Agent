import { Globe, Database, Newspaper, Calculator } from 'lucide-react';

interface SourceItemProps {
  source: {
    title: string;
    domain: string;
    url?: string;
    type?: string;
  };
}

function SourceItem({ source }: SourceItemProps) {
  // Choose icon based on source type
  const getIcon = () => {
    switch (source.type) {
      case 'financial_data':
        return Database;
      case 'news':
        return Newspaper;
      case 'calculation':
        return Calculator;
      default:
        return Globe;
    }
  };

  const Icon = getIcon();

  return (
    <div className="flex items-start gap-2.5 text-sm">
      <div className="w-4 h-4 rounded bg-gray-100 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Icon className="w-2.5 h-2.5 text-gray-600" strokeWidth={2} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-gray-800 font-medium truncate">{source.title}</div>
        <div className="text-gray-400 text-xs">{source.domain}</div>
      </div>
    </div>
  );
}

export default SourceItem;
