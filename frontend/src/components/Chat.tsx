import { useState, useRef, useEffect } from 'react';
import { Message, Agent, ThinkingStep } from '../types';
import { streamMessage } from '../api';
import MessageComponent from './Message';
import ChatInput from './ChatInput';
import { Sparkles, BarChart3, TrendingUp, Search, Globe, Briefcase, DollarSign } from 'lucide-react';

interface ChatProps {
  agent: Agent;
  agents: Agent[];
  onSelectAgent: (agent: Agent) => void;
}

const agentIcons: Record<string, any> = {
  dcf: BarChart3,
  analyst: TrendingUp,
  research: Search,
  market: Globe,
  portfolio: Briefcase,
  earnings: DollarSign,
};

function Chat({ agent, agents, onSelectAgent }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useRef(Math.random().toString(36).substring(7));
  const previousAgentId = useRef<string>(agent.id);
  // Use ref to track current thinking steps to avoid stale closures
  const thinkingStepsRef = useRef<ThinkingStep[]>([]);

  useEffect(() => {
    // Add system message when agent changes (only if actually changed and has messages)
    if (previousAgentId.current !== agent.id && messages.length > 0) {
      const systemMessage: Message = {
        id: Date.now().toString(),
        role: 'system',
        content: `Switched to **${agent.name}**. All future messages will be handled by this agent.`,
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

    // Create placeholder for assistant message
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
          model: 'gpt-4-turbo-preview',
          session_id: sessionId.current,
        },
        (event) => {
          if (event.type === 'start') {
            // Agent started processing
          } else if (event.type === 'ticker_metadata' && event.ticker) {
            // Store ticker metadata in the assistant message
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, ticker: event.ticker }
                  : msg
              )
            );
          } else if (event.type === 'thinking') {
            // Agent is thinking
          } else if (event.type === 'thought') {
            // Add thinking step
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'thought',
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'tool') {
            // Add tool usage step
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
            // Add tool result step
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
          } else if (event.type === 'agent_thought') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'agent_thought',
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'plan_created') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'plan_created',
              plan: event.plan,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => {
              const updated = [...prev, step];
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'plan_updated') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'plan_updated',
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
            // Start a new thinking block
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
            // Append to the current thinking block
            setThinkingSteps(prev => {
              const updated = [...prev];
              // Find the most recent thinking_start step and append to its thinkingText
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
            // Mark the thinking block as complete
            setThinkingSteps(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].type === 'thinking_start' && updated[i].isStreaming) {
                  updated[i] = {
                    ...updated[i],
                    isStreaming: false,
                  };
                  break;
                }
              }
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'reflection_start') {
            // Start a new reflection block
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
            // Append to the current reflection block
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
            // Mark the reflection block as complete
            setThinkingSteps(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].type === 'reflection_start' && updated[i].isStreaming) {
                  updated[i] = {
                    ...updated[i],
                    isStreaming: false,
                    content: updated[i].reflectionText, // Copy to content for backward compatibility
                  };
                  break;
                }
              }
              thinkingStepsRef.current = updated;
              return updated;
            });
          } else if (event.type === 'token_delta' && event.content) {
            // Token-by-token streaming from LLM
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + event.content }
                  : msg
              )
            );
          } else if (event.type === 'content' && event.content) {
            // Fallback for non-streaming (50-char chunks)
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + event.content }
                  : msg
              )
            );
          } else if (event.type === 'end') {
            // Save thinking steps to the message before clearing
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

  return (
    <div className="flex flex-col min-h-screen">
      {/* Welcome Screen */}
      {messages.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-4 pb-64">
          <div className="mb-8">
            <div className="w-16 h-16 bg-gray-900 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg">
              {(() => {
                const Icon = agentIcons[agent.id];
                return <Icon className="w-8 h-8 text-white" strokeWidth={2} />;
              })()}
            </div>
            <h2 className="text-3xl font-semibold text-gray-900 mb-3">
              {agent.name}
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl">
              {agent.description}
            </p>
          </div>

          {/* Example Prompts */}
          <div className="max-w-2xl w-full space-y-3">
            <p className="text-sm text-gray-500 mb-4 flex items-center justify-center gap-2">
              <Sparkles className="w-4 h-4" />
              Try asking:
            </p>
            <button
              onClick={() => setInput(agent.example)}
              className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
            >
              <p className="text-gray-700 group-hover:text-gray-900">{agent.example}</p>
            </button>

            {agent.id === 'dcf' && (
              <>
                <button
                  onClick={() => setInput("What is Microsoft's intrinsic value?")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">What is Microsoft's intrinsic value?</p>
                </button>
                <button
                  onClick={() => setInput("Perform DCF analysis on TSLA")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">Perform DCF analysis on TSLA</p>
                </button>
              </>
            )}

            {agent.id === 'analyst' && (
              <>
                <button
                  onClick={() => setInput("Analyze NVDA's competitive moat and industry position")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">Analyze NVDA's competitive moat and industry position</p>
                </button>
                <button
                  onClick={() => setInput("What are Apple's competitive advantages?")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">What are Apple's competitive advantages?</p>
                </button>
              </>
            )}

            {agent.id === 'research' && (
              <>
                <button
                  onClick={() => setInput("Compare Amazon and Walmart's profit margins")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">Compare Amazon and Walmart's profit margins</p>
                </button>
                <button
                  onClick={() => setInput("What's the latest news on Tesla?")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">What's the latest news on Tesla?</p>
                </button>
              </>
            )}

            {agent.id === 'market' && (
              <>
                <button
                  onClick={() => setInput("What's the current market sentiment?")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">What's the current market sentiment?</p>
                </button>
                <button
                  onClick={() => setInput("Analyze the technology sector performance")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">Analyze the technology sector performance</p>
                </button>
              </>
            )}

            {agent.id === 'portfolio' && (
              <>
                <button
                  onClick={() => setInput("Analyze my portfolio: [{'ticker': 'AAPL', 'shares': 100, 'cost_basis': 150.00}, {'ticker': 'MSFT', 'shares': 50, 'cost_basis': 250.00}, {'ticker': 'GOOGL', 'shares': 25, 'cost_basis': 100.00}]")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">Analyze my tech portfolio (AAPL, MSFT, GOOGL)</p>
                </button>
                <button
                  onClick={() => setInput("What are my tax loss harvesting opportunities in this portfolio: [{'ticker': 'TSLA', 'shares': 100, 'cost_basis': 300.00}, {'ticker': 'NVDA', 'shares': 50, 'cost_basis': 450.00}]")}
                  className="w-full p-4 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl text-left transition-colors duration-200 group"
                >
                  <p className="text-gray-700 group-hover:text-gray-900">Find tax loss harvesting opportunities</p>
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Messages */}
      {messages.length > 0 && (
        <div className="flex-1 overflow-y-auto">
          <div className="min-h-full flex flex-col justify-end">
            <div className="w-full space-y-6 px-4 pt-8 pb-32">
              {messages.map((message, index) => (
                <MessageComponent
                  key={message.id}
                  message={{
                    ...message,
                    // Attach current thinking steps to the streaming message
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
        </div>
      )}

      {/* Input - Fixed at bottom */}
      <div className="fixed bottom-0 left-20 right-0 bg-gradient-to-t from-gray-50 via-gray-50 to-transparent pt-8 pb-8">
        <div className="max-w-3xl mx-auto px-4">
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSendMessage}
            isLoading={isLoading}
            placeholder={`Ask about markets, stocks, or financial analysis...`}
            agents={agents}
            selectedAgent={agent}
            onSelectAgent={onSelectAgent}
          />
        </div>
      </div>
    </div>
  );
}

export default Chat;