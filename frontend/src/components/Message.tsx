import { Message, Agent } from '../types';
import ReactMarkdown from 'react-markdown';
import { User, BarChart3, TrendingUp, Search, Globe } from 'lucide-react';
import ThinkingSteps from './ThinkingSteps';

const agentIcons: Record<string, any> = {
  dcf: BarChart3,
  analyst: TrendingUp,
  research: Search,
  market: Globe,
};

interface MessageProps {
  message: Message;
  agent: Agent;
}

function MessageComponent({ message, agent }: MessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  const AgentIcon = agentIcons[agent.id];

  // Don't render anything if message has no content
  if (!message.content) return null;

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

        <div
          className={`px-5 py-3.5 rounded-3xl ${
            isUser
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-white border border-gray-100 text-gray-800 shadow-sm'
          }`}
        >
          {isUser ? (
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.content}</p>
          ) : (
            <>
              <div className="markdown-content text-[15px] leading-relaxed">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
              {message.thinkingSteps && message.thinkingSteps.length > 0 && (
                <details className="mt-4 pt-4 border-t border-gray-100">
                  <summary className="cursor-pointer text-sm font-medium text-pink-600 hover:text-pink-700 mb-2">
                    View agent reasoning ({message.thinkingSteps.length} steps)
                  </summary>
                  <div className="mt-3">
                    <ThinkingSteps steps={message.thinkingSteps} />
                  </div>
                </details>
              )}
            </>
          )}
        </div>
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
