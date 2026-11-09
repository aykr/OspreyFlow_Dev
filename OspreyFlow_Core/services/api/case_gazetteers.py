"""A case's gazetteers: their places copied into the case's own dataset (`06_DECISIONS.md` ADR-147
Amendment 2, the owner's ruling 6 of 9 November 2026, option C).

**Why copies.** A case reads one dataset (ADR-099 Amendment 12), and a case reading a composite is
read-only for loads (Amendment 15), so adding a gazetteer as a second dataset cost a working case
its loads (P4's open question). The owner ruled for copies: when a case's Author adds a gazetteer,
its places are copied into the case's own dataset, so the case stays one dataset and keeps its
loads.

**What a copy is.** A `Location` of its own, never the gazetteer's node (rule 6: nothing is merged
in storage), with an id made from the place's and the dataset's (`copy_id`), so a re-copy writes
the same node. It keeps the place's properties (its `osm_id` among them, stored) and the
gazetteer's handling, so every reader's clearance applies to it as to the place; its one source is
the gazetteer (`gazetteer:<dataset>`, `place`: no node id, path or row, rule 7); and its provenance
names the gazetteer (`Provenance.gazetteer`), kept through any later write
(`merge.merge_provenance`). **That provenance is what keeps decision 3b for a copy**: its source
identifiers are withheld from every request reader (`ontology.handling.withhold_sources`) and never
matched by the case's searches (`builders.match_any_field`), keyed on the provenance, not on a
`gazetteer-*` dataset name, which a copy is not in. The place search keeps a copy as a place.

**Who may.** Adding or removing a gazetteer changes the dataset for every case reading it, so it
is a dataset-level action (the orchestrator's review of P5, item 6): `PUT`/`DELETE
/v1/datasets/{dataset}/gazetteers/{gazetteer}`, behind the dataset route's own gate and
`run_pipelines`, the right that runs a load into a dataset; a gazetteer of the dataset's own unit
only. A composite or a drawn dataset is refused, as for any load.

**Recorded for the dataset** (`dataset_gazetteers`): every case reading it reads the copies and
sees the gazetteer added; a case deleted, or moved to another dataset, leaves the record with the
copies it describes.

**Copied in pages**, each its own transaction, never one unbounded write. **A copy the case has
written to** (another writer's source, as when a case's own load matched it by its `osm_id`, or a
person's confirmation) **is the case's data now**: a re-build does not write over it, and a removal
keeps it. **A removal also keeps a copy a link rests on**, read as the Conduit reads the dataset and
every analyst layer of a case reading it, so no case is left a link to nothing; a kept copy keeps
its gazetteer mark (3b holds). Every other copy is marked reverted (`GraphPort.revert_elements`:
never deleted, out of every read) and taken out of the working sets. A re-build drops the record of
a dataset no longer there, never writing into one, and reverts the copy of a place gone.

**Read as the Conduit.** The places are read, and the copies found, by the Conduit's own reader
scoped to the one dataset (`_reader`), inside `sources_in_full` so the identifiers are copied.
Nothing read here is sent to the Glass: the routes answer with the gazetteers' names, and the count
of kept copies the asker may read.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from ulid import ULID

from ontology.handling import HandlingScheme, sources_in_full
from ports.graph import GraphPort
from schemas.domain import (
    ExpandRequest,
    Node,
    NodeId,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

#: A copy's one source names the gazetteer it was copied from.
COPY_SOURCE_PREFIX = "gazetteer:"
#: How many nodes one write, or one read of a page, takes at a time; how many copies one link
#: check asks about.
_BATCH = 500
_LINK_BATCH = 100


@dataclass(frozen=True)
class AddedGazetteer:
    """A gazetteer copied into `case_dataset`, a case's own dataset: recorded **for the dataset**,
    which holds the copies, so every case that reads the dataset reads them and sees the gazetteer
    added, and a case deleted or moved to another dataset leaves the copies' record with them.
    `added_in` is the case it was added from, for the audit's sake."""

    case_dataset: str
    gazetteer: str
    added_in: str
    added_by: str
    added_at: datetime


