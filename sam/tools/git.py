"""Git status and diff tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult


class GitStatusTool(Tool):
    """Show git working tree status."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Show the git working tree status (modified, staged, untracked files)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs) -> ToolResult:
        return await self._run_git("status", "--short")

    async def _run_git(self, *args: str) -> ToolResult:
        try:
            process = await asyncio.create_subprocess_exec(
                "git", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                return ToolResult(
                    output=errors or f"git {args[0]} failed with code {process.returncode}",
                    error=True,
                )

            return ToolResult(output=output or "(clean working tree)")
        except FileNotFoundError:
            return ToolResult(output="git is not installed", error=True)
        except asyncio.TimeoutError:
            return ToolResult(output="git command timed out", error=True)
        except Exception as e:
            return ToolResult(output=f"git error: {e}", error=True)


class GitDiffTool(Tool):
    """Show git changes."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return (
            "Show git diff of changes. By default shows unstaged changes. "
            "Use staged=true to show staged changes."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes instead of unstaged. Default: false",
                },
                "path": {
                    "type": "string",
                    "description": "Limit diff to a specific file or directory",
                },
            },
        }

    async def execute(self, staged: bool = False, path: str | None = None, **kwargs) -> ToolResult:
        args = ["diff"]
        if staged:
            args.append("--cached")
        if path:
            args.append("--")
            args.append(path)

        try:
            process = await asyncio.create_subprocess_exec(
                "git", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                return ToolResult(output=errors or "git diff failed", error=True)

            if not output:
                return ToolResult(output="No changes")

            # Truncate very long diffs
            max_len = 8000
            if len(output) > max_len:
                output = output[:max_len] + f"\n... (diff truncated, {len(output)} chars total)"

            return ToolResult(output=output)
        except FileNotFoundError:
            return ToolResult(output="git is not installed", error=True)
        except asyncio.TimeoutError:
            return ToolResult(output="git diff timed out", error=True)
        except Exception as e:
            return ToolResult(output=f"git error: {e}", error=True)
