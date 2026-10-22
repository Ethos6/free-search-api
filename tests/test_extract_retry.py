"""extract_url retries once, politely, when a site says it is busy."""

import pytest

from freesearch import extract
from freesearch.http import Response

HTML = "<html><head><title>Hello</title></head><body><article><p>" + ("Plenty of real text here. " * 40) + "</p></article></body></html>"


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url, timeout=None, allow_redirects=True):
        self.calls += 1
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def no_dns_or_waiting(monkeypatch):
    monkeypatch.setattr(extract, "_is_public_url", lambda url: True)
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(extract.asyncio, "sleep", fake_sleep)
    return waits


def busy(status=429, retry_after=None):
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return Response(status=status, text="slow down", url="https://example.org/", headers=headers)


def ok():
    return Response(status=200, text=HTML, url="https://example.org/", headers={"content-type": "text/html"})


async def test_retries_once_after_429_and_succeeds(no_dns_or_waiting):
    client = FakeClient([busy(429, "2"), ok()])
    page = await extract.extract_url(client, "https://example.org/")
    assert page.ok and "Plenty of real text" in page.content
    assert client.calls == 2
    assert no_dns_or_waiting == [2.0]


async def test_gives_up_after_one_retry(no_dns_or_waiting):
    client = FakeClient([busy(503), busy(503)])
    page = await extract.extract_url(client, "https://example.org/")
    assert not page.ok and page.error == "HTTP 503"
    assert client.calls == 2


async def test_long_or_odd_retry_after_is_capped(no_dns_or_waiting):
    await extract.extract_url(FakeClient([busy(429, "3600"), ok()]), "https://example.org/")
    await extract.extract_url(FakeClient([busy(429, "Wed, 21 Oct 2026 07:28:00 GMT"), ok()]), "https://example.org/")
    assert no_dns_or_waiting == [extract.MAX_RETRY_WAIT, 1.0]


async def test_other_errors_are_not_retried(no_dns_or_waiting):
    client = FakeClient([busy(404), ok()])
    page = await extract.extract_url(client, "https://example.org/")
    assert page.error == "HTTP 404"
    assert client.calls == 1
