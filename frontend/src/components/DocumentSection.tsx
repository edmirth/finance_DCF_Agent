import React from 'react';
import { CitationBadge } from './CitationBadge';
import { Citation, parseParagraphCitations } from '../utils/citationParser';

interface DocumentSectionProps {
  title?: string;
  content: string;
  citations: Citation[];
  level?: 1 | 2 | 3;
}

export function DocumentSection({ title, content, citations, level = 2 }: DocumentSectionProps) {
  const citationMap = new Map(citations.map(c => [c.id, c]));

  // Render content with inline citations
  const renderContentWithCitations = (text: string) => {
    const parts = parseParagraphCitations(text);

    return parts.map((part, idx) => (
      <React.Fragment key={idx}>
        {part.text}
        {part.citations.map(citationId => {
          const citation = citationMap.get(citationId);
          return citation ? (
            <CitationBadge
              key={citationId}
              id={citation.id}
              url={citation.url}
              title={citation.title}
            />
          ) : null;
        })}
      </React.Fragment>
    ));
  };

  // Split content into paragraphs
  const paragraphs = content.split('\n\n').filter(p => p.trim());

  // Heading component based on level
  const Heading = level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3';
  const headingClass =
    level === 1
      ? 'text-[28px] font-semibold mb-4'
      : level === 2
      ? 'text-[20px] font-semibold mb-4'
      : 'text-lg font-semibold mb-3';
  const headingStyle = { fontFamily: 'Inter, sans-serif', color: '#1A1A1A', letterSpacing: level === 1 ? '-0.02em' : '-0.01em' };

  return (
    <section className="my-8">
      {title && <Heading className={headingClass} style={headingStyle}>{title}</Heading>}
      <div className="prose prose-gray max-w-none" style={{ fontFamily: 'Inter, sans-serif' }}>
        {paragraphs.map((paragraph, idx) => {
          // Check if paragraph is a list item
          if (paragraph.trim().startsWith('-') || paragraph.trim().startsWith('•')) {
            const items = paragraph.split('\n').filter(item => item.trim());
            return (
              <ul key={idx} className="list-disc list-inside space-y-2 mb-4" style={{ color: '#1A1A1A', lineHeight: '1.7' }}>
                {items.map((item, itemIdx) => (
                  <li key={itemIdx} className="ml-4">
                    {renderContentWithCitations(item.replace(/^[-•]\s*/, ''))}
                  </li>
                ))}
              </ul>
            );
          }

          // Check if paragraph is a numbered list
          if (/^\d+\./.test(paragraph.trim())) {
            const items = paragraph.split('\n').filter(item => item.trim());
            return (
              <ol key={idx} className="list-decimal list-inside space-y-2 mb-4" style={{ color: '#1A1A1A', lineHeight: '1.7' }}>
                {items.map((item, itemIdx) => (
                  <li key={itemIdx} className="ml-4">
                    {renderContentWithCitations(item.replace(/^\d+\.\s*/, ''))}
                  </li>
                ))}
              </ol>
            );
          }

          // Regular paragraph
          return (
            <p key={idx} className="mb-4" style={{ color: '#1A1A1A', lineHeight: '1.7', fontSize: '16px' }}>
              {renderContentWithCitations(paragraph)}
            </p>
          );
        })}
      </div>
    </section>
  );
}
