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
6. Places the Conduit's own records made before ADR-099 Amendment 3 (`place_records`): a link-type
   proposal or an alert records the case it was made in, and takes that case's first dataset. A
   saved pattern, watch, monitor or Studio recipe records no case, so nothing says which dataset it
   was meant for; those are counted, not guessed, and stay readable in every case of their owner,
   as they were (ADR-099 Amendment 5).

It ends by counting the elements still in no dataset, per type, and names them as such: they are
in no case's world until something claims them; and by counting, per dataset id, the elements that
name a dataset the registry does not hold (ADR-099 Amendment 6). Nothing is deleted.
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
from adapters.graph_arcadedb.serialization import edge_from_element_map, node_from_element_map
from demo_fixtures.datasets import SEED_DATASETS, SeedDataset
from ontology.loader import load_default_ontology
from schemas.domain import OntologySchema, Principal

#: The case each seed makes, by name: with an empty canvas and load ids that do not name the case
#: (the HMP seed's), the name is all that says what it holds.
SEED_CASE_NAMES: dict[str, str] = {d.case_name: d.id for d in SEED_DATASETS if d.case_name}
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
    derived: int = 0
    refused: list[str] = field(default_factory=list)
    unstamped: dict[str, int] = field(default_factory=dict)
    #: Elements naming a dataset the registry does not hold, by dataset id (ADR-099 Amendment 6).
    unregistered: dict[str, int] = field(default_factory=dict)


class _Sql:
    """The two ArcadeDB calls this script needs, against one database."""

    def __init__(self, client: ArcadeDBClient) -> None:
        self._client = client

    async def query(self, command: str, params: dict[str, Any] | None = None) -> list[Any]:
        return list(await self._client.sql(command, params=params or {}))

    async def gremlin(self, command: str) -> list[Any]:
        return list(await self._client.gremlin(command))

    async def count(self, command: str, params: dict[str, Any] | None = None) -> int:
        rows = await self.query(command, params)
        return int(rows[0].get("count", 0)) if rows else 0


def _shared(lists: Sequence[Sequence[str]]) -> list[str]:
    """The datasets every one of `lists` holds; none if any holds none."""
    if not lists:
        return []
    common = set(lists[0])
    for more in lists[1:]:
        common &= set(more)
    return sorted(common)


def _flat(value: Any) -> list[str]:
    """A `values("datasets").fold()` of one element: `[[a, b]]`, or `[]` when it has none."""
    out: list[str] = []
    for item in value or []:
        out.extend(item if isinstance(item, list) else [item])
    return out


async def _set_datasets(
    sql: _Sql, type_name: str, placed: dict[str, list[str]], *, write: bool
) -> int:
    if not write:
        return len(placed)
    by_datasets: dict[tuple[str, ...], list[str]] = {}
    for element_id, datasets in placed.items():
        by_datasets.setdefault(tuple(datasets), []).append(element_id)
    for held, ids in by_datasets.items():
        for start in range(0, len(ids), LOOKUP_BATCH):
            await sql.query(
                f"UPDATE {type_name} SET datasets = :ds WHERE id IN :ids AND {_IN_NO_DATASET}",
                {"ds": list(held), "ids": ids[start : start + LOOKUP_BATCH]},
            )
    return len(placed)


async def _derive(sql: _Sql, ontology: OntologySchema, *, write: bool) -> int:
    count = 0
    unplaced = 'filter(or(hasNot("datasets"), values("datasets").unfold().count().is(0)))'
    # A Document: the datasets shared by everything linked to it.
    document = physical_type_name("Document")
    if any(t.name == "Document" for t in ontology.entity_types):
        rows = await sql.gremlin(
            f'g.V().hasLabel("{document}").{unplaced}.project("id","n")'
            '.by(values("id")).by(both().values("datasets").fold())'
        )
        placed = {}
        for row in rows:
            # A projection comes back as the map itself, each neighbour's list one item of `n`.
            r = row.get("result", row)
            neighbours = [list(n) for n in r["n"] if n]
            shared = _shared(neighbours)
            if shared:
                placed[r["id"]] = shared
        count += await _set_datasets(sql, document, placed, write=write)
    # An entity found in a Document: that Document's datasets.
    node_types = [physical_type_name(t.name) for t in ontology.entity_types]
    holders: dict[str, list[str]] = {}
    for type_name in node_types:
        rows = await sql.query(
            f"SELECT id, provenance.sources.document_id AS d FROM {type_name} "
            f"WHERE {_IN_NO_DATASET}"
        )
        cited = {str(r["id"]): [str(d) for d in (r.get("d") or [])] for r in rows}
        wanted = sorted({d for ds in cited.values() for d in ds} - set(holders))
        if wanted:
            holders.update(await _datasets_by_id(sql, node_types, wanted))
        placed = {}
        for element_id, sources in cited.items():
            found = [holders[d] for d in sources if holders.get(d)]
            if found:
                placed[element_id] = sorted({d for ds in found for d in ds})
        count += await _set_datasets(sql, type_name, placed, write=write)
    # A link: the datasets its two ends share.
    for edge in ontology.edge_types:
        label = physical_type_name(edge.name)
        rows = await sql.gremlin(
            f'g.E().hasLabel("{label}").{unplaced}.project("id","a","b")'
            '.by(values("id")).by(outV().values("datasets").fold())'
            '.by(inV().values("datasets").fold())'
        )
        placed = {}
        for row in rows:
            r = row.get("result", row)
            shared = _shared([_flat(r["a"]), _flat(r["b"])])
            if shared:
                placed[r["id"]] = shared
        count += await _set_datasets(sql, label, placed, write=write)
    return count


