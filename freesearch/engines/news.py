"""News engines built on public RSS feeds (stable, structured, fast)."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

from lxml import etree

from ..models import Result, SearchRequest
from .base import Engine, EngineError, RequestSpec, clean, split_region, strip_tags


def _rfc822_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


def _items(text: str) -> list[etree._Element]:
    try:
        root = etree.fromstring(text.encode("utf-8"), parser=etree.XMLParser(recover=True, resolve_entities=False))
    except etree.XMLSyntaxError as exc:
        raise EngineError("invalid RSS") from exc
    if root is None:
        raise EngineError("empty RSS")
    return root.findall(".//item")


def _child(item: etree._Element, local: str) -> str | None:
    for el in item:
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag.split("}")[-1].split(":")[-1].lower() == local.lower():
            return el.text
    return None


class BingNews(Engine):
    name = "bing_news"
    category = "news"
    weight = 1.0
    description = "Bing News RSS feed"

    def build(self, req: SearchRequest) -> RequestSpec:
        country, lang = split_region(req.region)
        params = {"q": req.q, "format": "rss", "setlang": lang, "cc": country}
        if req.time_range:
            params["qft"] = {"day": 'interval="7"', "week": 'interval="8"'}.get(req.time_range, 'interval="9"')
        if req.page > 1:
            params["first"] = str((req.page - 1) * 10 + 1)
        return RequestSpec(url="https://www.bing.com/news/search", params=params)

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        out = []
        for item in _items(text):
            link = _child(item, "link") or ""
            parsed = urlparse(link)
            if "bing.com" in parsed.netloc:
                link = parse_qs(parsed.query).get("url", [link])[0]
            if not link.startswith("http"):
                continue
            out.append(
                Result(
                    title=clean(_child(item, "title")),
                    url=link,
                    content=strip_tags(_child(item, "description")),
                    published_date=_rfc822_to_iso(_child(item, "pubDate")),
                    source=clean(_child(item, "Source")) or None,
                )
            )
        return out


class GoogleNews(Engine):
    name = "google_news"
    category = "news"
    weight = 1.1
    description = "Google News RSS feed"

    def build(self, req: SearchRequest) -> RequestSpec:
        country, lang = split_region(req.region)
        q = req.q
        if req.time_range:
            q += " when:" + {"day": "1d", "week": "7d", "month": "30d", "year": "365d"}[req.time_range]
        cc = country.upper()
        return RequestSpec(
            url="https://news.google.com/rss/search",
            params={"q": q, "hl": f"{lang}-{cc}", "gl": cc, "ceid": f"{cc}:{lang}"},
        )

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        out = []
        for item in _items(text):
            title = clean(_child(item, "title"))
            source = clean(_child(item, "source")) or None
            if source and title.endswith(" - " + source):
                title = title[: -len(source) - 3]
            link = _child(item, "link") or ""
            if not link.startswith("http"):
                continue
            desc = strip_tags(_child(item, "description"))
            if source and desc.endswith(source):
                desc = desc[: -len(source)].strip()
            out.append(
                Result(
                    title=title,
                    url=link,
                    content=desc,
                    published_date=_rfc822_to_iso(_child(item, "pubDate")),
                    source=source,
                )
            )
        return out