class CaseGazetteerStore:
    """The additions, in the Conduit's Postgres."""

    _SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_gazetteers (
    case_dataset TEXT NOT NULL,
    gazetteer TEXT NOT NULL,
    added_in TEXT NOT NULL,
    added_by TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (case_dataset, gazetteer)
);
"""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> CaseGazetteerStore:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
        async with pool.acquire() as connection:
            await connection.execute(cls._SCHEMA)
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    async def add(self, added: AddedGazetteer) -> bool:
        """Records `added`; `False` if the dataset held the gazetteer already (the first record
        kept)."""
        async with self.pool.acquire() as connection:
            made = await connection.fetchval(
                "INSERT INTO dataset_gazetteers VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (case_dataset, gazetteer) DO NOTHING RETURNING true",
                added.case_dataset, added.gazetteer, added.added_in, added.added_by,
                added.added_at,
            )  # fmt: skip
        return bool(made)

    async def remove(self, case_dataset: str, gazetteer: str) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM dataset_gazetteers WHERE case_dataset = $1 AND gazetteer = $2",
                case_dataset, gazetteer,
            )  # fmt: skip

    async def of_dataset(self, case_dataset: str) -> list[AddedGazetteer]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT * FROM dataset_gazetteers WHERE case_dataset = $1 ORDER BY gazetteer",
                case_dataset,
            )
        return [_added(r) for r in rows]

    async def datasets_with(self, gazetteer: str) -> list[AddedGazetteer]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT * FROM dataset_gazetteers WHERE gazetteer = $1 ORDER BY case_dataset",
                gazetteer,
            )
        return [_added(r) for r in rows]


def _added(row: asyncpg.Record) -> AddedGazetteer:
    return AddedGazetteer(
        case_dataset=row["case_dataset"], gazetteer=row["gazetteer"], added_in=row["added_in"],
        added_by=row["added_by"], added_at=row["added_at"],
    )  # fmt: skip


class InMemoryCaseGazetteerStore:
    """The same calls with no Postgres, for tests and a process without one, answering as the
    Postgres store does (the first record kept)."""

    def __init__(self) -> None:
        self.added: dict[tuple[str, str], AddedGazetteer] = {}

    async def add(self, added: AddedGazetteer) -> bool:
        key = (added.case_dataset, added.gazetteer)
        if key in self.added:
            return False
        self.added[key] = added
        return True

    async def remove(self, case_dataset: str, gazetteer: str) -> None:
        self.added.pop((case_dataset, gazetteer), None)

    async def of_dataset(self, case_dataset: str) -> list[AddedGazetteer]:
        return sorted(
            (a for (held, _), a in self.added.items() if held == case_dataset),
            key=lambda a: a.gazetteer,
        )

    async def datasets_with(self, gazetteer: str) -> list[AddedGazetteer]:
        return sorted(
            (a for (_, held), a in self.added.items() if held == gazetteer),
            key=lambda a: a.case_dataset,
        )


def copy_id(place_id: NodeId, case_dataset: str) -> NodeId:
    """The copy of `place_id` in `case_dataset`: the same every time, so a re-copy writes the same
    node. A ULID, as every node id is (`list_nodes` pages by it): the place's own time, where its id
    is one, and the rest from a digest of the pair."""
    digest = hashlib.sha256(f"{case_dataset}|{place_id}".encode()).digest()
    try:
        time = ULID.from_str(place_id).bytes[:6]
    except ValueError:
        time = digest[16:22]
    return str(ULID.from_bytes(time + digest[:10]))


def _reader(
    scheme: HandlingScheme, datasets: list[str], *, unit: str = "system:case-gazetteers"
) -> Principal:
    """The Conduit's own reader of `datasets`: the scheme's highest clearance and every handling
    code, and `unit` (the case dataset's own, so a link under a restricted code of that unit is
    seen too). Never a request's principal; nothing it reads is sent."""
    return Principal(
        id="system:case-gazetteers",
        clearance=scheme.classification[-1],
        org_unit=unit,
        receivable_handling_codes=list(scheme.handling_codes),
        datasets=datasets,
    )


