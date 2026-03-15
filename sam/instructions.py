"""Load project instructions from SAM.md files.

Search order (all found files are concatenated):
  1. ~/.sam/SAM.md                — global user instructions
  2. Walk from CWD upward        — project-level instructions
  3. CWD/SAM.md or CWD/.sam.md   — local directory instructions
"""

from __future__ import annotations

from pathlib import Path

INSTRUCTION_FILENAMES = ("SAM.md", ".sam.md")


def load_project_instructions(working_dir: Path) -> str:
    """Load and concatenate all SAM.md instruction files.

    Returns empty string if none found.
    """
    found: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    # 1. Global instructions
    global_path = Path.home() / ".sam" / "SAM.md"
    if global_path.is_file():
        content = _read_safe(global_path)
        if content:
            found.append((global_path, content))
            seen.add(global_path.resolve())

    # 2. Walk from CWD upward (project-level)
    current = working_dir.resolve()
    for parent in [current, *current.parents]:
        for name in INSTRUCTION_FILENAMES:
            candidate = parent / name
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            if candidate.is_file():
                content = _read_safe(candidate)
                if content:
                    found.append((candidate, content))
                    seen.add(resolved)
        # Stop at home or filesystem root
        if parent == Path.home() or parent == parent.parent:
            break

    if not found:
        return ""

    sections = []
    for path, content in found:
        sections.append(f"<!-- Instructions from {path} -->\n{content}")

    return "\n\n---\n\n".join(sections)


def _read_safe(path: Path) -> str:
    """Read a file, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
