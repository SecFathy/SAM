"""OpenAI SDK wrapper for vLLM inference."""

from __future__ import annotations

import json
from typing import AsyncIterator

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionChunk,
    ChatCompletionMessageParam,
)

from sam.config import Settings
from sam.models.streaming import StreamAccumulator
from sam.models.tool_protocol import (
    convert_accumulator_with_hermes,
    inject_tools_into_system,
)


class ModelProvider:
    """Async wrapper around OpenAI SDK pointed at vLLM."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.hermes_mode = settings.hermes_tool_calling
        self.client = AsyncOpenAI(
            base_url=settings.api_base,
            api_key=settings.api_key,
        )

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> StreamAccumulator:
        """Send a chat completion request and accumulate the streamed response."""
        kwargs: dict = {
            "model": self.settings.model_id,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if stream:
            response = await self.client.chat.completions.create(**kwargs)
            accumulator = StreamAccumulator()
            async for chunk in response:
                accumulator.process_chunk(chunk)
                yield accumulator
        else:
            response = await self.client.chat.completions.create(**kwargs)
            accumulator = StreamAccumulator.from_complete(response)
            yield accumulator

    async def chat_complete(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[dict] | None = None,
    ) -> StreamAccumulator:
        """Non-streaming chat completion. Returns final accumulator."""
        msgs = list(messages)

        # Hermes mode: inject tools into system prompt instead of native tool calling
        if self.hermes_mode and tools:
            msgs = self._inject_hermes_tools(msgs, tools)
            api_tools = None
        else:
            api_tools = tools

        kwargs: dict = {
            "model": self.settings.model_id,
            "messages": msgs,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": False,
        }
        if api_tools:
            kwargs["tools"] = api_tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        acc = StreamAccumulator.from_complete(response)

        # Hermes mode: parse <tool_call> XML from text output
        if self.hermes_mode:
            acc = convert_accumulator_with_hermes(acc)

        return acc

    async def stream_chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamAccumulator]:
        """Stream chat completion, yielding accumulator at each chunk."""
        msgs = list(messages)

        if self.hermes_mode and tools:
            msgs = self._inject_hermes_tools(msgs, tools)
            api_tools = None
        else:
            api_tools = tools

        kwargs: dict = {
            "model": self.settings.model_id,
            "messages": msgs,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": True,
        }
        if api_tools:
            kwargs["tools"] = api_tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        accumulator = StreamAccumulator()
        async for chunk in response:
            accumulator.process_chunk(chunk)
            yield accumulator

        # Hermes mode: post-process final accumulator to extract tool calls from text
        if self.hermes_mode:
            convert_accumulator_with_hermes(accumulator)

    def _inject_hermes_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> list[dict]:
        """Inject tool definitions into the system prompt for Hermes-style calling."""
        msgs = list(messages)
        if msgs and msgs[0].get("role") == "system":
            msgs[0] = {
                **msgs[0],
                "content": inject_tools_into_system(msgs[0]["content"], tools),
            }
        else:
            # No system message — prepend one with tool definitions
            msgs.insert(0, {
                "role": "system",
                "content": inject_tools_into_system("", tools),
            })
        return msgs
