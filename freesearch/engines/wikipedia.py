"""Wikipedia via its official MediaWiki API (no scraping, very reliable)."""

from __future__ import annotations

import json
from urllib.parse import quote

from ..models import Result, SearchRequest
from .base import Engine, EngineError, RequestSpec, split_region, strip_tags

USER_AGENT = "FreeSearchAPI/1.0 (https://github.com/Ethos6/free-search-api)"


class Wikipedia(Engine):
    name = "wikipedia"
    weight = 0.7
    description = "Wikipedia — official MediaWiki search API"
    max_results = 3  # encyclopedia hits should complement, not flood, web results

    def build(self, req: SearchRequest) -> RequestSpec:
        _country, lang = split_region(req.region)
        limit = min(self.max_results, req.max_results)
        params = {
            "action": "query",
            "list": "search",
            "srsearch": req.q,
            "format": "json",
            "utf8": "1",
            "srlimit": str(limit),
            "sroffset": str((req.page - 1) * limit),
            "srprop": "snippet|timestamp",
        }
        return RequestSpec(
            url=f"https://{lang}.wikipedia.org/w/api.php",
            params=params,
            headers={"User-Agent": USER_AGENT, "Api-User-Agent": USER_AGENT},
            extra={"lang": lang},
        )

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise EngineError("invalid JSON from Wikipedia") from exc
        _country, lang = split_region(req.region)
        out: list[Result] = []
        for hit in data.get("query", {}).get("search", []):
            title = hit.get("title", "")
            out.append(
                Result(
                    title=title,
                    url=f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                    content=strip_tags(hit.get("snippet", "")),
                    published_date=hit.get("timestamp"),
                    source="Wikipedia",
                )
            )
        return out
