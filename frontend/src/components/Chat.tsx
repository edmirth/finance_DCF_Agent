import { useState, useRef, useEffect, useCallback } from 'react';
import { Message, Agent, ThinkingStep, UploadedFile } from '../types';
import { streamMessage, uploadDocument } from '../api';
import MessageComponent from './Message';
import ChatInput from './ChatInput';
import FileUploadModal from './FileUploadModal';
import { X } from 'lucide-react';

const ANALYSIS_AGENT_TYPES = new Set(['dcf', 'analyst', 'earnings', 'graph']);

interface ChatProps {
  agent: Agent;
  agents: Agent[];
  onSelectAgent: (agent: Agent) => void;
  /** Restore a previous session — pre-populate messages */
  initialMessages?: Message[];
  /** Fixed session ID to use (from URL ?session= param) */
  sessionId?: string;
  /** Watchlist ticker chips to show above the input */
  watchlistTickers?: string[];
  /** Called when a watchlist chip is clicked */
  onWatchlistChipClick?: (ticker: string) => void;
  /** Called when an analysis response is received (to show save toast) */
  onAnalysisSaved?: () => void;
  /** Called when the user adds a ticker via the [+ Add] chip */
  onAddWatchlistTicker?: (ticker: string) => Promise<void>;
}

function Chat({
  agent,
  agents,
  onSelectAgent,
  initialMessages,
  sessionId: sessionIdProp,
  watchlistTickers = [],
  onWatchlistChipClick,
  onAnalysisSaved,
  onAddWatchlistTicker,
}: ChatProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages ?? []);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Use provided session ID or generate a new stable one
  const sessionId = useRef(sessionIdProp || crypto.randomUUID());
  const previousAgentId = useRef<string>(agent.id);
  const thinkingStepsRef = useRef<ThinkingStep[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<UploadedFile[]>([]);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [showAddTicker, setShowAddTicker] = useState(false);
  const [newTickerInput, setNewTickerInput] = useState('');

  // Sync sessionId if prop changes (new session restored from URL)
  useEffect(() => {
    if (sessionIdProp) {
      sessionId.current = sessionIdProp;
    }
  }, [sessionIdProp]);

  // Restore messages when initialMessages changes
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      setMessages(initialMessages);
    }
  }, [initialMessages]);

  useEffect(() => {
    if (previousAgentId.current !== agent.id && messages.length > 0) {
      const label = agent.id === 'auto' ? 'Auto mode (smart routing)' : agent.name;
      const systemMessage: Message = {
        id: Date.now().toString(),
        role: 'system',
        content: `Switched to **${label}**`,
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

  const handleFilesAdded = useCallback(async (files: File[]) => {
    setIsUploading(true);
    for (const file of files) {
      const id = Date.now().toString() + Math.random().toString(36).slice(2);
      const placeholder: UploadedFile = {
        id,
        name: file.name,
        size: file.size,
        type: file.type,
        content: '',
        status: 'uploading',
      };
      setAttachedFiles(prev => [...prev, placeholder]);

      try {
        const result = await uploadDocument(file);
        setAttachedFiles(prev =>
          prev.map(f => f.id === id ? { ...f, content: result.content, status: 'ready' as const } : f)
        );
      } catch (err: any) {
        const message = err?.response?.data?.detail || err?.message || 'Upload failed';
        setAttachedFiles(prev =>
          prev.map(f => f.id === id ? { ...f, status: 'error' as const, error: message } : f)
        );
      }
    }
    setIsUploading(false);
  }, []);

  const handleFileRemove = useCallback((id: string) => {
    setAttachedFiles(prev => prev.filter(f => f.id !== id));
  }, []);

  /**
   * Core send function — adds user + assistant messages and streams the response.
   * Both handleSendMessage and handleQuickPromptSend delegate here.
   */
  const sendToAgent = (text: string) => {
    // Build message with document context if files are attached
    const readyFiles = attachedFiles.filter(f => f.status === 'ready');
    let messageToSend = text;
    if (readyFiles.length > 0) {
      const docContext = readyFiles
        .map(f => `[Attached: ${f.name}]\n${f.content}`)
        .join('\n\n---\n\n');
      messageToSend = `${docContext}\n\n---\n\n${text}`;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setAttachedFiles([]);
    setIsLoading(true);
    setThinkingSteps([]);
    thinkingStepsRef.current = [];

    const isAutoMode = agent.id === 'auto';
    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      agentType: isAutoMode ? undefined : agent.id,
      isAutoRouted: isAutoMode,
      thinkingSteps: [],
    };

    setMessages(prev => [...prev, assistantMessage]);

    const addThinkingStep = (step: ThinkingStep) => {
      setThinkingSteps(prev => {
        const updated = [...prev, step];
        thinkingStepsRef.current = updated;
        return updated;
      });
    };

    const updateLastThinkingStep = (
      matchType: string,
      updater: (step: ThinkingStep) => ThinkingStep
    ) => {
      setThinkingSteps(prev => {
        const updated = [...prev];
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].type === matchType && updated[i].isStreaming) {
            updated[i] = updater(updated[i]);
            break;
          }
        }
        thinkingStepsRef.current = updated;
        return updated;
      });
    };

    const updateAssistantContent = (append: string) => {
      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMessageId
            ? { ...msg, content: msg.content + append }
            : msg
        )
      );
    };

    const finishStream = (error?: string, resolvedAgentType?: string) => {
      if (error) {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === assistantMessageId
              ? { ...msg, content: `Error: ${error}` }
              : msg
          )
        );
      } else {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === assistantMessageId
              ? { ...msg, thinkingSteps: thinkingStepsRef.current }
              : msg
          )
        );
        // Fire sidebar refresh event (includes session ID so URL can update)
        window.dispatchEvent(new CustomEvent('sessionSaved', { detail: { sessionId: sessionId.current } }));
        // Notify parent if this was an analysis agent
        if (resolvedAgentType && ANALYSIS_AGENT_TYPES.has(resolvedAgentType)) {
          onAnalysisSaved?.();
        }
      }
      setIsLoading(false);
      setThinkingSteps([]);
    };

    // Track the resolved agent type for post-stream logic
    let resolvedAgentType = agent.id;

    streamMessage(
      {
        message: messageToSend,
        agent_type: agent.id, // 'auto' or specific agent id
        model: 'claude-sonnet-4-5-20250929',
        session_id: sessionId.current,
      },
      (event) => {
        if (event.type === 'routing_decision' && event.agent) {
          resolvedAgentType = event.agent;
          // Backend selected an agent via auto-routing — update the message
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, agentType: event.agent, routedAgent: event.agent }
                : msg
            )
          );
        } else if (event.type === 'ticker_metadata' && event.ticker) {
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, ticker: event.ticker }
                : msg
            )
          );
        } else if (event.type === 'thought' || event.type === 'agent_thought') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: event.type,
            content: event.content,
            timestamp: new Date(),
          });
        } else if (event.type === 'tool') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'tool',
            tool: event.tool,
            input: event.input,
            timestamp: new Date(),
          });
        } else if (event.type === 'tool_result') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'tool_result',
            content: event.content,
            timestamp: new Date(),
          });
        } else if (event.type === 'phase_start') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'phase_start',
            phase: event.phase as any,
            content: event.content,
            timestamp: new Date(),
          });
        } else if (event.type === 'search_query') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'search_query',
            searchQuery: event.query,
            content: event.query,
            timestamp: new Date(),
          });
        } else if (event.type === 'source_review') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'source_review',
            source: event.source,
            content: event.source?.title || '',
            timestamp: new Date(),
          });
        } else if (event.type === 'plan_created' || event.type === 'plan_updated') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: event.type,
            plan: event.plan,
            timestamp: new Date(),
          });
        } else if (event.type === 'reflection') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'reflection',
            content: event.content,
            timestamp: new Date(),
          });
        } else if (event.type === 'thinking_start') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'thinking_start',
            phase: (event.phase as any) || 'reasoning',
            thinkingText: '',
            isStreaming: true,
            timestamp: new Date(),
          });
        } else if (event.type === 'thinking_chunk' && event.content) {
          updateLastThinkingStep('thinking_start', (step) => ({
            ...step,
            thinkingText: (step.thinkingText || '') + event.content,
          }));
        } else if (event.type === 'thinking_end') {
          updateLastThinkingStep('thinking_start', (step) => ({
            ...step,
            isStreaming: false,
          }));
        } else if (event.type === 'reflection_start') {
          addThinkingStep({
            id: Date.now().toString() + Math.random(),
            type: 'reflection_start',
            reflectionText: '',
            isStreaming: true,
            timestamp: new Date(),
          });
        } else if (event.type === 'reflection_chunk' && event.content) {
          updateLastThinkingStep('reflection_start', (step) => ({
            ...step,
            reflectionText: (step.reflectionText || '') + event.content,
          }));
        } else if (event.type === 'reflection_end') {
          updateLastThinkingStep('reflection_start', (step) => ({
            ...step,
            isStreaming: false,
            content: step.reflectionText,
          }));
        } else if (event.type === 'follow_ups' && event.questions) {
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, followUps: event.questions }
                : msg
            )
          );
        } else if (event.type === 'token_delta' && event.content) {
          updateAssistantContent(event.content);
        } else if (event.type === 'content' && event.content) {
          updateAssistantContent(event.content);
        } else if (event.type === 'end') {
          finishStream(undefined, resolvedAgentType);
        } else if (event.type === 'error') {
          finishStream(event.error);
        }
      },
      (error) => {
        finishStream(error);
      }
    ).catch((error) => {
      console.error('Error sending message:', error);
      setIsLoading(false);
      setThinkingSteps([]);
    });
  };

  const handleSendMessage = () => {
    if (!input.trim() || isLoading) return;
    sendToAgent(input.trim());
  };

  const handleQuickPromptSend = (text: string) => {
    if (isLoading) return;
    sendToAgent(text);
  };


  const handleAddNewTicker = async () => {
    const ticker = newTickerInput.trim().toUpperCase();
    if (!ticker) { setShowAddTicker(false); return; }
    await onAddWatchlistTicker?.(ticker);
    setNewTickerInput('');
    setShowAddTicker(false);
  };

  // Watchlist chip bar — shown above the input in both welcome and conversation views
  const WatchlistBar = (watchlistTickers.length > 0 || onAddWatchlistTicker) ? (
    <div
      className="flex items-center gap-2 flex-wrap mb-3"
      style={{ minHeight: '32px' }}
    >
      {watchlistTickers.map(ticker => (
        <button
          key={ticker}
          onClick={() => {
            if (!isLoading) sendToAgent(`Analyze ${ticker}`);
            onWatchlistChipClick?.(ticker);
          }}
          style={{
            padding: '4px 10px',
            borderRadius: '8px',
            fontSize: '0.75rem',
            fontWeight: 700,
            fontFamily: 'IBM Plex Mono, monospace',
            letterSpacing: '0.02em',
            background: '#F3F4F6',
            color: '#374151',
            border: '1px solid #E5E7EB',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = '#1A1A1A';
            e.currentTarget.style.color = '#FFFFFF';
            e.currentTarget.style.borderColor = '#1A1A1A';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = '#F3F4F6';
            e.currentTarget.style.color = '#374151';
            e.currentTarget.style.borderColor = '#E5E7EB';
          }}
        >
          {ticker}
        </button>
      ))}
      {onAddWatchlistTicker && (
        showAddTicker ? (
          <input
            autoFocus
            value={newTickerInput}
            onChange={e => setNewTickerInput(e.target.value.toUpperCase())}
            onKeyDown={e => {
              if (e.key === 'Enter') handleAddNewTicker();
              if (e.key === 'Escape') { setShowAddTicker(false); setNewTickerInput(''); }
            }}
            onBlur={handleAddNewTicker}
            placeholder="AAPL"
            maxLength={5}
            style={{
              width: '70px',
              padding: '4px 8px',
              borderRadius: '8px',
              border: '1px solid #10B981',
              fontSize: '0.75rem',
              fontWeight: 700,
              fontFamily: 'IBM Plex Mono, monospace',
              outline: 'none',
              color: '#1A1A1A',
            }}
          />
        ) : (
          <button
            onClick={() => setShowAddTicker(true)}
            style={{
              padding: '4px 10px',
              borderRadius: '8px',
              fontSize: '0.75rem',
              fontWeight: 500,
              fontFamily: 'Inter, sans-serif',
              background: 'none',
              color: '#9CA3AF',
              border: '1px dashed #D1D5DB',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = '#10B981';
              e.currentTarget.style.color = '#10B981';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = '#D1D5DB';
              e.currentTarget.style.color = '#9CA3AF';
            }}
          >
            + Add
          </button>
        )
      )}
    </div>
  ) : null;

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
            {WatchlistBar}
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSendMessage}
              isLoading={isLoading}
              placeholder="Ask Phronesis anything..."
              agents={agents}
              selectedAgent={agent}
              onSelectAgent={onSelectAgent}
              onQuickPromptSend={handleQuickPromptSend}
              onPaperclipClick={() => setShowUploadModal(true)}
              attachedFileCount={attachedFiles.filter(f => f.status === 'ready').length}
            />
            {attachedFiles.length > 0 && (
              <div className="file-badges-row" style={{ marginTop: '0.5rem' }}>
                {attachedFiles.map(f => (
                  <span key={f.id} className="file-badge">
                    {f.name}
                    <button onClick={() => handleFileRemove(f.id)}><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            )}
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
                onFollowUpClick={sendToAgent}
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
            {WatchlistBar}
            {attachedFiles.length > 0 && (
              <div className="file-badges-row" style={{ marginBottom: '0.5rem' }}>
                {attachedFiles.map(f => (
                  <span key={f.id} className="file-badge">
                    {f.name}
                    <button onClick={() => handleFileRemove(f.id)}><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            )}
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSendMessage}
              isLoading={isLoading}
              placeholder="Ask a follow up..."
              agents={agents}
              selectedAgent={agent}
              onSelectAgent={onSelectAgent}
              onQuickPromptSend={handleQuickPromptSend}
              onPaperclipClick={() => setShowUploadModal(true)}
              attachedFileCount={attachedFiles.filter(f => f.status === 'ready').length}
            />
          </div>
        </div>
      )}

      <FileUploadModal
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        attachedFiles={attachedFiles}
        onFilesAdded={handleFilesAdded}
        onFileRemove={handleFileRemove}
        isUploading={isUploading}
      />
    </div>
  );
}

export default Chat;
