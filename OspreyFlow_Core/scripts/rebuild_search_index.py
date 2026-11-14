"""Rebuilds the search index from the graph (`spec/06_DECISIONS.md` ADR-150 decision 4). Run as
`python -m scripts.rebuild_search_index`, with the Conduit's environment. Every live node is
written into a new index named with its build time, the deployment's alias is moved onto it, and
the old index deleted, so readers never see a half-built index; running it twice is harmless.
`ospreyflow restore` runs it after a restore (ADR-114 Amendment 35 point 2). Its last line, on
success: `search index rebuilt: <documents> documents from <nodes> nodes, alias <alias> ->
<index>`."""

from __future__ import annotations

import asyncio
import sys

from services.search_index.rebuild import rebuild
from services.search_index.resources import feed_resources


async def _run() -> int:
    async with feed_resources() as r:
        done = await rebuild(r.source, r.texts, r.client, r.alias, r.schema)
        print(
            f"search index rebuilt: {done.documents} documents from {done.nodes} nodes, "
            f"alias {r.alias} -> {done.index}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv if argv is not None else sys.argv[1:]:
        print(
            "usage: python -m scripts.rebuild_search_index (it takes no arguments)", file=sys.stderr
        )
        return 2
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
