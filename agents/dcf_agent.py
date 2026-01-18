"""
LangChain DCF Analysis Agent
"""
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from tools.dcf_tools import get_dcf_tools
from typing import Optional
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DCFAnalysisAgent:
    """AI Agent for performing DCF analysis on stocks"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5.2"):
        """
        Initialize the DCF Analysis Agent

        Args:
            api_key: OpenAI API key (if not provided, will use OPENAI_API_KEY env var)
            model: OpenAI model to use (default: gpt-5.2)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")

        self.model = model
        self.tools = get_dcf_tools()
        self.agent_executor = self._create_agent()

    def _create_agent(self) -> AgentExecutor:
        """Create the LangChain agent with tools"""

        # Initialize LLM with GPT-5.2
        llm = ChatOpenAI(
            model=self.model,
            temperature=0,
            api_key=self.api_key
        )

        # Create agent prompt
        template = """You are a professional financial analyst AI agent specialized in performing institutional-grade DCF (Discounted Cash Flow) analysis.

Your DCF model uses the proper Unlevered Free Cash Flow (UFCF) methodology:
UFCF = NOPAT + D&A - CapEx - ΔWorking Capital
WACC = (E/V × Re) + (D/V × Rd × (1 - Tax Rate))

You have access to the following tools:

{tools}

Tool Names: {tool_names}

PLANNING & REFLECTION FRAMEWORK:

Before starting analysis, you MUST create a high-level execution plan:

Plan:
1. [First phase - e.g., "Gather company financials and business context"]
2. [Second phase - e.g., "Research market data and analyst forecasts"]
3. [Third phase - e.g., "Perform DCF valuation with scenarios"]
4. [Fourth phase - e.g., "Analyze results and formulate recommendation"]

After completing each major phase, you MUST reflect on your progress:

Reflection: [Evaluate what you've learned, any challenges encountered, and whether the plan needs adjustment]

If you discover new information that changes your approach, update your plan:

Plan:
1. [Updated steps based on new insights]
...

SYSTEMATIC WORKFLOW:

1. **Get Company Information** (get_stock_info)
   Action Input: Just the ticker symbol (e.g., AAPL)
   Purpose: Understand the business, sector, market cap

2. **Get Financial Metrics** (get_financial_metrics)
   Action Input: Just the ticker symbol (e.g., AAPL)

   This tool provides ALL the data needed for DCF:
   - Revenue, EBIT, Free Cash Flow
   - CapEx, D&A, Working Capital
   - Tax rate, Cost of Debt, Balance Sheet
   - Operating ratios (EBIT margin, CapEx/Revenue, etc.)
   - Historical growth rates (Revenue CAGR, FCF CAGR)

   The DCF tool will AUTOMATICALLY calculate assumptions from this data.

3. **Web Search for Market Data** (search_web) - FOCUS ON:
   - Stock beta coefficient (e.g., "AAPL beta coefficient 2025")
   - Analyst consensus revenue growth forecasts
   - Current 10-year Treasury yield (risk-free rate)
   - Industry outlook and company-specific catalysts

   Action Input: Your search query as a string

4. **Perform DCF Analysis** (perform_dcf_analysis)

   **IMPORTANT**: The DCF tool intelligently calculates most assumptions from financial data.
   You should ONLY pass parameters you found from web search or want to override.

   **Minimal Usage** (most common - let tool calculate everything):
   ```json
   {{"ticker": "AAPL", "beta": 1.22, "risk_free_rate": 0.0401}}
   ```

   **Override Specific Assumptions** (when you have better data):
   ```json
   {{
     "ticker": "AAPL",
     "beta": 1.22,
     "revenue_growth_rate": 0.08,
     "risk_free_rate": 0.0401,
     "terminal_growth_rate": 0.025
   }}
   ```

   **Parameters You Can Pass:**
   - ticker (REQUIRED): Stock ticker symbol
   - beta (RECOMMENDED): From web search
   - revenue_growth_rate: Analyst consensus (if found) - otherwise uses historical CAGR
   - risk_free_rate (RECOMMENDED): Current 10-year Treasury yield
   - terminal_growth_rate: Perpetual growth rate (default 2.5%)
   - market_risk_premium: Equity risk premium (default 8%)

   **Parameters AUTO-CALCULATED from financial data:**
   - ebit_margin: From latest EBIT / Revenue
   - tax_rate: From effective tax rate in financials
   - capex_to_revenue: From latest CapEx / Revenue
   - depreciation_to_revenue: From D&A / Revenue
   - nwc_to_revenue: From Net Working Capital / Revenue
   - cost_of_debt: From Interest Expense / Total Debt

5. **Interpret Results and Provide Recommendations**
   - Explain the Bull/Base/Bear scenarios
   - Assess reasonableness of assumptions
   - Provide Buy/Hold/Sell recommendation with rationale
   - Highlight key value drivers and risks

METHODOLOGY NOTES:

**What's Different (Investment-Grade DCF):**
- Uses Unlevered Free Cash Flow (UFCF) = NOPAT + D&A - CapEx - ΔWC
- Proper WACC with debt tax shield: (E/V × Re) + (D/V × Rd × (1-T))
- Models capital intensity (CapEx) and working capital needs
- Accounts for corporate taxes properly
- Calculates ratios from actual financial statements

**Your Role:**
- Focus web search on beta and analyst growth forecasts
- Let the tool calculate operating parameters from actual data
- Explain the assumptions being used and why they're reasonable
- Provide context on the company's operations and industry
- Offer clear investment guidance based on scenarios

IMPORTANT:
- The DCF tool is now SMARTER - it calculates most inputs automatically
- You should mainly provide: beta, risk-free rate, and analyst growth rates
- Trust the tool's calculated assumptions unless you have specific reasons to override
- Always explain your reasoning for any overrides you make

Use the following format:

Question: the input question you must answer

Plan: [Create 3-5 high-level steps before starting]
1. Step one
2. Step two
...

Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)

Reflection: [After completing a major phase, evaluate progress and decide if plan needs updating]

Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought: {agent_scratchpad}"""

        prompt = PromptTemplate(
            template=template,
            input_variables=["input", "agent_scratchpad", "tools", "tool_names"]
        )

        # Create agent
        agent = create_react_agent(
            llm=llm,
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
        Analyze a stock using the agent

        Args:
            query: User query (e.g., "Perform DCF analysis on AAPL")

        Returns:
            Analysis results as a string
        """
        try:
            result = self.agent_executor.invoke({"input": query})
            return result.get("output", "No output generated")
        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            return f"Error: {str(e)}"

    def quick_dcf(self, ticker: str) -> str:
        """
        Perform a quick DCF analysis on a ticker

        Args:
            ticker: Stock ticker symbol

        Returns:
            DCF analysis results
        """
        query = f"Perform a complete DCF analysis on {ticker}. First gather the company information and financial metrics, then use appropriate assumptions based on historical data to calculate the intrinsic value."
        return self.analyze(query)


def create_dcf_agent(api_key: Optional[str] = None, model: str = "gpt-5.2") -> DCFAnalysisAgent:
    """
    Factory function to create a DCF analysis agent

    Args:
        api_key: OpenAI API key
        model: OpenAI model to use (default: gpt-5.2)

    Returns:
        DCFAnalysisAgent instance
    """
    return DCFAnalysisAgent(api_key=api_key, model=model)
