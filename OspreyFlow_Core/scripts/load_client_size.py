"""Loads the client-size synthetic dataset (`scripts.generate_client_size`) into a running stack
once (ROUTE_052 step B, `v052-load`), resumably.

    python -m scripts.load_client_size --from DIR [--grant ACCOUNT=LEVEL ...]
                                       [--stages cases,nodes,edges,same_as,texts,events,check]

Run it where the stores are reachable (the stack's ArcadeDB, Postgres and analytics store, with
their passwords in the environment, as for any seed), with the Conduit stopped if the analytics
engine is DuckDB (its file lock). It writes through the paths the seeds use, never one of its own:

- **cases**: each source's dataset is registered, held by the source's owning unit, and read by a
  case of its own (`case_seed.case_from_arguments`, as every seed makes its case), shared as
  `--grant` says.
- **nodes**, then **edges**: each source's part files through the dataset-stamping graph
  (`stamping(adapter, dataset=...)`), so every element is stamped with its dataset; nodes by
  `upsert_nodes` in chunks of 40 (`seed_support.write_graph`), links through the adapter's bulk
  loader (ADR-058) in chunks of 100. Every element carries its marking (the source's, or the row's
  own where a source marks rows differently) and an asserted provenance naming its source row.
- **same_as**: the planted merge candidates through the unstamped adapter, as the resolver writes
  them (`services/resolve/same_as_writer.py`): `inferred` (rule 5), the score, the model version
  `client-size-plant-1`, marked as the more restrictive of the two records, and in no dataset when
  the two records are in different ones. The truth column of the plant files never reaches the
  store.
- **texts**: each document's full text into Postgres's `document_texts`, held by the document's
  owning unit (`ExtractionCandidateStore.store_document_text`).
- **events**: the analytics rows (`AnalyticsPort.load_events`), in batches of 50,000, each file
  under its own `load_id`, scoped to its source's case.
- **check**: the scan for link ids stored twice every seed ends with.

**Resumable.** A ledger (`load_state.json` beside the files, or `--state`) records each file when it
starts and when it is done; a rerun skips done files. A file that started and did not finish is
redone safely: a node file is an upsert keyed on id; a link file is bulk-loaded again with the
links already stored handed back as collisions and skipped (the generator writes each link once,
so a collision on a rerun is this file's own earlier write, never another's to merge); an events
file's partial rows are first removed by its `load_id` (`AnalyticsPort.retract_load`).

**Refused before anything is written:** a ledger written for another generated set (another seed,
scale or generator version), a missing or changed file (its SHA-256 is checked as it is read), and
a deployment whose marking ceiling (`OSPREY_HIGHEST_MARKING`) is below SECRET.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from scripts import client_size_plan as plan
from scripts.seed_support import BULK_CHUNK, write_graph

from ontology.handling import HandlingScheme, merge_handling
from ports.analytics import AnalyticsPort
from ports.graph import BulkGraphLoader, GraphPort
from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

STAGES = ("cases", "nodes", "edges", "same_as", "texts", "events", "check")
NODE_CHUNK = 40  # what every seed uses (ArcadeDB fails larger node transactions)
EVENT_BATCH = 50_000
LOADER = "client-size-loader"


class LoadRefused(RuntimeError):
    """The load cannot start, or cannot go on, without risking a wrong store."""


class TextStore(Protocol):
    async def store_document_text(
        self, document_id: str, text: str, principal: Principal
    ) -> None: ...


@dataclass
class Deps:
    """What the load writes through. `graph_for(dataset)` is the stamping graph for one dataset;
    `raw_graph` the adapter itself (for the cross-dataset merge candidates); `ensure_case(source)`
    registers the source's dataset and returns the id of the case that reads it."""

    graph_for: Callable[[str], GraphPort]
    raw_graph: GraphPort
    analytics: AnalyticsPort
    texts: TextStore
    ensure_case: Callable[[plan.Source], Awaitable[str]]
    scheme: HandlingScheme
    check: Callable[[Sequence[str]], Awaitable[int]] | None = None
    say: Callable[[str], None] = field(default=lambda line: print(line, flush=True))