async def _pages(graph: GraphPort, reader: Principal, dataset: str) -> AsyncIterator[list[Node]]:
    """`dataset`'s `Location`s that `reader` reads, whole (`sources_in_full`), a page at a time, to
    the end (`next_cursor is None`, never an empty page, is the end: rule 2)."""
    cursor: NodeId | None = None
    while True:
        with sources_in_full():
            page = await graph.list_nodes("Location", reader, cursor=cursor, limit=_BATCH)
        yield [n for n in page.nodes if dataset in n.datasets]
        cursor = page.next_cursor
        if cursor is None:
            return


async def _copies(
    graph: GraphPort, scheme: HandlingScheme, gazetteer: str, case_dataset: str
) -> list[Node]:
    found: list[Node] = []
    async for page in _pages(graph, _reader(scheme, [case_dataset]), case_dataset):
        found.extend(n for n in page if n.provenance.gazetteer == gazetteer)
    return found


def _the_gazetteer_s_alone(copy: Node, gazetteer: str) -> bool:
    """No other writer's source on it and no person's confirmation: what a re-build may write over
    and a removal may revert. Otherwise it is the case's data now (rule 6)."""
    own = f"{COPY_SOURCE_PREFIX}{gazetteer}"
    return (
        all(s.document_id == own for s in copy.provenance.sources)
        and copy.provenance.confirmed_by is None
        and copy.provenance.last_confirmed is None
    )


def _copy(place: Node, *, gazetteer: str, case_dataset: str, by: str, now: datetime) -> NodeWrite:
    return NodeWrite(
        id=copy_id(place.id, case_dataset),
        type=place.type,
        properties=dict(place.properties),
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            # The gazetteer alone: never the place's node id, nor the extract's path or row (rule
            # 7). `copy_id` already ties the copy to its place.
            sources=[
                SourceRef(
                    document_id=f"{COPY_SOURCE_PREFIX}{gazetteer}", locator="place", excerpt_hash=""
                )
            ],
            first_seen=now,
            gazetteer=gazetteer,
        ),
        handling=place.handling,
        created_by=by,
        created_at=now,
        load_id=f"gazetteer-copy:{gazetteer}",
        datasets=[case_dataset],
    )


async def copy_places(
    graph: GraphPort,
    scheme: HandlingScheme,
    *,
    gazetteer: str,
    case_dataset: str,
    by: str,
    link_datasets: list[str] | None = None,
    unit: str = "system:case-gazetteers",
) -> list[NodeId]:
    """Copies every place of `gazetteer` into `case_dataset`, **a page at a time, each page its own
    transaction** (a region's places are never one unbounded write; a copy that fails part way is
    finished by copying again, which writes the same nodes). **A copy the case has written to**
    (another writer's source, or a confirmation) **is not written over**: what the case asserted
    stands, whatever the gazetteer says now. Then marks reverted the copies of places the gazetteer
    no longer holds, as `remove_copies` judges them. Returns the ids reverted, for the caller to
    take out of working sets."""
    now = datetime.now(UTC)
    held = await _copies(graph, scheme, gazetteer, case_dataset)
    the_case_s = {c.id for c in held if not _the_gazetteer_s_alone(c, gazetteer)}
    written: set[NodeId] = set()
    async for page in _pages(graph, _reader(scheme, [gazetteer]), gazetteer):
        writes = [
            _copy(p, gazetteer=gazetteer, case_dataset=case_dataset, by=by, now=now) for p in page
        ]
        written.update(w.id for w in writes)
        writes = [w for w in writes if w.id not in the_case_s]
        if not writes:
            continue
        tx = await graph.begin_transaction()
        try:
            await graph.upsert_nodes(writes, tx)
            await graph.commit_transaction(tx)
        except BaseException:
            await graph.rollback_transaction(tx)
            raise
    reverted, _kept = await remove_copies(
        graph, scheme, gazetteer=gazetteer, case_dataset=case_dataset, keep=written,
        link_datasets=link_datasets, unit=unit,
    )  # fmt: skip
    return reverted


