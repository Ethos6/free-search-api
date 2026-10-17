"""Use an existing SearXNG instance as one more engine (set FREESEARCH_SEARXNG_URL)."""

from __future__ import annotations

import json

from ..models import Result, SearchRequest
from .base import Engine, EngineError, RequestSpec, clean, split_region

SAFE = {"off": "0", "moderate": "1", "strict": "2"}


class SearXNG(Engine):
    name = "searxng"
    weight = 1.0
    description = "Your own SearXNG instance (JSON API) — set FREESEARCH_SEARXNG_URL"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or "").rstrip("/")

    def build(self, req: SearchRequest) -> RequestSpec:
        if not self.base_url:
            raise EngineError("FREESEARCH_SEARXNG_URL is not set")
        _country, lang = split_region(req.region)
        params = {
            "q": req.q,
            "format": "json",
            "pageno": str(req.page),
            "language": lang,
            "safesearch": SAFE[req.safesearch],
            "categories": "news" if req.category == "news" else "general",
        }
        if req.time_range:
            params["time_range"] = req.time_range
        return RequestSpec(url=f"{self.base_url}/search", params=params)

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise EngineError("SearXNG did not return JSON (enable `json` in search.formats)") from exc
        return [
            Result(
                title=clean(r.get("title")),
                url=r["url"],
                content=clean(r.get("content")),
                published_date=r.get("publishedDate"),
            )
            for r in data.get("results", [])
            if r.get("url")
        ]
