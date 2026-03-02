"""Symbol extraction from source files using tree-sitter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sam.repo.languages import detect_language, get_parser


@dataclass
class Symbol:
    """A code symbol (function, class, method, etc.)."""

    name: str
    kind: str  # "function", "class", "method", etc.
    file: str
    line: int
    end_line: int = 0
    signature: str = ""


@dataclass
class FileSymbols:
    """All symbols extracted from a single file."""

    path: str
    language: str
    definitions: list[Symbol] = field(default_factory=list)
    references: set[str] = field(default_factory=set)


def extract_symbols(file_path: Path, base_dir: Path) -> FileSymbols | None:
    """Extract symbols from a source file using tree-sitter.

    Falls back to regex-based extraction if tree-sitter fails.
    """
    lang = detect_language(file_path)
    if lang is None:
        return None

    rel_path = str(file_path.relative_to(base_dir))

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Try tree-sitter first
    symbols = _extract_with_tree_sitter(content, lang, rel_path)
    if symbols is not None:
        return symbols

    # Fallback to regex
    return _extract_with_regex(content, lang, rel_path)


def _extract_with_tree_sitter(
    content: str, lang: str, rel_path: str
) -> FileSymbols | None:
    """Extract symbols using tree-sitter parsing."""
    parser = get_parser(lang)
    if parser is None:
        return None

    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception:
        return None

    result = FileSymbols(path=rel_path, language=lang)
    _walk_tree(tree.root_node, content, result)

    # Extract references (identifiers that aren't definitions)
    def_names = {s.name for s in result.definitions}
    _extract_references(tree.root_node, def_names, result)

    return result


def _walk_tree(node, content: str, result: FileSymbols) -> None:
    """Walk the tree-sitter AST to find definitions."""
    kind_map = {
        "function_definition": "function",
        "function_declaration": "function",
        "class_definition": "class",
        "class_declaration": "class",
        "method_definition": "method",
        "method_declaration": "method",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "impl",
        "interface_declaration": "interface",
        "type_declaration": "type",
        "function_item": "function",
        "arrow_function": "function",
    }

    if node.type in kind_map:
        kind = kind_map[node.type]
        name = _get_name(node)
        if name:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Get first line as signature
            lines = content.splitlines()
            if start_line - 1 < len(lines):
                sig = lines[start_line - 1].strip()
            else:
                sig = ""

            result.definitions.append(Symbol(
                name=name,
                kind=kind,
                file=result.path,
                line=start_line,
                end_line=end_line,
                signature=sig,
            ))

    for child in node.children:
        _walk_tree(child, content, result)


def _get_name(node) -> str | None:
    """Get the name identifier from a definition node."""
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "type_identifier", "field_identifier"):
            return child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
    return None


def _extract_references(node, def_names: set[str], result: FileSymbols) -> None:
    """Extract identifier references (symbols used but not defined here)."""
    if node.type in ("identifier", "property_identifier", "type_identifier"):
        name = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text
        if name and name not in def_names and len(name) > 1:
            result.references.add(name)

    for child in node.children:
        _extract_references(child, def_names, result)


def _extract_with_regex(content: str, lang: str, rel_path: str) -> FileSymbols:
    """Fallback regex-based symbol extraction."""
    result = FileSymbols(path=rel_path, language=lang)

    patterns = {
        "python": [
            (r"^(\s*)def\s+(\w+)\s*\(", "function"),
            (r"^(\s*)class\s+(\w+)", "class"),
        ],
        "javascript": [
            (r"^(\s*)function\s+(\w+)\s*\(", "function"),
            (r"^(\s*)class\s+(\w+)", "class"),
            (r"^(\s*)(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function)", "function"),
        ],
        "typescript": [
            (r"^(\s*)function\s+(\w+)\s*[(<]", "function"),
            (r"^(\s*)class\s+(\w+)", "class"),
            (r"^(\s*)interface\s+(\w+)", "interface"),
            (r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function)", "function"),
        ],
        "rust": [
            (r"^(\s*)(?:pub\s+)?fn\s+(\w+)", "function"),
            (r"^(\s*)(?:pub\s+)?struct\s+(\w+)", "struct"),
            (r"^(\s*)(?:pub\s+)?enum\s+(\w+)", "enum"),
            (r"^(\s*)(?:pub\s+)?trait\s+(\w+)", "trait"),
            (r"^(\s*)impl\s+(\w+)", "impl"),
        ],
        "go": [
            (r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", "function"),
            (r"^type\s+(\w+)\s+struct", "struct"),
            (r"^type\s+(\w+)\s+interface", "interface"),
        ],
        "java": [
            (r"(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)+(\w+)\s*\(", "method"),
            (r"(?:public\s+)?class\s+(\w+)", "class"),
            (r"(?:public\s+)?interface\s+(\w+)", "interface"),
        ],
    }

    lang_patterns = patterns.get(lang, [])

    for line_num, line in enumerate(content.splitlines(), 1):
        for pattern, kind in lang_patterns:
            m = re.match(pattern, line)
            if m:
                # Get the name from the last capture group
                name = m.group(m.lastindex)
                if name and not name.startswith("_") or kind == "class":
                    result.definitions.append(Symbol(
                        name=name,
                        kind=kind,
                        file=rel_path,
                        line=line_num,
                        signature=line.strip(),
                    ))
                break

    return result
