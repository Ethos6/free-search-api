"""Async HTTP client with browser TLS fingerprints and proxy rotation.

Search engines block obvious bots mostly by fingerprinting the TLS/HTTP2 handshake.
curl_cffi impersonates real browsers at that level, which is what keeps plain-HTTP
scraping fast (no headless browser) and reliable.
"""

from __future__ import annotations

import asyncio
import itertools
import random
from dataclasses import dataclass
from typing import Any

from curl_cffi.requests import AsyncSession

# Browser fingerprints to rotate between (curl_cffi aliases that track the newest version).
IMPERSONATE = ("chrome", "edge", "safari")


@dataclass
class Response:
    status: int
    text: str
    url: str
    headers: dict[str, str]


class HttpError(Exception):
    """Network-level failure (DNS, TLS, timeout, proxy...)."""


class HttpClient:
    def __init__(self, proxies: list[str] | None = None, timeout: float = 6.0) -> None:
        self.proxies: list[str | None] = list(proxies) if proxies else [None]
        self.timeout = timeout
        self._counter = itertools.count()
        self._sessions: dict[tuple[int, str | None], AsyncSession] = {}

    def _session(self, proxy: str | None) -> AsyncSession:
        loop_id = id(asyncio.get_running_loop())
        key = (loop_id, proxy)
        session = self._sessions.get(key)
        if session is None:
            session = AsyncSession(
                impersonate=random.choice(IMPERSONATE),
                proxy=proxy,
                timeout=self.timeout,
                allow_redirects=True,
                max_redirects=5,
            )
            self._sessions[key] = session
        return session

    def next_proxy(self) -> str | None:
        return self.proxies[next(self._counter) % len(self.proxies)]

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = True,
    ) -> Response:
        proxy = self.next_proxy()
        session = self._session(proxy)
        try:
            resp = await session.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                cookies=cookies,
                timeout=timeout or self.timeout,
                allow_redirects=allow_redirects,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # curl_cffi raises its own RequestsError subclasses
            raise HttpError(f"{type(exc).__name__}: {exc}") from exc
        return Response(
            status=resp.status_code,
            text=resp.text,
            url=str(resp.url),
            headers={k.lower(): v for k, v in resp.headers.items()},
        )

    async def get(self, url: str, **kw: Any) -> Response:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw: Any) -> Response:
        return await self.request("POST", url, **kw)

    async def aclose(self) -> None:
        sessions, self._sessions = list(self._sessions.values()), {}
        for s in sessions:
            try:
                await s.close()
            except Exception:  # pragma: no cover - best effort
                pass
