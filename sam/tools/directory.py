"""List directory contents."""

from __future__ import annotations

from pathlib import Path

from sam.tools.base import Tool, ToolResult


class DirectoryTool(Tool):
    """List contents of a directory."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return (
            "List the contents of a directory. Shows files and subdirectories "
            "with type indicators. Use to explore project structure."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Directory path (relative to working directory or absolute). Default: '.'"
                    ),
                },
            },
        }

    async def execute(self, path: str = ".", **kwargs) -> ToolResult:
        dir_path = self._resolve_path(path)

        if not dir_path.exists():
            return ToolResult(output=f"Directory not found: {path}", error=True)
        if not dir_path.is_dir():
            return ToolResult(output=f"Not a directory: {path}", error=True)

        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return ToolResult(output=f"Permission denied: {path}", error=True)

        lines = []
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in (".gitignore", ".env.example"):
                continue  # Skip hidden files by default

            if entry.is_dir():
                lines.append(f"  {entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"  {entry.name}  ({self._format_size(size)})")

        if not lines:
            return ToolResult(output=f"Directory is empty: {path}")

        header = f"Directory: {path} ({len(lines)} items)"
        return ToolResult(output=f"{header}\n" + "\n".join(lines))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.working_dir / p

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
