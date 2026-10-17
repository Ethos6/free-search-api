"""Instant answers: DuckDuckGo Instant Answer API, falling back to a Wikipedia summary."""

from __future__ import annotations

import json
from urllib.parse import quote

from .engines.base import split_region
from .engines.wikipedia import USER_AGENT
from .http import HttpClient, HttpError


def parse_ddg_answer(text: str) -> str | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    for key in ("Answer", "AbstractText", "Definition"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


async def instant_answer(client: HttpClient, query: str, region: str = "us-en") -> str | None:
    try:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1", "no_redirect": "1"},
        )
        if resp.status == 200:
            ans = parse_ddg_answer(resp.text)
            if ans:
                return ans
    except HttpError:
        pass
    # Fallback: best-matching Wikipedia article summary
    _c, lang = split_region(region)
    headers = {"User-Agent": USER_AGENT, "Api-User-Agent": USER_AGENT}
    try:
        resp = await client.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": query, "limit": "1", "format": "json", "profile": "fuzzy"},
            headers=headers,
        )
        titles = json.loads(resp.text)[1] if resp.status == 200 else []
        if not titles:
            return None
        resp = await client.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(titles[0].replace(' ', '_'))}",
            headers=headers,
        )
        if resp.status == 200:
            data = json.loads(resp.text)
            if data.get("type") != "disambiguation":
                return data.get("extract") or None
    except (HttpError, json.JSONDecodeError, IndexError, KeyError):
        return None
    return None
