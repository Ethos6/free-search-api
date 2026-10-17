"""Existing Tavily code, now free: just point the official client at your server."""

from tavily import TavilyClient  # pip install tavily-python

client = TavilyClient(api_key="anything-or-your-FREESEARCH-key", api_base_url="http://localhost:8000/tavily")
resp = client.search("latest python release", max_results=5, include_answer=True)
for r in resp["results"]:
    print(r["score"], r["title"], r["url"])
