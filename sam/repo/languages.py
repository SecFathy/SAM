"""Language detection and tree-sitter grammar registry."""

from __future__ import annotations

from dataclasses import dataclass
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

# Queries for extracting definitions per language
# These are tree-sitter query patterns
DEFINITION_QUERIES: dict[str, str] = {
    "python": """
        (function_definition name: (identifier) @name) @definition
        (class_definition name: (identifier) @name) @definition
    """,
    "javascript": """
        (function_declaration name: (identifier) @name) @definition
        (class_declaration name: (identifier) @name) @definition
        (method_definition name: (property_identifier) @name) @definition
        (arrow_function) @definition
    """,
    "typescript": """
        (function_declaration name: (identifier) @name) @definition
        (class_declaration name: (identifier) @name) @definition
        (method_definition name: (property_identifier) @name) @definition
        (interface_declaration name: (type_identifier) @name) @definition
    """,
    "rust": """
        (function_item name: (identifier) @name) @definition
        (struct_item name: (type_identifier) @name) @definition
        (impl_item type: (type_identifier) @name) @definition
        (enum_item name: (type_identifier) @name) @definition
        (trait_item name: (type_identifier) @name) @definition
    """,
    "go": """
        (function_declaration name: (identifier) @name) @definition
        (method_declaration name: (field_identifier) @name) @definition
        (type_declaration (type_spec name: (type_identifier) @name)) @definition
    """,
    "java": """
        (class_declaration name: (identifier) @name) @definition
        (method_declaration name: (identifier) @name) @definition
        (interface_declaration name: (identifier) @name) @definition
    """,
}


def detect_language(path: Path) -> str | None:
    """Detect the programming language from a file path."""
    return EXTENSION_MAP.get(path.suffix.lower())


def get_tree_sitter_language(lang_name: str):
    """Get a tree-sitter Language object for parsing."""
    try:
        from tree_sitter_languages import get_language
        return get_language(lang_name)
    except Exception:
        return None


def get_parser(lang_name: str):
    """Get a tree-sitter Parser configured for the given language."""
    try:
        from tree_sitter_languages import get_parser
        return get_parser(lang_name)
    except Exception:
        return None
