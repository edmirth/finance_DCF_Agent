import { useState } from 'react';
import { DollarSign, TrendingUp, Send } from 'lucide-react';
import { Message, ThinkingStep } from '../types';
import { streamMessage } from '../api';
import MessageComponent from '../components/Message';
import StatusIndicator from '../components/StatusIndicator';

function EarningsPage() {
  const [ticker, setTicker] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentStatus, setCurrentStatus] = useState('');
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);

  const analyzeEarnings = async () => {
    if (!ticker.trim()) return;

    setIsLoading(true);
    setCurrentStatus('Initializing earnings analysis...');
    setThinkingSteps([]);

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: `Analyze ${ticker.toUpperCase()}'s latest earnings and forward outlook`,
      timestamp: new Date(),
    };

    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      thinkingSteps: [],
    };

    setMessages(prev => [...prev, userMessage, assistantMessage]);

    try {
      await streamMessage(
        `Analyze ${ticker.toUpperCase()}'s latest earnings and forward outlook`,
        'earnings',
        (event) => {
          if (event.type === 'thinking') {
            setCurrentStatus(event.content || 'Processing...');
          } else if (event.type === 'thought') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'thought',
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => [...prev, step]);
          } else if (event.type === 'tool') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'tool',
              tool: event.tool,
              input: event.input,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => [...prev, step]);
            setCurrentStatus(`Using ${event.tool}...`);
          } else if (event.type === 'tool_result') {
            const step: ThinkingStep = {
              id: Date.now().toString() + Math.random(),
              type: 'tool_result',
              content: event.content,
              timestamp: new Date(),
            };
            setThinkingSteps(prev => [...prev, step]);
          } else if (event.type === 'content' && event.content) {
            setCurrentStatus('Generating analysis...');
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
                  ? { ...msg, thinkingSteps: thinkingSteps }
                  : msg
              )
            );
            setIsLoading(false);
            setCurrentStatus('');
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
            setCurrentStatus('');
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
          setCurrentStatus('');
          setThinkingSteps([]);
        }
      );
    } catch (error) {
      console.error('Error analyzing earnings:', error);
      setIsLoading(false);
      setCurrentStatus('');
      setThinkingSteps([]);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isLoading && ticker.trim()) {
      analyzeEarnings();
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-gray-50 to-gray-100 p-8 pl-28">
      <div className="max-w-7xl mx-auto">
        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-gradient-to-br from-yellow-500 to-yellow-600 rounded-xl shadow-lg shadow-yellow-600/30">
              <DollarSign className="w-6 h-6 text-white" strokeWidth={2.5} />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Earnings Analyst</h1>
              <p className="text-sm text-gray-600">Fast earnings-focused equity research with quarterly trends and estimates</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Ticker Input */}
          <div className="space-y-6">
            {/* Ticker Input Card */}
            <div className="bg-white rounded-2xl shadow-sm p-6 border border-gray-200 hover:shadow-md transition-shadow duration-200">
              <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
                <div className="p-1.5 bg-yellow-100 rounded-lg">
                  <TrendingUp className="w-4 h-4 text-yellow-600" />
                </div>
                Analyze Earnings
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
                    Ticker Symbol
                  </label>
                  <div className="relative">
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 p-1.5 bg-yellow-100 rounded-lg">
                      <DollarSign className="w-4 h-4 text-yellow-600" />
                    </div>
                    <input
                      type="text"
                      placeholder="AAPL, NVDA, MSFT..."
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value.toUpperCase())}
                      onKeyPress={handleKeyPress}
                      className="w-full pl-14 pr-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-yellow-500 focus:border-yellow-500 transition-all duration-200 bg-gray-50 focus:bg-white font-medium"
                    />
                  </div>
                </div>

                <button
                  onClick={analyzeEarnings}
                  disabled={!ticker.trim() || isLoading}
                  className="w-full py-3 bg-gradient-to-r from-yellow-500 to-yellow-600 text-white rounded-xl font-semibold hover:from-yellow-600 hover:to-yellow-700 disabled:from-gray-300 disabled:to-gray-300 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-yellow-600/30 hover:shadow-xl hover:shadow-yellow-600/40 disabled:shadow-none flex items-center justify-center gap-2"
                >
                  <Send className="w-4 h-4" />
                  {isLoading ? 'Analyzing...' : 'Analyze Earnings'}
                </button>
              </div>

              {/* Info Card */}
              <div className="mt-6 p-4 bg-gradient-to-r from-yellow-50 to-yellow-50/50 rounded-xl border border-yellow-200">
                <h3 className="text-xs font-bold text-yellow-900 uppercase tracking-wider mb-2">What You'll Get</h3>
                <ul className="space-y-1.5 text-sm text-yellow-800">
                  <li className="flex items-start gap-2">
                    <span className="text-yellow-600 mt-0.5">•</span>
                    <span>Quarterly earnings trends (last 8 quarters)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-yellow-600 mt-0.5">•</span>
                    <span>Earnings surprises vs analyst estimates</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-yellow-600 mt-0.5">•</span>
                    <span>Management guidance analysis</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-yellow-600 mt-0.5">•</span>
                    <span>Forward outlook and valuation context</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-yellow-600 mt-0.5">•</span>
                    <span>BUY/HOLD/SELL rating with price target</span>
                  </li>
                </ul>
              </div>

              {/* Example Queries */}
              <div className="mt-6">
                <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-3">Example Queries</h3>
                <div className="space-y-2">
                  {['NVDA', 'AAPL', 'MSFT', 'GOOGL'].map((symbol) => (
                    <button
                      key={symbol}
                      onClick={() => setTicker(symbol)}
                      disabled={isLoading}
                      className="w-full text-left px-4 py-2.5 bg-gradient-to-r from-gray-50 to-gray-50/50 hover:from-yellow-50 hover:to-yellow-50/50 border border-gray-200 hover:border-yellow-300 rounded-lg transition-all duration-200 text-sm font-medium text-gray-700 hover:text-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Analyze {symbol} earnings
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Right Column - Analysis Results */}
          <div className="bg-white rounded-2xl shadow-sm p-6 border border-gray-200 hover:shadow-md transition-shadow duration-200">
            <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
              <div className="p-1.5 bg-yellow-100 rounded-lg">
                <TrendingUp className="w-4 h-4 text-yellow-600" />
              </div>
              Earnings Analysis
            </h2>

            {messages.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <DollarSign className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium mb-2">No analysis yet</p>
                <p className="text-sm">Enter a ticker symbol and click "Analyze Earnings" to get started</p>
              </div>
            ) : (
              <div className="space-y-6 max-h-[calc(100vh-16rem)] overflow-y-auto">
                {messages.map((message) => (
                  <MessageComponent
                    key={message.id}
                    message={message}
                    agent={{
                      id: 'earnings',
                      name: 'Earnings Analyst',
                      description: 'Earnings analysis',
                      example: '',
                      icon: '💰',
                      color: 'bg-yellow-600',
                    }}
                  />
                ))}

                <StatusIndicator status={currentStatus} isVisible={isLoading} thinkingSteps={thinkingSteps} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default EarningsPage;
