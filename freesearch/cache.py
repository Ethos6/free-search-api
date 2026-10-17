"""Response cache: in-memory TTL/LRU by default, Redis when FREESEARCH_REDIS_URL is set."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Protocol


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int) -> None: ...
    async def aclose(self) -> None: ...


class MemoryCache:
    def __init__(self, max_items: int = 4096) -> None:
        self.max_items = max_items
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()

    async def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        if ttl <= 0 or self.max_items <= 0:
            return
        self._data[key] = (time.monotonic() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)

    async def aclose(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class RedisCache:  # pragma: no cover - needs a Redis server
    def __init__(self, url: str) -> None:
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise RuntimeError("pip install 'free-search-api[redis]' to use FREESEARCH_REDIS_URL") from exc
        self._r = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        try:
            return await self._r.get(f"freesearch:{key}")
        except Exception:
            return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        if ttl <= 0:
            return
        try:
            await self._r.set(f"freesearch:{key}", value, ex=ttl)
        except Exception:
            pass

    async def aclose(self) -> None:
        await self._r.aclose()


def make_cache(redis_url: str | None, max_items: int) -> Cache:
    if redis_url:
        return RedisCache(redis_url)
    return MemoryCache(max_items)
