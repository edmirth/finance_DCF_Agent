import { Search } from 'lucide-react';

interface SearchQueryItemProps {
  query: string;
}

function SearchQueryItem({ query }: SearchQueryItemProps) {
  return (
    <div className="flex items-start gap-2 text-sm text-gray-600">
      <Search className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-400" strokeWidth={2} />
      <span className="leading-relaxed">{query}</span>
    </div>
  );
}

export default SearchQueryItem;
