"""
Custom callback handler for displaying agent reasoning in a user-friendly way.

Similar to how Perplexity and Claude show their thinking process.
"""
from typing import Any, Dict, List, Optional
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
import logging

logger = logging.getLogger(__name__)


class ReasoningCallbackHandler(BaseCallbackHandler):
    """
    Callback handler that displays agent reasoning steps in a clean, professional format.

    Shows:
    - 💭 Thinking: What the agent is planning to do
    - 🔍 Searching: When calling tools
    - 📊 Analysis: Interpreting results
    - ✅ Conclusion: Final answer
    """

    def __init__(self, verbose: bool = True):
        """
        Initialize the reasoning callback handler.

        Args:
            verbose: Whether to show detailed reasoning (default: True)
        """
        self.verbose = verbose
        self.current_step = 0
        self.tool_inputs: Dict[str, Any] = {}

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        """
        Called when agent decides to use a tool.

        Shows what tool is being called and why.
        """
        if not self.verbose:
            return

        self.current_step += 1
        tool_name = action.tool
        tool_input = action.tool_input

        # Store for later reference
        self.tool_inputs[tool_name] = tool_input

        # Format the reasoning
        print(f"\n💭 **Step {self.current_step}: Planning**")
        print(f"   Using tool: `{tool_name}`")

        # Show what data we're fetching in human-readable format
        if isinstance(tool_input, dict):
            params = ", ".join([f"{k}={v}" for k, v in tool_input.items()])
            print(f"   Parameters: {params}")
        else:
            print(f"   Input: {tool_input}")

        print(f"\n🔍 **Executing...**")

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """
        Called when a tool finishes execution.

        Shows that the tool completed successfully.
        """
        if not self.verbose:
            return

        # Don't print the full output here - agent will analyze it
        print(f"✓ Data retrieved\n")

    def on_tool_error(self, error: Exception, **kwargs: Any) -> Any:
        """
        Called when a tool encounters an error.
        """
        if not self.verbose:
            return

        print(f"\n❌ **Error:** {str(error)}\n")

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        """
        Called when agent finishes and has a final answer.

        Shows the conclusion.
        """
        if not self.verbose:
            return

        print(f"\n📊 **Analysis Complete**")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        """
        Called when LLM starts processing.

        Can be used to show "thinking..." indicators.
        """
        # Only show for initial reasoning, not for every LLM call
        if self.current_step == 0 and self.verbose:
            print(f"\n🤔 **Analyzing your question...**\n")

    def reset(self):
        """Reset the callback state for a new conversation."""
        self.current_step = 0
        self.tool_inputs = {}


class StreamingReasoningCallback(ReasoningCallbackHandler):
    """
    Enhanced callback that can stream reasoning in real-time.

    Useful for web interfaces where you want to show progress as it happens.
    """

    def __init__(self, verbose: bool = True, on_reasoning_update: Optional[callable] = None):
        """
        Initialize streaming callback.

        Args:
            verbose: Whether to print to console
            on_reasoning_update: Optional callback function(step_type, message) for streaming updates
        """
        super().__init__(verbose)
        self.on_reasoning_update = on_reasoning_update

    def _emit_update(self, step_type: str, message: str):
        """
        Emit an update to both console and callback.

        Args:
            step_type: Type of step (thinking, searching, analysis, conclusion)
            message: The message to display
        """
        if self.verbose:
            print(message)

        if self.on_reasoning_update:
            self.on_reasoning_update(step_type, message)

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        """Override to use streaming updates."""
        self.current_step += 1
        tool_name = action.tool
        tool_input = action.tool_input

        self.tool_inputs[tool_name] = tool_input

        # Create human-friendly description of what we're doing
        friendly_descriptions = {
            'get_quick_data': '📊 Fetching financial metrics',
            'get_stock_info': 'ℹ️  Getting company information',
            'get_financial_metrics': '📈 Retrieving historical financials',
            'search_web': '🌐 Searching the web',
            'perform_dcf_analysis': '🧮 Running DCF valuation model',
            'calculate': '🔢 Performing calculation',
            'get_recent_news': '📰 Fetching recent news',
            'compare_companies': '⚖️  Comparing companies',
            'analyze_industry': '🏭 Analyzing industry structure',
            'analyze_competitors': '🥊 Analyzing competitive landscape',
            'analyze_moat': '🏰 Evaluating competitive moat',
            'analyze_management': '👔 Assessing management quality',
        }

        description = friendly_descriptions.get(tool_name, f'🔍 Using {tool_name}')

        msg = f"\n{description}"
        if isinstance(tool_input, dict):
            params = ", ".join([f"{k}={v}" for k, v in tool_input.items()])
            msg += f" ({params})"

        self._emit_update("searching", msg)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Override to use streaming updates."""
        self._emit_update("result", "✓ Done\n")

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        """Override to use streaming updates."""
        self._emit_update("conclusion", "\n📊 **Answer:**\n")
