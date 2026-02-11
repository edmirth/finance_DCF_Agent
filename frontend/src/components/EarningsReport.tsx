import { useMemo } from 'react';

interface EarningsReportProps {
  content: string;
}

interface ParsedSection {
  title: string;
  content: string;
}

interface ParsedReport {
  mainTitle: string;
  sections: ParsedSection[];
}

// Clean markdown bold markers and return formatted JSX
function renderInlineText(text: string): JSX.Element[] {
  const parts: JSX.Element[] = [];
  let key = 0;

  // Process bold markers and dollar amounts
  const regex = /\*\*([^*]+)\*\*|(\$[\d,.]+(?:\s*(?:billion|million|trillion|B|M|T))?)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      parts.push(<span key={`t-${key++}`}>{text.slice(lastIndex, match.index)}</span>);
    }

    if (match[1]) {
      // Bold text
      parts.push(<strong key={`b-${key++}`} className="font-semibold text-[#1A1A1A]">{match[1]}</strong>);
    } else if (match[2]) {
      // Dollar amount
      parts.push(<strong key={`d-${key++}`} className="font-semibold text-[#1A1A1A]">{match[2]}</strong>);
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(<span key={`t-${key++}`}>{text.slice(lastIndex)}</span>);
  }

  return parts.length > 0 ? parts : [<span key="0">{text}</span>];
}

