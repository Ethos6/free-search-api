"""Live checks against the real engines. Run with:  pytest -m live -v

Engines can rate-limit a single IP at any moment, so an individual engine failing is
reported but not fatal; the test only fails if the aggregate search returns nothing.
"""

import pytest

from freesearch.config import Settings
from freesearch.core import FreeSearch
from freesearch.models import SearchRequest

pytestmark = pytest.mark.live

WEB = ["duckduckgo", "brave", "bing", "yahoo", "wikipedia", "mojeek", "google"]
NEWS = ["bing_news", "google_news"]


@pytest.fixture
async def fs():
    async with FreeSearch(Settings.from_env()) as inst:
        yield inst


@pytest.mark.parametrize("engine", WEB + NEWS)
async def test_engine(fs, engine):
    category = "news" if engine in NEWS else "web"
    res = await fs.search(SearchRequest(q="python programming language", engines=[engine], category=category))
    report = res.engines[0]
    print(f"\n{engine}: ok={report.ok} results={report.results} {report.elapsed_ms}ms error={report.error}")
    if not report.ok:
        pytest.skip(f"{engine} unavailable from this IP: {report.error}")
    assert res.results, f"{engine} answered but returned no parsable results"
    assert all(r.url.startswith("http") and r.title for r in res.results)


async def test_default_search_returns_results(fs):
    res = await fs.search(SearchRequest(q="open source web search api", include_answer=True))
    ok = [e.name for e in res.engines if e.ok]
    print(f"\nengines ok: {ok}; results: {res.number_of_results}; {res.response_time}s")
    assert res.number_of_results > 0


async def test_extract(fs):
    page = (await fs.extract(["https://en.wikipedia.org/wiki/Web_search_engine"]))[0]
    print(f"\nextract: ok={page.ok} chars={len(page.content)} error={page.error}")
    if not page.ok and page.error in ("HTTP 429", "HTTP 503"):
        # Like the engines above: the site rate-limiting this runner's IP isn't a bug in Free Search.
        pytest.skip(f"wikipedia is rate-limiting this IP: {page.error}")
    assert page.ok and len(page.content) > 500
