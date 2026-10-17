"""Mojeek (independent UK crawler). Strict anti-bot: off by default."""

from __future__ import annotations

from ..models import Result, SearchRequest
from .base import Engine, RequestSpec, first, node_text, parse_html, split_region


class Mojeek(Engine):
    name = "mojeek"
    weight = 0.8
    description = "Mojeek — independent, privacy-first index (aggressive CAPTCHA, opt-in)"
    block_markers = ()

    def build(self, req: SearchRequest) -> RequestSpec:
        country, lang = split_region(req.region)
        params: dict[str, str] = {"q": req.q}
        if req.safesearch == "strict":
            params["safe"] = "1"
        if req.page > 1:
            params["s"] = str((req.page - 1) * 10 + 1)
        return RequestSpec(url="https://www.mojeek.com/search", params=params, cookies={"arc": country, "lb": lang})

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        tree = parse_html(text)
        out: list[Result] = []
        for item in tree.xpath("//ul[contains(@class,'results-standard')]/li"):
            a = first(item.xpath(".//h2//a[@href]"), item.xpath(".//a[contains(@class,'title')]"))
            if a is None:
                continue
            snippet = node_text(first(item.xpath(".//p[contains(@class,'s')]")))
            out.append(Result(title=node_text(a), url=a.get("href"), content=snippet))
        return out
