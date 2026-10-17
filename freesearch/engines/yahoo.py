"""Yahoo web search (HTML)."""

from __future__ import annotations

from urllib.parse import unquote_plus

from ..models import Result, SearchRequest
from .base import Engine, RequestSpec, first, node_text, parse_html, split_date_prefix

TIME = {"day": "d", "week": "w", "month": "m", "year": "y"}
SAFE = {"strict": "r", "moderate": "i", "off": "p"}


def unwrap_yahoo(href: str) -> str:
    """https://r.search.yahoo.com/.../RU=<encoded>/RK=.../RS=... -> target."""
    if "/RU=" not in href:
        return href
    target = href.split("/RU=", 1)[1]
    target = target.split("/RK=", 1)[0].split("/RS=", 1)[0]
    return unquote_plus(target)


class Yahoo(Engine):
    name = "yahoo"
    weight = 0.9
    description = "Yahoo web results"
    block_markers = ("unusual traffic from your computer",)

    def build(self, req: SearchRequest) -> RequestSpec:
        params: dict[str, str] = {"p": req.q, "vm": SAFE[req.safesearch]}
        if req.page > 1:
            params["b"] = str((req.page - 1) * 7 + 1)
        if req.time_range:
            params["btf"] = TIME[req.time_range]
        return RequestSpec(url="https://search.yahoo.com/search", params=params)

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        tree = parse_html(text)
        out: list[Result] = []
        for item in tree.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' algo ')]"):
            a = first(item.xpath(".//div[contains(@class,'compTitle')]//a[@href]"), item.xpath(".//h3//a[@href]"))
            if a is None:
                continue
            url = unwrap_yahoo(a.get("href", ""))
            if not url.startswith("http") or "/cbclk" in url or "bing.com/aclick" in url:
                continue
            h3 = first(item.xpath(".//h3"))
            # The title span is the last one inside <h3>; earlier spans hold the display URL.
            spans = h3.xpath(".//span") if h3 is not None else []
            title = node_text(spans[-1]) if spans else node_text(h3) or node_text(a)
            date, snippet = split_date_prefix(node_text(first(item.xpath(".//div[contains(@class,'compText')]"))))
            out.append(Result(title=title, url=url, content=snippet, published_date=date))
        return out
