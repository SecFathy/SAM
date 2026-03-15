"""Language detection and tree-sitter grammar registry."""

from __future__ import annotations

from pathlib import Path

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".sql": "sql",
    ".md": "markdown",
    ".el": "elisp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
}

def detect_language(path: Path) -> str | None:
    """Detect the programming language from a file path."""
    return EXTENSION_MAP.get(path.suffix.lower())


def get_parser(lang_name: str):
    """Get a tree-sitter Parser configured for the given language."""
    try:
        from tree_sitter_languages import get_parser
        return get_parser(lang_name)
    except Exception:
        return None
