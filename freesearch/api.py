"""FastAPI application: native API + drop-in compatible endpoints for popular search APIs."""

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings
from .core import FreeSearch
from .models import ExtractResult, SearchRequest, SearchResponse

TIME_ALIASES = {
    "d": "day",
    "w": "week",
    "m": "month",
    "y": "year",
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}


def _time(value: str | None) -> str | None:
    if not value:
        return None
    return TIME_ALIASES.get(value.lower().strip())


def _split(value: str | list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        items = [x for v in value for x in v.split(",")]
    else:
        items = value.split(",")
    items = [x.strip() for x in items if x.strip()]
    return items or None


class RateLimiter:
    """Fixed one-minute window per client. In-process; use a reverse proxy for multi-node limits."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])

    def allow(self, client: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        window = self._hits[client]
        if now - window[0] >= 60:
            window[0], window[1] = now, 0
        window[1] += 1
        if len(self._hits) > 50000:  # bound memory
            self._hits.clear()
        return window[1] <= self.per_minute


def create_app(settings: Settings | None = None, fs: FreeSearch | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    limiter = RateLimiter(settings.rate_limit)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.fs = fs or FreeSearch(settings)
        yield
        await app.state.fs.aclose()

    app = FastAPI(
        title="FreeSearch API",
        version=__version__,
        description=(
            "Self-hosted, keyless web search API. Aggregates DuckDuckGo, Brave, Bing, Yahoo, Wikipedia and more, "
            "with drop-in endpoints compatible with Tavily, Serper, Brave Search API and SearXNG."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    async def auth(request: Request) -> None:
        """Accepts every auth style the compatible APIs use, so existing clients just work."""
        token = None
        h = request.headers
        authz = h.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:].strip()
        token = token or h.get("x-api-key") or h.get("x-subscription-token") or request.query_params.get("api_key")
        if not token and request.method == "POST" and "json" in h.get("content-type", ""):
            try:
                body = await request.json()
                if isinstance(body, dict):
                    token = body.get("api_key")
            except Exception:
                pass
        if settings.api_keys and token not in settings.api_keys:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        client = token or (request.client.host if request.client else "anon")
        if not limiter.allow(client):
            raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": "60"})

    def get_fs(request: Request) -> FreeSearch:
        return request.app.state.fs

    Auth = Depends(auth)
    FS = Annotated[FreeSearch, Depends(get_fs)]

    async def run(fs_: FreeSearch, req: SearchRequest) -> SearchResponse:
        try:
            return await fs_.search(req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ------------------------------------------------------------------ meta
    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        page = Path(__file__).with_name("static").joinpath("index.html")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    @app.get("/engines", tags=["meta"], dependencies=[Auth])
    async def engines(fs_: FS) -> dict[str, Any]:
        return {"engines": fs_.engine_status()}

    # ------------------------------------------------------------------ native API
    @app.get("/search", response_model=SearchResponse, tags=["search"], dependencies=[Auth])
    async def search_get(
        fs_: FS,
        q: Annotated[str, Query(min_length=1, max_length=500, description="Search query")],
        max_results: Annotated[int, Query(ge=1, le=50)] = 10,
        page: Annotated[int, Query(ge=1, le=10)] = 1,
        region: str = "us-en",
        safesearch: Literal["off", "moderate", "strict"] = "moderate",
        time_range: Annotated[str | None, Query(description="day|week|month|year (or d|w|m|y)")] = None,
        engines: Annotated[str | None, Query(description="Comma-separated engine names")] = None,
        mode: Literal["full", "fast"] = "full",
        include_answer: bool = False,
        include_raw_content: bool = False,
        include_domains: Annotated[str | None, Query(description="Comma-separated domains")] = None,
        exclude_domains: Annotated[str | None, Query(description="Comma-separated domains")] = None,
    ) -> SearchResponse:
        return await run(
            fs_,
            SearchRequest(
                q=q,
                max_results=max_results,
                page=page,
                region=region,
                safesearch=safesearch,
                time_range=_time(time_range),  # type: ignore[arg-type]
                engines=_split(engines),
                mode=mode,
                include_answer=include_answer,
                include_raw_content=include_raw_content,
                include_domains=_split(include_domains),
                exclude_domains=_split(exclude_domains),
            ),
        )

    @app.post("/search", response_model=SearchResponse, tags=["search"], dependencies=[Auth])
    async def search_post(fs_: FS, req: SearchRequest) -> SearchResponse:
        return await run(fs_, req)

    @app.get("/news", response_model=SearchResponse, tags=["search"], dependencies=[Auth])
    async def news_get(
        fs_: FS,
        q: Annotated[str, Query(min_length=1, max_length=500)],
        max_results: Annotated[int, Query(ge=1, le=50)] = 10,
        region: str = "us-en",
        time_range: str | None = None,
        engines: str | None = None,
    ) -> SearchResponse:
        return await run(
            fs_,
            SearchRequest(
                q=q,
                category="news",
                max_results=max_results,
                region=region,
                time_range=_time(time_range),
                engines=_split(engines),  # type: ignore[arg-type]
            ),
        )

    class ExtractBody(BaseModel):
        urls: list[str] | str = Field(..., description="One URL or a list (max 20)")

    @app.get("/extract", response_model=ExtractResult, tags=["extract"], dependencies=[Auth])
    async def extract_get(fs_: FS, url: str) -> ExtractResult:
        return (await fs_.extract([url]))[0]

    @app.post("/extract", tags=["extract"], dependencies=[Auth])
    async def extract_post(fs_: FS, body: ExtractBody) -> dict[str, Any]:
        urls = [body.urls] if isinstance(body.urls, str) else body.urls
        if len(urls) > 20:
            raise HTTPException(400, "max 20 URLs per request")
        return {"results": [r.model_dump() for r in await fs_.extract(urls)]}

    # ------------------------------------------------------------------ Tavily-compatible
    class TavilySearch(BaseModel):
        query: str
        max_results: int = 5
        search_depth: str | None = None
        topic: str | None = "general"
        time_range: str | None = None
        days: int | None = None
        include_answer: bool | str = False
        include_raw_content: bool | str = False
        include_domains: list[str] | None = None
        exclude_domains: list[str] | None = None
        country: str | None = None

        model_config = {"extra": "allow"}

    @app.post("/tavily/search", tags=["compat: Tavily"], dependencies=[Auth])
    async def tavily_search(fs_: FS, body: TavilySearch) -> dict[str, Any]:
        tr = _time(body.time_range)
        if not tr and body.days:
            tr = "day" if body.days <= 1 else "week" if body.days <= 7 else "month" if body.days <= 31 else "year"
        res = await run(
            fs_,
            SearchRequest(
                q=body.query,
                category="news" if body.topic == "news" else "web",
                max_results=max(1, min(body.max_results, 50)),
                time_range=tr,  # type: ignore[arg-type]
                include_answer=bool(body.include_answer),
                include_raw_content=bool(body.include_raw_content),
                include_domains=body.include_domains or None,
                exclude_domains=body.exclude_domains or None,
            ),
        )
        return {
            "query": res.query,
            "answer": res.answer,
            "images": [],
            "follow_up_questions": None,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "content": r.content,
                    "score": r.score,
                    "raw_content": r.raw_content,
                    **({"published_date": r.published_date} if r.published_date else {}),
                }
                for r in res.results
            ],
            "response_time": res.response_time,
        }

    class TavilyExtract(BaseModel):
        urls: list[str] | str
        model_config = {"extra": "allow"}

    @app.post("/tavily/extract", tags=["compat: Tavily"], dependencies=[Auth])
    async def tavily_extract(fs_: FS, body: TavilyExtract) -> dict[str, Any]:
        started = time.perf_counter()
        urls = [body.urls] if isinstance(body.urls, str) else body.urls[:20]
        pages = await fs_.extract(urls)
        return {
            "results": [{"url": p.url, "raw_content": p.content, "images": []} for p in pages if p.ok],
            "failed_results": [{"url": p.url, "error": p.error} for p in pages if not p.ok],
            "response_time": round(time.perf_counter() - started, 3),
        }

    # ------------------------------------------------------------------ Serper-compatible
    class SerperBody(BaseModel):
        q: str
        num: int = 10
        page: int = 1
        gl: str | None = None
        hl: str | None = None
        tbs: str | None = None
        model_config = {"extra": "allow"}

    def _serper_req(body: SerperBody, category: str) -> SearchRequest:
        region = f"{(body.gl or 'us').lower()}-{(body.hl or 'en').lower().split('-')[0]}"
        tr = None
        if body.tbs and body.tbs.startswith("qdr:"):
            tr = _time(body.tbs[4:5])
        return SearchRequest(
            q=body.q,
            category=category,
            max_results=max(1, min(body.num, 50)),  # type: ignore[arg-type]
            page=max(1, min(body.page, 10)),
            region=region,
            time_range=tr,  # type: ignore[arg-type]
        )

    @app.post("/serper/search", tags=["compat: Serper"], dependencies=[Auth])
    async def serper_search(fs_: FS, body: Annotated[SerperBody, Body()]) -> dict[str, Any]:
        res = await run(fs_, _serper_req(body, "web"))
        return {
            "searchParameters": {
                "q": body.q,
                "type": "search",
                "num": body.num,
                "page": body.page,
                "engine": "freesearch",
            },
            "organic": [
                {
                    "title": r.title,
                    "link": r.url,
                    "snippet": r.content,
                    "position": r.position,
                    **({"date": r.published_date} if r.published_date else {}),
                }
                for r in res.results
            ],
        }

    @app.post("/serper/news", tags=["compat: Serper"], dependencies=[Auth])
    async def serper_news(fs_: FS, body: Annotated[SerperBody, Body()]) -> dict[str, Any]:
        res = await run(fs_, _serper_req(body, "news"))
        return {
            "searchParameters": {"q": body.q, "type": "news", "num": body.num, "engine": "freesearch"},
            "news": [
                {
                    "title": r.title,
                    "link": r.url,
                    "snippet": r.content,
                    "date": r.published_date,
                    "source": r.source,
                    "position": r.position,
                }
                for r in res.results
            ],
        }

    # ------------------------------------------------------------------ Brave Search API-compatible
    @app.get("/brave/res/v1/web/search", tags=["compat: Brave"], dependencies=[Auth])
    async def brave_web(
        fs_: FS,
        q: str,
        count: Annotated[int, Query(ge=1, le=50)] = 10,
        offset: Annotated[int, Query(ge=0, le=9)] = 0,
        country: str = "us",
        search_lang: str = "en",
        safesearch: Literal["off", "moderate", "strict"] = "moderate",
        freshness: str | None = None,
    ) -> dict[str, Any]:
        tr = {"pd": "day", "pw": "week", "pm": "month", "py": "year"}.get(freshness or "")
        res = await run(
            fs_,
            SearchRequest(
                q=q,
                max_results=count,
                page=offset + 1,
                region=f"{country.lower()}-{search_lang.lower()}",
                safesearch=safesearch,
                time_range=tr,  # type: ignore[arg-type]
            ),
        )
        return {
            "type": "search",
            "query": {"original": q, "more_results_available": bool(res.results)},
            "web": {
                "type": "search",
                "results": [
                    {
                        "type": "search_result",
                        "title": r.title,
                        "url": r.url,
                        "description": r.content,
                        **({"page_age": r.published_date} if r.published_date else {}),
                    }
                    for r in res.results
                ],
            },
        }

    # ------------------------------------------------------------------ SearXNG-compatible
    @app.get("/searxng/search", tags=["compat: SearXNG"], dependencies=[Auth])
    async def searxng_search(
        fs_: FS,
        q: str,
        pageno: Annotated[int, Query(ge=1, le=10)] = 1,
        language: str = "en",
        time_range: str | None = None,
        safesearch: int = 1,
        categories: str = "general",
        engines: str | None = None,
        format: str = "json",
    ) -> dict[str, Any]:
        lang = language.split("-")[0].lower() if language and language != "all" else "en"
        res = await run(
            fs_,
            SearchRequest(
                q=q,
                page=pageno,
                region=f"us-{lang}",
                time_range=_time(time_range),  # type: ignore[arg-type]
                safesearch={0: "off", 2: "strict"}.get(safesearch, "moderate"),  # type: ignore[arg-type]
                category="news" if "news" in categories else "web",
                engines=_split(engines),
                max_results=20,
            ),
        )
        return {
            "query": q,
            "number_of_results": res.number_of_results,
            "results": [
                {
                    "url": r.url,
                    "title": r.title,
                    "content": r.content,
                    "engine": r.engine,
                    "engines": r.engines,
                    "score": r.score,
                    "category": "news" if res.category == "news" else "general",
                    "publishedDate": r.published_date,
                    "positions": [r.position],
                }
                for r in res.results
            ],
            "answers": [res.answer] if res.answer else [],
            "corrections": [],
            "infoboxes": [],
            "suggestions": [],
            "unresponsive_engines": [[e.name, e.error or ""] for e in res.engines if not e.ok],
        }

    return app


app = create_app()
