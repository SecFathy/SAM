"""Core ReAct agent loop: Think -> Act -> Observe."""

from __future__ import annotations

import time
from pathlib import Path
from typing import AsyncIterator

from sam.agent.history import ConversationHistory
from sam.config import Settings
from sam.context import build_enriched_message
from sam.models.provider import ModelProvider
from sam.models.streaming import StreamAccumulator
from sam.tools.base import READONLY_TOOLS, ToolRegistry, ToolResult
from sam.ui.console import (
    console,
    print_assistant,
    print_error,
    print_tool_call,
    print_tool_result,
    print_warning,
)


class AgentLoop:
    """Core agentic loop implementing the ReAct pattern."""

    def __init__(
        self,
        settings: Settings,
        provider: ModelProvider,
        tools: ToolRegistry,
        history: ConversationHistory,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.tools = tools
        self.history = history
        self.plan_mode: bool = False
        self._pending_plan: str | None = None
        self._system_prompt_template: str = ""
        self._plan_prompt_template: str = ""
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        """Load the system prompt templates (normal + plan mode)."""
        prompts_dir = Path(__file__).parent.parent / "prompts"

        prompt_path = prompts_dir / "system.md"
        if prompt_path.exists():
            self._system_prompt_template = prompt_path.read_text()
        else:
            self._system_prompt_template = (
                "You are SAM, an AI coding assistant. "
                "Use the provided tools to help the user with their coding tasks. "
                "Working directory: {working_dir}\n{repo_map}"
            )

        plan_path = prompts_dir / "plan_mode.md"
        if plan_path.exists():
            self._plan_prompt_template = plan_path.read_text()
        else:
            self._plan_prompt_template = (
                "You are SAM in Plan Mode (read-only). "
                "Explore the code and produce a structured plan. "
                "Do NOT modify files. Working directory: {working_dir}\n{repo_map}"
            )

    def _build_system_prompt(self, repo_map: str = "") -> str:
        """Build the system prompt with current context."""
        repo_map_section = repo_map if repo_map else "No repository map available yet."
        template = self._plan_prompt_template if self.plan_mode else self._system_prompt_template
        return template.format(
            working_dir=str(self.settings.working_dir),
            repo_map=repo_map_section,
        )

    async def run_turn(self, user_message: str, repo_map: str = "") -> str:
        """Run a complete agent turn: user message -> (tool calls)* -> final response.

        Returns the final assistant text response.
        """
        # Update system prompt
        system_prompt = self._build_system_prompt(repo_map)
        self.history.add_system(system_prompt)

        # Resolve @file mentions and enrich the message
        enriched = build_enriched_message(user_message, self.settings.working_dir)

        # Add user message
        self.history.add_user(enriched)

        # Determine tool allow-list for this turn.
        allowed = READONLY_TOOLS if self.plan_mode else None

        final_text = ""
        iteration = 0

        while iteration < self.settings.max_iterations:
            iteration += 1

            # Call the LLM
            messages = self.history.get_messages()
            tool_schemas = self.tools.to_openai_schemas(allowed=allowed)

            try:
                accumulator = await self._call_llm(messages, tool_schemas)
            except Exception as e:
                error_msg = f"LLM call failed: {e}"
                print_error(error_msg)
                self.history.add_assistant(error_msg)
                return error_msg

            # Process the response
            if accumulator.content:
                print_assistant(accumulator.content)

            if accumulator.has_tool_calls:
                # Record assistant message with tool calls
                tool_call_dicts = [tc.to_dict() for tc in accumulator.tool_call_list]
                self.history.add_assistant(
                    content=accumulator.content or "",
                    tool_calls=tool_call_dicts,
                )

                # Execute each tool call
                for tc in accumulator.tool_call_list:
                    args = tc.parsed_arguments()
                    print_tool_call(tc.name, args)

                    result = await self.tools.execute(tc.name, args, allowed=allowed)
                    print_tool_result(result.output, result.error)

                    self.history.add_tool_result(
                        tool_call_id=tc.id,
                        content=result.output if not result.error else f"ERROR: {result.output}",
                    )

                # Continue the loop for more tool calls or final response
                continue
            else:
                # No tool calls — this is the final response
                final_text = accumulator.content or ""
                self.history.add_assistant(final_text)
                break

        if iteration >= self.settings.max_iterations:
            print_warning(f"Reached maximum iterations ({self.settings.max_iterations})")

        # Store plan for approval when in plan mode.
        if self.plan_mode and final_text:
            self._pending_plan = final_text

        return final_text

    async def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> StreamAccumulator:
        """Call LLM with streaming and return the final accumulator."""
        t0 = time.monotonic()
        with console.status("[thinking]Thinking...[/thinking]", spinner="dots"):
            accumulator = await self.provider.chat_complete(messages, tools=tools)
        if self.settings.show_response_time:
            elapsed = time.monotonic() - t0
            console.print(f"  [dim]Response time: {elapsed:.2f}s[/dim]")
        return accumulator

    async def run_turn_streaming(self, user_message: str, repo_map: str = "") -> str:
        """Run a turn with streaming output."""
        system_prompt = self._build_system_prompt(repo_map)
        self.history.add_system(system_prompt)

        # Resolve @file mentions and enrich the message
        enriched = build_enriched_message(user_message, self.settings.working_dir)
        self.history.add_user(enriched)

        # Determine tool allow-list for this turn.
        allowed = READONLY_TOOLS if self.plan_mode else None

        final_text = ""
        iteration = 0

        while iteration < self.settings.max_iterations:
            iteration += 1

            messages = self.history.get_messages()
            tool_schemas = self.tools.to_openai_schemas(allowed=allowed)

            try:
                accumulator = await self._stream_llm(messages, tool_schemas)
            except Exception as e:
                error_msg = f"LLM call failed: {e}"
                print_error(error_msg)
                self.history.add_assistant(error_msg)
                return error_msg

            if accumulator.has_tool_calls:
                tool_call_dicts = [tc.to_dict() for tc in accumulator.tool_call_list]
                self.history.add_assistant(
                    content=accumulator.content or "",
                    tool_calls=tool_call_dicts,
                )

                for tc in accumulator.tool_call_list:
                    args = tc.parsed_arguments()
                    print_tool_call(tc.name, args)

                    result = await self.tools.execute(tc.name, args, allowed=allowed)
                    print_tool_result(result.output, result.error)

                    self.history.add_tool_result(
                        tool_call_id=tc.id,
                        content=result.output if not result.error else f"ERROR: {result.output}",
                    )
                continue
            else:
                final_text = accumulator.content or ""
                self.history.add_assistant(final_text)
                break

        if iteration >= self.settings.max_iterations:
            print_warning(f"Reached maximum iterations ({self.settings.max_iterations})")

        # Store plan for approval when in plan mode.
        if self.plan_mode and final_text:
            self._pending_plan = final_text

        return final_text

    async def _stream_llm(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> StreamAccumulator:
        """Stream LLM response, printing content as it arrives."""
        last_acc = None
        started_printing = False
        t0 = time.monotonic()

        async for acc in self.provider.stream_chat(messages, tools=tools):
            last_acc = acc
            delta = acc.content_delta
            if delta:
                if not started_printing:
                    console.print()
                    started_printing = True
                console.print(delta, end="", markup=False, style="green")

        if started_printing:
            console.print()  # Final newline

        if self.settings.show_response_time:
            elapsed = time.monotonic() - t0
            console.print(f"  [dim]Response time: {elapsed:.2f}s[/dim]")

        return last_acc
