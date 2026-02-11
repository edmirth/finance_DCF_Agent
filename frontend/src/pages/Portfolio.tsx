import { useState } from 'react';
import { PortfolioHolding, Message, ThinkingStep } from '../types';
import { streamMessage } from '../api';
import { Plus, Trash2, TrendingUp, DollarSign, Hash, Send, Briefcase } from 'lucide-react';
import MessageComponent from '../components/Message';
import StatusIndicator from '../components/StatusIndicator';

function Portfolio() {
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([]);
  const [newHolding, setNewHolding] = useState({
    ticker: '',
    shares: '',
    cost_basis: '',
  });
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentStatus, setCurrentStatus] = useState('');
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const sessionId = Math.random().toString(36).substring(7);

  const addHolding = () => {
    if (!newHolding.ticker || !newHolding.shares || !newHolding.cost_basis) {
      return;
    }

    const holding: PortfolioHolding = {
      id: Date.now().toString(),
      ticker: newHolding.ticker.toUpperCase(),
      shares: parseFloat(newHolding.shares),
      cost_basis: parseFloat(newHolding.cost_basis),
    };

    setHoldings([...holdings, holding]);
    setNewHolding({ ticker: '', shares: '', cost_basis: '' });
  };

  const removeHolding = (id: string) => {
    setHoldings(holdings.filter(h => h.id !== id));
  };

  const analyzePortfolio = async (analysisType: 'overview' | 'diversification' | 'tax') => {
    if (holdings.length === 0) {
      return;
    }

    setIsLoading(true);
    setCurrentStatus('Analyzing portfolio...');
    setThinkingSteps([]);

    const portfolioJson = JSON.stringify(
      holdings.map(h => ({
        ticker: h.ticker,
        shares: h.shares,
        cost_basis: h.cost_basis,
      }))
    );

    let query = '';
    if (analysisType === 'overview') {
      query = `Analyze my portfolio: ${portfolioJson}`;
    } else if (analysisType === 'diversification') {
      query = `Analyze the diversification of my portfolio: ${portfolioJson}`;
    } else if (analysisType === 'tax') {
      query = `Find tax loss harvesting opportunities in my portfolio: ${portfolioJson}`;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);

    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      agentType: 'portfolio',
      thinkingSteps: [],
    };

    setMessages(prev => [...prev, assistantMessage]);

    try {
      await streamMessage(
        {
          message: query,
          agent_type: 'portfolio',
          model: 'claude-sonnet-4-5-20250929',
          session_id: sessionId,
        },
        (event) => {
          if (event.type === 'start') {
            setCurrentStatus('Processing portfolio data...');
          } else if (event.type === 'thinking') {
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
      console.error('Error analyzing portfolio:', error);
      setIsLoading(false);
      setCurrentStatus('');
      setThinkingSteps([]);
    }
  };

  const totalValue = holdings.reduce((sum, h) => sum + (h.shares * h.cost_basis), 0);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-gray-50 to-gray-100 p-8 pl-28">
      <div className="max-w-7xl mx-auto">
        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl shadow-lg shadow-gray-900/30">
              <Briefcase className="w-6 h-6 text-white" strokeWidth={2.5} />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Portfolio Manager</h1>
              <p className="text-sm text-gray-600">Track and analyze your investment portfolio with AI</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Portfolio Holdings */}
          <div className="space-y-6">
            {/* Add Holding Card */}
            <div className="bg-white rounded-2xl shadow-sm p-6 border border-gray-200 hover:shadow-md transition-shadow duration-200">
              <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
                <div className="p-1.5 bg-gray-100 rounded-lg">
                  <Plus className="w-4 h-4 text-gray-900" />
                </div>
                Add Holding
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
                    Ticker Symbol
                  </label>
                  <div className="relative">
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 p-1.5 bg-gray-100 rounded-lg">
                      <TrendingUp className="w-4 h-4 text-gray-900" />
                    </div>
                    <input
                      type="text"
                      placeholder="AAPL"
                      value={newHolding.ticker}
                      onChange={(e) => setNewHolding({ ...newHolding, ticker: e.target.value.toUpperCase() })}
                      className="w-full pl-14 pr-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-gray-900 focus:border-gray-900 transition-all duration-200 bg-gray-50 focus:bg-white font-medium"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
                    Number of Shares
                  </label>
                  <div className="relative">
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 p-1.5 bg-gray-100 rounded-lg">
                      <Hash className="w-4 h-4 text-gray-900" />
                    </div>
                    <input
                      type="number"
                      placeholder="100"
                      value={newHolding.shares}
                      onChange={(e) => setNewHolding({ ...newHolding, shares: e.target.value })}
                      className="w-full pl-14 pr-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-gray-900 focus:border-gray-900 transition-all duration-200 bg-gray-50 focus:bg-white font-medium"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
                    Cost Basis (per share)
                  </label>
                  <div className="relative">
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 p-1.5 bg-gray-100 rounded-lg">
                      <DollarSign className="w-4 h-4 text-gray-900" />
                    </div>
                    <input
                      type="number"
                      placeholder="150.00"
                      step="0.01"
                      value={newHolding.cost_basis}
                      onChange={(e) => setNewHolding({ ...newHolding, cost_basis: e.target.value })}
                      className="w-full pl-14 pr-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-gray-900 focus:border-gray-900 transition-all duration-200 bg-gray-50 focus:bg-white font-medium"
                    />
                  </div>
                </div>

                <button
                  onClick={addHolding}
                  disabled={!newHolding.ticker || !newHolding.shares || !newHolding.cost_basis}
                  className="w-full py-3 bg-gradient-to-r from-gray-800 to-gray-900 text-white rounded-xl font-semibold hover:from-gray-900 hover:to-black disabled:from-gray-300 disabled:to-gray-300 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-gray-900/30 hover:shadow-xl hover:shadow-gray-900/40 disabled:shadow-none flex items-center justify-center gap-2"
                >
                  <Plus className="w-5 h-5" />
                  Add to Portfolio
                </button>
              </div>
            </div>

            {/* Holdings List */}
            <div className="bg-white rounded-2xl shadow-sm p-6 border border-gray-200 hover:shadow-md transition-shadow duration-200">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold text-gray-900">Holdings</h2>
                <div className="px-3 py-1.5 bg-gradient-to-r from-gray-50 to-gray-100 rounded-lg border border-gray-200">
                  <span className="text-xs text-gray-600 font-medium">Total Value</span>
                  <p className="text-sm font-bold text-gray-900">${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                </div>
              </div>

              {holdings.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <Briefcase className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p>No holdings yet. Add your first position above.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {holdings.map((holding) => (
                    <div
                      key={holding.id}
                      className="group flex items-center justify-between p-4 bg-gradient-to-r from-gray-50 to-gray-50/50 hover:from-gray-100/50 hover:to-gray-100/30 rounded-xl border border-gray-200 hover:border-gray-300 transition-all duration-200"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <div className="px-3 py-1 bg-white rounded-lg border border-gray-200 group-hover:border-gray-400 transition-colors">
                            <span className="font-bold text-base text-gray-900">{holding.ticker}</span>
                          </div>
                          <span className="text-xs text-gray-600 font-medium">
                            {holding.shares} shares @ ${holding.cost_basis.toFixed(2)}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 font-medium">
                          Total Value: <span className="text-gray-900 font-semibold">${(holding.shares * holding.cost_basis).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => removeHolding(holding.id)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Analysis Buttons */}
              {holdings.length > 0 && (
                <div className="mt-6 space-y-3">
                  <button
                    onClick={() => analyzePortfolio('overview')}
                    disabled={isLoading}
                    className="w-full py-3 bg-gradient-to-r from-gray-800 to-gray-900 text-white rounded-xl font-semibold hover:from-gray-900 hover:to-black disabled:from-gray-300 disabled:to-gray-300 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-gray-900/30 hover:shadow-xl hover:shadow-gray-900/40 disabled:shadow-none flex items-center justify-center gap-2"
                  >
                    <Send className="w-4 h-4" />
                    Analyze Portfolio
                  </button>
                  <button
                    onClick={() => analyzePortfolio('diversification')}
                    disabled={isLoading}
                    className="w-full py-3 bg-gradient-to-r from-gray-700 to-gray-800 text-white rounded-xl font-semibold hover:from-gray-800 hover:to-gray-900 disabled:from-gray-300 disabled:to-gray-300 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-gray-800/30 hover:shadow-xl hover:shadow-gray-800/40 disabled:shadow-none flex items-center justify-center gap-2"
                  >
                    <Send className="w-4 h-4" />
                    Check Diversification
                  </button>
                  <button
                    onClick={() => analyzePortfolio('tax')}
                    disabled={isLoading}
                    className="w-full py-3 bg-gradient-to-r from-gray-600 to-gray-700 text-white rounded-xl font-semibold hover:from-gray-700 hover:to-gray-800 disabled:from-gray-300 disabled:to-gray-300 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-gray-700/30 hover:shadow-xl hover:shadow-gray-700/40 disabled:shadow-none flex items-center justify-center gap-2"
                  >
                    <Send className="w-4 h-4" />
                    Tax Loss Harvesting
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Analysis Results */}
          <div className="bg-white rounded-2xl shadow-sm p-6 border border-gray-200 hover:shadow-md transition-shadow duration-200">
            <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
              <div className="p-1.5 bg-gray-100 rounded-lg">
                <TrendingUp className="w-4 h-4 text-gray-900" />
              </div>
              Analysis Results
            </h2>

            {messages.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <TrendingUp className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium mb-2">No analysis yet</p>
                <p className="text-sm">Add holdings and click an analysis button to get started</p>
              </div>
            ) : (
              <div className="space-y-6 max-h-[calc(100vh-16rem)] overflow-y-auto">
                {messages.map((message) => (
                  <MessageComponent
                    key={message.id}
                    message={message}
                    agent={{
                      id: 'portfolio',
                      name: 'Portfolio Analyzer',
                      description: 'Portfolio analysis',
                      example: '',
                      icon: '💼',
                      color: 'bg-purple-600',
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

export default Portfolio;
