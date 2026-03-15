"""Fetch and extract text content from web URLs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sam.tools.base import Tool, ToolResult


class WebFetchTool(Tool):
    """Fetch a URL and extract readable text content."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a web page and extract its text content. "
            "Returns the main text without HTML tags. "
            "Useful for reading documentation, blog posts, and API references."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (default: 8000)",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, max_length: int = 8000, **kwargs) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(output="URL must start with http:// or https://", error=True)

        try:
            import httpx
        except ImportError:
            return ToolResult(
                output="httpx is not installed. Run: pip install httpx",
                error=True,
            )

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=15.0,
                headers={"User-Agent": "SAM-Agent/0.1 (coding assistant)"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.TimeoutException:
            return ToolResult(output=f"Request timed out: {url}", error=True)
        except httpx.HTTPStatusError as e:
            return ToolResult(output=f"HTTP {e.response.status_code}: {url}", error=True)
        except Exception as e:
            return ToolResult(output=f"Failed to fetch {url}: {e}", error=True)

        content_type = response.headers.get("content-type", "")
        text = response.text

        # Try BeautifulSoup for HTML extraction
        if "html" in content_type:
            text = self._extract_html(text)
        elif "json" in content_type:
            # Return raw JSON (already readable)
            pass
        else:
            # Plain text or other — use as-is
            pass

        # Truncate
        if len(text) > max_length:
            text = text[:max_length] + f"\n... (truncated, {len(text)} chars total)"

        return ToolResult(output=text)

    @staticmethod
    def _extract_html(html: str) -> str:
        """Extract readable text from HTML."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Remove script, style, nav, footer elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Try to find main content
            main = soup.find("main") or soup.find("article") or soup.find("body")
            if main:
                text = main.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            # Collapse multiple blank lines
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()

        except ImportError:
            # Fallback: regex-based tag stripping
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            return text.strip()
