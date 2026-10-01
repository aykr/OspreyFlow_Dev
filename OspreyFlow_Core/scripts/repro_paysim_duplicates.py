"""Replays the PaySim graph load into a throwaway database and reports duplicated transactions
(ADR-056 Amendment 9).

    docker compose -f deploy/compose/dev.yaml up -d arcadedb
    PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python -m scripts.repro_paysim_duplicates

Seen: a real load wrote 13,068 transactions and stored 13,076, eight ids twice. This runs the seed's
own graph build and its own `write_graph` (the same batches of 40) against the dev ArcadeDB, in a
`conformance_*` database that is dropped at the end, so nothing else is touched. It then reports
each
duplicated id with the batch that wrote it, the batches during which the client replayed a commit,
and any batch slow enough to have timed out. The real-data gate is the seed's own: it runs only from
a checkout and only with the dataset provisioned.

Needs the dev ArcadeDB on `localhost:2480` and its password in `ARCADEDB_ROOT_PASSWORD` if it is not
the development default. About half an hour for the default sample.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.seed_paysim import _HANDLING, NotProvisionedError, _is_checkout, resolve_source
from scripts.seed_support import write_graph

from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
from demo_fixtures.paysim import build_graph_writes, fraud_accounts, read_paysim
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology

_CLIENT_LOGGER = "adapters.graph_arcadedb.client"
_CHUNK = 40
_DEFAULT_SAMPLE = 500


class ReplayWatcher(logging.Handler):
    """Counts the client's replay warnings and says which batch each happened in, and times the
    batches. `batch_done` is `write_graph`'s `on_batch` hook: a warning logged while batch N ran
    is reported when N finishes."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        slow_seconds: float = 10.0,
    ) -> None:
        super().__init__(level=logging.WARNING)
        self._clock = clock
        self._slow_seconds = slow_seconds
        self._pending: list[str] = []
        self._last = clock()
        self.replayed: list[tuple[str, int, str]] = []
        self.slow: list[tuple[str, int, float]] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "replaying" in message:
            self._pending.append(message)

    def batch_done(self, noun: str, index: int) -> None:
        now = self._clock()
        seconds = now - self._last
        self._last = now
        for message in self._pending:
            self.replayed.append((noun, index, message))
        self._pending = []
        if seconds >= self._slow_seconds:
            self.slow.append((noun, index, seconds))


