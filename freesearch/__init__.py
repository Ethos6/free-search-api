"""FreeSearch API — self-hosted, keyless, unlimited web search API."""

__version__ = "1.0.0"

from .config import Settings  # noqa: E402
from .core import FreeSearch  # noqa: E402
from .models import Result, SearchRequest, SearchResponse  # noqa: E402


def search(q: str, **kwargs):
    """Synchronous one-liner: ``freesearch.search("python asyncio")``."""
    import asyncio

    async def _run():
        async with FreeSearch() as fs:
            return await fs.search(q, **kwargs)

    return asyncio.run(_run())


__all__ = ["FreeSearch", "Result", "SearchRequest", "SearchResponse", "Settings", "__version__", "search"]
