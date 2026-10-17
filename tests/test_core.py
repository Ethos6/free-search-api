import pytest

from freesearch.models import SearchRequest
from freesearch.ranking import domain_matches, normalize_url


async def test_merge_dedup_and_rank(fs):
    res = await fs.search(SearchRequest(q="test"))
    urls = [r.url for r in res.results]
    # two.com/x was returned by both engines -> merged once and ranked first
    assert res.results[0].engines == ["a", "b"] or set(res.results[0].engines) == {"a", "b"}
    assert sum("two.com/x" in u for u in urls) == 1
    assert res.results[0].score == 1.0
    assert len(urls) == 4
    reports = {e.name: e for e in res.engines}
    assert reports["a"].ok and reports["b"].ok
    assert not reports["c"].ok and "blocked" in reports["c"].error


async def test_blocked_engine_cools_down(fs):
    await fs.search(SearchRequest(q="first"))
    assert not fs.health["c"].available()
    calls = fs.engines["c"].calls
    res = await fs.search(SearchRequest(q="second"))
    assert fs.engines["c"].calls == calls  # skipped while cooling down
    assert any(e.name == "c" and e.skipped for e in res.engines)


async def test_cache(fs):
    r1 = await fs.search(SearchRequest(q="cache me"))
    r2 = await fs.search(SearchRequest(q="  Cache   ME "))
    assert not r1.cached and r2.cached
    assert [r.url for r in r1.results] == [r.url for r in r2.results]


async def test_max_results_and_domain_filters(fs):
    res = await fs.search(SearchRequest(q="x", max_results=2))
    assert len(res.results) == 2
    res = await fs.search(SearchRequest(q="y", include_domains=["two.com"]))
    assert all("two.com" in r.url for r in res.results)
    res = await fs.search(SearchRequest(q="z", exclude_domains=["two.com", "one.com"]))
    assert all("two.com" not in r.url and "one.com" not in r.url for r in res.results)


async def test_fast_mode_returns_early(fs):
    fs.engines["b"].delay = 0.8
    res = await fs.search(SearchRequest(q="fast", mode="fast", max_results=3))
    assert len(res.results) == 3
    assert res.response_time < 0.7


async def test_unknown_engine(fs):
    with pytest.raises(ValueError):
        await fs.search(SearchRequest(q="x", engines=["nope"]))


async def test_news_category_uses_news_engines(fs):
    res = await fs.search(SearchRequest(q="x", category="news"))
    assert [r.url for r in res.results] == ["https://news.com/1"]


def test_normalize_url():
    assert normalize_url("https://www.Example.com/a/?utm_source=x&b=2#frag") == normalize_url(
        "http://example.com/a?b=2"
    )
    assert normalize_url("https://a.com/x") != normalize_url("https://a.com/y")


def test_domain_matches():
    assert domain_matches("https://docs.python.org/3/", ["python.org"])
    assert not domain_matches("https://notpython.org/", ["python.org"])
