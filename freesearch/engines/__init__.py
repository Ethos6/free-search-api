"""Engine registry."""

from __future__ import annotations

from .base import Engine, EngineBlocked, EngineError, RequestSpec
from .bing import Bing
from .brave import Brave
from .duckduckgo import DuckDuckGo
from .google import Google
from .mojeek import Mojeek
from .news import BingNews, GoogleNews
from .searxng import SearXNG
from .wikipedia import Wikipedia
from .yahoo import Yahoo

ENGINE_CLASSES: dict[str, type[Engine]] = {
    cls.name: cls for cls in (DuckDuckGo, Brave, Bing, Yahoo, Wikipedia, Mojeek, Google, SearXNG, BingNews, GoogleNews)
}


def build_engines(searxng_url: str | None = None) -> dict[str, Engine]:
    engines: dict[str, Engine] = {}
    for name, cls in ENGINE_CLASSES.items():
        engines[name] = cls(searxng_url) if cls is SearXNG else cls()
    return engines


__all__ = ["ENGINE_CLASSES", "Engine", "EngineBlocked", "EngineError", "RequestSpec", "build_engines"]
