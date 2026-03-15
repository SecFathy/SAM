"""Regex search across codebase."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from sam.tools.base import Tool, ToolResult

# Directories to always skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".eggs", "egg-info",
}

# Binary file extensions to skip
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".o", ".a", ".dylib", ".dll",
    ".exe", ".bin", ".jpg", ".jpeg", ".png", ".gif", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4",
}


class GrepTool(Tool):
    """Search file contents with regex patterns."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Search for a regex pattern across files in the codebase. "
            "Returns matching lines with file paths and line numbers. "
            "Optionally filter by file glob pattern."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in. Default: working directory",
                },
                "include": {
                    "type": "string",
                    "description": "File glob pattern to include (e.g. '*.py', '*.ts')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matches to return. Default: 50",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        max_results: int = 50,
        **kwargs,
    ) -> ToolResult:
        search_path = self._resolve_path(path)

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(output=f"Invalid regex pattern: {e}", error=True)

        if not search_path.exists():
            return ToolResult(output=f"Path not found: {path}", error=True)

        matches = []
        files_searched = 0

        if search_path.is_file():
            files = [search_path]
        else:
            files = self._walk_files(search_path, include)

        for file_path in files:
            if len(matches) >= max_results:
                break

            files_searched += 1
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        rel = self._relative_path(file_path)
                        matches.append(f"{rel}:{line_num}: {line.rstrip()}")
                        if len(matches) >= max_results:
                            break
            except Exception:
                continue

        if not matches:
            return ToolResult(
                output=f"No matches found for pattern '{pattern}' ({files_searched} files searched)"
            )

        result = "\n".join(matches)
        truncated = f" (showing first {max_results})" if len(matches) >= max_results else ""
        return ToolResult(
            output=(
                f"Found {len(matches)} matches{truncated}"
                f" ({files_searched} files searched):\n{result}"
            )
        )

    def _walk_files(self, root: Path, include: str | None) -> list[Path]:
        """Walk directory tree yielding source files."""
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Filter out skipped directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() in BINARY_EXTENSIONS:
                    continue
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                files.append(fpath)

        return files

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.working_dir))
        except ValueError:
            return str(path)

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.working_dir / p