async def _bodies_by_id(
    sql: _Sql, types: Sequence[str], ids: Sequence[str], parse: Callable[[Any], Any]
) -> dict[str, Any]:
    """Each element's current body, read as the adapter reads it (`@type` is its label)."""
    found: dict[str, Any] = {}
    for start in range(0, len(ids), LOOKUP_BATCH):
        chunk = list(ids[start : start + LOOKUP_BATCH])
        for type_name in types:
            for row in await sql.query(
                f"SELECT *, @type AS label FROM {type_name} WHERE id IN :ids", {"ids": chunk}
            ):
                body = parse(row)
                found[body.id] = body
    return found


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
                # The seed's own id, or a Studio row's `<source>:<file>` (the HMP seed's shape).
                "provenance.sources CONTAINS (document_id = :src OR document_id LIKE :pre)",
                seed.id,
                {"src": seed.source, "pre": f"{seed.source}:%"},
                write=write,
            )
        report.stamped_by_source[seed.id] = total
        say(f"  {seed.name}: {total:,} elements {'stamped' if write else 'to stamp'}")

    # 2a. What was derived from data joins the data it was derived from (as resolution now writes
    # a `SAME_AS`): a Document the datasets shared by what it is linked to, an entity the Document
    # it was found in, a link the datasets its two ends share. In that order, since each reads
    # what the one before it placed.
    report.derived = await _derive(sql, ontology, write=write)
    say(
        f"  derived from stamped data: {report.derived:,} elements "
        f"{'stamped' if write else 'to stamp'}"
    )

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
                    own = await datasets.create(
                        seeder, case.name or f"Case {case.id}", suffix_if_taken=True
                    )
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

        # 5. The working set's own copies, which the canvas is drawn from: the graph's current
        # body where it holds the element (its datasets, and its counts if a load was written
        # again), else the copy stamped with the case's first dataset.
        if write and (node_ids or edge_ids):
            node_bodies = await _bodies_by_id(sql, node_types, node_ids, node_from_element_map)
            edge_types = [physical_type_name(t.name) for t in ontology.edge_types]
            edge_bodies = await _bodies_by_id(sql, edge_types, edge_ids, edge_from_element_map)
            nodes = await working_sets.source_fidelity_nodes(case.id)
            edges = await working_sets.source_fidelity_edges(case.id)
            await working_sets.add_nodes(
                case.id,
                [
                    node_bodies.get(n.id)
                    or n.model_copy(update={"datasets": n.datasets or [first]})
                    for n in nodes.values()
                ],
            )
            await working_sets.add_edges(
                case.id,
                [
                    edge_bodies.get(e.id)
                    or e.model_copy(update={"datasets": e.datasets or [first]})
                    for e in edges.values()
                ],
            )

    # What is left in no dataset, named as such.
    for type_name in types:
        left = await sql.count(f"SELECT count(*) AS count FROM {type_name} WHERE {_IN_NO_DATASET}")
        if left:
            report.unstamped[logical_type_name(type_name)] = left
    if report.unstamped:
        say("  in no dataset yet (no case reads them):")
        for type_name, left in report.unstamped.items():
            say(f"    {type_name}: {left:,}")
    # What names a dataset nobody registered: no case can be given it, so none of it can be read.
    named: dict[str, int] = {}
    for step in ("V", "E"):
        for row in await sql.gremlin(f"g.{step}().values('datasets').unfold().groupCount()"):
            for dataset_id, count in (row or {}).items():
                named[str(dataset_id)] = named.get(str(dataset_id), 0) + int(count)
    held = await datasets.known(sorted(named))
    report.unregistered = {d: n for d, n in sorted(named.items()) if d not in held}
    if report.unregistered:
        say("  naming a dataset nobody registered (no case can read them):")
        for dataset_id, count in report.unregistered.items():
            say(f"    {dataset_id}: {count:,}")
    for line in report.refused:
        say(f"  not given: {line}")
    return report


