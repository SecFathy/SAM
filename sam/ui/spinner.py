"""Thinking indicators and progress spinners."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from sam.ui.console import console


@contextmanager
def thinking_spinner(message: str = "Thinking...") -> Generator[None, None, None]:
    """Show a spinner while the model is thinking."""
    spinner = Spinner("dots", text=Text(f" {message}", style="dim italic"))
    with Live(spinner, console=console, transient=True):
        yield


@contextmanager
def tool_spinner(tool_name: str) -> Generator[None, None, None]:
    """Show a spinner while a tool is executing."""
    spinner = Spinner("dots", text=Text(f" Running {tool_name}...", style="magenta"))
    with Live(spinner, console=console, transient=True):
        yield


def show_token_usage(prompt_tokens: int, completion_tokens: int) -> None:
    """Display token usage info."""
    total = prompt_tokens + completion_tokens
    console.print(
        f"[dim]Tokens: {prompt_tokens:,} prompt + {completion_tokens:,} completion = {total:,} total[/dim]"
    )
