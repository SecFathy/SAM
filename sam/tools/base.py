"""Tool ABC, ToolResult, and ToolRegistry."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# Tools that only read / observe — safe for plan mode.
READONLY_TOOLS: frozenset[str] = frozenset({
    "read_file",
    "grep",
    "glob",
    "list_directory",
    "git_status",
    "git_diff",
    "ask_user",
    "web_fetch",
    "web_search",
    "memory_read",
})


@dataclass
class ToolResult:
    """Result from executing a tool."""

    output: str
    error: bool = False

    def to_message(self, tool_call_id: str) -> dict:
        """Convert to an OpenAI tool message."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": self.output if not self.error else f"ERROR: {self.output}",
        }


class Tool(ABC):
    """Base class for all SAM tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name as it appears in the API."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments."""
        ...

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_openai_schemas(self, *, allowed: frozenset[str] | None = None) -> list[dict]:
        """Return OpenAI tool schemas, optionally filtered to *allowed* names."""
        tools = self._tools.values()
        if allowed is not None:
            tools = [t for t in tools if t.name in allowed]
        return [t.to_openai_schema() for t in tools]

    async def execute(
        self, name: str, arguments: dict, *, allowed: frozenset[str] | None = None,
    ) -> ToolResult:
        """Execute a tool by name with given arguments."""
        # Reject tools not in the allow-list (e.g. plan mode).
        if allowed is not None and name not in allowed:
            return ToolResult(
                output=f"Tool '{name}' is not available in plan mode. "
                       f"Only read-only tools are allowed: {', '.join(sorted(allowed))}",
                error=True,
            )
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(output=f"Unknown tool: {name}", error=True)
        try:
            return await tool.execute(**arguments)
        except TypeError as e:
            return ToolResult(output=f"Invalid arguments for {name}: {e}", error=True)
        except Exception as e:
            return ToolResult(output=f"Tool {name} failed: {e}", error=True)
