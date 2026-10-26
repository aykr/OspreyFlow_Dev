"""Closes, at their start, the PaySim `TRANSACTED` links that were stored as instants before ADR-127
decision 11, so that none of them is read as a span still open:

    python -m scripts.close_paysim_instants --written-before 2026-10-27T00:00:00Z \\
        --run-by <principal id>
    python -m scripts.close_paysim_instants --written-before ... --run-by ... --dry-run

**Why.** Until decision 11 a link with no end (`valid_to`) was an instant, and the PaySim seeder
(`packages/demo_fixtures/paysim.py`) wrote its `TRANSACTED` links so. From decision 11 every reader
takes a missing end as a span still running, so a deployment seeded with PaySim before it would show
those links as open and keep them in every later window. (The seeder now writes the start as the
end.)

**Which links, and only these.** A link is closed only if all of these hold:

- it is a `TRANSACTED` link;
- **every source its provenance names is `paysim-dataset`**, the document id the PaySim seeder gives
  every link it writes (`demo_fixtures.datasets.PAYSIM.source`, which `stamp_datasets` also finds
  its elements by). This is the most specific marker a stored link carries: the seeder stamps no
  load id, and its dataset id is added later and may be missing from an older store;
- it is live (not reverted, not superseded), has a start and no end;
- it was written before the cutoff (its audit `created_at`);
- it is not a link an analyst changed: a link changed through the link-change route is a successor
  carrying the original's sources, so it is excluded by its id in the `link_changes` table, whose
  `edge_id` names each successor. An open end an analyst recorded stays open.

Everything else is left alone, whatever its end: other `TRANSACTED` links (an AML recipe's, for
instance), the PID's `HELD_AT`, `PRESENT_AT` and `PASSES_ITEMS_TO` links, which are deliberately
open while custody or presence is current (ADR-120 Amendment 9), and every other link type. A link
the store holds no readable creation time for is left open and counted on its own.

**What it does.** It sets the nested `interval.valid_to` and the flattened `valid_to` of each such
link to the link's own start.

**Safe to run again.** A closed link has an end, so a rerun finds nothing. `--dry-run` reads and
counts and writes nothing. The summary is counts only, per link type and in all: never an id.

Run it inside the deployment, where ArcadeDB and Postgres are reachable; the Conduit may keep
running. `--run-by` is recorded in the audit trail with the counts; it is not checked against
anyone, so name the person who is doing this.

Exit codes: 0 done (or counted, for `--dry-run`), 64 the cutoff did not read as a time with a zone.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.naming import physical_type_name
from demo_fixtures.datasets import PAYSIM
from ontology.loader import load_default_ontology
from schemas.domain import OntologySchema, Principal

#: The one link type the PaySim seeder writes.
LINK_TYPE = "TRANSACTED"
#: Links read and written at a time.
PAGE = 500
#: Updates in flight together: a one-off over a large store, not a request.
CONCURRENCY = 25
AUDIT_ACTION = "close_paysim_instants"


@dataclass
class Counts:
    """What a run did, as counts."""

    dry_run: bool = False
    #: PaySim links closed (or, in a dry run, that would be).
    closed: int = 0
    #: PaySim links with no end that were written at or after the cutoff, and so left open.
    left_open_after_cutoff: int = 0
    #: PaySim links with no end whose creation time the store does not hold in a readable form.
    left_open_no_creation_time: int = 0
    #: PaySim links with no end that an analyst changed, and so left open.
    left_open_changed_by_an_analyst: int = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.close_paysim_instants",
        description="Close, at their start, the PaySim links stored as instants before decision 11",
    )
    parser.add_argument(
        "--written-before",
        required=True,
        help="ISO time with a zone: only links written before it are closed",
    )
    parser.add_argument(
        "--run-by", required=True, help="the principal id to record as having run this"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="count what would be closed; write nothing"
    )
    return parser


def parse_cutoff(text: str) -> datetime:
    """The cutoff as a UTC time. A time with no zone is refused: it would be read as the machine's
    own, and a cutoff an hour out closes or spares the wrong links."""
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("the cutoff needs a zone (for example 2026-10-27T00:00:00Z)")
    return parsed.astimezone(UTC)


def _written(created: Any) -> datetime | None:
    if not isinstance(created, str) or not created:
        return None
    try:
        parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _only_paysim(sources: Any) -> bool:
    """Whether the link's provenance names the PaySim seed and nothing else."""
    named = {str(s) for s in (sources or [])}
    return named == {PAYSIM.source}


