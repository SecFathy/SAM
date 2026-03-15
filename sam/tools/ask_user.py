"""AskUserQuestion tool — lets the agent ask the user for clarification mid-turn."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sam.tools.base import Tool, ToolResult
from sam.ui.console import console


class AskUserQuestionTool(Tool):
    """Ask the user a question during agent execution."""

    def __init__(self, input_fn: Callable[[str], Awaitable[str]]) -> None:
        self._input_fn = input_fn

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "Ask the user a clarifying question and wait for their response. "
            "Use this when you need more information to proceed, want to confirm "
            "a destructive action, or need the user to choose between options. "
            "Provide a clear question and optionally a list of short options."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of choices for the user. "
                        "If provided, they are displayed as numbered options."
                    ),
                },
            },
            "required": ["question"],
        }

    async def execute(
        self, question: str, options: list[str] | None = None, **kwargs: Any
    ) -> ToolResult:
        # Display the question
        console.print()
        console.print(f"[bold yellow]? {question}[/bold yellow]")

        if options:
            for i, opt in enumerate(options, 1):
                console.print(f"  [cyan]{i}.[/cyan] {opt}")
            console.print("[dim]  Enter a number or type your own answer.[/dim]")

        # Get user answer
        try:
            answer = await self._input_fn(question)
        except (EOFError, KeyboardInterrupt):
            return ToolResult(output="User cancelled the question.", error=True)

        answer = answer.strip()
        if not answer:
            return ToolResult(output="User gave no answer (empty response).", error=True)

        # Resolve numbered choice
        if options and answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(options):
                answer = options[idx - 1]

        return ToolResult(output=answer)
