"""Write/create file tool with diff preview for existing files."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult
from sam.ui.console import console


class FileWriteTool(Tool):
    """Create or overwrite a file with diff preview."""

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
            "Parent directories are created automatically. "
            "Shows a diff preview when overwriting existing files."
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
            original = ""

            if existed:
                try:
                    original = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            # Show diff preview for overwrites
            diff_text = ""
            if existed and original:
                diff_text = self._generate_diff(original, content, path)
                if diff_text:
                    from rich.syntax import Syntax
                    console.print(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))

            file_path.write_text(content, encoding="utf-8")

            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            action = "Overwrote" if existed else "Created"
            output = f"{action} {path} ({lines} lines)"
            if diff_text:
                output += f"\n{diff_text}"
            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(output=f"Failed to write {path}: {e}", error=True)

    @staticmethod
    def _generate_diff(original: str, modified: str, filename: str) -> str:
        """Generate a compact unified diff."""
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines, mod_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=3,
        )
        diff_text = "".join(diff)
        if len(diff_text) > 2000:
            diff_text = diff_text[:2000] + "\n... (diff truncated)"
        return diff_text

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.working_dir / p
