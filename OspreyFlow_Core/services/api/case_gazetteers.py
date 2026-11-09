"""A case's gazetteers: their places copied into the case's own dataset (`06_DECISIONS.md` ADR-147
Amendment 2, the owner's ruling 6 of 9 November 2026, option C).

**Why copies.** A case reads one dataset (ADR-099 Amendment 12), and a case reading a composite is
read-only for loads (Amendment 15), so adding a gazetteer as a second dataset cost a working case
its loads (P4's open question). The owner ruled for copies: when a case's Author adds a gazetteer,
its places are copied into the case's own dataset, so the case stays one dataset and keeps its
loads.

**What a copy is.** A `Location` of its own, never the gazetteer's node (rule 6: nothing is merged
in storage), with an id made from the place's and the case dataset's (`copy_id`), so a re-copy
writes the same node. It keeps the place's properties (its `osm_id` among them, stored) and the
gazetteer's handling, so every reader's clearance applies to it as to the place; its one source is
the gazetteer (`gazetteer:<dataset>`, `place <node id>`: no path, no row of the extract); and its
provenance names the gazetteer (`Provenance.gazetteer`), kept through any later write
(`merge.merge_provenance`). **That provenance is what keeps decision 3b for a copy**: its source
identifiers are withheld from every request reader (`ontology.handling.withhold_sources`) and never
matched by the case's searches (`builders.match_any_field`), keyed on the provenance, not on a
`gazetteer-*` dataset name, which a copy is not in. The place search keeps a copy as a place.

**Who may.** The case's Author, with the right that changes what a case reads (`share_case`), a
gazetteer of the Author's unit (a dataset they may choose, ADR-099 decision 3), into a case reading
one source dataset of its own. A case reading a composite or nothing is refused in words.

**Refreshed and removed.** Each addition is recorded here (`case_gazetteers`). A re-build of a
gazetteer copies its places again into every case that added it (`refresh_cases`), and marks
reverted the copies of places it no longer holds. Removing a gazetteer from a case marks its copies
reverted (`GraphPort.revert_elements`: never deleted, out of every read) and takes them out of the
case's working sets; **never another load's nodes**: a copy that another writer has also written
(a source not the gazetteer's) or that a link rests on is the case's data now, and is kept.

**Read as the Conduit.** The places are read, and the copies found, by the Conduit's own service
principal scoped to the one dataset (`_reader`), inside `sources_in_full` so the identifiers are
copied. Nothing read here is sent to the Glass: the routes answer with the gazetteers' names, and
whether any copy was kept, judged on the copies the asker may read.
"""

from __future__ import annotations

import hashlib
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
#: How many nodes one write, one read of a page, or one link check takes at a time.
_BATCH = 500
_LINK_BATCH = 100


@dataclass(frozen=True)
class AddedGazetteer:
    """One gazetteer a case added: copied into `case_dataset`, the case's own dataset then."""

    investigation_id: str
    gazetteer: str
    case_dataset: str
    added_by: str
    added_at: datetime


class CaseGazetteerStore:
    """The additions, in the Conduit's Postgres."""

    _SCHEMA = """
CREATE TABLE IF NOT EXISTS case_gazetteers (
    investigation_id TEXT NOT NULL,
    gazetteer TEXT NOT NULL,
    case_dataset TEXT NOT NULL,
    added_by TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (investigation_id, gazetteer)
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

    async def add(self, added: AddedGazetteer) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO case_gazetteers VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (investigation_id, gazetteer) DO UPDATE SET "
                "case_dataset = EXCLUDED.case_dataset",
                added.investigation_id, added.gazetteer, added.case_dataset, added.added_by,
                added.added_at,
            )  # fmt: skip

    async def remove(self, investigation_id: str, gazetteer: str) -> AddedGazetteer | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                "DELETE FROM case_gazetteers WHERE investigation_id = $1 AND gazetteer = $2 "
                "RETURNING *",
                investigation_id, gazetteer,
            )  # fmt: skip
        return _added(row) if row else None

    async def of_case(self, investigation_id: str) -> list[AddedGazetteer]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT * FROM case_gazetteers WHERE investigation_id = $1 ORDER BY gazetteer",
                investigation_id,
            )
        return [_added(r) for r in rows]

    async def cases_with(self, gazetteer: str) -> list[AddedGazetteer]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT * FROM case_gazetteers WHERE gazetteer = $1 ORDER BY investigation_id",
                gazetteer,
            )
        return [_added(r) for r in rows]


def _added(row: asyncpg.Record) -> AddedGazetteer:
    return AddedGazetteer(
        investigation_id=row["investigation_id"], gazetteer=row["gazetteer"],
        case_dataset=row["case_dataset"], added_by=row["added_by"], added_at=row["added_at"],
    )  # fmt: skip


class InMemoryCaseGazetteerStore:
    """The same calls with no Postgres, for tests and a process without one."""

    def __init__(self) -> None:
        self.added: dict[tuple[str, str], AddedGazetteer] = {}

    async def add(self, added: AddedGazetteer) -> None:
        self.added[(added.investigation_id, added.gazetteer)] = added

    async def remove(self, investigation_id: str, gazetteer: str) -> AddedGazetteer | None:
        return self.added.pop((investigation_id, gazetteer), None)

    async def of_case(self, investigation_id: str) -> list[AddedGazetteer]:
        return sorted(
            (a for (case, _), a in self.added.items() if case == investigation_id),
            key=lambda a: a.gazetteer,
        )

    async def cases_with(self, gazetteer: str) -> list[AddedGazetteer]:
        return sorted(
            (a for (_, held), a in self.added.items() if held == gazetteer),
            key=lambda a: a.investigation_id,
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


def _reader(scheme: HandlingScheme, dataset: str) -> Principal:
    """The Conduit's own reader of one dataset: the scheme's highest clearance and every handling
    code, so what it finds is the dataset's (bounded by a restricted code's unit, which no
    gazetteer recipe sets). Never a request's principal; nothing it reads is sent."""
    return Principal(
        id="system:case-gazetteers",
        clearance=scheme.classification[-1],
        org_unit="system:case-gazetteers",
        receivable_handling_codes=list(scheme.handling_codes),
        datasets=[dataset],
    )


