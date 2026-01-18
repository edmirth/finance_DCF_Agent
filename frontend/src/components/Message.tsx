import { Message, Agent } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, BarChart3, TrendingUp, Search, Globe, Briefcase, DollarSign } from 'lucide-react';
import StockChartCard from './StockChartCard';
import { extractTicker } from '../utils/tickerDetection';
import ReasoningDisplay from './ReasoningDisplay';
import { useState } from 'react';

const agentIcons: Record<string, any> = {
  dcf: BarChart3,
  analyst: TrendingUp,
  research: Search,
  market: Globe,
  portfolio: Briefcase,
  earnings: DollarSign,
};

interface MessageProps {
  message: Message;
  agent: Agent;
  isStreaming?: boolean;
}

function MessageComponent({ message, agent, isStreaming = false }: MessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [isReasoningCollapsed, setIsReasoningCollapsed] = useState(false);

  const AgentIcon = agentIcons[agent.id];

  // Don't render anything if message has no content
  if (!message.content && !message.thinkingSteps?.length) return null;

  // Filter out ReAct format markers from displayed content
  const cleanContent = (content: string): string => {
    if (!content) return '';
    // Remove ReAct format markers but keep the actual content
    return content
      .replace(/\*\*PLAN:\*\*[\s\S]*?(?=\n\n|\*\*|$)/g, '') // Remove **PLAN:** sections
      .replace(/Plan:[\s\S]*?(?=\n\n|Thought:|$)/g, '') // Remove Plan: sections
      .replace(/Thought:[\s\S]*?(?=\n\nAction:|$)/g, '') // Remove Thought: sections
      .replace(/Reflection:[\s\S]*?(?=\n\n|$)/g, '') // Remove Reflection: sections
      .replace(/Action:[\s\S]*?(?=\n\nAction Input:|$)/g, '') // Remove Action: lines
      .replace(/Action Input:[\s\S]*?(?=\n\nObservation:|$)/g, '') // Remove Action Input: sections
      .replace(/Observation:[\s\S]*?(?=\n\nThought:|$)/g, '') // Remove Observation: sections
      .replace(/Final Answer:\s*/g, '') // Remove "Final Answer:" prefix
      .trim();
  };

  const displayContent = isUser ? message.content : cleanContent(message.content);

  // Use ticker from metadata (if available), otherwise extract from content as fallback
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

  // System messages (agent switches, notifications)
  if (isSystem) {
    return (
      <div className="flex justify-center my-4 animate-in fade-in">
        <div className="px-4 py-2 bg-gray-100/80 border border-gray-200/50 rounded-full text-xs text-gray-600 font-medium">
          <ReactMarkdown className="inline">{message.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2`}>
      {!isUser && (
        <div className="bg-gray-900 w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm mt-1">
          <AgentIcon className="w-3.5 h-3.5 text-white" strokeWidth={2} />
        </div>
      )}

      <div className={`flex flex-col max-w-3xl ${isUser ? 'items-end' : 'items-start'}`}>
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="text-xs font-semibold text-gray-700">
            {isUser ? 'You' : agent.name}
          </span>
          <span className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        {/* Reasoning Display - show BEFORE content for assistant messages */}
        {!isUser && message.thinkingSteps && message.thinkingSteps.length > 0 && (
          <div className="w-full mb-3">
            <ReasoningDisplay
              steps={message.thinkingSteps}
              isStreaming={isStreaming}
              isCollapsed={isReasoningCollapsed}
              onToggleCollapse={() => setIsReasoningCollapsed(!isReasoningCollapsed)}
              onCopy={handleCopyReasoning}
            />
          </div>
        )}

        {/* Stock Chart Card - show before message content for assistant messages */}
        {ticker && !isUser && (
          <div className="w-full mb-3">
            <StockChartCard ticker={ticker} />
          </div>
        )}

        {displayContent && (isUser ? (
          <div className="px-5 py-3.5 rounded-3xl bg-blue-600 text-white shadow-sm">
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{displayContent}</p>
          </div>
        ) : (
          <div className="px-5 py-3.5 rounded-3xl bg-white border border-gray-100 text-gray-800 shadow-sm">
            <div className="markdown-content text-[15px] leading-relaxed overflow-x-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
            </div>
          </div>
        ))}
      </div>

      {isUser && (
        <div className="bg-blue-600 w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm mt-1">
          <User className="w-3.5 h-3.5 text-white" strokeWidth={2} />
        </div>
      )}
    </div>
  );
}

export default MessageComponent;
