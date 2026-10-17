import pytest
from fastapi.testclient import TestClient

from freesearch.api import create_app


@pytest.fixture
def client(fs, settings):
    app = create_app(settings, fs=fs)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def locked_client(fs, settings):
    settings.api_keys = ["secret"]
    app = create_app(settings, fs=fs)
    with TestClient(app) as c:
        yield c


def test_health_and_index(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "FreeSearch" in client.get("/").text
    assert client.get("/openapi.json").status_code == 200


def test_search_get_and_post(client):
    r = client.get("/search", params={"q": "hello", "max_results": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["number_of_results"] == 3
    assert {"title", "url", "content", "score", "engines"} <= set(body["results"][0])
    r = client.post("/search", json={"q": "hello", "max_results": 2})
    assert r.json()["number_of_results"] == 2


def test_bad_engine_is_400(client):
    assert client.get("/search", params={"q": "x", "engines": "nope"}).status_code == 400


def test_engines_endpoint(client):
    names = {e["name"] for e in client.get("/engines").json()["engines"]}
    assert {"a", "b", "c"} <= names


def test_news(client):
    r = client.get("/news", params={"q": "x"})
    assert r.json()["results"][0]["url"] == "https://news.com/1"


def test_tavily_compat(client):
    r = client.post("/tavily/search", json={"query": "hello", "max_results": 2, "api_key": "anything"})
    body = r.json()
    assert r.status_code == 200
    assert body["query"] == "hello" and len(body["results"]) == 2
    assert {"title", "url", "content", "score"} <= set(body["results"][0])


def test_serper_compat(client):
    r = client.post("/serper/search", json={"q": "hello", "num": 2}, headers={"X-API-KEY": "x"})
    body = r.json()
    assert body["organic"][0]["position"] == 1
    assert {"title", "link", "snippet"} <= set(body["organic"][0])


def test_brave_compat(client):
    r = client.get("/brave/res/v1/web/search", params={"q": "hello", "count": 2})
    body = r.json()
    assert body["type"] == "search"
    assert {"title", "url", "description"} <= set(body["web"]["results"][0])


def test_searxng_compat(client):
    r = client.get("/searxng/search", params={"q": "hello", "format": "json"})
    body = r.json()
    assert body["results"] and {"url", "title", "content", "engine"} <= set(body["results"][0])
    assert any(e[0] == "c" for e in body["unresponsive_engines"])


def test_api_keys(locked_client):
    assert locked_client.get("/search", params={"q": "x"}).status_code == 401
    assert (
        locked_client.get("/search", params={"q": "x"}, headers={"Authorization": "Bearer secret"}).status_code == 200
    )
    assert locked_client.get("/search", params={"q": "x"}, headers={"X-API-Key": "secret"}).status_code == 200
    assert locked_client.get("/search", params={"q": "x", "api_key": "secret"}).status_code == 200
    r = locked_client.post("/tavily/search", json={"query": "x", "api_key": "secret"})
    assert r.status_code == 200
    assert locked_client.get("/health").status_code == 200  # health stays public


def test_rate_limit(fs, settings):
    settings.rate_limit = 2
    with TestClient(create_app(settings, fs=fs)) as c:
        codes = [c.get("/search", params={"q": f"q{i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_extract_blocks_private_addresses(client):
    r = client.get("/extract", params={"url": "http://127.0.0.1:8000/health"})
    body = r.json()
    assert body["ok"] is False and "public" in body["error"]
