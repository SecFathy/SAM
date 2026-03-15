"""Permission system for tool execution approval.

Three modes:
  - auto:  All tools auto-execute (no prompts). Default for one-shot mode.
  - safe:  Read-only tools auto-execute; write/shell tools require approval.
  - ask:   Every tool call requires user approval.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from sam.tools.base import READONLY_TOOLS
from sam.ui.console import console

# Permission mode constants
AUTO = "auto"
SAFE = "safe"
ASK = "ask"

async def check_permission(
    tool_name: str,
    arguments: dict,
    mode: str,
    input_fn: Callable[[str], Awaitable[str]] | None = None,
) -> bool:
    """Check whether a tool call is permitted under the current mode.

    Returns True if allowed, False if denied by the user.
    """
    if mode == AUTO:
        return True

    if mode == SAFE:
        # Read-only tools are always allowed
        if tool_name in READONLY_TOOLS:
            return True
        # Write/shell tools need confirmation
        return await _prompt_user(tool_name, arguments, input_fn)

    if mode == ASK:
        return await _prompt_user(tool_name, arguments, input_fn)

    # Unknown mode — default allow
    return True


async def _prompt_user(
    tool_name: str,
    arguments: dict,
    input_fn: Callable[[str], Awaitable[str]] | None = None,
) -> bool:
    """Prompt the user to approve a tool call."""
    # Build summary
    summary = _summarize_call(tool_name, arguments)
    console.print(f"\n[bold yellow]Permission required:[/bold yellow] {summary}")
    console.print("[dim]  Allow? (y)es / (n)o / (a)lways for this session[/dim]")

    if input_fn is None:
        # Fallback to blocking stdin
        loop = asyncio.get_event_loop()
        try:
            answer = await loop.run_in_executor(None, lambda: input("  ❯ "))
        except (EOFError, KeyboardInterrupt):
            return False
    else:
        try:
            answer = await input_fn("Allow?")
        except (EOFError, KeyboardInterrupt):
            return False

    answer = answer.strip().lower()
    if answer in ("y", "yes"):
        return True
    if answer in ("a", "always"):
        # Signal to caller to upgrade mode — handled via return value "always"
        # For simplicity, we return True and let the caller check
        return True
    return False


def _summarize_call(tool_name: str, arguments: dict) -> str:
    """Build a one-line summary of the tool call for the permission prompt."""
    if tool_name == "run_command":
        cmd = arguments.get("command", "")
        return f"[magenta]run_command[/magenta] → [white]{cmd}[/white]"
    if tool_name == "edit_file":
        path = arguments.get("path", "")
        return f"[magenta]edit_file[/magenta] → [white]{path}[/white]"
    if tool_name == "write_file":
        path = arguments.get("path", "")
        return f"[magenta]write_file[/magenta] → [white]{path}[/white]"

    # Generic
    args_str = ", ".join(f"{k}={str(v)[:40]}" for k, v in arguments.items())
    return f"[magenta]{tool_name}[/magenta]({args_str})"
