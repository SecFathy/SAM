"""File pattern matching tool."""

from __future__ import annotations

from pathlib import Path

from sam.tools.base import Tool, ToolResult

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".eggs",
}


class GlobTool(Tool):
    """Find files matching glob patterns."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "Find files matching a glob pattern in the codebase. "
            "Supports ** for recursive matching. "
            "Example patterns: '*.py', 'src/**/*.ts', '**/test_*.py'"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g. '**/*.py', 'src/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory for the search. Default: working directory",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = ".", **kwargs) -> ToolResult:
        base_path = self._resolve_path(path)

        if not base_path.exists():
            return ToolResult(output=f"Path not found: {path}", error=True)

        matches = []
        try:
            for match in sorted(base_path.glob(pattern)):
                # Skip hidden and blacklisted directories
                parts = match.relative_to(base_path).parts
                if any(p in SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
                    continue
                # Skip hidden files (but allow .gitignore etc)
                if match.name.startswith(".") and match.name not in (
                    ".gitignore", ".env.example", ".editorconfig"
                ):
                    continue

                rel = self._relative_path(match)
                if match.is_dir():
                    matches.append(f"{rel}/")
                else:
                    matches.append(rel)

                if len(matches) >= 200:
                    break
        except Exception as e:
            return ToolResult(output=f"Glob error: {e}", error=True)

        if not matches:
            return ToolResult(output=f"No files matching pattern '{pattern}'")

        truncated = " (truncated at 200)" if len(matches) >= 200 else ""
        result = "\n".join(matches)
        return ToolResult(
            output=f"Found {len(matches)} matches{truncated}:\n{result}"
        )

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
