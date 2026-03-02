"""Repo map generation: tree-sitter + PageRank → token-budgeted map."""

from __future__ import annotations

import os
from pathlib import Path

import tiktoken

from sam.repo.graph import build_dependency_graph, rank_files
from sam.repo.languages import detect_language
from sam.repo.tags import FileSymbols, extract_symbols

# Directories to skip during repo scanning
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".eggs", "egg-info", ".idea", ".vscode",
}


class RepoMapper:
    """Generate a compact repository map showing key definitions."""

    def __init__(
        self,
        root: Path,
        token_budget: int = 2048,
        personalized_files: list[str] | None = None,
    ) -> None:
        self.root = root
        self.token_budget = token_budget
        self.personalized_files = personalized_files or []
        try:
            self._encoder = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            self._encoder = tiktoken.get_encoding("cl100k_base")

    def generate(self) -> str:
        """Generate the repository map string."""
        # 1. Scan all source files and extract symbols
        all_symbols = self._scan_files()
        if not all_symbols:
            return self._fallback_tree()

        # 2. Build dependency graph
        graph = build_dependency_graph(all_symbols)

        # 3. Rank files by importance
        ranked = rank_files(graph, personalized_files=self.personalized_files)

        # 4. Build symbol index for ranked files
        symbols_by_file = {fs.path: fs for fs in all_symbols}

        # 5. Format into token-budgeted map
        return self._format_map(ranked, symbols_by_file)

    def _scan_files(self) -> list[FileSymbols]:
        """Scan all source files in the repository."""
        all_symbols = []

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                if detect_language(fpath) is None:
                    continue

                symbols = extract_symbols(fpath, self.root)
                if symbols and symbols.definitions:
                    all_symbols.append(symbols)

        return all_symbols

    def _format_map(
        self,
        ranked_files: list,
        symbols_by_file: dict[str, FileSymbols],
    ) -> str:
        """Format the repo map within token budget."""
        lines = ["## Repository Map", ""]
        token_count = self._count_tokens("\n".join(lines))

        for rf in ranked_files:
            fs = symbols_by_file.get(rf.path)
            if not fs:
                continue

            file_section = [f"### {rf.path}"]
            for defn in fs.definitions:
                sig = defn.signature
                if len(sig) > 100:
                    sig = sig[:97] + "..."
                file_section.append(f"  {defn.kind} {defn.name} (L{defn.line}): {sig}")

            section_text = "\n".join(file_section) + "\n"
            section_tokens = self._count_tokens(section_text)

            if token_count + section_tokens > self.token_budget:
                break

            lines.extend(file_section)
            lines.append("")
            token_count += section_tokens

        if len(lines) <= 2:
            return self._fallback_tree()

        return "\n".join(lines)

    def _fallback_tree(self) -> str:
        """Simple directory tree as fallback when no symbols found."""
        lines = ["## Repository Structure", ""]
        count = 0

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in sorted(dirnames)
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            depth = len(Path(dirpath).relative_to(self.root).parts)
            if depth > 3:
                dirnames.clear()
                continue

            indent = "  " * depth
            rel = Path(dirpath).relative_to(self.root)
            if depth > 0:
                lines.append(f"{indent}{rel.name}/")

            for fname in sorted(filenames):
                if fname.startswith(".") and fname != ".gitignore":
                    continue
                lines.append(f"{indent}  {fname}")
                count += 1
                if count > 100:
                    lines.append("  ... (truncated)")
                    return "\n".join(lines)

        return "\n".join(lines) if len(lines) > 2 else "No files found in repository."

    def _count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))
