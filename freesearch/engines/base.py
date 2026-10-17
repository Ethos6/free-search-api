"""Base class and helpers for search engines.

An engine is two pure functions plus metadata:

* ``build(req)``  -> the HTTP request to send (``RequestSpec``)
* ``parse(text, req)`` -> a list of ``Result``

Keeping them pure makes every parser unit-testable against saved HTML.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from lxml import html as lxml_html

from ..http import HttpClient, Response
from ..models import Result, SearchRequest


class EngineError(Exception):
    """The engine answered but something is wrong (bad status, unparsable page...)."""


class EngineBlocked(EngineError):
    """The engine is rate-limiting or showing a CAPTCHA to this IP."""


@dataclass
class RequestSpec:
    url: str
    method: str = "GET"
    params: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Engine:
    name: ClassVar[str]
    category: ClassVar[str] = "web"  # "web" or "news"
    weight: ClassVar[float] = 1.0  # importance when merging results
    description: ClassVar[str] = ""
    experimental: ClassVar[bool] = False
    #  Substrings that mean "you are being blocked".
    block_markers: ClassVar[tuple[str, ...]] = ()

    def build(self, req: SearchRequest) -> RequestSpec:  # pragma: no cover - abstract
        raise NotImplementedError

    def parse(self, text: str, req: SearchRequest) -> list[Result]:  # pragma: no cover - abstract
        raise NotImplementedError

    def check(self, resp: Response) -> None:
        """Raise if the response is a block page or an error."""
        if resp.status in (403, 429) or resp.status == 202:
            raise EngineBlocked(f"HTTP {resp.status}")
        if resp.status >= 400:
            raise EngineError(f"HTTP {resp.status}")
        head = resp.text[:20000].lower()
        title = _TITLE.search(head)
        if title and ("captcha" in title.group(1) or "are you a robot" in title.group(1)):
            raise EngineBlocked("CAPTCHA page")
        for marker in self.block_markers:
            if marker in head:
                raise EngineBlocked(f"block page detected ({marker!r})")

    async def search(self, client: HttpClient, req: SearchRequest) -> list[Result]:
        spec = self.build(req)
        resp = await client.request(
            spec.method,
            spec.url,
            params=spec.params,
            data=spec.data,
            headers=spec.headers,
            cookies=spec.cookies,
        )
        self.check(resp)
        results = self.parse(resp.text, req)
        for i, r in enumerate(results, 1):
            r.engine = self.name
            r.engines = [self.name]
            r.position = i
        return results


# --------------------------------------------------------------------------- helpers

_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)


def clean(text: str | None) -> str:
    """Collapse whitespace and unescape HTML entities."""
    if not text:
        return ""
    return _WS.sub(" ", html_lib.unescape(text)).strip()


def strip_tags(text: str | None) -> str:
    return clean(_TAG.sub(" ", text or ""))


def parse_html(text: str) -> lxml_html.HtmlElement:
    if not text or not text.strip():
        raise EngineError("empty response")
    return lxml_html.fromstring(text)


def node_text(node: Any) -> str:
    if node is None:
        return ""
    return clean(node.text_content())


def first(*node_lists: list[Any]) -> Any:
    """First node of the first non-empty list (lets callers pass fallbacks in order)."""
    for nodes in node_lists:
        if len(nodes):
            return nodes[0]
    return None


def split_region(region: str) -> tuple[str, str]:
    """'us-en' -> ('us', 'en'). Tolerates 'en-US' and bare 'en'."""
    parts = region.lower().replace("_", "-").split("-")
    if len(parts) == 1:
        return ("us", parts[0] or "en")
    a, b = parts[0], parts[1]
    # Accept both <country>-<lang> and <lang>-<country>
    langs = {"en", "de", "fr", "es", "it", "pt", "nl", "ru", "ja", "zh", "ko", "hi", "ar", "pl", "tr", "sv"}
    if a in langs and b not in langs:
        return (b, a)
    return (a, b)


_DATE_PREFIX = re.compile(
    r"^((?:\d{1,2} \w{3,9},? \d{4})|(?:\w{3,9} \d{1,2}, \d{4})|(?:\d+ (?:hours?|days?|weeks?|mins?|minutes?) ago))\s*[·\-–—]\s*",
    re.IGNORECASE,
)


def split_date_prefix(snippet: str) -> tuple[str | None, str]:
    """Many engines prefix snippets with a date ("20 Jun 2026 · ...")."""
    m = _DATE_PREFIX.match(snippet)
    if not m:
        return None, snippet
    return m.group(1), snippet[m.end() :]
