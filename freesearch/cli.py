"""Command line: `freesearch serve | search | news | extract | mcp | engines`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import __version__


def _print_results(res, as_json: bool) -> None:
    if as_json:
        print(res.model_dump_json(indent=2))
        return
    if res.answer:
        print(f"\n  {res.answer}\n")
    for r in res.results:
        extra = " · ".join(x for x in (r.source, r.published_date) if x)
        print(f"{r.position:>2}. {r.title}")
        print(f"    {r.url}")
        if extra:
            print(f"    {extra}")
        if r.content:
            print(f"    {r.content[:200]}")
        print(f"    [{', '.join(r.engines)}]")
    status = ", ".join(f"{e.name}:{'ok' if e.ok else (e.error or 'fail')}" for e in res.engines)
    print(f"\n{res.number_of_results} results in {res.response_time}s  ({status})", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="freesearch", description="Self-hosted keyless web search API")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the HTTP API server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--reload", action="store_true")

    for name in ("search", "news"):
        q = sub.add_parser(name, help=f"{name} from the terminal")
        q.add_argument("query", nargs="+")
        q.add_argument("-n", "--max-results", type=int, default=10)
        q.add_argument("-e", "--engines", help="comma-separated engines")
        q.add_argument("-t", "--time-range", choices=["day", "week", "month", "year"])
        q.add_argument("-r", "--region", default="us-en")
        q.add_argument("--answer", action="store_true", help="include instant answer")
        q.add_argument("--json", action="store_true")

    x = sub.add_parser("extract", help="print a page's main content as Markdown")
    x.add_argument("url")

    sub.add_parser("engines", help="list engines")

    m = sub.add_parser("mcp", help="run as an MCP server")
    m.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8001)

    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("freesearch.api:app", host=args.host, port=args.port, workers=args.workers, reload=args.reload)
        return

    if args.cmd == "mcp":
        from .mcp_server import run

        run(args.transport, args.host, args.port)
        return

    from .core import FreeSearch
    from .models import SearchRequest

    async def go() -> None:
        async with FreeSearch() as fs:
            if args.cmd in ("search", "news"):
                req = SearchRequest(
                    q=" ".join(args.query),
                    category="news" if args.cmd == "news" else "web",
                    max_results=args.max_results,
                    engines=args.engines.split(",") if args.engines else None,
                    time_range=args.time_range,
                    region=args.region,
                    include_answer=args.answer,
                )
                _print_results(await fs.search(req), args.json)
            elif args.cmd == "extract":
                page = (await fs.extract([args.url]))[0]
                if not page.ok:
                    sys.exit(f"error: {page.error}")
                print(f"# {page.title or page.url}\n\n{page.content}")
            elif args.cmd == "engines":
                print(json.dumps(fs.engine_status(), indent=2))

    asyncio.run(go())


if __name__ == "__main__":
    main()
