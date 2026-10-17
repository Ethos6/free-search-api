"""Bing web search (HTML)."""

from __future__ import annotations

import base64
from time import time
from urllib.parse import parse_qs, urlparse

from ..models import Result, SearchRequest
from .base import Engine, RequestSpec, first, node_text, parse_html, split_date_prefix, split_region

SAFE = {"strict": "strict", "moderate": "moderate", "off": "off"}


def unwrap_bing(href: str) -> str:
    """https://www.bing.com/ck/a?...&u=a1<base64url> -> original URL."""
    parsed = urlparse(href)
    if not (parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/a")):
        return href
    u = parse_qs(parsed.query).get("u", [""])[0]
    if len(u) <= 2:
        return href
    b64 = u[2:]
    try:
        return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode()
    except Exception:
        return href


class Bing(Engine):
    name = "bing"
    weight = 1.0
    description = "Microsoft Bing web results"
    block_markers = ("/turing/captcha", "b_captcha", "challenges.cloudflare")

    def build(self, req: SearchRequest) -> RequestSpec:
        country, lang = split_region(req.region)
        params: dict[str, str] = {"q": req.q, "setlang": lang, "cc": country, "adlt": SAFE[req.safesearch]}
        if req.page > 1:
            params["first"] = str((req.page - 1) * 10 + 1)
            params["FORM"] = "PERE"
        if req.time_range:
            day = int(time() // 86400)
            code = {"day": "ez1", "week": "ez2", "month": "ez3"}.get(req.time_range) or f"ez5_{day - 365}_{day}"
            params["filters"] = f'ex1:"{code}"'
        cookies = {
            "_EDGE_CD": f"m={lang}-{country}&u={lang}-{country}",
            "_EDGE_S": f"mkt={lang}-{country}&ui={lang}-{country}",
            "SRCHHPGUSR": f"ADLT={SAFE[req.safesearch].upper()}",
        }
        return RequestSpec(url="https://www.bing.com/search", params=params, cookies=cookies)

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        tree = parse_html(text)
        out: list[Result] = []
        for item in tree.xpath("//li[contains(concat(' ', normalize-space(@class), ' '), ' b_algo ')]"):
            a = first(item.xpath(".//h2//a[@href]"))
            if a is None:
                continue
            url = unwrap_bing(a.get("href", ""))
            if not url.startswith("http") or "bing.com/aclick" in url:
                continue
            p = first(item.xpath(".//div[contains(@class,'b_caption')]//p"), item.xpath(".//p"))
            date, snippet = split_date_prefix(node_text(p))
            out.append(Result(title=node_text(a), url=url, content=snippet, published_date=date))
        return out
