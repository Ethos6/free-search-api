"""The search orchestrator: fan-out, failover, circuit breaking, caching, merging."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field

from .answer import instant_answer
from .cache import make_cache
from .config import Settings
from .engines import Engine, EngineBlocked, build_engines
from .extract import extract_url
from .http import HttpClient, HttpError
from .models import EngineReport, ExtractResult, Result, SearchRequest, SearchResponse
from .ranking import domain_matches, merge


@dataclass
class EngineHealth:
    """Circuit breaker state. Failing / blocked engines cool down so healthy ones answer fast."""

    failures: int = 0
    cooldown_until: float = 0.0
    last_error: str | None = None
    last_ok: float | None = None
    requests: int = 0
    successes: int = 0
    latencies: list[int] = field(default_factory=list)

    def available(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    def ok(self, ms: int) -> None:
        self.failures = 0
        self.cooldown_until = 0.0
        self.last_ok = time.time()
        self.requests += 1
        self.successes += 1
        self.latencies = (self.latencies + [ms])[-50:]

    def fail(self, error: str, blocked: bool) -> None:
        self.failures += 1
        self.requests += 1
        self.last_error = error
        if blocked:
            delay = min(60 * 2 ** (self.failures - 1), 1800)
        elif self.failures >= 3:
            delay = min(15 * 2 ** (self.failures - 3), 600)
        else:
            delay = 0
        self.cooldown_until = time.monotonic() + delay

    def as_dict(self) -> dict:
        lat = sorted(self.latencies)
        return {
            "available": self.available(),
            "cooldown_seconds": max(0, round(self.cooldown_until - time.monotonic())),
            "consecutive_failures": self.failures,
            "requests": self.requests,
            "success_rate": round(self.successes / self.requests, 3) if self.requests else None,
            "median_latency_ms": lat[len(lat) // 2] if lat else None,
            "last_error": self.last_error,
        }


class FreeSearch:
    """Use as a library::

    async with FreeSearch() as fs:
        res = await fs.search("best open source llm")
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.client = HttpClient(self.settings.proxies, timeout=self.settings.timeout)
        self.engines: dict[str, Engine] = build_engines(self.settings.searxng_url)
        self.health: dict[str, EngineHealth] = {name: EngineHealth() for name in self.engines}
        self.cache = make_cache(self.settings.redis_url, self.settings.cache_size)

    async def __aenter__(self) -> FreeSearch:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.client.aclose()
        await self.cache.aclose()

    # ------------------------------------------------------------------ helpers
    def _pick_engines(self, req: SearchRequest) -> list[str]:
        if req.engines:
            names = [e.strip().lower() for e in req.engines if e.strip()]
        else:
            names = self.settings.news_engines if req.category == "news" else self.settings.engines
            if self.settings.searxng_url and "searxng" not in names:
                names = [*names, "searxng"]
        unknown = [n for n in names if n not in self.engines]
        if unknown:
            raise ValueError(f"unknown engine(s): {', '.join(unknown)}. Available: {', '.join(self.engines)}")
        return list(dict.fromkeys(names))

    @staticmethod
    def _cache_key(req: SearchRequest, engines: list[str]) -> str:
        payload = req.model_dump(exclude={"engines"})
        payload["engines"] = sorted(engines)
        payload["q"] = " ".join(req.q.lower().split())
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _engine_query(req: SearchRequest) -> SearchRequest:
        q = req.q
        if req.include_domains:
            sites = " OR ".join(f"site:{d}" for d in req.include_domains[:5])
            q = f"{q} ({sites})" if len(req.include_domains) > 1 else f"{q} {sites}"
        if req.exclude_domains:
            q += " " + " ".join(f"-site:{d}" for d in req.exclude_domains[:5])
        return req.model_copy(update={"q": q})

    async def _run_engine(self, name: str, req: SearchRequest) -> tuple[str, list[Result], EngineReport]:
        engine = self.engines[name]
        health = self.health[name]
        start = time.perf_counter()
        try:
            results = await asyncio.wait_for(engine.search(self.client, req), timeout=self.settings.timeout + 1)
        except asyncio.CancelledError:
            raise
        except EngineBlocked as exc:
            health.fail(f"blocked: {exc}", blocked=True)
            return name, [], EngineReport(name=name, ok=False, error=f"blocked: {exc}", elapsed_ms=_ms(start))
        except (asyncio.TimeoutError, TimeoutError):
            health.fail("timeout", blocked=False)
            return name, [], EngineReport(name=name, ok=False, error="timeout", elapsed_ms=_ms(start))
        except (HttpError, Exception) as exc:  # noqa: BLE001 - one engine must never break a search
            health.fail(str(exc)[:200], blocked=False)
            return name, [], EngineReport(name=name, ok=False, error=str(exc)[:200], elapsed_ms=_ms(start))
        elapsed = _ms(start)
        health.ok(elapsed)
        return name, results, EngineReport(name=name, ok=True, results=len(results), elapsed_ms=elapsed)

    # ------------------------------------------------------------------ public API
    async def search(self, req: SearchRequest | str, **kwargs: object) -> SearchResponse:
        if isinstance(req, str):
            req = SearchRequest(q=req, **kwargs)  # type: ignore[arg-type]
        started = time.perf_counter()
        names = self._pick_engines(req)
        key = self._cache_key(req, names)
        cached = await self.cache.get(key)
        if cached:
            resp = SearchResponse.model_validate_json(cached)
            resp.cached = True
            resp.response_time = round(time.perf_counter() - started, 3)
            return resp

        available = [n for n in names if self.health[n].available()]
        skipped = [n for n in names if n not in available]
        if not available:  # everything is cooling down: try anyway rather than return nothing
            available, skipped = names, []

        engine_req = self._engine_query(req)
        reports: list[EngineReport] = [
            EngineReport(name=n, ok=False, skipped=True, error="cooling down") for n in skipped
        ]
        by_engine: dict[str, list[Result]] = {}

        tasks = [asyncio.create_task(self._run_engine(n, engine_req)) for n in available]
        answer_task = (
            asyncio.create_task(instant_answer(self.client, req.q, req.region)) if req.include_answer else None
        )
        deadline = self.settings.timeout + 1.5
        try:
            if req.mode == "fast":
                for fut in asyncio.as_completed(tasks, timeout=deadline):
                    try:
                        name, results, report = await fut
                    except (asyncio.TimeoutError, TimeoutError):
                        break
                    reports.append(report)
                    if results:
                        by_engine[name] = results
                    if sum(len(v) for v in by_engine.values()) >= req.max_results:
                        break
            else:
                done, _pending = await asyncio.wait(tasks, timeout=deadline)
                for t in done:
                    name, results, report = t.result()
                    reports.append(report)
                    if results:
                        by_engine[name] = results
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
        reported = {r.name for r in reports}
        for n in available:
            if n not in reported:
                reports.append(EngineReport(name=n, ok=False, error="cancelled (enough results / deadline)"))

        weights = {n: self.engines[n].weight for n in by_engine}
        merged = merge(by_engine, weights)
        if req.include_domains:
            merged = [r for r in merged if domain_matches(r.url, req.include_domains)]
        if req.exclude_domains:
            merged = [r for r in merged if not domain_matches(r.url, req.exclude_domains)]
        merged = merged[: req.max_results]
        for i, r in enumerate(merged, 1):
            r.position = i

        if req.include_raw_content and merged:
            pages = await self.extract([r.url for r in merged])
            for r, page in zip(merged, pages, strict=False):
                r.raw_content = page.content if page.ok else None

        answer = None
        if answer_task is not None:
            try:
                answer = await asyncio.wait_for(answer_task, timeout=self.settings.timeout)
            except Exception:  # noqa: BLE001
                answer = None

        order = {n: i for i, n in enumerate(names)}
        reports.sort(key=lambda r: order.get(r.name, 99))
        resp = SearchResponse(
            query=req.q,
            category=req.category,
            answer=answer,
            results=merged,
            number_of_results=len(merged),
            engines=reports,
            response_time=round(time.perf_counter() - started, 3),
        )
        if merged:
            await self.cache.set(key, resp.model_dump_json(), self.settings.cache_ttl)
        return resp

    async def news(self, q: str, **kwargs: object) -> SearchResponse:
        return await self.search(SearchRequest(q=q, category="news", **kwargs))  # type: ignore[arg-type]

    async def extract(self, urls: list[str]) -> list[ExtractResult]:
        sem = asyncio.Semaphore(self.settings.extract_concurrency)

        async def one(u: str) -> ExtractResult:
            async with sem:
                try:
                    return await extract_url(self.client, u, max_chars=self.settings.extract_max_chars)
                except Exception as exc:  # noqa: BLE001
                    return ExtractResult(url=u, ok=False, error=str(exc)[:200])

        return await asyncio.gather(*(one(u) for u in urls))

    def engine_status(self) -> list[dict]:
        out = []
        for name, eng in self.engines.items():
            default = name in (self.settings.news_engines if eng.category == "news" else self.settings.engines)
            out.append(
                {
                    "name": name,
                    "category": eng.category,
                    "description": eng.description,
                    "default": default,
                    "experimental": eng.experimental,
                    "weight": eng.weight,
                    **self.health[name].as_dict(),
                }
            )
        return out


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
