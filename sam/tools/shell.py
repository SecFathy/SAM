"""Shell command execution with timeout and safety."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult

# Commands that are always blocked — catastrophic risk
BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){",       # fork bomb
    ":(){ :|:",   # fork bomb variant
    "> /dev/sda",
    "chmod -r 000 /",
    "chown -r",
]

# Commands that trigger a warning in output (risky but allowed)
WARN_PATTERNS = [
    "git push --force",
    "git push -f ",
    "git reset --hard",
    "git clean -f",
    "git checkout -- .",
    "git restore .",
    "drop table",
    "drop database",
    "truncate table",
    "docker rm",
    "docker rmi",
    "kubectl delete",
    "rm -rf",
    "rm -r ",
    "pip install",
    "npm install",
    "chmod ",
    "chown ",
    "sudo ",
]


class ShellTool(Tool):
    """Execute shell commands with timeout and safety checks."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in the working directory. "
            "Use for running tests, installing packages, checking compilation, etc. "
            "Commands time out after 30 seconds by default."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default: 30",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, timeout: int = 30, **kwargs) -> ToolResult:
        # Safety check — blocked patterns
        cmd_lower = command.strip().lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return ToolResult(
                    output=f"Command blocked for safety: {command}",
                    error=True,
                )

        # Check for risky patterns — flag in output
        warnings = []
        for pattern in WARN_PATTERNS:
            if pattern in cmd_lower:
                warnings.append(f"WARNING: command matches risky pattern '{pattern}'")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    output=f"Command timed out after {timeout}s: {command}",
                    error=True,
                )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            # Truncate very long output
            max_len = 10000
            if len(stdout_str) > max_len:
                stdout_str = stdout_str[:max_len] + f"\n... (truncated, {len(stdout_str)} chars total)"
            if len(stderr_str) > max_len:
                stderr_str = stderr_str[:max_len] + f"\n... (truncated, {len(stderr_str)} chars total)"

            parts = []
            if stdout_str:
                parts.append(stdout_str)
            if stderr_str:
                parts.append(f"STDERR:\n{stderr_str}")

            output = "\n".join(parts) if parts else "(no output)"

            # Prepend safety warnings if any
            if warnings:
                output = "\n".join(warnings) + "\n" + output

            if process.returncode != 0:
                output = f"Exit code: {process.returncode}\n{output}"
                return ToolResult(output=output, error=True)

            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(output=f"Failed to execute command: {e}", error=True)
