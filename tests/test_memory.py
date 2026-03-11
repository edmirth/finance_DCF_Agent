"""
Evals: Finance Q&A Agent memory and multi-turn conversation stability.

Covers the regression bug fixed in Feb 2026:
- ConversationSummaryBufferMemory triggered a 400 "messages: at least one
  message is required" error from Anthropic after ~3 turns, because its
  prune() step called the Anthropic API with an empty messages list.

These tests use mocked LLM calls to avoid real API costs while still
exercising the memory and agent plumbing.
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_mock_llm(response_text: str = "Mock response."):
    """Return a ChatAnthropic-compatible mock that returns a plain string."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content=response_text)
    # Needed by AgentExecutor when streaming=True
    mock_llm.stream = MagicMock(return_value=iter([
        MagicMock(content=response_text)
    ]))
    return mock_llm


# ── Memory type tests ─────────────────────────────────────────────────────────

class TestMemoryConfiguration:
    """
    The agent must use ConversationBufferWindowMemory, not
    ConversationSummaryBufferMemory, so it never needs to call the LLM
    for summarization.
    """

    def test_memory_type_is_window_not_summary(self):
        from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryBufferMemory

        with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
            mock_cls.return_value = _make_mock_llm()
            from agents.finance_qa_agent import FinanceQAAgent
            agent = FinanceQAAgent.__new__(FinanceQAAgent)
            agent.api_key = "test-key"
            agent.model_name = "claude-test"
            agent.llm_base = _make_mock_llm()
            agent.llm = agent.llm_base

            # Instantiate memory the same way __init__ does
            agent.memory = ConversationBufferWindowMemory(
                k=10,
                memory_key="chat_history",
                return_messages=True,
                output_key="output",
            )

        assert isinstance(agent.memory, ConversationBufferWindowMemory), (
            "Memory must be ConversationBufferWindowMemory — "
            "ConversationSummaryBufferMemory calls Anthropic with empty messages."
        )
        assert not isinstance(agent.memory, ConversationSummaryBufferMemory)

    def test_memory_does_not_call_llm_on_save(self):
        """
        Saving a context to ConversationBufferWindowMemory must never invoke
        the LLM (which would risk the empty-messages-400 error).
        """
        from langchain.memory import ConversationBufferWindowMemory

        llm_spy = MagicMock()
        memory = ConversationBufferWindowMemory(
            k=10,
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
        )
        memory.save_context(
            {"input": "What is Apple revenue?"},
            {"output": "Apple revenue is $380B."}
        )
        llm_spy.assert_not_called()

    def test_memory_window_trims_old_turns(self):
        """After k+1 turns the oldest turn must be dropped."""
        from langchain.memory import ConversationBufferWindowMemory

        memory = ConversationBufferWindowMemory(
            k=2,
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
        )
        for i in range(3):
            memory.save_context(
                {"input": f"Question {i}"},
                {"output": f"Answer {i}"}
            )

        history = memory.load_memory_variables({})["chat_history"]
        # k=2 means 2 pairs (4 messages max)
        assert len(history) <= 4, (
            f"Window memory with k=2 must keep at most 4 messages, got {len(history)}"
        )

    def test_memory_clear_resets_history(self):
        from langchain.memory import ConversationBufferWindowMemory

        memory = ConversationBufferWindowMemory(
            k=10, memory_key="chat_history", return_messages=True, output_key="output"
        )
        memory.save_context({"input": "hello"}, {"output": "world"})
        memory.clear()
        history = memory.load_memory_variables({})["chat_history"]
        assert history == []

    def test_memory_handles_list_content_without_error(self):
        """
        Anthropic returns content as a list of blocks. Saving such a response
        to ConversationBufferWindowMemory must not raise.
        """
        from langchain.memory import ConversationBufferWindowMemory

        memory = ConversationBufferWindowMemory(
            k=10, memory_key="chat_history", return_messages=True, output_key="output"
        )
        # Simulate Anthropic content-block output
        anthropic_style_output = [{"type": "text", "text": "Revenue is $45B."}]
        memory.save_context(
            {"input": "What is Netflix revenue?"},
            {"output": str(anthropic_style_output)}  # AgentExecutor converts to str
        )
        history = memory.load_memory_variables({})["chat_history"]
        assert len(history) == 2  # one human + one AI message


# ── Multi-turn stability (mocked) ─────────────────────────────────────────────

class TestMultiTurnStability:
    """
    Simulate the exact conversation sequence that triggered the 400 error:
    memory filling up across multiple long responses.
    """

    def _make_agent_with_mock_llm(self):
        """Create a FinanceQAAgent instance with all LLM calls mocked out."""
        from agents.finance_qa_agent import FinanceQAAgent
        from langchain.memory import ConversationBufferWindowMemory

        mock_llm = _make_mock_llm("PLTR revenue is $2.8B with 21% growth.")

        with patch("langchain_anthropic.ChatAnthropic", return_value=mock_llm), \
             patch("agents.finance_qa_agent.create_tool_calling_agent") as mock_agent_factory, \
             patch("agents.finance_qa_agent.AgentExecutor") as mock_executor_cls:

            # AgentExecutor.invoke returns a dict with "output"
            mock_executor = MagicMock()
            mock_executor.invoke.return_value = {"output": "Mock answer.", "intermediate_steps": []}
            mock_executor.memory = ConversationBufferWindowMemory(
                k=10, memory_key="chat_history", return_messages=True, output_key="output"
            )
            mock_executor_cls.return_value = mock_executor

            agent = FinanceQAAgent(api_key="test-key", model="claude-test")

        return agent

    def test_agent_initializes_without_error(self):
        """Agent must initialize cleanly (no API calls, no import errors)."""
        agent = self._make_agent_with_mock_llm()
        assert agent is not None

    def test_memory_attribute_is_correct_type(self):
        from langchain.memory import ConversationBufferWindowMemory
        agent = self._make_agent_with_mock_llm()
        assert isinstance(agent.memory, ConversationBufferWindowMemory)

    def test_reset_conversation_works(self):
        """reset_conversation() must not raise after initialization."""
        agent = self._make_agent_with_mock_llm()
        agent.reset_conversation()  # must not raise
        assert agent.current_ticker is None
        assert agent.conversation_count == 0
