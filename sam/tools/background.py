"""Background task execution — run long commands without blocking the agent."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path

from sam.tools.base import Tool, ToolResult


@dataclass
class BackgroundTask:
    """A background shell command."""

    task_id: str
    command: str
    started_at: float
    process: asyncio.subprocess.Process
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    finished: bool = False


class BackgroundTaskManager:
    """Manages background shell tasks."""

    _instance: BackgroundTaskManager | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._counter: int = 0

    @classmethod
    def get(cls) -> BackgroundTaskManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _next_id(self) -> str:
        self._counter += 1
        return f"bg_{self._counter}"

    def add(self, task: BackgroundTask) -> None:
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[BackgroundTask]:
        return list(self._tasks.values())


class BackgroundRunTool(Tool):
    """Run a shell command in the background."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "run_background"

    @property
    def description(self) -> str:
        return (
            "Run a shell command in the background without waiting for it to finish. "
            "Returns a task ID immediately. Use background_status to check if it's done "
            "and read the output. Useful for long-running commands like builds, "
            "test suites, servers, or deployments."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run in the background",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, **kwargs) -> ToolResult:
        from sam.tools.shell import BLOCKED_PATTERNS

        # Safety check
        cmd_lower = command.strip().lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return ToolResult(
                    output=f"Command blocked for safety: {command}",
                    error=True,
                )

        mgr = BackgroundTaskManager.get()
        task_id = mgr._next_id()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )
        except Exception as e:
            return ToolResult(output=f"Failed to start background task: {e}", error=True)

        task = BackgroundTask(
            task_id=task_id,
            command=command,
            started_at=time.time(),
            process=process,
        )
        mgr.add(task)

        # Start a coroutine to collect output when done
        asyncio.create_task(_collect_output(task))

        return ToolResult(
            output=f"Background task started: {task_id}\n"
            f"Command: {command}\n"
            f"Use background_status with task_id='{task_id}' to check progress."
        )


class BackgroundStatusTool(Tool):
    """Check status and output of background tasks."""

    @property
    def name(self) -> str:
        return "background_status"

    @property
    def description(self) -> str:
        return (
            "Check the status and output of a background task. "
            "Pass a task_id to check a specific task, or omit it to list all tasks."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to check (from run_background). Omit to list all.",
                },
            },
        }

    async def execute(self, task_id: str | None = None, **kwargs) -> ToolResult:
        mgr = BackgroundTaskManager.get()

        if task_id:
            task = mgr.get_task(task_id)
            if not task:
                return ToolResult(output=f"Unknown task ID: {task_id}", error=True)
            return ToolResult(output=_format_task(task))

        # List all tasks
        tasks = mgr.all_tasks()
        if not tasks:
            return ToolResult(output="No background tasks.")

        lines = []
        for t in tasks:
            lines.append(_format_task_summary(t))

        return ToolResult(output="\n".join(lines))


async def _collect_output(task: BackgroundTask) -> None:
    """Wait for a background process to finish and collect its output."""
    try:
        stdout, stderr = await task.process.communicate()

        max_len = 10000
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        if len(stdout_str) > max_len:
            stdout_str = stdout_str[:max_len] + f"\n... (truncated, {len(stdout_str)} chars total)"
        if len(stderr_str) > max_len:
            stderr_str = stderr_str[:max_len] + f"\n... (truncated, {len(stderr_str)} chars total)"

        task.stdout = stdout_str
        task.stderr = stderr_str
        task.returncode = task.process.returncode
        task.finished = True

    except Exception as e:
        task.stdout = ""
        task.stderr = str(e)
        task.returncode = -1
        task.finished = True


def _format_task(task: BackgroundTask) -> str:
    """Format full task details."""
    elapsed = time.time() - task.started_at
    status = "FINISHED" if task.finished else "RUNNING"

    parts = [
        f"Task: {task.task_id} [{status}]",
        f"Command: {task.command}",
        f"Elapsed: {elapsed:.1f}s",
    ]

    if task.finished:
        parts.append(f"Exit code: {task.returncode}")
        if task.stdout:
            parts.append(f"Output:\n{task.stdout}")
        if task.stderr:
            parts.append(f"Stderr:\n{task.stderr}")
    else:
        parts.append("(still running — check again later)")

    return "\n".join(parts)


def _format_task_summary(task: BackgroundTask) -> str:
    """Format a one-line task summary."""
    elapsed = time.time() - task.started_at
    if task.finished:
        code = f"exit={task.returncode}"
        return f"  {task.task_id}: DONE ({code}, {elapsed:.1f}s) — {task.command[:60]}"
    return f"  {task.task_id}: RUNNING ({elapsed:.1f}s) — {task.command[:60]}"
