#!/usr/bin/env sh
# Native API
curl "http://localhost:8000/search?q=rust+async+runtime&max_results=5"
curl "http://localhost:8000/news?q=open+source+ai&time_range=week"
curl "http://localhost:8000/extract?url=https://en.wikipedia.org/wiki/Web_search_engine"

# Tavily-compatible
curl -X POST http://localhost:8000/tavily/search -H "Content-Type: application/json" \
  -d '{"query": "rust async runtime", "max_results": 5, "include_answer": true}'

# Serper-compatible
curl -X POST http://localhost:8000/serper/search -H "X-API-KEY: any" -H "Content-Type: application/json" \
  -d '{"q": "rust async runtime", "num": 5}'

# Brave Search API-compatible
curl "http://localhost:8000/brave/res/v1/web/search?q=rust+async+runtime&count=5"

# SearXNG-compatible
curl "http://localhost:8000/searxng/search?q=rust+async+runtime&format=json"
