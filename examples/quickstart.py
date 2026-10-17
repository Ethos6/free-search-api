"""Use FreeSearch as a Python library (no server needed)."""

import asyncio

from freesearch import FreeSearch, SearchRequest


async def main() -> None:
    async with FreeSearch() as fs:
        res = await fs.search(SearchRequest(q="best open source vector database", max_results=5, include_answer=True))
        print("answer:", res.answer)
        for r in res.results:
            print(f"{r.position}. {r.title}\n   {r.url}\n   via {', '.join(r.engines)}")

        news = await fs.news("open source AI", time_range="week")
        for r in news.results[:5]:
            print(f"[{r.source}] {r.title} — {r.published_date}")

        page = (await fs.extract([res.results[0].url]))[0]
        print(page.content[:500])


asyncio.run(main())
