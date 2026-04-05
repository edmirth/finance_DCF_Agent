"""
Custom callback handler for displaying agent reasoning in a user-friendly way.

Similar to how Perplexity and Claude show their thinking process.
"""
import os
import sys
from typing import Any, Callable, Dict, List, Optional
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish
import logging

# Add parent directory to path to import shared constants (only if not already present)
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.append(_parent_dir)
from shared.constants import TOOL_DESCRIPTIONS

logger = logging.getLogger(__name__)


class ReasoningCallbackHandler(BaseCallbackHandler):
    """
    Callback handler that displays agent reasoning steps in a clean, professional format.

    Shows:
    - [Thinking]: What the agent is planning to do
    - [Searching]: When calling tools
    - [Analysis]: Interpreting results
    - [Done]: Final answer
    """

    def __init__(self, verbose: bool = True):
        """
        Initialize the reasoning callback handler.

        Args:
            verbose: Whether to show detailed reasoning (default: True)
        """
        self.verbose = verbose
        self.current_step = 0

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        """Called when agent decides to use a tool."""
        if not self.verbose:
            return

        self.current_step += 1
        tool_name = action.tool
        tool_input = action.tool_input

        print(f"\n[Step {self.current_step}: Planning]")
        print(f"   Using tool: `{tool_name}`")

        if isinstance(tool_input, dict):
            params = ", ".join([f"{k}={v}" for k, v in tool_input.items()])
            print(f"   Parameters: {params}")
        else:
            print(f"   Input: {tool_input}")

        print(f"\n[Executing...]")

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Called when a tool finishes execution."""
        if not self.verbose:
            return

        print(f"[OK] Data retrieved\n")

    def on_tool_error(self, error: Exception, **kwargs: Any) -> Any:
        """Called when a tool encounters an error."""
        if not self.verbose:
            return

        print(f"\n[ERROR] {str(error)}\n")

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        """Called when agent finishes and has a final answer."""
        if not self.verbose:
            return

        print(f"\n[Analysis Complete]")
        print(f"----------------------------------------------------------------------\n")

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        """Called when LLM starts processing."""
        if self.current_step == 0 and self.verbose:
            print(f"\n[Analyzing your question...]\n")

    def reset(self):
        """Reset the callback state for a new conversation."""
        self.current_step = 0


class StreamingReasoningCallback(ReasoningCallbackHandler):
    """
    Enhanced callback that can stream reasoning to both console and a web callback.

    Useful for web interfaces where you want to show progress as it happens.
    The on_reasoning_update callback is wired by api_server.py when serving web requests.
    For CLI use it prints directly to stdout.
    """

    def __init__(self, verbose: bool = True, on_reasoning_update: Optional[Callable[[str, str], None]] = None):
        """
        Initialize streaming callback.

        Args:
            verbose: Whether to print to console
            on_reasoning_update: Optional callback function(step_type, message) for streaming updates
        """
        super().__init__(verbose)
        self.on_reasoning_update = on_reasoning_update

    def _emit_update(self, step_type: str, message: str):
        """Emit an update to both console and optional web callback."""
        if self.verbose:
            print(message)

        if self.on_reasoning_update:
            self.on_reasoning_update(step_type, message)

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        """Called when LLM starts — show initial thinking indicator."""
        if self.current_step == 0:
            self._emit_update("thinking", "\n[Analyzing your question...]\n")

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        """Called when agent decides to use a tool."""
        self.current_step += 1
        tool_name = action.tool
        tool_input = action.tool_input

        description = TOOL_DESCRIPTIONS.get(tool_name, f'[Using {tool_name}]')

        msg = f"\n[Step {self.current_step}] {description}"
        if isinstance(tool_input, dict):
            params = ", ".join([f"{k}={v}" for k, v in tool_input.items()])
            msg += f" ({params})"

        self._emit_update("searching", msg)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Called when tool finishes."""
        self._emit_update("result", "[OK] Done\n")

    def on_tool_error(self, error: Exception, **kwargs: Any) -> Any:
        """Called when a tool encounters an error."""
        self._emit_update("error", f"\n[ERROR] {str(error)}\n")

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        """Called when agent has a final answer."""
        self._emit_update("conclusion", "\n[Answer]\n")

    def reset(self):
        """Reset the callback state for a new conversation."""
        super().reset()
