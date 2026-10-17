"""Query every engine once and print a Markdown health table (used by the live CI job)."""

import asyncio
import sys

from freesearch import FreeSearch, SearchRequest
from freesearch.engines import ENGINE_CLASSES

QUERY = sys.argv[1] if len(sys.argv) > 1 else "python programming language"


async def main() -> int:
    rows = []
    async with FreeSearch() as fs:
        for name, cls in ENGINE_CLASSES.items():
            if name == "searxng" and not fs.settings.searxng_url:
                continue
            req = SearchRequest(q=QUERY, engines=[name], category=cls.category, max_results=10)
            res = await fs.search(req)
            e = res.engines[0]
            top = res.results[0].url if res.results else ""
            status = "✅" if e.ok and e.results else ("⚠️ empty" if e.ok else "❌")
            rows.append(f"| {name} | {status} | {e.results} | {e.elapsed_ms} | {(e.error or '')[:80]} | {top[:70]} |")
        agg = await fs.search(SearchRequest(q=QUERY, include_answer=True))
    print(f"### Engine health — query: `{QUERY}`\n")
    print("| engine | status | results | ms | error | top result |\n|---|---|---|---|---|---|")
    print("\n".join(rows))
    print(
        f"\n**Default multi-engine search:** {agg.number_of_results} results in {agg.response_time}s; "
        f"answer: {'yes' if agg.answer else 'no'}"
    )
    return 0 if agg.number_of_results else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
