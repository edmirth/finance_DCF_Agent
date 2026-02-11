import { useState, useRef, useEffect } from 'react';
import { Message, Agent, ThinkingStep } from '../types';
import { streamMessage } from '../api';
import MessageComponent from './Message';
import ChatInput from './ChatInput';
import { BarChart3, TrendingUp, Search, Globe } from 'lucide-react';

interface ChatProps {
  agent: Agent;
  agents: Agent[];
  onSelectAgent: (agent: Agent) => void;
}

function Chat({ agent, agents, onSelectAgent }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useRef(Math.random().toString(36).substring(7));
  const previousAgentId = useRef<string>(agent.id);
  const thinkingStepsRef = useRef<ThinkingStep[]>([]);

  useEffect(() => {
    if (previousAgentId.current !== agent.id && messages.length > 0) {
      const systemMessage: Message = {
        id: Date.now().toString(),
        role: 'system',
        content: `Switched to **${agent.name}**`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, systemMessage]);
    }
    previousAgentId.current = agent.id;
  }, [agent.id, agent.name]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setThinkingSteps([]);
    thinkingStepsRef.current = [];

    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      agentType: agent.id,
      thinkingSteps: [],
    };

    setMessages(prev => [...prev, assistantMessage]);

    try {
      await streamMessage(
        {
          message: userMessage.content,
          agent_type: agent.id,
          model: 'claude-sonnet-4-5-20250929',
          session_id: sessionId.current,
        },
        (event) => {
          if (event.type === 'ticker_metadata' && event.ticker) {
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, ticker: event.ticker }
                  : msg
              )
            );
          } else if (event.type === 'thought' || event.type === 'agent_thought') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: event.type,
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'tool') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'tool',
              tool: event.tool,
              input: event.input,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'tool_result') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'tool_result',
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'phase_start') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'phase_start',
              phase: event.phase as any,
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'search_query') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'search_query',
              searchQuery: event.query,
              content: event.query,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'source_review') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'source_review',
              source: event.source,
              content: event.source?.title || '',
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'plan_created' || event.type === 'plan_updated') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: event.type,
              plan: event.plan,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'reflection') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'reflection',
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'thinking_start') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'thinking_start',
              phase: (event.phase as any) || 'reasoning',
              thinkingText: '',
              isStreaming: true,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'thinking_chunk' && event.content) {
            setThinkingSteps(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].type === 'thinking_start' && updated[i].isStreaming) {
                  updated[i] = {
                    ...updated[i],
                    thinkingText: (updated[i].thinkingText || '') + event.content,
                  };
                  break;
                }
              }
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'thinking_end') {
            setThinkingSteps(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].type === 'thinking_start' && updated[i].isStreaming) {
                  updated[i] = { ...updated[i], isStreaming: false };
                  break;
                }
              }
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'reflection_start') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'reflection_start',
              reflectionText: '',
              isStreaming: true,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'reflection_chunk' && event.content) {
            setThinkingSteps(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].type === 'reflection_start' && updated[i].isStreaming) {
                  updated[i] = {
                    ...updated[i],
                    reflectionText: (updated[i].reflectionText || '') + event.content,
                  };
                  break;
                }
              }
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'reflection_end') {
            setThinkingSteps(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].type === 'reflection_start' && updated[i].isStreaming) {
                  updated[i] = {
                    ...updated[i],
                    isStreaming: false,
                    content: updated[i].reflectionText,
                  };
                  break;
                }
              }
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'token_delta' && event.content) {
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + event.content }
                  : msg
              )
            );
          } else if (event.type === 'content' && event.content) {
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + event.content }
                  : msg
              )
            );
          } else if (event.type === 'end') {
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, thinkingSteps: thinkingStepsRef.current }
                  : msg
              )
            );
            setIsLoading(false);
            setThinkingSteps([]);
          } else if (event.type === 'error') {
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: `Error: ${event.error}` }
                  : msg
              )
            );
            setIsLoading(false);
            setThinkingSteps([]);
          }
        },
        (error) => {
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, content: `Error: ${error}` }
                : msg
            )
          );
          setIsLoading(false);
          setThinkingSteps([]);
        }
      );
    } catch (error) {
      console.error('Error sending message:', error);
      setIsLoading(false);
      setThinkingSteps([]);
    }
  };

  // Quick action definitions
  const quickActions = [
    { icon: Search, label: 'Research Stock', query: 'What are the latest developments and financial outlook for ' },
    { icon: TrendingUp, label: 'Equity Analysis', query: "Analyze the competitive moat and industry position of " },
    { icon: Globe, label: 'Market Overview', query: "What's the current market sentiment and key trends?" },
    { icon: BarChart3, label: 'Compare Stocks', query: 'Compare the financial performance of AAPL vs MSFT' },
  ];

  return (
    <div className="flex flex-col min-h-screen">
      {/* Welcome Screen */}
      {messages.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center px-4" style={{ marginTop: '-5vh' }}>
          {/* Title */}
          <h1 className="home-title mb-10 text-center animate-fade-in">
            What can Phronesis help with today?
          </h1>

          {/* Input box */}
          <div className="w-full max-w-[600px] mb-6 animate-fade-in" style={{ animationDelay: '0.1s', animationFillMode: 'both' }}>
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSendMessage}
              isLoading={isLoading}
              placeholder="Ask Phronesis anything..."
              agents={agents}
              selectedAgent={agent}
              onSelectAgent={onSelectAgent}
            />
          </div>

          {/* Quick actions */}
          <div className="flex flex-wrap justify-center gap-1 animate-fade-in" style={{ animationDelay: '0.2s', animationFillMode: 'both' }}>
            {quickActions.map(({ icon: Icon, label, query }) => (
              <button
                key={label}
                className="quick-action-chip"
                onClick={() => setInput(query)}
              >
                <div className="chip-icon">
                  <Icon className="w-3.5 h-3.5" />
                </div>
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      {messages.length > 0 && (
        <div className="flex-1 overflow-y-auto pt-8 pb-32">
          <div className="space-y-6">
            {messages.map((message, index) => (
              <MessageComponent
                key={message.id}
                message={{
                  ...message,
                  thinkingSteps: (isLoading && index === messages.length - 1)
                    ? thinkingSteps
                    : message.thinkingSteps
                }}
                agent={agent}
                isStreaming={isLoading && index === messages.length - 1}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {/* Input - Fixed at bottom (only when messages exist) */}
      {messages.length > 0 && (
        <div
          className="fixed bottom-0 left-20 right-0 pb-6 pt-4 z-20"
          style={{ background: 'linear-gradient(to top, #FFFFFF 60%, transparent)' }}
        >
          <div className="max-w-[720px] mx-auto px-6">
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSendMessage}
              isLoading={isLoading}
              placeholder="Ask a follow up..."
              agents={agents}
              selectedAgent={agent}
              onSelectAgent={onSelectAgent}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default Chat;
