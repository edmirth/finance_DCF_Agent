/**
 * Strip common markdown markers from a string so LLM-generated text can be
 * displayed as clean plain text in compact UI contexts (card summaries, row
 * labels, etc.) where a full markdown renderer is not appropriate.
 */
export const stripMarkdown = (text: string): string =>
  text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/_(.*?)_/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/#+\s/g, '')
    .trim();
