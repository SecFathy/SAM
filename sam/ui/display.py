"""Markdown and code rendering for the terminal."""

from __future__ import annotations

from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from sam.ui.console import console


def render_markdown(text: str) -> None:
    """Render markdown text to the terminal."""
    md = Markdown(text)
    console.print(md)


def render_code(code: str, language: str = "python", title: str = "") -> None:
    """Render syntax-highlighted code."""
    syntax = Syntax(
        code,
        language,
        theme="monokai",
        line_numbers=True,
        word_wrap=True,
    )
    if title:
        console.print(Panel(syntax, title=title, border_style="dim"))
    else:
        console.print(syntax)


def render_diff(diff_text: str) -> None:
    """Render a unified diff with syntax highlighting."""
    syntax = Syntax(
        diff_text,
        "diff",
        theme="monokai",
        word_wrap=True,
    )
    console.print(syntax)


def render_panel(content: str, title: str = "", style: str = "dim") -> None:
    """Render content in a bordered panel."""
    console.print(Panel(content, title=title, border_style=style))
