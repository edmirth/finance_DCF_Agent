"""
Custom callback handler for displaying agent reasoning in a user-friendly way.

Similar to how Perplexity and Claude show their thinking process.
"""
import os
import sys
from typing import Any, Dict, List, Optional
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
import logging
import re

# Add parent directory to path to import shared constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.constants import TOOL_DESCRIPTIONS

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
        self.plan_shown = False  # Track if we've shown the plan already

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

        # Get human-friendly description from shared constants
        description = TOOL_DESCRIPTIONS.get(tool_name, f'🔍 Using {tool_name}')

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

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        """
        Capture and display plan, thoughts, and reflections from LLM output.

        This method extracts structured reasoning from the LLM's text response.
        """
        # Get the LLM's text output
        if not response.generations or not response.generations[0]:
            return

        llm_output = response.generations[0][0].text

        # Extract and display plan (only once at the beginning)
        plan = self._extract_plan(llm_output)
        if plan and not self.plan_shown:
            self._display_plan(plan)
            self.plan_shown = True

        # Extract and display reflection (after each tool call)
        reflection = self._extract_reflection(llm_output)
        if reflection:
            self._display_reflection(reflection)

    def _extract_plan(self, text: str) -> Optional[List[str]]:
        """
        Extract numbered plan steps from LLM output.

        Looks for "**PLAN:**" header followed by numbered items.
        Returns list of plan steps if found, None otherwise.
        """
        # Look for "PLAN:" or "Plan:" header (with or without asterisks)
        plan_match = re.search(r'\*\*PLAN:\*\*|Plan:', text, re.IGNORECASE)
        if not plan_match:
            return None

        # Extract numbered items (1. 2. 3. etc.) from after the PLAN header
        plan_section = text[plan_match.end():]

        # Match numbered items, handling multi-line content
        steps = re.findall(r'^\s*(\d+)\.\s*(.+?)(?=\n\s*\d+\.|$)', plan_section, re.MULTILINE | re.DOTALL)

        # Require minimum 2 steps for a valid plan
        if len(steps) >= 2:
            return [step[1].strip() for step in steps]
        return None

    def _display_plan(self, steps: List[str]):
        """
        Display the agent's plan in a clean format.

        Shows numbered steps with a header.
        """
        if not self.verbose:
            return

        msg = "\n📋 **PLAN:**\n"
        for i, step in enumerate(steps, 1):
            msg += f"   {i}. {step}\n"
        msg += "\n"

        self._emit_update("planning", msg)

    def _extract_reflection(self, text: str) -> Optional[str]:
        """
        Extract reflection from LLM output.

        Looks for "Reflection:" followed by the reflection text.
        Returns cleaned reflection text if found, None otherwise.
        """
        # Match "Reflection:" followed by text until double newline or next major section
        match = re.search(r'Reflection:\s*(.+?)(?=\n\n|Action:|$)', text, re.DOTALL)
        return match.group(1).strip() if match else None

    def _display_reflection(self, reflection: str):
        """
        Display agent's reflection after a tool call.

        Shows what the agent learned and what it plans to do next.
        """
        if not self.verbose:
            return

        msg = f"\n💭 **REFLECTION:** {reflection}\n"
        self._emit_update("reflection", msg)

    def reset(self):
        """Reset the callback state for a new conversation."""
        super().reset()
        self.plan_shown = False  # Reset plan display flag
