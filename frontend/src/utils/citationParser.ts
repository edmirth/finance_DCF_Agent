export interface Citation {
  id: number;
  title: string;
  url?: string;
  type: 'financial_data' | 'web_search' | 'news' | 'calculation';
}

export interface ParsedContent {
  text: string;
  citations: number[];
}

/**
 * Extract citations from markdown content
 * Looks for patterns like [1], [2], etc.
 */
export function extractCitations(content: string): {
  citations: Citation[];
  cleanedContent: string;
} {
  const citations: Citation[] = [];
  const citationMap = new Map<number, Citation>();

  // Pattern to match citation markers like [1], [2]
  const citationRegex = /\[(\d+)\]/g;
  let match;

  while ((match = citationRegex.exec(content)) !== null) {
    const citationId = parseInt(match[1]);

    if (!citationMap.has(citationId)) {
      citationMap.set(citationId, {
        id: citationId,
        title: `Source ${citationId}`,
        type: 'financial_data'
      });
    }
  }

  // Convert map to array and sort by ID
  citations.push(...Array.from(citationMap.values()).sort((a, b) => a.id - b.id));

  return {
    citations,
    cleanedContent: content
  };
}

/**
 * Parse a paragraph and identify citation positions
 */
export function parseParagraphCitations(text: string): ParsedContent[] {
  const parts: ParsedContent[] = [];
  const citationRegex = /\[(\d+)\]/g;
  let lastIndex = 0;
  let match;

  while ((match = citationRegex.exec(text)) !== null) {
    // Add text before citation
    if (match.index > lastIndex) {
      parts.push({
        text: text.substring(lastIndex, match.index),
        citations: []
      });
    }

    // Add the citation marker
    const citationId = parseInt(match[1]);
    parts.push({
      text: '',
      citations: [citationId]
    });

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push({
      text: text.substring(lastIndex),
      citations: []
    });
  }

  // If no citations found, return the whole text
  if (parts.length === 0) {
    parts.push({
      text,
      citations: []
    });
  }

  return parts;
}

/**
 * Infer citation type from context
 */
export function inferCitationType(context: string): Citation['type'] {
  const lowerContext = context.toLowerCase();

  if (lowerContext.includes('calculated') || lowerContext.includes('formula')) {
    return 'calculation';
  }
  if (lowerContext.includes('news') || lowerContext.includes('reported')) {
    return 'news';
  }
  if (lowerContext.includes('search') || lowerContext.includes('according to')) {
    return 'web_search';
  }

  return 'financial_data';
}