def duplicate_batches(
    edge_ids: Sequence[str], duplicated: Iterable[str], *, chunk: int
) -> dict[str, int]:
    """Which batch of `chunk` wrote each duplicated id; -1 for an id the load never wrote."""
    position = {edge_id: i for i, edge_id in enumerate(edge_ids)}
    return {d: (position[d] // chunk if d in position else -1) for d in duplicated}


def batch_faults(wrote: Sequence[str], stored: Mapping[str, int]) -> dict[str, int]:
    """Of the ids one batch wrote, those not stored exactly once: id -> how many are stored
    (0 for an id that is missing). Ids the batch did not write are ignored."""
    return {i: stored.get(i, 0) for i in wrote if stored.get(i, 0) != 1}


def limit_batches(
    nodes: list[Any], edges: list[Any], *, batches: int | None, chunk: int
) -> tuple[list[Any], list[Any]]:
    """The first `batches` transaction batches, and only the accounts their edges touch (the
    adapter refuses an edge whose endpoint is missing). `None` keeps everything."""
    if batches is None:
        return nodes, edges
    kept_edges = list(edges[: batches * chunk])
    touched = {e.source for e in kept_edges} | {e.target for e in kept_edges}
    return [n for n in nodes if n.id in touched], kept_edges


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.repro_paysim_duplicates", description=__doc__
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("OSPREYFLOW_INTERNAL_DEMO_DATA_DIR", "../OspreyFlow_Data"),
    )
    parser.add_argument(
        "--fraud-rows",
        type=int,
        default=_DEFAULT_SAMPLE,
        help="The seed's graph sample (its default): the first N fraud rows and what touches them.",
    )
    parser.add_argument(
        "--edge-batches",
        type=int,
        default=None,
        help="Write only the first N transaction batches (and the accounts they touch): minutes, "
        "not half an hour.",
    )
    parser.add_argument("--chunk", type=int, default=_CHUNK, help="Edges per transaction.")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace, source: Path) -> int:
    accounts = fraud_accounts(read_paysim(source), limit=args.fraud_rows)
    touching = [r for r in read_paysim(source) if r.origin in accounts or r.destination in accounts]
    nodes, edges = build_graph_writes(touching, created_by="paysim-seed-worker", handling=_HANDLING)
    nodes, edges = limit_batches(nodes, edges, batches=args.edge_batches, chunk=args.chunk)
    print(f"built {len(nodes):,} accounts and {len(edges):,} transactions from the sample")

    watcher = ReplayWatcher()
    logger = logging.getLogger(_CLIENT_LOGGER)
    logger.addHandler(watcher)
    try:
        async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as graph:
            client: Any = graph._client  # noqa: SLF001 - a diagnostic, in the adapter's own package
            edge_type = groovy_identifier(physical_type_name("TRANSACTED"))
            seen_at_commit: dict[str, int] = {}

            async def after_batch(noun: str, index: int) -> None:
                watcher.batch_done(noun, index)
                if noun != "transactions":
                    return
                wrote = [e.id for e in edges[index * args.chunk : (index + 1) * args.chunk]]
                ids = ", ".join(f"'{i}'" for i in wrote)
                rows = await client.sql(
                    f"SELECT id, count(*) AS n FROM {edge_type} WHERE id IN [{ids}] GROUP BY id"
                )
                faults = batch_faults(wrote, {r["id"]: int(r["n"]) for r in rows})
                for edge_id, count in faults.items():
                    seen_at_commit[edge_id] = count
                    where = await client.sql(
                        f"SELECT @rid AS rid FROM {edge_type} WHERE id LIKE '{edge_id}'"
                    )
                    print(
                        f"  !! right after batch {index} committed, {edge_id} is stored {count} "
                        f"time(s): {[w['rid'] for w in where]}",
                        flush=True,
                    )

            await write_graph(
                graph,
                nodes,
                edges,
                chunk=args.chunk,
                nouns=("accounts", "transactions"),
                on_batch=after_batch,
            )
            stored = (await client.sql(f"SELECT count(*) AS n FROM {edge_type}"))[0]["n"]
            grouped = await client.sql(
                f"SELECT id, count(*) AS n FROM {edge_type} GROUP BY id ORDER BY n DESC LIMIT 1000"
            )
    finally:
        logger.removeHandler(watcher)

    duplicated = [row["id"] for row in grouped if row["n"] > 1]
    print(
        f"\nwritten: {len(edges):,} transactions; stored: {stored:,}; "
        f"ids stored more than once: {len(duplicated)}"
    )
    by_batch = duplicate_batches([e.id for e in edges], duplicated, chunk=args.chunk)
    for edge_id, batch in sorted(by_batch.items(), key=lambda kv: kv[1]):
        print(f"  duplicate {edge_id}: written in transaction batch {batch}")
    replay_batches = sorted(
        {index for noun, index, _ in watcher.replayed if noun == "transactions"}
    )
    print(f"batches during which the client replayed a commit: {replay_batches or 'none'}")
    for noun, index, message in watcher.replayed:
        print(f"  {noun} batch {index}: {message}")
    for noun, index, seconds in watcher.slow:
        print(f"  slow: {noun} batch {index} took {seconds:.0f}s")
    print(
        "duplicates already present right after their own batch committed: "
        f"{sorted(set(by_batch[i] for i in seen_at_commit if i in by_batch)) or 'none'}"
    )
    overlap = sorted(set(by_batch.values()) & set(replay_batches))
    print(f"duplicates that sit in a batch with a replayed commit: {overlap or 'none'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s: %(message)s")
    try:
        source = resolve_source(Path(args.data_dir), is_checkout=_is_checkout())
    except NotProvisionedError as error:
        print(error, file=sys.stderr)
        return 1
    return asyncio.run(_run(args, source))


if __name__ == "__main__":
    raise SystemExit(main())
