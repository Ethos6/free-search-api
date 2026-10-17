"""Google (experimental).

Google's normal results page needs JavaScript. The lightweight WML endpoint still
serves plain HTML to very old mobile browsers, so this engine identifies as one.
Google blocks datacenter IPs quickly — keep it opt-in and pair it with proxies.
"""

from __future__ import annotations

import random
from urllib.parse import parse_qs, urlparse

from ..models import Result, SearchRequest
from .base import Engine, RequestSpec, first, node_text, parse_html, split_region

SAFE = {"strict": "2", "moderate": "1", "off": "0"}
TIME = {"day": "d", "week": "w", "month": "m", "year": "y"}


def _old_phone_ua() -> str:
    fw = random.choice(("2.0617.1.0.3", "2.0625.2.0.2", "2.0635.2.0.2", "5.0706.4.0.1"))
    return f"NokiaN72/{fw} Series60/2.8 Profile/MIDP-2.0 Configuration/CLDC-1.1"


def unwrap_google(href: str) -> str:
    if href.startswith("/url?"):
        q = parse_qs(urlparse(href).query)
        return (q.get("q") or q.get("url") or [href])[0]
    return href


class Google(Engine):
    name = "google"
    weight = 1.3
    experimental = True
    description = "Google via the legacy WML endpoint (experimental, blocks datacenter IPs)"
    block_markers = ("/sorry/index", "unusual traffic", "enablejs")

    def build(self, req: SearchRequest) -> RequestSpec:
        country, lang = split_region(req.region)
        params = {
            "q": req.q,
            "hl": f"{lang}-{country.upper()}",
            "lr": f"lang_{lang}",
            "filter": SAFE[req.safesearch],
            "start": str((req.page - 1) * 10),
        }
        if req.time_range:
            params["tbs"] = f"qdr:{TIME[req.time_range]}"
        return RequestSpec(
            url="https://www.google.com/wml/search",
            params=params,
            headers={"User-Agent": _old_phone_ua()},
            cookies={"CONSENT": "YES+"},
        )

    def parse(self, text: str, req: SearchRequest) -> list[Result]:
        tree = parse_html(text[text.find("?>") + 2 :] if text.lstrip().startswith("<?") else text)
        out: list[Result] = []
        for item in tree.xpath("//div[./div[1]/a and ./div[2][table]]"):
            a = first(item.xpath("./div[a]/a"))
            if a is None:
                continue
            url = unwrap_google(a.get("href", ""))
            if not url.startswith("http"):
                continue
            title = node_text(first(a.xpath("./span[1]"))) or node_text(a)
            out.append(Result(title=title, url=url, content=node_text(first(item.xpath("./div[2]")))))
        return out