# --- The ledger -----------------------------------------------------------------------------------


class Ledger:
    """What has been loaded, kept as JSON beside the files and rewritten atomically after each
    file, so a stop at any point loses at most the file in hand."""

    def __init__(self, path: Path, identity: dict[str, Any]) -> None:
        self.path = path
        self.identity = identity
        self.data: dict[str, Any] = {"identity": identity, "cases": {}, "started": {}, "done": {}}
        if path.exists():
            held = json.loads(path.read_text())
            if held.get("identity") != identity:
                raise LoadRefused(
                    f"{path} records a load of another generated set ({held.get('identity')}); "
                    f"this set is {identity}. Move the ledger aside only if the store is fresh."
                )
            self.data = held

    def save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=1, sort_keys=True))
        os.replace(temporary, self.path)

    def is_done(self, name: str) -> bool:
        return name in self.data["done"]

    def was_started(self, name: str) -> bool:
        return name in self.data["started"]

    def start(self, name: str) -> None:
        self.data["started"][name] = _now_text()
        self.save()

    def finish(self, name: str, **facts: Any) -> None:
        self.data["done"][name] = {"at": _now_text(), **facts}
        self.save()

    @property
    def cases(self) -> dict[str, str]:
        return cast(dict[str, str], self.data["cases"])


def _now_text() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Reading the generated files --------------------------------------------------------------


def read_manifest(folder: Path) -> dict[str, Any]:
    path = folder / "manifest.json"
    if not path.exists():
        raise LoadRefused(f"{folder} holds no manifest.json: not a generated set")
    manifest = cast(dict[str, Any], json.loads(path.read_text()))
    if manifest.get("generator_version") != plan.GENERATOR_VERSION:
        raise LoadRefused(
            f"the set was written by generator version {manifest.get('generator_version')}; "
            f"this loader reads version {plan.GENERATOR_VERSION}"
        )
    return manifest


def identity_of(manifest: dict[str, Any]) -> dict[str, Any]:
    return {k: manifest[k] for k in ("generator_version", "seed", "scale", "graph_scale")}


def _lines(folder: Path, entry: dict[str, Any]) -> Iterator[bytes]:
    """The file's lines, its SHA-256 checked when the last is read: a changed file is refused at
    its end, and since nothing in it is marked done, a rerun after regenerating starts it again."""
    digest = hashlib.sha256()
    path = folder / entry["path"]
    if not path.exists():
        raise LoadRefused(f"{entry['path']} is listed in the manifest and missing")
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            yield line
    if digest.hexdigest() != entry["sha256"]:
        raise LoadRefused(f"{entry['path']} is not the file the manifest lists (SHA-256 differs)")


def _json_rows(folder: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _lines(folder, entry)]


# --- Building writes ------------------------------------------------------------------------------


def _handling(marking: dict[str, str]) -> Handling:
    return Handling(
        classification=marking["classification"],
        handling_code=marking["handling_code"],
        originator=marking["originator"],
        owning_unit=marking["owning_unit"],
    )


def _provenance(dataset: str, locator: str, moment: datetime) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id=f"client-size:{dataset}", locator=locator, excerpt_hash="")],
        first_seen=moment,
    )


def node_writes(
    source: plan.Source, rows: Sequence[dict[str, Any]], moment: datetime
) -> list[NodeWrite]:
    """The rows as node writes. No `datasets`: the stamping graph stamps the source's."""
    default = source.marking.as_dict()
    return [
        NodeWrite(
            id=row["id"],
            type=row["type"],
            properties=row["props"],
            provenance=_provenance(source.dataset, row["loc"], moment),
            handling=_handling(row.get("marking") or default),
            created_by=LOADER,
            created_at=moment,
        )
        for row in rows
    ]


def _interval(row: dict[str, Any]) -> Interval | None:
    if "from" not in row:
        return None
    return Interval(
        valid_from=datetime.fromisoformat(row["from"]),
        valid_to=datetime.fromisoformat(row["to"]) if row.get("to") else None,
    )


