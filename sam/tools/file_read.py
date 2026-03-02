"""Read file contents with optional offset/limit pagination."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult


class FileReadTool(Tool):
    """Read file contents with optional line range."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Supports optional offset and limit for pagination. "
            "Returns line-numbered output. Use this to understand code before editing."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path (relative to working directory or absolute)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (1-based). Default: 1",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read. Default: 500",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, offset: int = 1, limit: int = 500, **kwargs) -> ToolResult:
        file_path = self._resolve_path(path)

        if not file_path.exists():
            return ToolResult(output=f"File not found: {path}", error=True)
        if not file_path.is_file():
            return ToolResult(output=f"Not a file: {path}", error=True)

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(output=f"Failed to read {path}: {e}", error=True)

        lines = content.splitlines()
        total_lines = len(lines)

        # Apply pagination
        start = max(0, offset - 1)
        end = start + limit
        selected = lines[start:end]

        # Format with line numbers
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:>6}\t{line}")

        result = "\n".join(numbered)

        # Add pagination info
        if total_lines > end:
            result += f"\n\n... ({total_lines - end} more lines. Use offset={end + 1} to continue)"

        header = f"File: {path} ({total_lines} lines total)"
        if start > 0 or end < total_lines:
            header += f" [showing lines {start + 1}-{min(end, total_lines)}]"

        return ToolResult(output=f"{header}\n{result}")

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.working_dir / p