async def remove_copies(
    graph: GraphPort,
    scheme: HandlingScheme,
    *,
    gazetteer: str,
    case_dataset: str,
    keep: set[NodeId] | frozenset[NodeId] = frozenset(),
    link_datasets: list[str] | None = None,
    unit: str = "system:case-gazetteers",
) -> tuple[list[NodeId], list[NodeId]]:
    """Marks reverted `gazetteer`'s copies in `case_dataset` (but those in `keep`) that are the
    gazetteer's alone (`_the_gazetteer_s_alone`) **and that no link rests on**, so no case is left a
    link to nothing (the orchestrator's review of P5, item 7). The links are read as the Conduit
    reads the dataset and every analyst layer of a case reading it (`link_datasets`), at the
    highest clearance, with every handling code, as the dataset's own unit. A kept copy keeps its
    gazetteer mark, so decision 3b still holds for it. Returns `(reverted, kept)`, in batches."""
    reader = _reader(scheme, list(dict.fromkeys([case_dataset, *(link_datasets or [])])), unit=unit)
    copies = [c for c in await _copies(graph, scheme, gazetteer, case_dataset) if c.id not in keep]
    alone = [c.id for c in copies if _the_gazetteer_s_alone(c, gazetteer)]
    linked: set[NodeId] = set()
    for start in range(0, len(alone), _LINK_BATCH):
        around = await graph.expand(
            ExpandRequest(node_ids=alone[start : start + _LINK_BATCH], depth=1), reader
        )
        for edge in around.edges:
            linked.update((edge.source, edge.target))
    reverted = [i for i in alone if i not in linked]
    for start in range(0, len(reverted), _BATCH):
        tx = await graph.begin_transaction()
        try:
            await graph.revert_elements(reverted[start : start + _BATCH], [], tx)
            await graph.commit_transaction(tx)
        except BaseException:
            await graph.rollback_transaction(tx)
            raise
    gone = set(reverted)
    return reverted, [c.id for c in copies if c.id not in gone]


async def reading_datasets(datasets: object, case_dataset: str) -> list[str]:
    """The analyst layers of every case reading `case_dataset`, where a case's own links to a copy
    may be (ADR-143 Amendment 1)."""
    layers: list[str] = []
    for case in await datasets.cases_reading(case_dataset):  # type: ignore[attr-defined]
        layer = await datasets.layer_of_case(case)  # type: ignore[attr-defined]
        if layer:
            layers.append(layer)
    return layers


async def refresh_cases(
    graph: GraphPort, scheme: HandlingScheme, store: object, datasets: object, gazetteer: str
) -> list[NodeId]:
    """After a build of `gazetteer` commits: its places copied again into every dataset that holds
    its copies. A dataset no longer there is dropped from the record, never written into. Returns
    the copies reverted, across the datasets."""
    reverted: list[NodeId] = []
    for added in await store.datasets_with(gazetteer):  # type: ignore[attr-defined]
        held = await datasets.egress_of([added.case_dataset])  # type: ignore[attr-defined]
        if added.case_dataset not in held:
            await store.remove(added.case_dataset, gazetteer)  # type: ignore[attr-defined]
            continue
        reverted += await copy_places(
            graph, scheme, gazetteer=gazetteer, case_dataset=added.case_dataset,
            by=added.added_by, link_datasets=await reading_datasets(datasets, added.case_dataset),
            unit=held[added.case_dataset].owning_unit,
        )  # fmt: skip
    return reverted


async def refresh_cases_from_env(graph: GraphPort, scheme: HandlingScheme, gazetteer: str) -> int:
    """The command-line builds' refresh, against the Conduit's own database. Returns how many
    datasets were given the places again. An unreachable database raises
    `OSError`/`asyncpg.PostgresError`, which the builds say in words."""
    from .config import PostgresConfig
    from .datasets import PostgresDatasetStore

    dsn = PostgresConfig.from_env().dsn
    store = await CaseGazetteerStore.connect(dsn)
    datasets = await PostgresDatasetStore.connect(dsn)
    try:
        await refresh_cases(graph, scheme, store, datasets, gazetteer)
        return len(await store.datasets_with(gazetteer))
    finally:
        await datasets.close()
        await store.close()