def edge_writes(
    source: plan.Source, rows: Sequence[dict[str, Any]], moment: datetime
) -> list[EdgeWrite]:
    default = source.marking.as_dict()
    return [
        EdgeWrite(
            id=row["id"],
            type=row["type"],
            source=row["s"],
            target=row["t"],
            properties=row.get("props") or {},
            interval=_interval(row),
            occurrences=row.get("occ", 1),
            provenance=_provenance(source.dataset, row["loc"], moment),
            handling=_handling(row.get("marking") or default),
            created_by=LOADER,
            created_at=moment,
        )
        for row in rows
    ]


#: Node ids written under a shared prefix, and the source whose marking they carry.
_SHARED_PREFIXES = {"cs-msisdn-": "calls", "cs-imei-": "subscribers", "cs-iban-": "transactions"}


def marking_of(node_id: str) -> plan.Marking:
    """The marking of a node the plan writes, from its id alone. A subject of a narrative source
    carries its source's marking (only its documents vary)."""
    for prefix, source in _SHARED_PREFIXES.items():
        if node_id.startswith(prefix):
            return plan.SOURCES_BY_KEY[source].marking
    key = node_id.split("-")[1]
    return plan.SOURCES_BY_KEY[key].marking


def dataset_of(node_id: str) -> str:
    for prefix, source in _SHARED_PREFIXES.items():
        if node_id.startswith(prefix):
            return plan.SOURCES_BY_KEY[source].dataset
    return plan.SOURCES_BY_KEY[node_id.split("-")[1]].dataset


def _restrictiveness(marking: plan.Marking, scheme: HandlingScheme) -> tuple[int, int]:
    order = {"permitted": 0, "conditional": 1, "restricted": 2}
    code = scheme.handling_codes[marking.handling_code]
    return scheme.classification.index(marking.classification), order[code.dissemination]


def same_as_writes(
    rows: Sequence[dict[str, Any]], scheme: HandlingScheme, moment: datetime
) -> list[EdgeWrite]:
    """The planted candidates as the resolver writes a `SAME_AS`: inferred, scored, marked as the
    more restrictive record (its unit kept), and in only the datasets both records are in."""
    writes = []
    for row in rows:
        ends = sorted(
            (marking_of(row["s"]), marking_of(row["t"])),
            key=lambda m: _restrictiveness(m, scheme),
            reverse=True,
        )
        handling = merge_handling(
            _handling(ends[0].as_dict()), _handling(ends[1].as_dict()), scheme
        )
        shared = sorted({dataset_of(row["s"])} & {dataset_of(row["t"])})
        writes.append(
            EdgeWrite(
                id=row["id"],
                type="SAME_AS",
                source=row["s"],
                target=row["t"],
                properties={
                    "score": row["score"],
                    "model_version": plan.SAME_AS_MODEL,
                    "comparison_vector": json.dumps({"spelling": row["distance"]}),
                },
                provenance=Provenance(
                    state=ProvenanceState.INFERRED,
                    sources=[
                        SourceRef(
                            document_id=f"{plan.SAME_AS_MODEL}:{row['s']}:{row['t']}",
                            locator=plan.SAME_AS_MODEL,
                            excerpt_hash="",
                        )
                    ],
                    first_seen=moment,
                    extraction_confidence=row["score"],
                ),
                handling=handling,
                created_by=LOADER,
                created_at=moment,
                datasets=shared,
            )
        )
    return writes


