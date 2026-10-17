"""Brave Search (independent index, HTML)."""

from __future__ import annotations

from ..models import Result, SearchRequest
from .base import Engine, RequestSpec, first, node_text, parse_html, split_date_prefix, split_region

TIME = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}


class Brave(Engine):
    name = "brave"
    weight = 1.1
    description = "Brave Search — its own independent web index"
    block_markers = ("pow-captcha", "/search/captcha")

    def build(self, req: SearchRequest) -> RequestSpec:
        country, _lang = split_region(req.region)
        params: dict[str, str] = {"q": req.q, "source": "web"}
        if req.page > 1:
            params["offset"] = str(req.page - 1)
        if req.time_range:
            params["tf"] = TIME[req.time_range]
        cookies = {"safesearch": req.safesearch, "country": country, "useLocation": "0"}
        return RequestSpec(url="https://search.brave.com/search", params=params, cookies=cookies)

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        tree = parse_html(text)
        out: list[Result] = []
        for item in tree.xpath("//div[@data-type='web']"):
            a = first(item.xpath(".//a[starts-with(@href, 'http')]"))
            if a is None:
                continue
            title_node = first(item.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' title ')]"))
            title = node_text(title_node) or node_text(a)
            desc = first(
                item.xpath(".//div[contains(@class,'generic-snippet')]//div[contains(@class,'content')]"),
                item.xpath(".//div[contains(@class,'generic-snippet')]"),
                item.xpath(".//*[contains(@class,'snippet-description')]"),
            )
            date, snippet = split_date_prefix(node_text(desc))
            out.append(Result(title=title, url=a.get("href"), content=snippet, published_date=date))
        return out
