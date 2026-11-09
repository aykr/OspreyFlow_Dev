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

**Recorded for the dataset.** Each addition is recorded against the dataset holding the copies
(`dataset_gazetteers`), not the case: every case reading that dataset reads the copies, so each sees
the gazetteer added, and a case's Author removing it removes it for all of them, as a load into
the dataset is every reader's. A case deleted, or moved to another dataset, leaves the record with
the copies it describes.

**Refreshed and removed.** A re-build of a gazetteer copies its places again into every dataset
recorded for it (`refresh_cases`), drops the record of a dataset no longer there, and marks
reverted the copies of places it no longer holds. Removing a gazetteer marks its copies reverted
(`GraphPort.revert_elements`: never deleted, out of every read) and takes them out of the cases'
working sets; **never another load's data**: a copy that another writer has also written (a source
not the gazetteer's, as when a case's own load matched it) or that an analyst confirmed is the
case's data now, and is kept. Judged on the copy alone, never on the links around it (rule 3).

**A case's own load may match a copy** by its `osm_id` (`find_node`, a load's lookup, which matches
its one named field unguarded, ADR-147 Amendment 1 decision 3b): the identifier is the loader's own
source row's, not one told it by the store, and what the load is told back is a count. The copy so
matched carries the load's source too, keeps its provenance (`merge_provenance`) and so its
identifiers stay withheld from every reader; a removal keeps it, as another writer's.

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
#: How many nodes one write, or one read of a page, takes at a time.
_BATCH = 500


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
    gazetteer's alone: every source on them the gazetteer's, and none confirmed by a person. A
    copy another writer also wrote (a case's load matched it), or one an analyst confirmed, is the
    case's data now and is kept (rule 6: never another load's data). Judged on the copy itself,
    never on what is around it: a link resting on a copy goes out of every read with it, and comes
    back when the gazetteer is added again (the copy's id is the same, and writing it revives it),
    so whether a copy goes never depends on a link a reader may not see (rule 3).
    Returns `(reverted, kept)`."""
    own = f"{COPY_SOURCE_PREFIX}{gazetteer}"
    copies = [
        n
        for n in await _locations(graph, _reader(scheme, case_dataset), case_dataset)
        if n.provenance.gazetteer == gazetteer and n.id not in keep
    ]
    reverted = [
        c.id
        for c in copies
        if all(s.document_id == own for s in c.provenance.sources)
        and c.provenance.confirmed_by is None
        and c.provenance.last_confirmed is None
    ]
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
            by=added.added_by,
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
