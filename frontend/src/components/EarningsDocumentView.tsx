import { useMemo } from 'react';
import { MetadataBar, SourceType } from './MetadataBar';
import { DocumentSection } from './DocumentSection';
import { extractCitations } from '../utils/citationParser';

interface EarningsDocumentViewProps {
  content: string;
  metadata?: {
    analysisTime?: string;
    sources?: SourceType[];
    sourceCount?: number;
  };
}

interface ParsedSection {
  title: string;
  content: string;
  level: 1 | 2 | 3;
}

export function EarningsDocumentView({ content, metadata }: EarningsDocumentViewProps) {
  // Extract ticker and company name from content
  const { ticker, companyName } = useMemo(() => {
    const tickerMatch = content.match(/(?:Ticker|Symbol):\s*([A-Z]+)/i);
    const companyMatch = content.match(/(?:Company|Company Name):\s*([^\n]+)/i);

    return {
      ticker: tickerMatch?.[1] || '',
      companyName: companyMatch?.[1] || 'Company'
    };
  }, [content]);

  // Extract citations from content
  const { citations, cleanedContent } = useMemo(() => {
    return extractCitations(content);
  }, [content]);

  // Parse content into sections
  const sections = useMemo(() => {
    const parsedSections: ParsedSection[] = [];
    const lines = cleanedContent.split('\n');
    let currentSection: ParsedSection | null = null;

    for (const line of lines) {
      // Check for markdown headers
      if (line.startsWith('# ')) {
        if (currentSection) parsedSections.push(currentSection);
        currentSection = { title: line.replace(/^#\s+/, ''), content: '', level: 1 };
      } else if (line.startsWith('## ')) {
        if (currentSection) parsedSections.push(currentSection);
        currentSection = { title: line.replace(/^##\s+/, ''), content: '', level: 2 };
      } else if (line.startsWith('### ')) {
        if (currentSection) parsedSections.push(currentSection);
        currentSection = { title: line.replace(/^###\s+/, ''), content: '', level: 3 };
      } else if (currentSection) {
        currentSection.content += (currentSection.content ? '\n' : '') + line;
      } else {
        // Content before first section
        if (!currentSection) {
          currentSection = { title: '', content: line, level: 2 };
        }
      }
    }

    if (currentSection) parsedSections.push(currentSection);

    return parsedSections;
  }, [cleanedContent]);

  // Extract table data if present
  const tableData = useMemo(() => {
    const tableMatch = content.match(/\|(.+)\|/g);
    if (!tableMatch || tableMatch.length < 2) return null;

    const rows = tableMatch.map(row =>
      row
        .split('|')
        .filter(cell => cell.trim())
        .map(cell => cell.trim())
    );

    // Skip separator rows (containing dashes)
    const filteredRows = rows.filter(row => !row[0].includes('---'));

    if (filteredRows.length < 2) return null;

    return {
      headers: filteredRows[0],
      rows: filteredRows.slice(1)
    };
  }, [content]);

  return (
    <div className="earnings-document mx-auto bg-white px-8 py-6" style={{ maxWidth: '760px' }}>
      {/* Metadata Bar */}
      <MetadataBar
        analysisTime={metadata?.analysisTime}
        sourceCount={metadata?.sourceCount}
        sourceTypes={metadata?.sources}
      />

      {/* Main Title */}
      <h1 className="document-title text-[28px] font-semibold mb-6 leading-tight" style={{ fontFamily: 'Inter, sans-serif', color: '#1A1A1A' }}>
        {companyName} {ticker && `(${ticker})`} Earnings Analysis
      </h1>

      {/* Body Content with Citations */}
      <div className="document-body">
        {sections.map((section, idx) => (
          <DocumentSection
            key={idx}
            title={section.title || undefined}
            content={section.content}
            citations={citations}
            level={section.level}
          />
        ))}
      </div>

      {/* Tables */}
      {tableData && (
        <div className="my-8 overflow-x-auto">
          <table className="w-full border-collapse earnings-table">
            <thead>
              <tr>
                {tableData.headers.map((header, idx) => (
                  <th
                    key={idx}
                    className="py-3 px-4 font-semibold text-sm"
                    style={{
                      textAlign: idx === 0 ? 'left' : 'right',
                      color: '#1A1A1A',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableData.rows.map((row, rowIdx) => (
                <tr key={rowIdx}>
                  {row.map((cell, cellIdx) => (
                    <td
                      key={cellIdx}
                      className="py-3 px-4 text-sm"
                      style={{
                        textAlign: cellIdx === 0 ? 'left' : 'right',
                        color: '#1A1A1A',
                        fontFamily: cellIdx === 0 ? 'Inter, sans-serif' : 'IBM Plex Mono, monospace'
                      }}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Citations Reference (if any) */}
      {citations.length > 0 && (
        <div className="mt-12 pt-6" style={{ borderTop: '1px solid #E5E5E5' }}>
          <h3 className="text-[20px] font-semibold mb-4" style={{ color: '#1A1A1A', fontFamily: 'Inter, sans-serif' }}>
            Sources
          </h3>
          <ol className="space-y-2 text-sm" style={{ color: '#666666', fontFamily: 'Inter, sans-serif' }}>
            {citations.map(citation => (
              <li key={citation.id} className="flex items-start gap-2">
                <span
                  className="inline-flex items-center justify-center w-5 h-5 text-xs font-semibold rounded-sm flex-shrink-0"
                  style={{ color: '#10B981', border: '1px solid #10B981' }}
                >
                  {citation.id}
                </span>
                {citation.url ? (
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline"
                    style={{ color: '#10B981' }}
                  >
                    {citation.title}
                  </a>
                ) : (
                  <span>{citation.title}</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