def event_records(
    source: plan.Source, lines: Iterator[bytes], *, scope: str, load_id: str
) -> Iterator[EventRecord]:
    handling = _handling(source.marking.as_dict())
    reader = csv.reader(line.decode() for line in lines)
    header = next(reader)
    if tuple(header) != plan.EVENT_COLUMNS:
        raise LoadRefused(f"an events file of {source.key} has the header {header}")
    for (
        event_id,
        edge_id,
        edge_type,
        source_id,
        target_id,
        occurred_at,
        duration,
        cell_site,
        lat,
        lon,
        direction,
        properties,
    ) in reader:
        yield EventRecord(
            event_id=event_id,
            edge_id=edge_id,
            edge_type=edge_type,
            source_id=source_id,
            target_id=target_id,
            occurred_at=datetime.fromisoformat(occurred_at),
            duration_s=float(duration) if duration else None,
            cell_site=cell_site or None,
            lat=float(lat) if lat else None,
            lon=float(lon) if lon else None,
            direction=direction or None,
            properties=json.loads(properties),
            investigation_scope=scope,
            handling=handling,
            load_id=load_id,
        )


# --- The stages ---------------------------------------------------------------------------------


def _files(manifest: dict[str, Any], kind: str, source: str | None = None) -> list[dict[str, Any]]:
    """The manifest's files of one kind, in load order: by source (the plan's order), then by
    stream (the source's own order, so a stream's nodes come before a later one's links), then
    by part."""
    order = {s.key: i for i, s in enumerate(plan.SOURCES)}
    streams = {(s.key, st.name): i for s in plan.SOURCES for i, st in enumerate(s.streams)}
    chosen = [
        f
        for f in manifest["files"]
        if f["kind"] == kind and (source is None or f["source"] == source)
    ]
    return sorted(
        chosen,
        key=lambda f: (
            order.get(f["source"], 99),
            streams.get((f["source"], f["stream"]), 0),
            f["part"],
        ),
    )


async def _links(
    graph: GraphPort, writes: list[EdgeWrite], *, resumed: bool, say: Callable[[str], None]
) -> tuple[int, int]:
    """(written, skipped). A first attempt goes through `write_graph`'s bulk path, which merges a
    collision as every seed does; a resumed one skips collisions, which are its own earlier
    writes."""
    if not resumed:
        await write_graph(
            graph,
            [],
            writes,
            chunk=NODE_CHUNK,
            nouns=("nodes", "links"),
            progress=say,
            method="bulk",
        )
        return len(writes), 0
    if not isinstance(graph, BulkGraphLoader):
        raise LoadRefused("the graph does not offer bulk loading; a resumed file cannot be redone")
    result = await graph.bulk_load_edges(writes, chunk_size=BULK_CHUNK)
    say(
        f"  graph: resumed: {len(result.written):,} links written, "
        f"{len(result.collisions):,} already stored and skipped"
    )
    return len(result.written), len(result.collisions)


@dataclass
class Totals:
    files: int = 0
    skipped: int = 0
    rows: int = 0
    seconds: float = 0.0


