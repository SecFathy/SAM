"""Web search using DuckDuckGo."""

from __future__ import annotations

from typing import Any

from sam.tools.base import Tool, ToolResult


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo and return results."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. "
            "Useful for finding documentation, libraries, error solutions, and APIs."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5, max: 10)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        max_results = min(max_results, 10)

        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return ToolResult(
                output="duckduckgo-search is not installed. Run: pip install duckduckgo-search",
                error=True,
            )

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)
        except Exception as e:
            return ToolResult(output=f"Search failed: {e}", error=True)

        if not results:
            return ToolResult(output=f"No results found for: {query}")

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", ""))
            formatted.append(f"{i}. {title}\n   {url}\n   {snippet}")

        return ToolResult(output="\n\n".join(formatted))
