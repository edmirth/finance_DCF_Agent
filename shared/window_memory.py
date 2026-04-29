"""
Lightweight conversation memory that keeps only the last k chat turns.

This avoids LangChain's deprecated memory abstractions while preserving the
behavior the agents rely on: storing recent user/assistant turns and injecting
them into the prompt as `chat_history`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, get_buffer_string


@dataclass
class WindowConversationMemory:
    k: int = 5
    memory_key: str = "history"
    return_messages: bool = False
    output_key: Optional[str] = None
    input_key: Optional[str] = None
    human_prefix: str = "Human"
    ai_prefix: str = "AI"
    messages: list[BaseMessage] = field(default_factory=list)

    @property
    def memory_variables(self) -> list[str]:
        return [self.memory_key]

    @property
    def buffer_as_messages(self) -> list[BaseMessage]:
        return self.messages[-self.k * 2 :] if self.k > 0 else []

    @property
    def buffer_as_str(self) -> str:
        return get_buffer_string(
            self.buffer_as_messages,
            human_prefix=self.human_prefix,
            ai_prefix=self.ai_prefix,
        )

    @property
    def buffer(self) -> str | list[BaseMessage]:
        return self.buffer_as_messages if self.return_messages else self.buffer_as_str

    def load_memory_variables(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {self.memory_key: self.buffer}

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, Any]) -> None:
        input_str = self._get_input_value(inputs)
        output_str = self._get_output_value(outputs)
        self.messages.extend(
            [
                HumanMessage(content=input_str),
                AIMessage(content=output_str),
            ]
        )
        if self.k > 0:
            self.messages = self.messages[-self.k * 2 :]

    def clear(self) -> None:
        self.messages = []

    def _get_input_value(self, inputs: dict[str, Any]) -> str:
        if self.input_key is not None:
            return str(inputs.get(self.input_key, ""))

        for key, value in inputs.items():
            if key not in self.memory_variables:
                return str(value)
        return ""

    def _get_output_value(self, outputs: dict[str, Any]) -> str:
        if self.output_key is not None:
            return self._stringify(outputs.get(self.output_key, ""))

        if len(outputs) == 1:
            return self._stringify(next(iter(outputs.values())))

        if "output" in outputs:
            return self._stringify(outputs["output"])

        raise ValueError(
            f"Got multiple output keys: {outputs.keys()}, cannot determine which to store in memory."
        )

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in value
            )
        return str(value) if value is not None else ""
