"""Gives a store loaded before ADR-099 its datasets, so no re-seed is needed (`06_DECISIONS.md`
ADR-099 step 3).

Run inside the deployment, where ArcadeDB, Postgres and Valkey are reachable, the Conduit may keep
running:

    python -m scripts.stamp_datasets --dry-run     # says what it would do, writes nothing
    python -m scripts.stamp_datasets               # does it

What it does, in order, each step safe to run again:

1. Registers the seeds' datasets (`demo_fixtures.datasets`) as the unit's (`--org-unit`).
2. Stamps every node and link a seed loaded with that seed's dataset, found by the provenance
   source the seed has always written (`enron-corpus`, `fixture-corp`, ...). A dataset already on
   an element is kept; this one is added.
3. Gives every case that reads nothing yet its datasets: those of the seeds that loaded into it
   (their load ids name it, or it bears the seed's case name), those of what is on its canvas, and
   its parent's if it is a branch (parents first). A case with none of these gets a dataset of its
   own, named after it, so it never reads everything or nothing by accident.
4. Stamps what is on each case's canvas and has no dataset yet (an entity the analyst marked or
   accepted before ADR-099) with the case's first dataset.
5. Rewrites each case's working-set copies of its nodes and links with their datasets, since the
   canvas is projected from those copies (`WorkingSetService._project`).

It ends by counting the elements still in no dataset, per type, and names them as such: they are
in no case's world until something claims them. Nothing is deleted.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import asyncpg
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.datasets import Dataset, DatasetStore, PostgresDatasetStore
from services.api.working_set.store import ValkeyWorkingSetStore, WorkingSetStorage
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.naming import logical_type_name, physical_type_name
from demo_fixtures.datasets import SEED_DATASETS, SeedDataset
from ontology.loader import load_default_ontology
from schemas.domain import OntologySchema, Principal

#: The case names the seeds that make their own case use (`seed_enron`, `seed_paysim`).
SEED_CASE_NAMES: dict[str, str] = {
    "Enron corpus (real data, this machine only)": "enron",
    "PaySim mobile money (internal)": "paysim",
}
#: Seeds whose load id names the case they loaded into: `<prefix>:<investigation id>`.
SEED_LOAD_PREFIXES: dict[str, str] = {"fixture-corp": "fixture-corp", "scenarios": "scenarios"}
LOOKUP_BATCH = 500
#: "In no dataset": no list at all (loaded before ADR-099) or an empty one (written since, naming
#: none). `size()` is 0 for both on ArcadeDB 25.5.1; `datasets = []` misses a missing list.
_IN_NO_DATASET = "(datasets IS NULL OR datasets.size() = 0)"


@dataclass
class CaseRow:
    id: str
    name: str
    owning_unit: str
    branched_from: str | None


@dataclass
class StampReport:
    stamped_by_source: dict[str, int] = field(default_factory=dict)
    case_datasets: dict[str, list[str]] = field(default_factory=dict)
    own_datasets_made: list[str] = field(default_factory=list)
    canvas_stamped: int = 0
    refused: list[str] = field(default_factory=list)
    unstamped: dict[str, int] = field(default_factory=dict)


class _Sql:
    """The two ArcadeDB calls this script needs, against one database."""

    def __init__(self, client: ArcadeDBClient) -> None:
        self._client = client

    async def query(self, command: str, params: dict[str, Any] | None = None) -> list[Any]:
        return list(await self._client.sql(command, params=params or {}))

    async def count(self, command: str, params: dict[str, Any] | None = None) -> int:
        rows = await self.query(command, params)
        return int(rows[0].get("count", 0)) if rows else 0


def _type_names(ontology: OntologySchema) -> list[str]:
    return [physical_type_name(t.name) for t in ontology.entity_types] + [
        physical_type_name(t.name) for t in ontology.edge_types
    ]


async def _add_dataset_where(
    sql: _Sql, type_name: str, where: str, dataset: str, params: dict[str, Any], *, write: bool
) -> int:
    """Adds `dataset` to every element of `type_name` matching `where` that lacks it. Two steps,
    measured on ArcadeDB 25.5.1: `datasets.append(x)` turns a list into a string, and there is no
    `union()`; `||` appends to a list, and a missing list is set outright."""
    lacking = f"({where}) AND (datasets IS NULL OR NOT (datasets CONTAINS :ds))"
    found = await sql.count(
        f"SELECT count(*) AS count FROM {type_name} WHERE {lacking}", {**params, "ds": dataset}
    )
    if write and found:
        await sql.query(
            f"UPDATE {type_name} SET datasets = [:ds] WHERE ({where}) AND datasets IS NULL",
            {**params, "ds": dataset},
        )
        await sql.query(
            f"UPDATE {type_name} SET datasets = datasets || [:ds] "
            f"WHERE ({where}) AND datasets IS NOT NULL AND NOT (datasets CONTAINS :ds)",
            {**params, "ds": dataset},
        )
    return found


async def _datasets_by_id(
    sql: _Sql, types: Sequence[str], ids: Sequence[str]
) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for start in range(0, len(ids), LOOKUP_BATCH):
        chunk = list(ids[start : start + LOOKUP_BATCH])
        for type_name in types:
            for row in await sql.query(
                f"SELECT id, datasets FROM {type_name} WHERE id IN :ids", {"ids": chunk}
            ):
                found[str(row["id"])] = list(row.get("datasets") or [])
    return found


async def _cases(dsn: str) -> list[CaseRow]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, name, owning_unit, branched_from FROM investigations "
            "WHERE removed_at IS NULL ORDER BY created_at"
        )
    finally:
        await conn.close()
    return [CaseRow(r["id"], r["name"], r["owning_unit"], r["branched_from"]) for r in rows]


def _parents_first(cases: Sequence[CaseRow]) -> list[CaseRow]:
    by_id = {c.id: c for c in cases}
    ordered: list[CaseRow] = []
    placed: set[str] = set()

    def place(case: CaseRow, seen: frozenset[str]) -> None:
        if case.id in placed or case.id in seen:
            return
        parent = by_id.get(case.branched_from or "")
        if parent is not None:
            place(parent, seen | {case.id})
        placed.add(case.id)
        ordered.append(case)

    for case in cases:
        place(case, frozenset())
    return ordered


async def stamp(
    *,
    sql: _Sql,
    ontology: OntologySchema,
    datasets: DatasetStore,
    working_sets: WorkingSetStorage,
    cases: Sequence[CaseRow],
    org_unit: str,
    write: bool,
    say: Callable[[str], None] = print,
) -> StampReport:
    report = StampReport()
    types = _type_names(ontology)
    node_types = [physical_type_name(t.name) for t in ontology.entity_types]
    seeds: dict[str, SeedDataset] = {d.id: d for d in SEED_DATASETS}
    now = datetime.now(UTC)

    # 1. The seeds' datasets.
    if write:
        for seed in SEED_DATASETS:
            await datasets.register(
                Dataset(
                    id=seed.id,
                    name=seed.name,
                    owning_unit=org_unit,
                    created_at=now,
                    created_by="stamp-datasets",
                )
            )

    # 2. What each seed loaded, by its provenance source.
    for seed in SEED_DATASETS:
        total = 0
        for type_name in types:
            total += await _add_dataset_where(
                sql,
                type_name,
                "provenance.sources.document_id CONTAINS :src",
                seed.id,
                {"src": seed.source},
                write=write,
            )
        report.stamped_by_source[seed.id] = total
        say(f"  {seed.name}: {total:,} elements {'stamped' if write else 'to stamp'}")

    # 3 to 5, per case, parents first.
    for case in _parents_first(cases):
        held = await datasets.ids_of_case(case.id)
        node_ids = sorted(await working_sets.node_ids(case.id))
        edge_ids = sorted(await working_sets.edge_ids(case.id))
        if not held:
            chosen: list[str] = []
            named = SEED_CASE_NAMES.get(case.name)
            if named:
                chosen.append(named)
            for seed_id, prefix in SEED_LOAD_PREFIXES.items():
                load_id = f"{prefix}:{case.id}"
                for type_name in node_types:
                    if await sql.count(
                        f"SELECT count(*) AS count FROM {type_name} WHERE audit.load_id = :lid",
                        {"lid": load_id},
                    ):
                        chosen.append(seed_id)
                        break
            if case.branched_from:
                chosen.extend(report.case_datasets.get(case.branched_from, []))
                chosen.extend(await datasets.ids_of_case(case.branched_from))
            on_canvas = await _datasets_by_id(sql, types, [*node_ids, *edge_ids])
            for in_these in on_canvas.values():
                chosen.extend(in_these)
            ordered = list(dict.fromkeys(chosen))
            ordered = sorted(
                ordered, key=lambda d: (0, list(seeds).index(d)) if d in seeds else (1, d)
            )
            seeder = Principal(id="stamp-datasets", clearance="SECRET", org_unit=case.owning_unit)
            if case.owning_unit != org_unit:
                kept = [d for d in ordered if d not in seeds]
                if len(kept) != len(ordered):
                    report.refused.append(
                        f"{case.name} ({case.id}): seed datasets are {org_unit}'s, the case is "
                        f"{case.owning_unit}'s"
                    )
                ordered = kept
            if not ordered:
                if write:
                    own = await datasets.create(seeder, case.name or f"Case {case.id}")
                    ordered = [own.id]
                else:
                    ordered = [f"(new: {case.name or case.id})"]
                report.own_datasets_made.append(case.id)
            if write:
                await datasets.set_for_case(case.id, ordered, seeder)
            held = ordered
        report.case_datasets[case.id] = list(held)
        say(f"  case {case.name or case.id}: reads {', '.join(held)}")

        # 4. What is on the canvas and in no dataset joins the case's first.
        first = held[0]
        if node_ids or edge_ids:
            for type_name in types:
                for start in range(0, max(len(node_ids), len(edge_ids)), LOOKUP_BATCH):
                    chunk = [
                        *node_ids[start : start + LOOKUP_BATCH],
                        *edge_ids[start : start + LOOKUP_BATCH],
                    ]
                    unplaced = await sql.count(
                        f"SELECT count(*) AS count FROM {type_name} "
                        f"WHERE id IN :ids AND {_IN_NO_DATASET}",
                        {"ids": chunk},
                    )
                    if write and unplaced:
                        await sql.query(
                            f"UPDATE {type_name} SET datasets = [:ds] "
                            f"WHERE id IN :ids AND {_IN_NO_DATASET}",
                            {"ids": chunk, "ds": first},
                        )
                    report.canvas_stamped += unplaced

        # 5. The working set's own copies.
        if write and (node_ids or edge_ids):
            stored = await _datasets_by_id(sql, types, [*node_ids, *edge_ids])
            nodes = await working_sets.source_fidelity_nodes(case.id)
            edges = await working_sets.source_fidelity_edges(case.id)
            await working_sets.add_nodes(
                case.id,
                [
                    n.model_copy(update={"datasets": stored.get(n.id) or n.datasets or [first]})
                    for n in nodes.values()
                ],
            )
            await working_sets.add_edges(
                case.id,
                [
                    e.model_copy(update={"datasets": stored.get(e.id) or e.datasets or [first]})
                    for e in edges.values()
                ],
            )

    # What is left in no dataset, named as such.
    for type_name in types:
        left = await sql.count(
            f"SELECT count(*) AS count FROM {type_name} WHERE {_IN_NO_DATASET}"
        )
        if left:
            report.unstamped[logical_type_name(type_name)] = left
    if report.unstamped:
        say("  in no dataset yet (no case reads them):")
        for type_name, left in report.unstamped.items():
            say(f"    {type_name}: {left:,}")
    for line in report.refused:
        say(f"  not given: {line}")
    return report


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.stamp_datasets", description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what it would do; write nothing."
    )
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    write = not args.dry_run
    print("Dry run: nothing will be written." if not write else "Stamping datasets.")
    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    dsn = PostgresConfig.from_env().dsn
    datasets = await PostgresDatasetStore.connect(dsn)
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    try:
        await stamp(
            sql=_Sql(client),
            ontology=load_default_ontology(),
            datasets=datasets,
            working_sets=ValkeyWorkingSetStore(valkey),
            cases=await _cases(dsn),
            org_unit=args.org_unit,
            write=write,
        )
    finally:
        await client.aclose()
        await datasets.close()
        await valkey.aclose()
    print("Done." if write else "Dry run finished: nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
