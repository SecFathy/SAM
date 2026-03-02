"""Stream chunk accumulator for OpenAI streaming responses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ToolCallAccumulator:
    """Accumulates a single tool call across stream chunks."""

    id: str = ""
    name: str = ""
    arguments: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.id and self.name and self.arguments)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }

    def parsed_arguments(self) -> dict:
        """Parse the JSON arguments, with fallback for malformed JSON."""
        try:
            return json.loads(self.arguments)
        except json.JSONDecodeError:
            # Try to fix common issues: trailing comma, unclosed braces
            fixed = self.arguments.rstrip().rstrip(",")
            # Count braces
            open_braces = fixed.count("{") - fixed.count("}")
            fixed += "}" * open_braces
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return {}


@dataclass
class StreamAccumulator:
    """Accumulates streaming chat completion chunks into a complete response."""

    content: str = ""
    tool_calls: dict[int, ToolCallAccumulator] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: dict | None = None
    _content_delta: str = ""

    @property
    def content_delta(self) -> str:
        """Get the latest content delta (reset after reading)."""
        delta = self._content_delta
        self._content_delta = ""
        return delta

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def tool_call_list(self) -> list[ToolCallAccumulator]:
        return [self.tool_calls[i] for i in sorted(self.tool_calls.keys())]

    def process_chunk(self, chunk) -> None:
        """Process a single streaming chunk."""
        if not chunk.choices:
            # Usage-only chunk
            if chunk.usage:
                self.usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
            return

        choice = chunk.choices[0]
        delta = choice.delta

        if delta.content:
            self.content += delta.content
            self._content_delta = delta.content

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in self.tool_calls:
                    self.tool_calls[idx] = ToolCallAccumulator()

                acc = self.tool_calls[idx]
                if tc.id:
                    acc.id = tc.id
                if tc.function:
                    if tc.function.name:
                        acc.name = tc.function.name
                    if tc.function.arguments:
                        acc.arguments += tc.function.arguments

        if choice.finish_reason:
            self.finish_reason = choice.finish_reason

    @classmethod
    def from_complete(cls, response) -> StreamAccumulator:
        """Build accumulator from a non-streaming response."""
        acc = cls()
        choice = response.choices[0]
        message = choice.message

        if message.content:
            acc.content = message.content

        if message.tool_calls:
            for i, tc in enumerate(message.tool_calls):
                acc.tool_calls[i] = ToolCallAccumulator(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )

        acc.finish_reason = choice.finish_reason

        if response.usage:
            acc.usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return acc
