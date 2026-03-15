"""Git checkpoint for multi-file rollback safety.

Creates a lightweight git stash before multi-file operations,
and can restore if something goes wrong.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult


class CheckpointCreateTool(Tool):
    """Create a git checkpoint (stash) before risky operations."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "checkpoint_create"

    @property
    def description(self) -> str:
        return (
            "Create a safety checkpoint of the current working tree state. "
            "Use before multi-file refactoring or risky operations. "
            "Returns a checkpoint ID that can be used with checkpoint_restore."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Description of what operation is about to happen",
                },
            },
            "required": ["message"],
        }

    async def execute(self, message: str, **kwargs) -> ToolResult:
        try:
            # Check if we're in a git repo
            proc = await asyncio.create_subprocess_shell(
                "git rev-parse --is-inside-work-tree",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            await proc.communicate()
            if proc.returncode != 0:
                return ToolResult(output="Not inside a git repository.", error=True)

            # Check if there are changes to stash
            proc = await asyncio.create_subprocess_shell(
                "git status --porcelain",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            stdout, _ = await proc.communicate()
            status = stdout.decode().strip()

            if not status:
                # Nothing to stash — just record the current commit
                proc = await asyncio.create_subprocess_shell(
                    "git rev-parse --short HEAD",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.working_dir),
                )
                stdout, _ = await proc.communicate()
                commit_hash = stdout.decode().strip()
                return ToolResult(
                    output=f"Checkpoint: clean tree at commit {commit_hash}. "
                    f"No stash needed — use `git checkout .` to restore."
                )

            # Create a stash with message
            stash_msg = f"SAM checkpoint: {message}"
            proc = await asyncio.create_subprocess_shell(
                f'git stash push -m "{stash_msg}" --include-untracked',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode().strip()

            if proc.returncode != 0:
                return ToolResult(
                    output=f"Failed to create checkpoint: {stderr.decode().strip()}",
                    error=True,
                )

            # Re-apply the stashed changes so work continues
            proc2 = await asyncio.create_subprocess_shell(
                "git stash apply",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )
            await proc2.communicate()

            return ToolResult(
                output=f"Checkpoint created: {stash_msg}\n"
                f"Use checkpoint_restore to roll back if needed."
            )

        except Exception as e:
            return ToolResult(output=f"Checkpoint failed: {e}", error=True)


class CheckpointRestoreTool(Tool):
    """Restore from the most recent checkpoint (git stash)."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "checkpoint_restore"

    @property
    def description(self) -> str:
        return (
            "Restore the working tree to the most recent SAM checkpoint. "
            "Discards all changes made since the checkpoint was created. "
            "Use when a multi-file operation went wrong."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Find the most recent SAM checkpoint stash
            proc = await asyncio.create_subprocess_shell(
                "git stash list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            stdout, _ = await proc.communicate()
            stash_list = stdout.decode().strip()

            if not stash_list:
                return ToolResult(output="No checkpoints found.", error=True)

            # Find the first SAM checkpoint
            sam_stash = None
            for line in stash_list.splitlines():
                if "SAM checkpoint:" in line:
                    # Extract stash ref like stash@{0}
                    sam_stash = line.split(":")[0].strip()
                    break

            if not sam_stash:
                return ToolResult(
                    output="No SAM checkpoints found in stash list.",
                    error=True,
                )

            # Discard current changes and apply stash
            proc = await asyncio.create_subprocess_shell(
                "git checkout -- .",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )
            await proc.communicate()

            # Clean untracked files that were added
            proc = await asyncio.create_subprocess_shell(
                "git clean -fd",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )
            await proc.communicate()

            # Apply the stash
            proc = await asyncio.create_subprocess_shell(
                f"git stash pop {sam_stash}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={**os.environ, "TERM": "dumb"},
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    output=f"Failed to restore: {stderr.decode().strip()}",
                    error=True,
                )

            return ToolResult(
                output=f"Restored from checkpoint ({sam_stash}). "
                f"All changes since checkpoint have been discarded."
            )

        except Exception as e:
            return ToolResult(output=f"Restore failed: {e}", error=True)
