"""Test helpers: a FreeSearch instance whose engines return canned results (no network)."""

from __future__ import annotations

import asyncio

import pytest

from freesearch.config import Settings
from freesearch.core import FreeSearch
from freesearch.engines import EngineBlocked
from freesearch.models import Result


def fake_results(engine: str, urls: list[str]) -> list[Result]:
    return [Result(title=f"{engine} {u}", url=u, content=f"snippet from {engine} for {u}") for u in urls]


class FakeEngine:
    def __init__(self, name, urls=None, exc=None, delay=0.0, category="web", weight=1.0):
        self.name, self.urls, self.exc, self.delay = name, urls or [], exc, delay
        self.category, self.weight, self.description, self.experimental = category, weight, "fake", False
        self.calls = 0

    async def search(self, client, req):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        res = fake_results(self.name, self.urls)
        for i, r in enumerate(res, 1):
            r.engine, r.engines, r.position = self.name, [self.name], i
        return res


@pytest.fixture
def settings():
    return Settings(engines=["a", "b", "c"], news_engines=["n"], timeout=1.0, cache_ttl=60)


@pytest.fixture
def fs(settings):
    inst = FreeSearch(settings)
    inst.engines = {
        "a": FakeEngine("a", ["https://one.com/", "https://two.com/x", "https://three.com"]),
        "b": FakeEngine("b", ["https://www.two.com/x?utm_source=z", "https://four.com"]),
        "c": FakeEngine("c", exc=EngineBlocked("captcha")),
        "n": FakeEngine("n", ["https://news.com/1"], category="news"),
    }
    inst.health = {k: type(next(iter(inst.health.values())))() for k in inst.engines}
    return inst
