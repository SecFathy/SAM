"""Persistent memory tool — read/write/search memories across sessions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult

MEMORY_DIR = Path.home() / ".sam" / "memory"


def _ensure_memory_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _memory_file() -> Path:
    return MEMORY_DIR / "memories.json"


def _load_memories() -> list[dict]:
    path = _memory_file()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_memories(memories: list[dict]) -> None:
    _ensure_memory_dir()
    _memory_file().write_text(
        json.dumps(memories, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_relevant_memories(query: str, limit: int = 5) -> str:
    """Get memories relevant to a query (simple keyword matching).

    Called from the agent loop to inject into the system prompt.
    """
    memories = _load_memories()
    if not memories:
        return ""

    query_words = set(query.lower().split())
    scored = []
    for mem in memories:
        content = mem.get("content", "").lower()
        tags = " ".join(mem.get("tags", [])).lower()
        text = content + " " + tags
        score = sum(1 for w in query_words if w in text)
        if score > 0:
            scored.append((score, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    if not top:
        # Return the most recent memories as fallback
        top = [(0, m) for m in memories[-limit:]]

    lines = []
    for _, mem in top:
        tags = ", ".join(mem.get("tags", []))
        lines.append(f"- [{tags}] {mem['content']}")

    return "\n".join(lines)


class MemoryWriteTool(Tool):
    """Save a memory for future sessions."""

    @property
    def name(self) -> str:
        return "memory_write"

    @property
    def description(self) -> str:
        return (
            "Save a piece of information to persistent memory. "
            "Memories survive across sessions. Use for user preferences, "
            "project patterns, important decisions, and recurring solutions. "
            "Include relevant tags for searchability."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization (e.g., ['preference', 'python'])",
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str, tags: list[str] | None = None, **kwargs) -> ToolResult:
        memories = _load_memories()

        # Check for duplicate
        for mem in memories:
            if mem.get("content") == content:
                return ToolResult(output="This memory already exists.")

        memory = {
            "content": content,
            "tags": tags or [],
            "created_at": time.time(),
        }
        memories.append(memory)
        _save_memories(memories)

        return ToolResult(output=f"Memory saved ({len(memories)} total).")


class MemoryReadTool(Tool):
    """Search and read persistent memories."""

    @property
    def name(self) -> str:
        return "memory_read"

    @property
    def description(self) -> str:
        return (
            "Search persistent memories by keyword or tag. "
            "Returns matching memories from past sessions."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (matches content and tags)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 10)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, limit: int = 10, **kwargs) -> ToolResult:
        memories = _load_memories()
        if not memories:
            return ToolResult(output="No memories stored yet.")

        query_lower = query.lower()
        matches = []
        for mem in memories:
            content = mem.get("content", "")
            tags = " ".join(mem.get("tags", []))
            if query_lower in content.lower() or query_lower in tags.lower():
                matches.append(mem)

        if not matches:
            return ToolResult(output=f"No memories matching '{query}'.")

        matches = matches[:limit]
        lines = []
        for mem in matches:
            tags = ", ".join(mem.get("tags", []))
            tag_str = f" [{tags}]" if tags else ""
            lines.append(f"- {mem['content']}{tag_str}")

        return ToolResult(output=f"Found {len(matches)} memories:\n" + "\n".join(lines))


class MemoryDeleteTool(Tool):
    """Delete a memory by content match."""

    @property
    def name(self) -> str:
        return "memory_delete"

    @property
    def description(self) -> str:
        return "Delete a memory that matches the given content string."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content of the memory to delete (exact or substring match)",
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str, **kwargs) -> ToolResult:
        memories = _load_memories()
        content_lower = content.lower()
        remaining = [m for m in memories if content_lower not in m.get("content", "").lower()]

        deleted = len(memories) - len(remaining)
        if deleted == 0:
            return ToolResult(output=f"No memories matching '{content}'.")

        _save_memories(remaining)
        return ToolResult(output=f"Deleted {deleted} memory(s). {len(remaining)} remaining.")
