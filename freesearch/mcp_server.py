"""MCP server: gives Claude Desktop, Cursor, Windsurf, etc. free web search + page reading.

freesearch mcp                                  # stdio (for desktop apps)
freesearch mcp --transport streamable-http      # http://localhost:8001/mcp
"""

from __future__ import annotations

from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from .core import FreeSearch
from .models import SearchRequest

_fs: FreeSearch | None = None


def _get() -> FreeSearch:
    global _fs
    if _fs is None:
        _fs = FreeSearch()
    return _fs


def build_server() -> Any:
    server = MCPServer(
        "freesearch",
        instructions="Free web search. Use web_search to find pages, then read_page to read the most relevant ones.",
    )

    @server.tool()
    async def web_search(query: str, max_results: int = 8, time_range: str | None = None) -> str:
        """Search the web. Returns numbered results with title, URL and snippet.

        Args:
            query: what to search for
            max_results: 1-20
            time_range: optional freshness filter: day, week, month or year
        """
        tr = time_range if time_range in ("day", "week", "month", "year") else None
        res = await _get().search(
            SearchRequest(q=query, max_results=max(1, min(max_results, 20)), time_range=tr, include_answer=True)  # type: ignore[arg-type]
        )
        return _format(res)

    @server.tool()
    async def news_search(query: str, max_results: int = 8) -> str:
        """Search recent news articles. Returns title, source, date, URL and summary."""
        res = await _get().search(SearchRequest(q=query, category="news", max_results=max(1, min(max_results, 20))))
        return _format(res)

    @server.tool()
    async def read_page(url: str) -> str:
        """Fetch a web page and return its main content as Markdown."""
        page = (await _get().extract([url]))[0]
        if not page.ok:
            return f"Could not read {url}: {page.error}"
        return f"# {page.title or url}\n\nSource: {page.url}\n\n{page.content}"

    return server


def _format(res: Any) -> str:
    lines = []
    if res.answer:
        lines.append(f"Answer: {res.answer}\n")
    for r in res.results:
        meta = " · ".join(x for x in (r.source, r.published_date) if x)
        lines.append(f"{r.position}. {r.title}\n   {r.url}" + (f"\n   {meta}" if meta else "") + f"\n   {r.content}")
    return "\n".join(lines) or "No results."


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8001) -> None:
    server = build_server()
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=host, port=port)