// Parse a block of content into formatted JSX elements
function renderContentBlock(text: string): JSX.Element[] {
  const lines = text.split('\n');
  const elements: JSX.Element[] = [];
  let currentParagraph: string[] = [];
  let key = 0;
  let inTable = false;
  let tableHeaders: string[] = [];
  let tableRows: string[][] = [];

  const flushParagraph = () => {
    if (currentParagraph.length > 0) {
      const paraText = currentParagraph.join(' ').trim();
      if (paraText) {
        elements.push(
          <p key={`p-${key++}`} className="document-body document-paragraph">
            {renderInlineText(paraText)}
          </p>
        );
      }
      currentParagraph = [];
    }
  };

  const flushTable = () => {
    if (tableHeaders.length > 0 || tableRows.length > 0) {
      elements.push(
        <div key={`tw-${key++}`} className="my-6 overflow-x-auto">
          <table className="earnings-table">
            {tableHeaders.length > 0 && (
              <thead>
                <tr>
                  {tableHeaders.map((h, i) => (
                    <th key={i}>{h.trim()}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {tableRows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci}>{renderInlineText(cell.trim())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableHeaders = [];
      tableRows = [];
      inTable = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Empty line
    if (!trimmed) {
      if (inTable) flushTable();
      flushParagraph();
      continue;
    }

    // Table separator line (|---|---|)
    if (trimmed.match(/^\|[\s-:|]+\|$/)) {
      continue; // Skip separator, it's handled implicitly
    }

    // Table row (| col1 | col2 |)
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushParagraph();
      const cells = trimmed.split('|').filter(c => c.trim() !== '');

      if (!inTable) {
        inTable = true;
        tableHeaders = cells;
      } else {
        // Check if this is a separator line
        if (!cells.every(c => c.trim().match(/^[-:]+$/))) {
          tableRows.push(cells);
        }
      }
      continue;
    }

    // If we were in a table and hit a non-table line, flush
    if (inTable) {
      flushTable();
    }

    // === Section headers ===
    if (trimmed.match(/^={3,}$/)) {
      continue; // Skip pure separator lines
    }

    // ### Heading level 3
    const h3Match = trimmed.match(/^###\s+(.+)/);
    if (h3Match) {
      flushParagraph();
      elements.push(
        <h3 key={`h3-${key++}`} className="section-heading" style={{ fontSize: '1.125rem' }}>
          {h3Match[1].replace(/\*\*/g, '')}
        </h3>
      );
      continue;
    }

    // ## Heading level 2
    const h2Match = trimmed.match(/^##\s+(.+)/);
    if (h2Match) {
      flushParagraph();
      elements.push(
        <>
          <hr key={`hr-${key++}`} className="section-divider" />
          <h2 key={`h2-${key++}`} className="section-heading">
            {h2Match[1].replace(/\*\*/g, '')}
          </h2>
        </>
      );
      continue;
    }

    // # Heading level 1
    const h1Match = trimmed.match(/^#\s+(.+)/);
    if (h1Match) {
      flushParagraph();
      elements.push(
        <h1 key={`h1-${key++}`} className="document-title">
          {h1Match[1].replace(/\*\*/g, '')}
        </h1>
      );
      continue;
    }

    // ALL CAPS HEADING (from === delimited sections)
    if (trimmed === trimmed.toUpperCase() && trimmed.length > 3 && trimmed.length < 80 && !trimmed.startsWith('-') && !trimmed.startsWith('|') && trimmed.match(/^[A-Z\s&:,()]+$/)) {
      flushParagraph();
      // Title-case the heading
      const titleCased = trimmed
        .toLowerCase()
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');

      elements.push(
        <>
          <hr key={`hr-${key++}`} className="section-divider" />
          <h2 key={`hcaps-${key++}`} className="section-heading">{titleCased}</h2>
        </>
      );
      continue;
    }

    // Numbered list item: 1. **Label:** content
    const numberedBoldMatch = trimmed.match(/^(\d+)\.\s*\*\*([^*]+)\*\*:?\s*(.*)/);
    if (numberedBoldMatch) {
      flushParagraph();
      const [, , label, content] = numberedBoldMatch;
      elements.push(
        <div key={`nl-${key++}`} className="flex gap-3 items-baseline mb-3 ml-1">
          <span className="flex-shrink-0 text-[#10B981] font-semibold text-sm" style={{ minWidth: '1.25rem' }}>
            {numberedBoldMatch[1]}.
          </span>
          <p className="document-body flex-1">
            <strong className="font-semibold text-[#1A1A1A]">{label}</strong>
            {content && <span> {renderInlineText(content)}</span>}
          </p>
        </div>
      );
      continue;
    }

    // Simple numbered list: 1. content
    const numberedMatch = trimmed.match(/^(\d+)\.\s+(.+)/);
    if (numberedMatch) {
      flushParagraph();
      const [, num, content] = numberedMatch;
      elements.push(
        <div key={`nl-${key++}`} className="flex gap-3 items-baseline mb-2 ml-1">
          <span className="flex-shrink-0 text-[#10B981] font-semibold text-sm" style={{ minWidth: '1.25rem' }}>
            {num}.
          </span>
          <p className="document-body flex-1">{renderInlineText(content)}</p>
        </div>
      );
      continue;
    }

    // Bullet with bold: - **Label:** content
    const bulletBoldMatch = trimmed.match(/^[-*]\s*\*\*([^*]+)\*\*:?\s*(.*)/);
    if (bulletBoldMatch) {
      flushParagraph();
      const [, label, content] = bulletBoldMatch;
      elements.push(
        <div key={`bl-${key++}`} className="flex gap-3 items-baseline mb-2 ml-1">
          <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[#10B981] mt-2" />
          <p className="document-body flex-1">
            <strong className="font-semibold text-[#1A1A1A]">{label}</strong>
            {content && <span> {renderInlineText(content)}</span>}
          </p>
        </div>
      );
      continue;
    }

    // Simple bullet: - content
    const bulletMatch = trimmed.match(/^[-*]\s+(.+)/);
    if (bulletMatch) {
      flushParagraph();
      elements.push(
        <div key={`bl-${key++}`} className="flex gap-3 items-baseline mb-2 ml-1">
          <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[#D1D5DB] mt-2" />
          <p className="document-body flex-1">{renderInlineText(bulletMatch[1])}</p>
        </div>
      );
      continue;
    }

    // Standalone bold heading: **Some Label:**
    const standaloneHeadingMatch = trimmed.match(/^\*\*([^*]+)\*\*:?\s*$/);
    if (standaloneHeadingMatch) {
      flushParagraph();
      elements.push(
        <h3 key={`sh-${key++}`} className="font-semibold text-[#1A1A1A] text-base mt-5 mb-2" style={{ fontFamily: 'Inter, sans-serif' }}>
          {standaloneHeadingMatch[1]}
        </h3>
      );
      continue;
    }

    // Regular text line - accumulate into paragraph
    currentParagraph.push(trimmed);
  }

  // Flush remaining
  if (inTable) flushTable();
  flushParagraph();

  return elements;
}

// Parse full report into title and sections
function parseReport(text: string): ParsedReport {
  // Try to extract the main title
  let mainTitle = '';
  const sections: ParsedSection[] = [];

  // Check for === delimited sections
  const sectionRegex = /={3,}\s*\n([A-Z][A-Z\s&:,()]+?)\s*\n={3,}\s*\n([\s\S]*?)(?=\n\n={3,}|\n={3,}|$)/gi;
  let match;
  const foundSections: { title: string; content: string; index: number }[] = [];

  while ((match = sectionRegex.exec(text)) !== null) {
    foundSections.push({
      title: match[1].trim(),
      content: match[2].trim(),
      index: match.index
    });
  }

  if (foundSections.length > 0) {
    // Use first section as main title if it looks like one
    const first = foundSections[0];
    if (first.title.match(/EARNINGS.*REPORT|ANALYSIS/i)) {
      mainTitle = first.content.split('\n')[0]?.replace(/[=\-]/g, '').trim() || first.title;
      // Get content before first section as intro
      const intro = text.slice(0, first.index).trim();
      if (intro) {
        sections.push({ title: '', content: intro });
      }
    }

    foundSections.forEach(s => {
      if (!s.title.match(/EARNINGS.*REPORT$/i)) {
        sections.push({ title: s.title, content: s.content });
      }
    });
  }

  // If no === sections found, treat the whole text as content
  if (sections.length === 0) {
    // Try to find a markdown h1 title
    const h1Match = text.match(/^#\s+(.+)/m);
    if (h1Match) {
      mainTitle = h1Match[1].replace(/\*\*/g, '');
    }
    sections.push({ title: '', content: text });
  }

  // Try to extract title from COMPANY: line
  if (!mainTitle) {
    const companyMatch = text.match(/COMPANY:\s*([^(]+?)\s*\(([A-Z]+)\)/i);
    if (companyMatch) {
      mainTitle = `${companyMatch[1].trim()} (${companyMatch[2]}) Earnings Analysis`;
    }
  }

  // Fallback title
  if (!mainTitle) {
    const firstLine = text.split('\n').find(l => l.trim().length > 10 && !l.trim().startsWith('='));
    mainTitle = firstLine?.replace(/[#*=]/g, '').trim() || 'Earnings Analysis Report';
  }

  return { mainTitle, sections };
}

function EarningsReport({ content }: EarningsReportProps) {
  const parsed = useMemo(() => parseReport(content), [content]);

  return (
    <div className="document-body">
      {/* Main document title */}
      <h1 className="document-title">{parsed.mainTitle}</h1>

      {/* Render all sections as flowing document */}
      {parsed.sections.map((section, idx) => (
        <div key={idx}>
          {section.title && (
            <>
              {idx > 0 && <hr className="section-divider" />}
              <h2 className="section-heading">
                {section.title
                  .toLowerCase()
                  .split(' ')
                  .map(w => w.charAt(0).toUpperCase() + w.slice(1))
                  .join(' ')}
              </h2>
            </>
          )}
          <div className="prose-gray">
            {renderContentBlock(section.content)}
          </div>
        </div>
      ))}

      {/* Footer */}
      <div className="mt-12 pt-6 border-t border-[#E5E5E5]">
        <p className="text-sm text-[#9CA3AF]" style={{ fontFamily: 'Inter, sans-serif' }}>
          Generated by AI Earnings Analyst
        </p>
      </div>
    </div>
  );
}

export default EarningsReport;
