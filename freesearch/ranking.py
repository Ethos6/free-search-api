"""Merge results from several engines: URL normalization, de-duplication and
Reciprocal Rank Fusion (RRF). A page that several independent engines rank highly
floats to the top, which beats any single engine's ordering."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .models import Result

RRF_K = 60
TRACKING_PARAMS = {"fbclid", "gclid", "msclkid", "yclid", "mc_cid", "mc_eid", "ref_src", "srsltid", "_hsenc", "_hsmi"}


def normalize_url(url: str) -> str:
    """A comparison key: scheme-, www-, fragment-, tracking- and trailing-slash-insensitive."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if p.port and p.port not in (80, 443):
        host = f"{host}:{p.port}"
    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
        )
    )
    path = p.path.rstrip("/") or "/"
    return urlunparse(("", host, path, "", query, ""))


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def domain_matches(url: str, domains: list[str]) -> bool:
    host = domain_of(url)
    for d in domains:
        d = d.lower().strip().removeprefix("www.").split("/")[0]
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def merge(results_by_engine: dict[str, list[Result]], weights: dict[str, float]) -> list[Result]:
    merged: dict[str, Result] = {}
    best_contrib: dict[str, float] = {}
    for engine, results in results_by_engine.items():
        w = weights.get(engine, 1.0)
        for rank, r in enumerate(results, 1):
            if not r.title or not r.url.startswith(("http://", "https://")):
                continue
            key = normalize_url(r.url)
            contrib = w / (RRF_K + rank)
            cur = merged.get(key)
            if cur is None:
                merged[key] = r.model_copy(update={"engines": [engine], "engine": engine, "score": contrib})
                best_contrib[key] = contrib
                continue
            cur.score += contrib
            if engine not in cur.engines:
                cur.engines.append(engine)
            # keep the richest snippet and any date/source we learn
            if len(r.content) > len(cur.content):
                cur.content = r.content
            cur.published_date = cur.published_date or r.published_date
            cur.source = cur.source or r.source
            if contrib > best_contrib[key]:
                best_contrib[key] = contrib
                cur.engine = engine
    ranked = sorted(merged.values(), key=lambda r: r.score, reverse=True)
    top = ranked[0].score if ranked else 1.0
    for i, r in enumerate(ranked, 1):
        r.position = i
        r.score = round(r.score / top, 4) if top else 0.0
    return ranked
