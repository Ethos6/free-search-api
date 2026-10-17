"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    # Engines used when a request does not name any.
    engines: list[str] = field(default_factory=list)
    news_engines: list[str] = field(default_factory=list)
    # Per-engine HTTP timeout and overall deadline for a search (seconds).
    timeout: float = 6.0
    # Optional API keys. Empty = open server (fine for localhost / private networks).
    api_keys: list[str] = field(default_factory=list)
    # Optional outbound proxies (http://, https://, socks5://), rotated round-robin.
    proxies: list[str] = field(default_factory=list)
    # Cache
    cache_ttl: int = 3600
    cache_size: int = 4096
    redis_url: str | None = None
    # Requests per minute per API key / client IP. 0 = unlimited.
    rate_limit: int = 0
    # Optional upstream SearXNG instance, used by the "searxng" engine.
    searxng_url: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    # Max pages fetched in parallel when include_raw_content=true
    extract_concurrency: int = 5
    extract_max_chars: int = 20000

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(os.getenv("FREESEARCH_ENV_FILE", ".env"))
        return cls(
            engines=_list("FREESEARCH_ENGINES", "duckduckgo,brave,bing,yahoo,wikipedia"),
            news_engines=_list("FREESEARCH_NEWS_ENGINES", "bing_news,google_news"),
            timeout=_float("FREESEARCH_TIMEOUT", 6.0),
            api_keys=_list("FREESEARCH_API_KEYS"),
            proxies=_list("FREESEARCH_PROXIES"),
            cache_ttl=_int("FREESEARCH_CACHE_TTL", 3600),
            cache_size=_int("FREESEARCH_CACHE_SIZE", 4096),
            redis_url=os.getenv("FREESEARCH_REDIS_URL") or None,
            rate_limit=_int("FREESEARCH_RATE_LIMIT", 0),
            searxng_url=os.getenv("FREESEARCH_SEARXNG_URL") or None,
            cors_origins=_list("FREESEARCH_CORS_ORIGINS", "*"),
            extract_concurrency=_int("FREESEARCH_EXTRACT_CONCURRENCY", 5),
            extract_max_chars=_int("FREESEARCH_EXTRACT_MAX_CHARS", 20000),
        )