async def _close_links(
    client: Any,
    label: str,
    *,
    cutoff: datetime,
    dry_run: bool,
    changed_link_ids: Collection[str],
    counts: Counts,
) -> None:
    last_id = ""
    while True:
        rows = await client.sql(
            "SELECT id, interval, audit.created_at AS created, "
            f"provenance.sources.document_id AS sources FROM `{label}` "
            "WHERE interval IS NOT NULL AND interval.valid_to IS NULL "
            "AND (reverted IS NULL OR reverted = false) AND superseded_by IS NULL "
            f"AND provenance.sources.document_id CONTAINS '{PAYSIM.source}' "
            f"AND id > :last_id ORDER BY id LIMIT {PAGE}",
            params={"last_id": last_id},
        )
        if not rows:
            return
        last_id = str(rows[-1]["id"])
        pending: list[tuple[str, dict[str, Any]]] = []
        for row in rows:
            interval = dict(row["interval"])
            if not _only_paysim(row.get("sources")) or not interval.get("valid_from"):
                continue
            if str(row["id"]) in changed_link_ids:
                counts.left_open_changed_by_an_analyst += 1
                continue
            written = _written(row.get("created"))
            if written is None:
                counts.left_open_no_creation_time += 1
                continue
            if written >= cutoff:
                counts.left_open_after_cutoff += 1
                continue
            interval["valid_to"] = interval["valid_from"]
            pending.append((str(row["id"]), interval))
        counts.closed += len(pending)
        if dry_run:
            continue
        for start in range(0, len(pending), CONCURRENCY):
            await asyncio.gather(
                *(
                    client.sql(
                        f"UPDATE `{label}` SET interval = :new_interval, valid_to = valid_from "
                        "WHERE id = :id",
                        params={"id": link_id, "new_interval": interval},
                    )
                    for link_id, interval in pending[start : start + CONCURRENCY]
                )
            )


async def close_paysim_instants(
    client: Any,
    *,
    cutoff: datetime,
    dry_run: bool,
    ontology: OntologySchema,
    changed_link_ids: Collection[str] = (),
) -> Counts:
    """Closes (or counts) the PaySim `TRANSACTED` links described above. `client` is the ArcadeDB
    client (`sql`); `changed_link_ids` are the ids of the links an analyst changed, which are left
    open."""
    counts = Counts(dry_run=dry_run)
    if not any(t.name == LINK_TYPE for t in ontology.edge_types):
        return counts
    label = physical_type_name(LINK_TYPE)
    held = {
        row["name"] for row in await client.sql("SELECT name FROM schema:types WHERE type = 'edge'")
    }
    if label in held:
        await _close_links(
            client, label, cutoff=cutoff, dry_run=dry_run, changed_link_ids=changed_link_ids,
            counts=counts,
        )  # fmt: skip
    return counts


def describe(counts: Counts) -> str:
    """The summary, counts only."""
    verb = "would close" if counts.dry_run else "closed"
    return "\n".join(
        [
            f"{verb} {counts.closed} PaySim {LINK_TYPE} link(s) at their start",
            f"left open, written at or after the cutoff: {counts.left_open_after_cutoff}",
            f"left open, no creation time: {counts.left_open_no_creation_time}",
            f"left open, changed by an analyst: {counts.left_open_changed_by_an_analyst}",
        ]
    )


async def _changed_link_ids(dsn: str) -> set[str]:
    """The ids of the links produced by an analyst's change (`link_changes.edge_id`): none if the
    table was never made."""
    connection = await asyncpg.connect(dsn)
    try:
        if await connection.fetchval("SELECT to_regclass('link_changes')") is None:
            return set()
        return {r["edge_id"] for r in await connection.fetch("SELECT edge_id FROM link_changes")}
    finally:
        await connection.close()


async def _main(args: argparse.Namespace) -> int:
    try:
        cutoff = parse_cutoff(args.written_before)
    except ValueError as error:
        print(f"--written-before: {error}")
        return 64  # before any store is opened
    from services.api.audit import AuditWriter
    from services.api.config import PostgresConfig

    dsn = PostgresConfig.from_env().dsn
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    audit = await AuditWriter.connect(dsn)
    try:
        counts = await close_paysim_instants(
            client,
            cutoff=cutoff,
            dry_run=args.dry_run,
            ontology=load_default_ontology(),
            changed_link_ids=await _changed_link_ids(dsn),
        )
        print(describe(counts))
        if not args.dry_run:
            await audit.record(
                principal=Principal(id=args.run_by, clearance="OFFICIAL", org_unit="operator"),
                action=AUDIT_ACTION,
                resolved_query={
                    "written_before": cutoff.isoformat(),
                    "closed": counts.closed,
                    "left_open_after_cutoff": counts.left_open_after_cutoff,
                    "left_open_no_creation_time": counts.left_open_no_creation_time,
                    "left_open_changed_by_an_analyst": counts.left_open_changed_by_an_analyst,
                },
                result_cardinality=counts.closed,
            )
        return 0
    finally:
        await client.aclose()
        await audit.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
