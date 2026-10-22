"""Fetch a web page and return its main content as clean Markdown (for LLMs / RAG)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

from .http import HttpClient, HttpError
from .models import ExtractResult


def _is_public_url(url: str) -> bool:
    """Block SSRF: only http(s) URLs that resolve to public IP addresses."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True  # resolution may happen through a proxy; let the fetch decide
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def html_to_markdown(html: str, url: str | None = None) -> tuple[str | None, str]:
    import trafilatura

    title = None
    try:
        meta = trafilatura.extract_metadata(html, default_url=url)
        title = meta.title if meta else None
    except Exception:
        pass
    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=False,
        favor_recall=True,
    )
    if not text:
        from lxml import html as lxml_html

        try:
            tree = lxml_html.fromstring(html)
            for bad in tree.xpath("//script|//style|//noscript|//nav|//footer|//header"):
                bad.drop_tree()
            text = " ".join(tree.text_content().split())
        except Exception:
            text = ""
    return title, text or ""


#: Statuses that mean "busy, try again shortly" (rate limiting, temporary overload).
RETRY_STATUSES = (429, 503)
#: Longest Retry-After we are willing to wait for, in seconds.
MAX_RETRY_WAIT = 3.0


def _retry_delay(value: str | None) -> float:
    """Seconds to wait before retrying, from a Retry-After header (seconds form only)."""
    try:
        return min(MAX_RETRY_WAIT, max(0.0, float(value))) if value else 1.0
    except ValueError:
        return 1.0  # an HTTP-date or garbage: use a short default


async def extract_url(client: HttpClient, url: str, max_chars: int = 20000, timeout: float = 10.0) -> ExtractResult:
    current = url
    retried = False
    for _hop in range(7):  # follow redirects manually so every hop is SSRF-checked
        if not await asyncio.to_thread(_is_public_url, current):
            return ExtractResult(url=current, ok=False, error="URL is not a public http(s) address")
        try:
            resp = await client.get(current, timeout=timeout, allow_redirects=False)
        except HttpError as exc:
            return ExtractResult(url=current, ok=False, error=str(exc))
        if resp.status in RETRY_STATUSES and not retried:
            # One polite retry: sites such as Wikipedia rate-limit busy shared IPs briefly.
            retried = True
            await asyncio.sleep(_retry_delay(resp.headers.get("retry-after")))
            continue
        location = resp.headers.get("location")
        if resp.status in (301, 302, 303, 307, 308) and location:
            current = urljoin(current, location)
            continue
        break
    else:
        return ExtractResult(url=current, ok=False, error="too many redirects")
    if resp.status >= 400:
        return ExtractResult(url=url, ok=False, error=f"HTTP {resp.status}")
    ctype = resp.headers.get("content-type", "")
    if "text/plain" in ctype or "markdown" in ctype:
        return ExtractResult(url=current, content=resp.text[:max_chars])
    if "html" not in ctype and "xml" not in ctype and ctype:
        return ExtractResult(url=current, ok=False, error=f"unsupported content-type: {ctype}")
    title, text = await asyncio.to_thread(html_to_markdown, resp.text, current)
    return ExtractResult(url=current, title=title, content=text[:max_chars], ok=bool(text))
