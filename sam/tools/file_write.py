"""Write/create file tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult


class FileWriteTool(Tool):
    """Create or overwrite a file."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Create a new file or overwrite an existing file completely. "
            "Use edit_file for partial modifications to existing files. "
            "Parent directories are created automatically."
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
                "content": {
                    "type": "string",
                    "description": "Complete file content to write",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        file_path = self._resolve_path(path)

        try:
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            existed = file_path.exists()
            file_path.write_text(content, encoding="utf-8")

            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            action = "Overwrote" if existed else "Created"
            return ToolResult(output=f"{action} {path} ({lines} lines)")

        except Exception as e:
            return ToolResult(output=f"Failed to write {path}: {e}", error=True)

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.working_dir / p
