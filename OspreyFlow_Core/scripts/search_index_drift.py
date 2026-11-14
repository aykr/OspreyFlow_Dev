"""Reports the difference between the graph and the search index (`spec/06_DECISIONS.md` ADR-150
decision 5). Run as `python -m scripts.search_index_drift`, with the Conduit's environment; it only
reads. Exits 0 with `search index drift: none (<n> nodes in the graph, <n> documents in the index)`
when they agree; otherwise exits 1 with the counts of documents missing from the index, in it but
not live in the graph, stale (a field differs), and refused (set aside: OpenSearch refused them for
good, each with its reason), and the first ids of each. A rebuild mends any but the refused, which
need their node mended. When the outboxes still hold rows it says so: a change on its way shows as
drift until the indexer has sent it."""

from __future__ import annotations

import asyncio
import sys

from services.search_index.rebuild import drift
from services.search_index.resources import feed_resources

_SHOWN = 10


async def _run() -> int:
    async with feed_resources() as r:
        report = await drift(r.source, r.texts, r.client, r.alias, r.schema)
    if report.pending:
        print("the outboxes still hold changes on their way: run it again once they are drained")
    if report.none:
        print(
            f"search index drift: none ({report.graph_nodes} nodes in the graph, "
            f"{report.index_documents} documents in the index)"
        )
        return 0
    for name, ids, count in (
        ("missing", report.missing, report.missing_count),
        ("extra", report.extra, report.extra_count),
        ("stale", report.stale, report.stale_count),
    ):
        if count:
            more = f" and {count - _SHOWN} more" if count > _SHOWN else ""
            print(f"{name}: {count} ({', '.join(ids[:_SHOWN])}{more})")
    for doc_id, reason in list(report.refused.items())[:_SHOWN]:
        print(f"refused: {doc_id}: {reason}")
    if report.refused_count > _SHOWN:
        print(f"refused: and {report.refused_count - _SHOWN} more")
    print(
        f"search index drift: {report.missing_count} missing, {report.extra_count} extra, "
        f"{report.stale_count} stale, {report.refused_count} refused "
        f"({report.graph_nodes} nodes in the graph, "
        f"{report.index_documents} documents in the index); "
        "python -m scripts.rebuild_search_index mends it"
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    if argv if argv is not None else sys.argv[1:]:
        print(
            "usage: python -m scripts.search_index_drift (it takes no arguments)", file=sys.stderr
        )
        return 2
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