async def _locations(graph: GraphPort, reader: Principal, dataset: str) -> list[Node]:
    """Every `Location` of `dataset` that `reader` reads, whole (`sources_in_full`), paged to the
    end (`next_cursor is None`, never an empty page, is the end)."""
    found: list[Node] = []
    cursor: NodeId | None = None
    with sources_in_full():
        while True:
            page = await graph.list_nodes("Location", reader, cursor=cursor, limit=_BATCH)
            found.extend(n for n in page.nodes if dataset in n.datasets)
            cursor = page.next_cursor
            if cursor is None:
                return found


def _copy(place: Node, *, gazetteer: str, case_dataset: str, by: str, now: datetime) -> NodeWrite:
    return NodeWrite(
        id=copy_id(place.id, case_dataset),
        type=place.type,
        properties=dict(place.properties),
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(
                    document_id=f"{COPY_SOURCE_PREFIX}{gazetteer}",
                    locator=f"place {place.id}",
                    excerpt_hash="",
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
) -> list[NodeId]:
    """Copies every place of `gazetteer` into `case_dataset`, in one transaction, and marks
    reverted the copies of places the gazetteer no longer holds (a re-build's), as `remove_copies`
    judges them. Returns the copies' ids reverted, for the caller to take out of working sets."""
    now = datetime.now(UTC)
    places = await _locations(graph, _reader(scheme, gazetteer), gazetteer)
    writes = [
        _copy(p, gazetteer=gazetteer, case_dataset=case_dataset, by=by, now=now) for p in places
    ]
    tx = await graph.begin_transaction()
    try:
        for start in range(0, len(writes), _BATCH):
            await graph.upsert_nodes(writes[start : start + _BATCH], tx)
        await graph.commit_transaction(tx)
    except BaseException:
        await graph.rollback_transaction(tx)
        raise
    reverted, _kept = await remove_copies(
        graph, scheme, gazetteer=gazetteer, case_dataset=case_dataset,
        keep={w.id for w in writes},
    )  # fmt: skip
    return reverted


async def remove_copies(
    graph: GraphPort,
    scheme: HandlingScheme,
    *,
    gazetteer: str,
    case_dataset: str,
    keep: set[NodeId] | frozenset[NodeId] = frozenset(),
) -> tuple[list[NodeId], list[NodeId]]:
    """Marks reverted `gazetteer`'s copies in `case_dataset` (but those in `keep`) that are the
    gazetteer's alone: no other writer's source on them and no link resting on them (rule 6:
    never another load's data). Returns `(reverted, kept)`."""
    reader = _reader(scheme, case_dataset)
    own = f"{COPY_SOURCE_PREFIX}{gazetteer}"
    copies = [
        n
        for n in await _locations(graph, reader, case_dataset)
        if n.provenance.gazetteer == gazetteer and n.id not in keep
    ]
    alone = [c.id for c in copies if all(s.document_id == own for s in c.provenance.sources)]
    linked: set[NodeId] = set()
    for start in range(0, len(alone), _LINK_BATCH):
        batch = alone[start : start + _LINK_BATCH]
        around = await graph.expand(ExpandRequest(node_ids=batch, depth=1), reader)
        for edge in around.edges:
            linked.update((edge.source, edge.target))
    reverted = [i for i in alone if i not in linked]
    if reverted:
        tx = await graph.begin_transaction()
        try:
            await graph.revert_elements(reverted, [], tx)
            await graph.commit_transaction(tx)
        except BaseException:
            await graph.rollback_transaction(tx)
            raise
    gone = set(reverted)
    return reverted, [c.id for c in copies if c.id not in gone]


async def refresh_cases(
    graph: GraphPort, scheme: HandlingScheme, store: object, gazetteer: str
) -> list[NodeId]:
    """After a build of `gazetteer` commits: its places copied again into every case that added
    it. Returns the copies reverted, across the cases."""
    reverted: list[NodeId] = []
    for added in await store.cases_with(gazetteer):  # type: ignore[attr-defined]
        reverted += await copy_places(
            graph, scheme, gazetteer=gazetteer, case_dataset=added.case_dataset,
            by=added.added_by,
        )  # fmt: skip
    return reverted


async def refresh_cases_from_env(graph: GraphPort, scheme: HandlingScheme, gazetteer: str) -> int:
    """The command-line builds' refresh, against the Conduit's own database. Returns how many cases
    were refreshed. An unreachable database raises `OSError`/`asyncpg.PostgresError`, which the
    builds say in words."""
    from .config import PostgresConfig

    store = await CaseGazetteerStore.connect(PostgresConfig.from_env().dsn)
    try:
        cases = await store.cases_with(gazetteer)
        await refresh_cases(graph, scheme, store, gazetteer)
        return len(cases)
    finally:
        await store.close()