async def load(
    folder: Path,
    deps: Deps,
    *,
    stages: Sequence[str] = STAGES,
    state: Path | None = None,
    moment: datetime | None = None,
) -> dict[str, Totals]:
    manifest = read_manifest(folder)
    ledger = Ledger(state or folder / "load_state.json", identity_of(manifest))
    unknown = sorted(set(stages) - set(STAGES))
    if unknown:
        raise LoadRefused(f"no stage called {', '.join(unknown)} (the stages: {', '.join(STAGES)})")
    moment = moment or datetime.now(UTC)
    say = deps.say
    totals: dict[str, Totals] = {}

    async def each(
        stage: str,
        entries: list[dict[str, Any]],
        run: Callable[[dict[str, Any], bool], Awaitable[int]],
    ) -> None:
        t = totals.setdefault(stage, Totals())
        started = time.monotonic()
        for i, entry in enumerate(entries, 1):
            name = f"{stage}:{entry['path']}"
            if ledger.is_done(name):
                t.skipped += 1
                continue
            resumed = ledger.was_started(name)
            ledger.start(name)
            began = time.monotonic()
            rows = await run(entry, resumed)
            seconds = time.monotonic() - began
            ledger.finish(name, rows=rows, seconds=round(seconds, 1))
            t.files += 1
            t.rows += rows
            rate = f", {rows / seconds:,.0f} a second" if seconds > 0 else ""
            say(
                f"  {stage}: {entry['path']} ({i:,} of {len(entries):,}): {rows:,} rows in "
                f"{seconds:,.0f}s{rate}{' (resumed)' if resumed else ''}"
            )
        t.seconds += time.monotonic() - started

    if "cases" in stages:
        for source in plan.SOURCES:
            if source.key not in ledger.cases:
                ledger.cases[source.key] = await deps.ensure_case(source)
                ledger.save()
                say(f"  cases: {source.dataset} is read by case {ledger.cases[source.key]}")

    if "nodes" in stages:

        async def nodes(entry: dict[str, Any], _resumed: bool) -> int:
            source = plan.SOURCES_BY_KEY[entry["source"]]
            writes = node_writes(source, _json_rows(folder, entry), moment)
            await write_graph(
                deps.graph_for(source.dataset),
                writes,
                [],
                chunk=NODE_CHUNK,
                nouns=("nodes", "links"),
                progress=say,
            )
            return len(writes)

        await each("nodes", _files(manifest, "nodes"), nodes)

    if "edges" in stages:

        async def edges(entry: dict[str, Any], resumed: bool) -> int:
            source = plan.SOURCES_BY_KEY[entry["source"]]
            writes = edge_writes(source, _json_rows(folder, entry), moment)
            written, _skipped = await _links(
                deps.graph_for(source.dataset), writes, resumed=resumed, say=say
            )
            return written

        await each("edges", _files(manifest, "edges"), edges)

    if "same_as" in stages:

        async def same_as(entry: dict[str, Any], resumed: bool) -> int:
            writes = same_as_writes(_json_rows(folder, entry), deps.scheme, moment)
            written, _skipped = await _links(deps.raw_graph, writes, resumed=resumed, say=say)
            return written

        await each("same_as", _files(manifest, "same_as"), same_as)

    if "texts" in stages:

        async def texts(entry: dict[str, Any], _resumed: bool) -> int:
            rows = _json_rows(folder, entry)
            for row in rows:
                reader = Principal(id=LOADER, clearance="SECRET", org_unit=row["owning_unit"])
                await deps.texts.store_document_text(row["document_id"], row["text"], reader)
            return len(rows)

        await each("texts", _files(manifest, "texts"), texts)

    if "events" in stages:

        async def events(entry: dict[str, Any], resumed: bool) -> int:
            source = plan.SOURCES_BY_KEY[entry["source"]]
            scope = ledger.cases.get(source.key)
            if scope is None:
                raise LoadRefused(f"no case recorded for {source.key}: run the cases stage first")
            load_id = f"client-size:{entry['path']}"
            if resumed:
                gone = await deps.analytics.retract_load(load_id)
                say(f"  events: {entry['path']} was part-loaded; {gone:,} rows removed first")
            loaded = 0
            batch: list[EventRecord] = []
            for record in event_records(
                source, _lines(folder, entry), scope=scope, load_id=load_id
            ):
                batch.append(record)
                if len(batch) >= EVENT_BATCH:
                    await deps.analytics.load_events(batch)
                    loaded += len(batch)
                    batch = []
            if batch:
                await deps.analytics.load_events(batch)
                loaded += len(batch)
            return loaded

        await each("events", _files(manifest, "events"), events)

    if "check" in stages and deps.check is not None:
        await deps.check(EDGE_TYPES)
    return totals


#: Every link type the plan writes (a test holds this to what the generated files hold).
EDGE_TYPES = (
    "ASSOCIATE_OF",
    "COMMUNICATED_WITH",
    "FAMILY_OF",
    "MEMBER_OF",
    "MENTIONED_IN",
    "PRESENT_AT",
    "SAME_AS",
    "TRANSACTED",
    "USES",
)


# --- Running against a real stack ---------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.load_client_size", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("--from", dest="folder", required=True, type=Path)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--stages", default=",".join(STAGES))
    parser.add_argument("--grant", action="append", default=[], metavar="ACCOUNT=LEVEL")
    args = parser.parse_args(argv)
    args.stages = [s for s in args.stages.split(",") if s]
    return args


