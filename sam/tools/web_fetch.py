"""Fetch and extract text content from web URLs.

Supports two strategies:
1. Fast HTTP fetch via httpx (default) — works for static pages
2. Headless browser via Playwright — for SPAs and JS-rendered content

When the fast fetch returns very little text (SPA indicator), it
automatically retries with Playwright if available.
"""

from __future__ import annotations

import re

from sam.tools.base import Tool, ToolResult

# Minimum text length to consider a page "real" content.
# Below this, the page is likely a SPA shell with no server-rendered content.
SPA_THRESHOLD = 200


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
            "Automatically uses a headless browser (Playwright) for SPAs "
            "and JavaScript-rendered pages when the static fetch returns little content. "
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
                "browser": {
                    "type": "boolean",
                    "description": (
                    "Force headless browser mode (for known SPAs). Default: false (auto-detect)"
                ),
                },
            },
            "required": ["url"],
        }

    async def execute(
        self, url: str, max_length: int = 8000, browser: bool = False, **kwargs
    ) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(output="URL must start with http:// or https://", error=True)

        # If browser mode is forced, go straight to Playwright
        if browser:
            return await self._fetch_with_browser(url, max_length)

        # Try fast static fetch first
        result = await self._fetch_static(url, max_length)
        if result.error:
            return result

        # Check if we got meaningful content
        text = result.output
        stripped = re.sub(r"\s+", "", text)

        if len(stripped) < SPA_THRESHOLD:
            # Looks like a SPA shell — try headless browser
            browser_result = await self._fetch_with_browser(url, max_length)
            if not browser_result.error:
                browser_stripped = re.sub(r"\s+", "", browser_result.output)
                if len(browser_stripped) > len(stripped):
                    return browser_result
            # Browser didn't help or isn't available — return the static result
            if not browser_result.error:
                return browser_result

        return result

    async def _fetch_static(self, url: str, max_length: int) -> ToolResult:
        """Fast HTTP fetch via httpx."""
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
                headers={"User-Agent": "SAM-Agent/0.2 (coding assistant)"},
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

        if "html" in content_type:
            text = _extract_html(text)
        elif "json" in content_type:
            pass
        # else: plain text as-is

        if len(text) > max_length:
            text = text[:max_length] + f"\n... (truncated, {len(text)} chars total)"

        return ToolResult(output=text)

    async def _fetch_with_browser(self, url: str, max_length: int) -> ToolResult:
        """Fetch using Playwright headless browser for JS-rendered pages."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolResult(
                output=(
                    "Playwright is not installed. To enable browser fetching for SPAs:\n"
                    "  pip install playwright\n"
                    "  playwright install chromium"
                ),
                error=True,
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="SAM-Agent/0.2 (coding assistant)",
                )
                page = await context.new_page()

                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception:
                    # Fallback: try with just domcontentloaded
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        # Give JS a moment to render
                        await page.wait_for_timeout(2000)
                    except Exception as e:
                        await browser.close()
                        return ToolResult(output=f"Browser failed to load {url}: {e}", error=True)

                # Extract text content
                html = await page.content()
                await browser.close()

        except Exception as e:
            return ToolResult(output=f"Browser fetch failed: {e}", error=True)

        text = _extract_html(html)

        if len(text) > max_length:
            text = text[:max_length] + f"\n... (truncated, {len(text)} chars total)"

        if not text.strip():
            return ToolResult(output=f"Page rendered but no text content extracted from {url}")

        return ToolResult(output=f"[browser-rendered]\n{text}")


class BrowserFetchTool(Tool):
    """Dedicated headless browser tool for JS-heavy pages."""

    @property
    def name(self) -> str:
        return "browser_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a web page using a headless Chromium browser (Playwright). "
            "Use this for Single Page Applications (SPAs), JavaScript-rendered content, "
            "pages behind client-side routing, or when web_fetch returns empty/minimal content. "
            "Slower than web_fetch but handles dynamic content."
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
                "wait_for": {
                    "type": "string",
                    "description": "CSS selector to wait for before extracting content (optional)",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (default: 8000)",
                },
                "screenshot": {
                    "type": "boolean",
                    "description": "Save a screenshot to /tmp/sam_screenshot.png (default: false)",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        wait_for: str | None = None,
        max_length: int = 8000,
        screenshot: bool = False,
        **kwargs,
    ) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(output="URL must start with http:// or https://", error=True)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolResult(
                output=(
                    "Playwright is not installed. Run:\n"
                    "  pip install playwright\n"
                    "  playwright install chromium"
                ),
                error=True,
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="SAM-Agent/0.2 (coding assistant)",
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()

                # Navigate
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception:
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(3000)
                    except Exception as e:
                        await browser.close()
                        return ToolResult(output=f"Failed to load {url}: {e}", error=True)

                # Wait for specific element if requested
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except Exception:
                        pass  # Continue anyway — element might not appear

                # Take screenshot if requested
                screenshot_msg = ""
                if screenshot:
                    screenshot_path = "/tmp/sam_screenshot.png"
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        screenshot_msg = f"\nScreenshot saved: {screenshot_path}"
                    except Exception:
                        screenshot_msg = "\nScreenshot failed."

                # Get page title
                title = await page.title()

                # Extract text content
                html = await page.content()

                # Also get the visible text directly from the page
                visible_text = await page.evaluate("""
                    () => {
                        const body = document.body;
                        if (!body) return '';
                        // Remove script/style/nav elements
                        const clone = body.cloneNode(true);
                        clone.querySelectorAll(
                            'script, style, nav, footer, header, aside, [aria-hidden="true"]'
                        )
                            .forEach(el => el.remove());
                        return clone.innerText || clone.textContent || '';
                    }
                """)

                await browser.close()

        except Exception as e:
            return ToolResult(output=f"Browser fetch failed: {e}", error=True)

        # Prefer JS-extracted visible text, fall back to HTML parsing
        if visible_text and len(visible_text.strip()) > 100:
            text = re.sub(r"\n{3,}", "\n\n", visible_text.strip())
        else:
            text = _extract_html(html)

        if len(text) > max_length:
            text = text[:max_length] + f"\n... (truncated, {len(text)} chars total)"

        if not text.strip():
            return ToolResult(output=f"Page loaded but no text content found at {url}")

        header = f"Title: {title}\nURL: {url}{screenshot_msg}\n\n"
        return ToolResult(output=header + text)


def _extract_html(html: str) -> str:
    """Extract readable text from HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    except ImportError:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
