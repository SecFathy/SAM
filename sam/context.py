"""Parse @file mentions in user input and resolve file contents."""

from __future__ import annotations

import re
from pathlib import Path

from sam.repo.languages import EXTENSION_MAP
from sam.ui.console import print_warning

# Match @path/to/file patterns — must contain at least one dot (file extension)
# or be a dotfile. The @ must be at start of string or preceded by whitespace
# (prevents matching emails like user@file.py).
_FILE_MENTION_RE = re.compile(
    r"(?:^|(?<=\s))@(\.?[\w\-./]+\.[\w]+)",
)


def _lang_tag(path: Path) -> str:
    """Return a markdown code-fence language tag for a file path."""
    lang = EXTENSION_MAP.get(path.suffix.lower(), "")
    return lang


def resolve_file_mentions(
    user_input: str,
    working_dir: Path,
) -> tuple[str, str]:
    """Parse @file mentions, read files, return (clean_message, file_blocks).

    Parameters
    ----------
    user_input:
        Raw user input possibly containing @file references.
    working_dir:
        Base directory for resolving relative paths.

    Returns
    -------
    tuple of (clean_message, file_context):
        clean_message: user input with @file references stripped.
        file_context: formatted file contents block (empty string if none).
    """
    matches = _FILE_MENTION_RE.findall(user_input)
    if not matches:
        return user_input, ""

    seen: set[str] = set()
    file_blocks: list[str] = []
    clean = user_input

    for raw_path in matches:
        if raw_path in seen:
            continue
        seen.add(raw_path)

        resolved = (working_dir / raw_path).resolve()

        if not resolved.is_file():
            print_warning(f"File not found: {raw_path}")
            # Strip the mention from the message
            clean = clean.replace(f"@{raw_path}", raw_path)
            continue

        try:
            contents = resolved.read_text(errors="replace")
        except OSError as exc:
            print_warning(f"Cannot read {raw_path}: {exc}")
            clean = clean.replace(f"@{raw_path}", raw_path)
            continue

        lang = _lang_tag(resolved)
        block = f"### {raw_path}\n```{lang}\n{contents}\n```"
        file_blocks.append(block)

        # Strip the @mention from the clean message
        clean = clean.replace(f"@{raw_path}", "")

    clean = clean.strip()
    if not file_blocks:
        return clean or user_input, ""

    file_context = "--- Attached Files ---\n\n" + "\n\n".join(file_blocks)
    return clean, file_context


def build_enriched_message(user_input: str, working_dir: Path) -> str:
    """Build a single enriched message from user input + resolved @file contents."""
    clean, file_context = resolve_file_mentions(user_input, working_dir)
    if not file_context:
        return clean
    return f"{clean}\n\n{file_context}"
