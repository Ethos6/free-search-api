"""DuckDuckGo (HTML endpoint, no JavaScript needed)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from ..models import Result, SearchRequest
from .base import Engine, RequestSpec, first, node_text, parse_html, split_region

SAFE = {"strict": "1", "moderate": "-1", "off": "-2"}
TIME = {"day": "d", "week": "w", "month": "m", "year": "y"}


def unwrap_ddg(href: str) -> str:
    """//duckduckgo.com/l/?uddg=<encoded target>&rut=... -> target."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return href


class DuckDuckGo(Engine):
    name = "duckduckgo"
    weight = 1.2
    description = "DuckDuckGo HTML results (independent crawler + Bing index)"
    block_markers = ("anomaly-modal", "anomaly.js", "challenge-form")

    def build(self, req: SearchRequest) -> RequestSpec:
        country, lang = split_region(req.region)
        data = {"q": req.q, "b": "", "kl": f"{country}-{lang}", "kp": SAFE[req.safesearch]}
        if req.time_range:
            data["df"] = TIME[req.time_range]
        if req.page > 1:
            data["s"] = str(10 + (req.page - 2) * 15)
            data["dc"] = str(11 + (req.page - 2) * 15)
        return RequestSpec(
            url="https://html.duckduckgo.com/html/",
            method="POST",
            data=data,
            headers={"Referer": "https://html.duckduckgo.com/", "Origin": "https://html.duckduckgo.com"},
        )

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        tree = parse_html(text)
        out: list[Result] = []
        for item in tree.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' result ')]"):
            cls = item.get("class", "")
            if "result--ad" in cls or "result--no-result" in cls:
                continue
            a = first(item.xpath(".//a[contains(@class, 'result__a')]"))
            if a is None:
                continue
            url = unwrap_ddg(a.get("href", ""))
            if not url.startswith("http") or "duckduckgo.com/y.js" in url:
                continue
            snippet = node_text(first(item.xpath(".//*[contains(@class, 'result__snippet')]")))
            out.append(Result(title=node_text(a), url=url, content=snippet))
        return out
