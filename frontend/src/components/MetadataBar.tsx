import { Clock, Globe, FileText, Calculator, TrendingUp } from 'lucide-react';

export type SourceType = 'financial_data' | 'web_search' | 'news' | 'calculation' | 'earnings';

interface MetadataBarProps {
  analysisTime?: string;
  sourceCount?: number;
  sourceTypes?: SourceType[];
}

function SourceIcon({ type }: { type: SourceType }) {
  const iconClass = "w-4 h-4 text-gray-500";

  switch (type) {
    case 'financial_data':
      return <TrendingUp className={iconClass} />;
    case 'web_search':
      return <Globe className={iconClass} />;
    case 'news':
      return <FileText className={iconClass} />;
    case 'calculation':
      return <Calculator className={iconClass} />;
    case 'earnings':
      return <TrendingUp className={iconClass} />;
    default:
      return <Globe className={iconClass} />;
  }
}

export function MetadataBar({ analysisTime, sourceCount = 0, sourceTypes = [] }: MetadataBarProps) {
  // Default source types if none provided
  const defaultSourceTypes: SourceType[] = ['financial_data', 'web_search', 'earnings'];
  const displaySourceTypes = sourceTypes.length > 0 ? sourceTypes : defaultSourceTypes;

  return (
    <div className="flex items-center justify-between py-3 text-sm border-b mb-6" style={{ color: '#666666', borderColor: '#E5E5E5', fontFamily: 'Inter, sans-serif' }}>
      <div className="flex items-center gap-2">
        <Clock className="w-4 h-4" />
        <span>{analysisTime || 'Analysis complete'}</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1">
          {displaySourceTypes.map((type, idx) => (
            <SourceIcon key={idx} type={type} />
          ))}
        </div>
        <span>{sourceCount > 0 ? `${sourceCount} sources` : 'Multiple sources'}</span>
      </div>
    </div>
  );
}
