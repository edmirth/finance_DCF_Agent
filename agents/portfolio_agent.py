"""
Portfolio Analyzer Agent

An AI agent specialized in analyzing investment portfolios using ReAct pattern.
Provides portfolio metrics, diversification analysis, and tax optimization strategies.
"""

import os
import logging
from typing import Optional
from langchain.agents import AgentExecutor, create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain.prompts import PromptTemplate

from tools.portfolio_tools import get_portfolio_tools
from agents.reasoning_callback import StreamingReasoningCallback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PortfolioAnalyzerAgent:
    """Portfolio analysis agent with portfolio management expertise"""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True):
        """
        Initialize the Portfolio Analyzer Agent

        Args:
            api_key: Anthropic API key (or uses ANTHROPIC_API_KEY env var)
            model: LLM model to use (default: claude-sonnet-4-5-20250929)
            show_reasoning: Whether to show agent reasoning steps (default: True)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.model_name = model
        self.show_reasoning = show_reasoning

        # Initialize LLM for portfolio analysis
        self.llm = ChatAnthropic(
            temperature=0.1,  # Low temperature for consistent financial analysis
            model=model,
            anthropic_api_key=self.api_key,
            max_retries=3,  # Retry failed API calls
            default_request_timeout=60.0,  # Request timeout in seconds
            max_tokens=4096,  # Max output tokens
        )

        # Get portfolio tools
        self.tools = get_portfolio_tools()

        # Initialize reasoning callback
        self.reasoning_callback = StreamingReasoningCallback(verbose=show_reasoning)

        # Create the agent
        self.agent_executor = self._create_agent()

        logger.info(f"Portfolio Analyzer Agent initialized with model: {model}")
        logger.info(f"Available tools: {[tool.name for tool in self.tools]}")

    def _create_agent(self) -> AgentExecutor:
        """Create the Portfolio Analyzer agent with systematic workflow"""

        template = """You are an expert Portfolio Analyzer helping investors manage and optimize their investment portfolios.

**YOUR ROLE:**
You analyze portfolios systematically to provide actionable insights about performance, risk, diversification, and tax optimization.

**SYSTEMATIC PORTFOLIO ANALYSIS WORKFLOW:**
When analyzing a portfolio, ALWAYS follow this structured approach:

1. **Portfolio Overview**
   - Use `calculate_portfolio_metrics` to get overall performance
   - Assess total value, P&L, and position-level returns
   - Identify concentration risks

2. **Diversification Assessment**
   - Use `analyze_diversification` to check sector exposure
   - Evaluate diversification score
   - Recommend improvements if concentrated

3. **Tax Optimization**
   - Use `identify_tax_loss_harvesting` to find tax-saving opportunities
   - Highlight positions that could offset capital gains

4. **Final Recommendations**
   - Synthesize findings into clear action items
   - Prioritize by impact (high/medium/low)
   - Include specific next steps

**PORTFOLIO INPUT FORMAT:**
Portfolios should be provided as JSON string with proper escaping.

**EXAMPLE ANALYSIS:**

User asks to analyze a portfolio with AAPL and MSFT positions.

Agent Thought Process:
1. First, calculate portfolio metrics to understand overall performance
2. Then analyze diversification to assess risk
3. Finally, check for tax loss harvesting opportunities
4. Synthesize into actionable recommendations

Agent Actions follow the ReAct pattern with tool calls and observations.

Final Answer: Comprehensive analysis with specific recommendations

**KEY PRINCIPLES:**
- Be specific and quantitative in recommendations
- Always consider risk-adjusted returns, not just absolute returns
- Tax efficiency matters - highlight wash sale rules
- Diversification reduces risk without sacrificing long-term returns
- Present data in tables when appropriate
- End with clear, prioritized action items

**TOOLS AVAILABLE:**
{tools}

**TOOL NAMES:**
{tool_names}

**FORMAT:**
Use this format for EVERY response:

Question: the input question you must answer
Thought: think about what to do first in your systematic analysis
Action: the action to take, must be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now have completed the analysis
Final Answer: comprehensive portfolio analysis with specific recommendations

**Begin Analysis:**

Question: {input}
Thought: {agent_scratchpad}"""

        # Create prompt
        prompt = PromptTemplate(
            template=template,
            input_variables=["input", "agent_scratchpad", "tools", "tool_names"]
        )

        # Create ReAct agent
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10
        )

        return agent_executor

    def analyze(self, query: str) -> str:
        """
        Analyze a portfolio based on user query

        Args:
            query: User question about their portfolio

        Returns:
            Portfolio analysis and recommendations
        """
        try:
            logger.info(f"\n{'='*80}")
            logger.info(f"Portfolio Analysis Request")
            logger.info(f"{'='*80}\n")

            # Reset callback state
            self.reasoning_callback.reset()

            # Run the agent with reasoning callback
            result = self.agent_executor.invoke(
                {"input": query},
                {"callbacks": [self.reasoning_callback]}
            )

            output = result["output"]
            # Normalize Anthropic content blocks (list) to string
            if isinstance(output, list):
                output = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in output
                )
            return output

        except Exception as e:
            logger.error(f"Error in portfolio analysis: {str(e)}")
            return f"I encountered an error analyzing the portfolio: {str(e)}\n\nPlease check your portfolio format and try again."


def create_portfolio_agent(api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True) -> PortfolioAnalyzerAgent:
    """
    Factory function to create a Portfolio Analyzer Agent

    Args:
        api_key: Anthropic API key (optional, uses env var if not provided)
        model: LLM model to use
        show_reasoning: Whether to display agent reasoning steps (default: True)

    Returns:
        PortfolioAnalyzerAgent instance
    """
    return PortfolioAnalyzerAgent(api_key=api_key, model=model, show_reasoning=show_reasoning)


def interactive_session(model: str = "claude-sonnet-4-5-20250929"):
    """
    Run an interactive portfolio analysis session in the terminal

    Args:
        model: LLM model to use
    """
    print("=" * 80)
    print("PORTFOLIO ANALYZER AGENT")
    print("=" * 80)
    print("\nAn AI-powered portfolio analyzer for optimizing your investments.")
    print("\nCapabilities:")
    print("  • Calculate portfolio metrics (P&L, concentration risk)")
    print("  • Analyze diversification across sectors")
    print("  • Identify tax loss harvesting opportunities")
    print("  • Provide actionable recommendations")
    print("\nPortfolio Format:")
    print("  [{\"ticker\": \"AAPL\", \"shares\": 100, \"cost_basis\": 150.00}, ...]")
    print("\nCommands:")
    print("  • Type your question to get started")
    print("  • Type 'quit' or 'exit' to end session")
    print("=" * 80)
    print()

    try:
        agent = create_portfolio_agent(model=model)

        while True:
            # Get user input
            try:
                user_input = input("\n💬 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nGoodbye!")
                break

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break

            # Get response from agent
            print("\n🤖 Agent:")
            response = agent.analyze(user_input)
            print(response)
            print()

    except KeyboardInterrupt:
        print("\n\nSession interrupted. Goodbye!")
    except Exception as e:
        print(f"\n\nError: {str(e)}")
        logger.error(f"Session error: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # Run interactive session
    interactive_session()