#: Records that name the case they were made in: placed in its first dataset.
_PLACED_BY_CASE = ("link_type_proposals", "alerts")
#: Records that name no case: counted only.
_NO_CASE = ("saved_patterns", "hotlists", "monitors", "studio_recipes")


@dataclass
class RecordsReport:
    placed: dict[str, int] = field(default_factory=dict)
    unplaced: dict[str, int] = field(default_factory=dict)
    #: Tables whose `dataset_id` column does not exist yet: the Conduit adds it when it starts.
    not_ready: list[str] = field(default_factory=list)


async def _has_dataset_column(conn: asyncpg.Connection, table: str) -> bool:
    return bool(
        await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = $1 AND column_name = 'dataset_id'",
            table,
        )
    )


async def place_records(
    conn: asyncpg.Connection, *, write: bool, say: Callable[[str], None] = print
) -> RecordsReport:
    """Step 6. A record whose case reads no dataset yet is left as it is, and counted with the
    unplaced; one that already has a dataset is never moved, so a second run changes nothing."""
    report = RecordsReport()
    first_dataset = (
        "(SELECT d.dataset_id FROM investigation_datasets d "
        "WHERE d.investigation_id = r.investigation_id ORDER BY d.position LIMIT 1)"
    )
    for table in (*_PLACED_BY_CASE, *_NO_CASE):
        if not await _has_dataset_column(conn, table):
            report.not_ready.append(table)
            continue
        if table in _PLACED_BY_CASE:
            placeable = f"FROM {table} r WHERE r.dataset_id IS NULL AND {first_dataset} IS NOT NULL"
            report.placed[table] = await conn.fetchval(f"SELECT count(*) {placeable}")
            if write and report.placed[table]:
                await conn.execute(
                    f"UPDATE {table} r SET dataset_id = {first_dataset} "
                    f"WHERE r.dataset_id IS NULL AND {first_dataset} IS NOT NULL"
                )
        left = await conn.fetchval(f"SELECT count(*) FROM {table} WHERE dataset_id IS NULL")
        if write or table not in _PLACED_BY_CASE:
            report.unplaced[table] = left
        else:
            report.unplaced[table] = left - report.placed[table]
    for table, count in report.placed.items():
        if count:
            say(f"  {table}: {count:,} placed in their case's dataset")
    for table, count in report.unplaced.items():
        if count:
            say(f"  {table}: {count:,} in no dataset (readable in every case of their owner)")
    for table in report.not_ready:
        say(f"  {table}: no dataset column yet; start the Conduit once, then run this again")
    return report


def unit_for(given: str | None, cases: Sequence[CaseRow]) -> str:
    """The unit the seeds' datasets are registered under. Seen on the owner's deployment: the
    cases were the `verify` unit's while the old default was `unit-1`, so every seed dataset would
    have been refused to them. With no unit given, the one unit all cases share; never a guess."""
    if given:
        return given
    units = sorted({c.owning_unit for c in cases})
    if len(units) == 1:
        return units[0]
    raise SystemExit(
        "The cases are in more than one unit (" + ", ".join(units) + "): say which owns the "
        "seeds' datasets with --org-unit."
    )


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.stamp_datasets", description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what it would do; write nothing."
    )
    parser.add_argument(
        "--org-unit",
        default=os.environ.get("OSPREY_ORG_UNIT"),
        help="The unit the seeds' datasets belong to. Left out: the one unit every case is in.",
    )
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
    cases = await _cases(dsn)
    try:
        await stamp(
            sql=_Sql(client),
            ontology=load_default_ontology(),
            datasets=datasets,
            working_sets=ValkeyWorkingSetStore(valkey),
            cases=cases,
            org_unit=unit_for(args.org_unit, cases),
            write=write,
        )
        conn = await asyncpg.connect(dsn)
        try:
            await place_records(conn, write=write)
        finally:
            await conn.close()
    finally:
        await client.aclose()
        await datasets.close()
        await valkey.aclose()
    print("Done." if write else "Dry run finished: nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