def refuse_below_secret() -> None:
    """The plan holds SECRET records; a deployment whose ceiling is lower would refuse them
    part-way through (the stamping graph's backstop), so the load refuses at the start."""
    from services.ingest.ceiling import AboveTheDeploymentCeiling, refuse_writes_above_the_ceiling

    probe = NodeWrite(
        id="probe",
        type="Person",
        properties={},
        created_by=LOADER,
        created_at=datetime.now(UTC),
        provenance=_provenance("probe", "probe", datetime.now(UTC)),
        handling=Handling(
            classification="SECRET", handling_code="R", originator="x", owning_unit="x"
        ),
    )
    try:
        refuse_writes_above_the_ceiling([probe])
    except AboveTheDeploymentCeiling as error:
        raise LoadRefused(f"this deployment's marking ceiling is below SECRET: {error}") from None


async def _run(args: argparse.Namespace) -> int:
    from scripts.case_seed import case_from_arguments
    from scripts.seed_support import KNOWN_STRAY_ADVICE, report_ids_stored_twice
    from services.api.analytics_store import open_analytics
    from services.api.config import PostgresConfig
    from services.api.dataset_scope import stamping
    from services.api.review import ExtractionCandidateStore

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from demo_fixtures.datasets import SeedDataset
    from ontology.handling import load_uk_le_scheme
    from ontology.packs import load_deployment_ontology

    # Everything that can refuse without a store does so before any connection is opened.
    refuse_below_secret()
    folder = args.folder.resolve()
    Ledger(args.state or folder / "load_state.json", identity_of(read_manifest(folder)))
    scheme = load_uk_le_scheme()
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    adapter = GraphArcadeDBAdapter(client, scheme)
    engine = os.environ.get("OSPREY_ANALYTICS_ENGINE", "duckdb")
    analytics, close_analytics = await open_analytics(
        engine,
        duckdb_path=os.environ.get(
            "ANALYTICS_DB_PATH", "../OspreyFlow_Data/_local-runtime/analytics.duckdb"
        ),
        handling_scheme=scheme,
    )
    texts = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    graphs: dict[str, GraphPort] = {}

    def graph_for(dataset: str) -> GraphPort:
        if dataset not in graphs:
            graphs[dataset] = cast(GraphPort, stamping(adapter, dataset=dataset))
        return graphs[dataset]

    async def ensure_case(source: plan.Source) -> str:
        seeder = Principal(
            id=f"{LOADER}-{source.marking.owning_unit}",
            clearance="SECRET",
            org_unit=source.marking.owning_unit,
            receivable_handling_codes=["P", "C", "R"],
        )
        dataset = SeedDataset(
            id=source.dataset,
            name=source.name,
            source=f"client-size:{source.dataset}",
            case_name=f"Client-size: {source.name}",
        )
        case = await case_from_arguments(
            name=f"Client-size: {source.name}",
            seeder=seeder,
            grant_texts=list(args.grant),
            dataset=dataset,
        )
        return case.id

    async def check(types: Sequence[str]) -> int:
        from adapters.graph_arcadedb.naming import physical_type_name

        return await report_ids_stored_twice(
            client,
            edge_types=[physical_type_name(t) for t in types],
            prefix="cs-",
            advice=KNOWN_STRAY_ADVICE,
        )

    try:
        await client.create_database_if_absent()
        await adapter.apply_schema(load_deployment_ontology())
        deps = Deps(
            graph_for=graph_for,
            raw_graph=cast(GraphPort, adapter),
            analytics=analytics,
            texts=texts,
            ensure_case=ensure_case,
            scheme=scheme,
            check=check,
        )
        totals = await load(folder, deps, stages=args.stages, state=args.state)
    finally:
        await texts.close()
        await close_analytics()
        await client.aclose()
    for stage, t in totals.items():
        print(
            f"{stage}: {t.files:,} file(s) loaded, {t.skipped:,} already done, {t.rows:,} rows, "
            f"{t.seconds / 3600:,.2f} h"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return asyncio.run(_run(args))
    except LoadRefused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
