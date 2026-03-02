"""Search/replace file editing with 4-layer fuzzy fallback.

This is the highest-impact component. Open-source models frequently get
whitespace and indentation wrong, so we use cascading match strategies:

1. Exact match — fastest, most precise
2. Whitespace-normalized — collapse whitespace runs
3. Indentation-flexible — strip leading whitespace, match content
4. Fuzzy (difflib) — sliding window with SequenceMatcher, threshold 0.6
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult


class FileEditTool(Tool):
    """Edit files using search/replace with fuzzy matching fallback."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing a search string with a replacement string. "
            "The search string should be a unique snippet from the file. "
            "Include enough context lines to make the match unique. "
            "Has fuzzy matching — handles minor whitespace/indentation differences. "
            "Do NOT include line numbers in the search string."
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
                "search": {
                    "type": "string",
                    "description": "The exact text to find in the file (multi-line supported)",
                },
                "replace": {
                    "type": "string",
                    "description": "The text to replace it with",
                },
            },
            "required": ["path", "search", "replace"],
        }

    async def execute(self, path: str, search: str, replace: str, **kwargs) -> ToolResult:
        file_path = self._resolve_path(path)

        if not file_path.exists():
            return ToolResult(output=f"File not found: {path}", error=True)

        try:
            original = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(output=f"Failed to read {path}: {e}", error=True)

        # Try 4-layer matching
        result, method = self._find_and_replace(original, search, replace)

        if result is None:
            # Generate helpful error with closest match
            closest = self._find_closest(original, search)
            msg = f"Could not find the search string in {path}."
            if closest:
                msg += f"\n\nClosest match found:\n```\n{closest}\n```"
            return ToolResult(output=msg, error=True)

        try:
            file_path.write_text(result, encoding="utf-8")
        except Exception as e:
            return ToolResult(output=f"Failed to write {path}: {e}", error=True)

        return ToolResult(output=f"Edited {path} (matched via {method})")

    def _find_and_replace(
        self, content: str, search: str, replace: str
    ) -> tuple[str | None, str]:
        """Try 4 matching strategies in order. Returns (new_content, method) or (None, '')."""

        # Layer 1: Exact match
        if search in content:
            return content.replace(search, replace, 1), "exact match"

        # Layer 2: Whitespace-normalized match
        result = self._whitespace_normalized_replace(content, search, replace)
        if result is not None:
            return result, "whitespace-normalized"

        # Layer 3: Indentation-flexible match
        result = self._indentation_flexible_replace(content, search, replace)
        if result is not None:
            return result, "indentation-flexible"

        # Layer 4: Fuzzy match (difflib)
        result = self._fuzzy_replace(content, search, replace)
        if result is not None:
            return result, "fuzzy match"

        return None, ""

    def _whitespace_normalized_replace(
        self, content: str, search: str, replace: str
    ) -> str | None:
        """Match after collapsing whitespace runs to single spaces."""
        def normalize_ws(s: str) -> str:
            return re.sub(r"[ \t]+", " ", s)

        norm_content = normalize_ws(content)
        norm_search = normalize_ws(search)

        if norm_search not in norm_content:
            return None

        # Find the position in normalized space, map back to original
        idx = norm_content.index(norm_search)

        # Map normalized index back to original content
        orig_start = self._map_normalized_index(content, idx)
        orig_end = self._map_normalized_index(content, idx + len(norm_search))

        return content[:orig_start] + replace + content[orig_end:]

    def _map_normalized_index(self, original: str, norm_idx: int) -> int:
        """Map an index in whitespace-normalized text back to the original."""
        orig_pos = 0
        norm_pos = 0
        in_whitespace = False

        while norm_pos < norm_idx and orig_pos < len(original):
            char = original[orig_pos]
            if char in " \t":
                if not in_whitespace:
                    norm_pos += 1  # counts as single space
                    in_whitespace = True
            else:
                norm_pos += 1
                in_whitespace = False
            orig_pos += 1

        return orig_pos

    def _indentation_flexible_replace(
        self, content: str, search: str, replace: str
    ) -> str | None:
        """Match ignoring leading whitespace on each line."""
        content_lines = content.splitlines(keepends=True)
        search_lines = search.splitlines()

        if not search_lines:
            return None

        # Strip leading whitespace from search lines for matching
        stripped_search = [line.lstrip() for line in search_lines]

        # Slide through content looking for a match
        for i in range(len(content_lines) - len(search_lines) + 1):
            match = True
            for j, s_line in enumerate(stripped_search):
                c_line = content_lines[i + j].rstrip("\n").rstrip("\r")
                if c_line.lstrip() != s_line:
                    match = False
                    break

            if match:
                # Found a match — apply the replacement preserving indentation
                # Detect the indentation of the first matched line
                original_indent = self._get_indent(content_lines[i])
                search_indent = self._get_indent(search.splitlines()[0])

                # Apply indent adjustment to replacement
                replace_lines = replace.splitlines(keepends=True)
                adjusted_replace = self._adjust_indent(
                    replace_lines, original_indent, search_indent
                )

                before = "".join(content_lines[:i])
                after = "".join(content_lines[i + len(search_lines):])

                return before + adjusted_replace + after

        return None

    def _fuzzy_replace(
        self, content: str, search: str, replace: str, threshold: float = 0.6
    ) -> str | None:
        """Fuzzy match using difflib SequenceMatcher with a sliding window."""
        content_lines = content.splitlines(keepends=True)
        search_lines = search.splitlines()

        if not search_lines:
            return None

        window_size = len(search_lines)
        best_ratio = 0.0
        best_start = -1

        search_text = "\n".join(search_lines)

        for i in range(len(content_lines) - window_size + 1):
            window = "".join(content_lines[i : i + window_size])
            ratio = difflib.SequenceMatcher(
                None, search_text, window.rstrip("\n")
            ).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_start = i

        if best_ratio >= threshold and best_start >= 0:
            # Apply the replacement
            original_indent = self._get_indent(content_lines[best_start])
            search_indent = self._get_indent(search.splitlines()[0])

            replace_lines = replace.splitlines(keepends=True)
            adjusted_replace = self._adjust_indent(
                replace_lines, original_indent, search_indent
            )

            before = "".join(content_lines[:best_start])
            after = "".join(content_lines[best_start + window_size:])

            return before + adjusted_replace + after

        return None

    def _find_closest(self, content: str, search: str, max_lines: int = 10) -> str | None:
        """Find the closest matching region in the file for error reporting."""
        content_lines = content.splitlines()
        search_lines = search.splitlines()

        if not search_lines:
            return None

        window_size = min(len(search_lines), max_lines)
        best_ratio = 0.0
        best_window = None

        search_text = "\n".join(search_lines[:max_lines])

        for i in range(len(content_lines) - window_size + 1):
            window = "\n".join(content_lines[i : i + window_size])
            ratio = difflib.SequenceMatcher(None, search_text, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_window = window

        if best_ratio > 0.3 and best_window:
            return best_window

        return None

    @staticmethod
    def _get_indent(line: str) -> str:
        """Extract the leading whitespace from a line."""
        return line[: len(line) - len(line.lstrip())]

    @staticmethod
    def _adjust_indent(
        lines: list[str], target_indent: str, source_indent: str
    ) -> str:
        """Adjust indentation of replacement lines to match the target."""
        if not lines:
            return ""

        result = []
        for line in lines:
            stripped = line.lstrip()
            if not stripped:
                result.append(line)
                continue

            current_indent = line[: len(line) - len(stripped)]
            # Remove source indent prefix and add target indent
            if current_indent.startswith(source_indent):
                new_indent = target_indent + current_indent[len(source_indent):]
            else:
                new_indent = target_indent + current_indent

            result.append(new_indent + stripped)

        return "".join(result)

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.working_dir / p
