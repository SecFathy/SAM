"""Rich console setup and output helpers."""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.theme import Theme

SAM_THEME = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red bold",
    "tool": "magenta",
    "thinking": "dim italic",
})

console = Console(theme=SAM_THEME)


class _LineNumberCodeBlock(CodeBlock):
    """Code block with line numbers."""

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        code = str(self.text).rstrip()
        syntax = Syntax(
            code,
            self.lexer_name,
            theme=self.theme,
            line_numbers=True,
            word_wrap=True,
            padding=1,
        )
        yield syntax


# Register our custom code block renderer
Markdown.elements["fence"] = _LineNumberCodeBlock
Markdown.elements["code_block"] = _LineNumberCodeBlock


def print_assistant(content: str) -> None:
    """Print assistant's markdown response in green with syntax-highlighted code blocks."""
    if content.strip():
        md = Markdown(content, code_theme="monokai")
        console.print(md, style="green")


def print_tool_call(name: str, args: dict) -> None:
    """Print a tool call notification."""
    args_summary = _summarize_args(args)
    console.print(f"  [tool]> {name}[/tool] {args_summary}")


def print_tool_result(result_text: str, is_error: bool = False) -> None:
    """Print a tool result (truncated)."""
    max_display = 500
    text = result_text[:max_display]
    if len(result_text) > max_display:
        text += f"\n... ({len(result_text)} chars total)"

    style = "error" if is_error else "dim"
    console.print(f"  [{style}]{text}[/{style}]")


def print_error(msg: str) -> None:
    console.print(f"[error]{msg}[/error]")


def print_info(msg: str) -> None:
    console.print(f"[info]{msg}[/info]")


def print_success(msg: str) -> None:
    console.print(f"[success]{msg}[/success]")


def print_warning(msg: str) -> None:
    console.print(f"[warning]{msg}[/warning]")


def print_banner() -> None:
    """Print SAM startup banner with ASCII art."""
    art = (
        "[bold bright_cyan]▓▓▓▓▓▓▓  ▓▓▓▓▓  ▓▓    ▓▓[/bold bright_cyan]\n"
        "[bold cyan]▓▓       ▓▓   ▓▓ ▓▓▓▓ ▓▓▓▓[/bold cyan]\n"
        "[cyan]▒▒▒▒▒▒  ▒▒▒▒▒▒▒ ▒▒ ▒▒ ▒▒[/cyan]\n"
        "[dim cyan]     ░░ ░░   ░░ ░░    ░░[/dim cyan]\n"
        "[dim cyan]░░░░░░░ ░░   ░░ ░░    ░░[/dim cyan]"
    )
    console.print(
        Panel(
            f"{art}\n\n"
            "[bold cyan]Smart Agentic Model[/bold cyan]\n"
            "[dim]CLI coding agent for open-source LLMs[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def _summarize_args(args: dict) -> str:
    """Create a short summary of tool arguments."""
    parts = []
    for key, val in args.items():
        val_str = str(val)
        if len(val_str) > 60:
            val_str = val_str[:57] + "..."
        parts.append(f"{key}={val_str}")
    return " ".join(parts)
