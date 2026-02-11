import { Message, Agent } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import StockChartCard from './StockChartCard';
import { extractTicker } from '../utils/tickerDetection';
import ReasoningDisplay from './ReasoningDisplay';
import { useState } from 'react';

interface MessageProps {
  message: Message;
  agent: Agent;
  isStreaming?: boolean;
}

function MessageComponent({ message, agent, isStreaming = false }: MessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [isReasoningCollapsed, setIsReasoningCollapsed] = useState(false);

  if (!message.content && !message.thinkingSteps?.length) return null;

  // Filter out ReAct format markers
  const cleanContent = (content: string): string => {
    if (!content) return '';
    return content
      .replace(/\*\*PLAN:\*\*[\s\S]*?(?=\n\n|\*\*|$)/g, '')
      .replace(/Plan:[\s\S]*?(?=\n\n|Thought:|$)/g, '')
      .replace(/Thought:[\s\S]*?(?=\n\nAction:|$)/g, '')
      .replace(/Reflection:[\s\S]*?(?=\n\n|$)/g, '')
      .replace(/Action:[\s\S]*?(?=\n\nAction Input:|$)/g, '')
      .replace(/Action Input:[\s\S]*?(?=\n\nObservation:|$)/g, '')
      .replace(/Observation:[\s\S]*?(?=\n\nThought:|$)/g, '')
      .replace(/Final Answer:\s*/g, '')
      .trim();
  };

  const displayContent = isUser ? message.content : cleanContent(message.content);

  // Detect ticker from metadata or content
  const ticker = !isUser && !isSystem
    ? (message.ticker || extractTicker(message.content))
    : null;

  const handleCopyReasoning = () => {
    if (!message.thinkingSteps) return;
    let text = '=== AGENT REASONING ===\n\n';
    message.thinkingSteps.forEach((step, i) => {
      text += `${i + 1}. [${step.type}] ${step.content || step.tool || ''}\n`;
    });
    navigator.clipboard.writeText(text);
  };

  // System messages
  if (isSystem) {
    return (
      <div className="flex justify-center my-4 animate-fade-in">
        <div
          className="px-4 py-1.5 rounded-full text-xs"
          style={{
            fontFamily: 'Inter, sans-serif',
            color: '#9CA3AF',
            background: 'rgba(0, 0, 0, 0.03)',
          }}
        >
          <ReactMarkdown className="inline">{message.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  // User message - dark pill bubble
  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="user-message">
          {displayContent}
        </div>
      </div>
    );
  }

  // Assistant message - document-style flow
  return (
    <div className="animate-fade-in">
      {/* Reasoning Display */}
      {message.thinkingSteps && message.thinkingSteps.length > 0 && (
        <div className="mb-3">
          <ReasoningDisplay
            steps={message.thinkingSteps}
            isStreaming={isStreaming}
            isCollapsed={isReasoningCollapsed}
            onToggleCollapse={() => setIsReasoningCollapsed(!isReasoningCollapsed)}
            onCopy={handleCopyReasoning}
          />
        </div>
      )}

      {/* Stock Chart */}
      {ticker && (
        <div className="mb-4">
          <StockChartCard ticker={ticker} />
        </div>
      )}

      {/* Response content */}
      {displayContent && (
        <div className="assistant-response">
          <div className="mb-2">
            <span
              className="text-xs font-medium"
              style={{ fontFamily: 'Inter, sans-serif', color: '#9CA3AF' }}
            >
              {agent.name}
            </span>
          </div>
          <div className="prose-gray">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

export default MessageComponent;
