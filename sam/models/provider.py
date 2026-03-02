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


class ModelProvider:
    """Async wrapper around OpenAI SDK pointed at vLLM."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
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
        kwargs: dict = {
            "model": self.settings.model_id,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        return StreamAccumulator.from_complete(response)

    async def stream_chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamAccumulator]:
        """Stream chat completion, yielding accumulator at each chunk."""
        kwargs: dict = {
            "model": self.settings.model_id,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        accumulator = StreamAccumulator()
        async for chunk in response:
            accumulator.process_chunk(chunk)
            yield accumulator
