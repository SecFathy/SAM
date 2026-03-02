"""Conversation history with token tracking."""

from __future__ import annotations

from typing import Any

import tiktoken


class ConversationHistory:
    """Manages conversation messages and tracks token usage."""

    def __init__(self, context_window: int = 32768) -> None:
        self.messages: list[dict] = []
        self.context_window = context_window
        self._encoder: tiktoken.Encoding | None = None

    @property
    def encoder(self) -> tiktoken.Encoding:
        if self._encoder is None:
            try:
                self._encoder = tiktoken.encoding_for_model("gpt-4")
            except Exception:
                self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder

    def add_system(self, content: str) -> None:
        """Set or replace the system message."""
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = content
        else:
            self.messages.insert(0, {"role": "system", "content": content})

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str, tool_calls: list[dict] | None = None) -> None:
        msg: dict = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def get_messages(self) -> list[dict]:
        return list(self.messages)

    def estimate_tokens(self) -> int:
        """Rough token count of the entire conversation."""
        total = 0
        for msg in self.messages:
            content = msg.get("content", "")
            if content:
                total += len(self.encoder.encode(content))
            # Account for tool calls
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    total += len(self.encoder.encode(func.get("name", "")))
                    total += len(self.encoder.encode(func.get("arguments", "")))
            # Overhead per message
            total += 4
        return total

    @property
    def needs_condensation(self) -> bool:
        """Check if we've exceeded 75% of context window."""
        return self.estimate_tokens() > int(self.context_window * 0.75)

    def to_serializable(self) -> list[dict]:
        """Return messages in a JSON-serializable format."""
        return self.messages

    @classmethod
    def from_serializable(cls, messages: list[dict], context_window: int = 32768) -> ConversationHistory:
        history = cls(context_window=context_window)
        history.messages = messages
        return history
