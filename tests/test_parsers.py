"""Parser tests against fixtures modeled on each engine's live markup."""

from pathlib import Path

import pytest

from freesearch.engines import EngineBlocked, build_engines
from freesearch.engines.base import split_date_prefix, split_region
from freesearch.http import Response
from freesearch.models import SearchRequest

FIX = Path(__file__).parent / "fixtures"
ENGINES = build_engines()
REQ = SearchRequest(q="fastapi tutorial")


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_duckduckgo():
    res = ENGINES["duckduckgo"].parse(load("duckduckgo.html"), REQ)
    assert [r.url for r in res] == [
        "https://fastapi.tiangolo.com/tutorial/",
        "https://www.geeksforgeeks.org/python/fastapi-tutorial/?utm_source=x",
    ]
    assert res[0].title == "Tutorial - User Guide - FastAPI"
    assert res[0].content.startswith("This tutorial shows you")


def test_bing_unwraps_redirects_and_skips_ads():
    res = ENGINES["bing"].parse(load("bing.html"), REQ)
    assert [r.url for r in res] == [
        "https://fastapi.tiangolo.com/tutorial/",
        "https://www.geeksforgeeks.org/python/fastapi-tutorial/",
    ]
    assert res[1].published_date == "20 Jun 2026"
    assert res[1].content.startswith("FastAPI is a modern")


def test_brave():
    res = ENGINES["brave"].parse(load("brave.html"), REQ)
    assert len(res) == 2  # video block ignored
    assert res[0].title == "Tutorial - User Guide - FastAPI"
    assert res[0].url == "https://fastapi.tiangolo.com/tutorial/"
    assert res[1].published_date == "20 June 2026"


def test_yahoo_unwraps_ru_and_picks_title_span():
    res = ENGINES["yahoo"].parse(load("yahoo.html"), REQ)
    assert res[0].url == "https://fastapi.tiangolo.com/tutorial/"
    assert res[0].title == "Tutorial - User Guide - FastAPI"
    assert res[1].published_date == "Jun 20, 2026"


def test_mojeek():
    res = ENGINES["mojeek"].parse(load("mojeek.html"), REQ)
    assert res[0].url == "https://fastapi.tiangolo.com/tutorial/"
    assert res[0].content == "This tutorial shows you how to use FastAPI."


def test_wikipedia():
    res = ENGINES["wikipedia"].parse(load("wikipedia.json"), REQ)
    assert res[0].url == "https://en.wikipedia.org/wiki/FastAPI"
    assert res[0].content == "FastAPI is a modern web framework"
    assert "Python_%28programming_language%29" in res[1].url


def test_bing_news():
    res = ENGINES["bing_news"].parse(load("bing_news.xml"), REQ)
    assert res[0].url == "https://example.com/news/openai-story"
    assert res[0].source == "Example News"
    assert res[0].published_date.startswith("2026-10-17T06:00:00")
    assert "today" in res[0].content


def test_google_news_strips_source_suffix():
    res = ENGINES["google_news"].parse(load("google_news.xml"), REQ)
    assert res[0].title == "OpenAI models do something"
    assert res[0].source == "Ars Technica"


@pytest.mark.parametrize(
    "body,status",
    [
        ("<html><head><title>Captcha</title></head></html>", 200),
        ("<html>ok</html>", 429),
        ('<div class="anomaly-modal">', 200),
    ],
)
def test_block_detection(body, status):
    eng = ENGINES["duckduckgo"]
    with pytest.raises(EngineBlocked):
        eng.check(Response(status=status, text=body, url="https://x", headers={}))


def test_build_requests():
    for name, eng in ENGINES.items():
        if name == "searxng":
            continue
        spec = eng.build(SearchRequest(q="hello world", page=2, time_range="week", region="in-en"))
        assert spec.url.startswith("https://")


def test_helpers():
    assert split_region("us-en") == ("us", "en")
    assert split_region("en-US") == ("us", "en")
    assert split_region("de") == ("us", "de")
    assert split_date_prefix("3 days ago · hello") == ("3 days ago", "hello")
    assert split_date_prefix("no date here") == (None, "no date here")
