"""Data models shared by engines, the aggregator and the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SafeSearch = Literal["off", "moderate", "strict"]
TimeRange = Literal["day", "week", "month", "year"]
Category = Literal["web", "news"]


class SearchRequest(BaseModel):
    """Parameters for one search."""

    q: str = Field(..., min_length=1, max_length=500, description="Search query")
    category: Category = "web"
    max_results: int = Field(10, ge=1, le=50)
    page: int = Field(1, ge=1, le=10)
    region: str = Field("us-en", description="Region as <country>-<language>, e.g. us-en, in-en, de-de")
    safesearch: SafeSearch = "moderate"
    time_range: TimeRange | None = None
    engines: list[str] | None = Field(None, description="Engines to use (default: server config)")
    mode: Literal["full", "fast"] = Field(
        "full",
        description="full = query engines in parallel and merge; fast = return the first engine that has enough results",
    )
    include_answer: bool = Field(False, description="Add an instant answer (DuckDuckGo / Wikipedia)")
    include_raw_content: bool = Field(False, description="Fetch every result page and return its main text as Markdown")
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None


class Result(BaseModel):
    """One normalized search result."""

    title: str
    url: str
    content: str = Field("", description="Snippet / description")
    engine: str = Field("", description="Engine that ranked this result highest")
    engines: list[str] = Field(default_factory=list, description="Every engine that returned this URL")
    score: float = 0.0
    position: int = 0
    published_date: str | None = None
    source: str | None = None
    raw_content: str | None = None


class EngineReport(BaseModel):
    """What happened when an engine was queried."""

    name: str
    ok: bool
    results: int = 0
    elapsed_ms: int = 0
    error: str | None = None
    skipped: bool = False


class SearchResponse(BaseModel):
    """Search output."""

    query: str
    category: Category = "web"
    answer: str | None = None
    results: list[Result]
    number_of_results: int
    engines: list[EngineReport]
    cached: bool = False
    response_time: float = 0.0


class ExtractResult(BaseModel):
    url: str
    title: str | None = None
    content: str = ""
    ok: bool = True
    error: str | None = None
