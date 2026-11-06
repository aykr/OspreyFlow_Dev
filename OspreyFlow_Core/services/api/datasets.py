"""Datasets, and the datasets each case may read (`06_DECISIONS.md` ADR-099).

A dataset is a named body of data held by a unit: the Enron corpus, Fixture Corp, a body of data
loaded through the Ingest Studio. Every node and link carries the datasets that wrote it, and a case
reads only elements of its own datasets, enforced in the graph adapter with the handling axes
(`AccessFilter.gremlin_structural_step`). This module holds the two records that limit rests on:
the datasets of each unit, and the datasets of each case.

**Who may name what.** A case names at least one dataset, every one of its own unit. A dataset of
another unit and one that does not exist are refused with the same answer, so a refusal says
nothing about another unit's data. Changing a case's datasets is its Author's (the route's level);
a branch takes its parent's.

**Names are unique within a unit (ADR-099 Amendment 6),** ignoring case and spacing, so two of a
unit's datasets never read alike; the id stays what every element and case refers to. A dataset
asked for by name is refused when the name is taken; the one a case makes for itself, and a seed's,
take a suffix instead ("Branch of Enron (2)").

**Egress (ADR-136 decision 2).** Each dataset says where its material may go when a model is asked:
`none`, never to a hosted engine; `contracted`, only to a provider under a privacy contract; `any`,
to any enabled provider. It is `none` until an administrator changes it in the Admin area (each
change audited by the route), a dataset made before ADR-136 included: the column is added with that
default. The routing reads it (`model_routing.RoutedModel`); a dataset it cannot find is `none`.

**No role, no list (ADR-099 Amendment 11; the owner, 4 November 2026).** A person holding no right
(`rights_for(roles)` empty: no role, or only roles this deployment does not know) reads no dataset's
name or id, though an administrator has given them a unit, or an Author a case level, before a role.
The rule is here, in the one place every dataset's name is read from, as a condition of the query
itself (rule 3): `list_for` and `of_case` take the reader, and the reader's holding a right is part
of the `WHERE` clause, so no row is fetched for them. The answer is the same empty list whatever
the unit or case holds, so it says nothing of what exists. `list_all` and `egress_of` take no
reader: the first is the Admin area's (`administer_system`, refused before any query), the second
the model routing's, behind its own rights.

**Three kinds (ADR-140 R8, ADR-099 Amendments 12 and 13, ADR-143 decision 1).** A `source`
dataset is loaded through the Studio or a seed. A `composite` names two or more of its unit's
source datasets (`members`) and holds none of their data: a case reading it reads each member, and
the composite's own id, at read time. An `analyst_layer` belongs to exactly one case (`layer_of`),
is made with it, named for it, of its unit, and is never offered: no list (`list_for`, `list_all`,
`of_case`) returns one, none can be chosen for a case or as a member, and its name takes no place
in the unit's names (the unique-name index leaves layers out, so a name refused would not say a
layer exists).

**One dataset per case.** A case chooses exactly one dataset, a source or a composite
(`set_for_case`). What a request under the case reads, its *read set* (`ids_of_case`), is that
dataset (a composite as its members, then its own id) **plus** the case's own layer, and nothing
else. The order matters to writers that take the first (`dataset_scope.made_in`, the stamping
graph): the first is the case's source, or a composite's first member, exactly as before this
change (where writes go is the owner's: ADR-143 open question 1, ADR-099 Amendment 12 item 5). A
deployment made before this keeps reading every dataset a case named until
`scripts.migrate_cases_to_one_dataset` places it; the one-row index on `investigation_datasets` is
built once no case names two.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

import asyncpg
from pydantic import BaseModel, Field

from conduit_common.identity import new_id
from schemas.admin import DatasetEgress
from schemas.domain import Principal
from schemas.rights import rights_for

MAX_DATASET_NAME = 200
#: A composite names at least two datasets (one would be the dataset itself) and a bounded number.
MAX_COMPOSITE_MEMBERS = 50

DatasetKind = Literal["source", "composite", "analyst_layer"]
SOURCE: DatasetKind = "source"
COMPOSITE: DatasetKind = "composite"
ANALYST_LAYER: DatasetKind = "analyst_layer"

_EGRESS_ORDER: dict[DatasetEgress, int] = {"none": 0, "contracted": 1, "any": 2}


class Dataset(BaseModel):
    id: str
    name: str
    owning_unit: str
    created_at: datetime
    created_by: str
    #: ADR-136 decision 2: `none` until an administrator changes it.
    egress: DatasetEgress = "none"
    #: ADR-099 Amendments 12 and 13: what kind of dataset this is.
    kind: DatasetKind = SOURCE
    #: A composite's members, in order; empty for any other kind.
    members: list[str] = Field(default_factory=list)
    #: An analyst layer's case; `None` for any other kind.
    layer_of: str | None = None


def layer_name(case_name: str | None, investigation_id: str) -> str:
    """What a case's layer is called: for the case (ADR-143 decision 1). Never shown in a list."""
    named = " ".join((case_name or "").split()) or investigation_id
    return f"Analyst layer: {named}"[:MAX_DATASET_NAME]


def strictest_egress(egresses: Sequence[DatasetEgress]) -> DatasetEgress:
    """The most limiting of `egresses`; `none` when there are none to go by (ADR-136: not known is
    `none`)."""
    return min(egresses, key=_EGRESS_ORDER.__getitem__, default="none")


def layer_egress(case_egresses: Sequence[DatasetEgress]) -> DatasetEgress:
    """A layer's egress (ADR-136), held here and nowhere else: the strictest of what its case
    otherwise reads, so a layer neither stops a case asking a hosted model nor lets its material
    go further than the case's source would. Pending the owner's ruling on a layer's egress,
    raised at ADR-143's step L3.1."""
    return strictest_egress(case_egresses)


def read_set(chosen: Sequence[Dataset], layer: str | None) -> list[str]:
    """ADR-143 decision 1: what a request under a case reads, from what the case chose and its
    layer. A composite reads as its members then its own id (ADR-099 Amendment 12 item 3). A case
    that has chosen nothing reads nothing, its layer included."""
    if not chosen:
        return []
    ids: list[str] = []
    for dataset in chosen:
        if dataset.kind == COMPOSITE:
            ids.extend(dataset.members)
        ids.append(dataset.id)
    if layer is not None:
        ids.append(layer)
    return list(dict.fromkeys(ids))


class CreateDatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_DATASET_NAME)


class CaseDatasetsRequest(BaseModel):
    #: ADR-099 Amendment 12: exactly one, a source or a composite. A list, for the wire shape the
    #: Glass already sends; the store refuses any other length with the one refusal.
    dataset_ids: list[str] = Field(min_length=1, max_length=100)


class CreateCompositeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_DATASET_NAME)
    member_ids: list[str] = Field(min_length=2, max_length=MAX_COMPOSITE_MEMBERS)


def reads_dataset_names(reader: Principal) -> bool:
    """ADR-099 Amendment 11: whether `reader` may be told any dataset's name — only while holding a
    right. A person with no role, or with only roles this deployment does not know, may not."""
    return bool(rights_for(reader.roles))


class DatasetRefusedError(Exception):
    """A case was given no dataset, or one that is not of the principal's unit (or not at all):
    one answer for both, so the refusal does not say whether another unit holds it."""


class DatasetStore(Protocol):
    async def create(
        self, principal: Principal, name: str, *, suffix_if_taken: bool = False
    ) -> Dataset: ...
    async def known(self, dataset_ids: Sequence[str]) -> set[str]: ...
    async def register(self, dataset: Dataset) -> Dataset: ...
    #: ADR-099 Amendment 11: both name datasets, so both take the reader and name none to a reader
    #: holding no right (`reads_dataset_names`).
    async def list_for(self, reader: Principal) -> list[Dataset]: ...
    async def of_case(self, investigation_id: str, reader: Principal) -> list[Dataset]: ...
    #: The read set (module docstring): what a request under the case reads, its layer included.
    async def ids_of_case(self, investigation_id: str) -> list[str]: ...
    #: Exactly one dataset, a source or a composite; makes the case's layer if it has none.
    async def set_for_case(
        self,
        investigation_id: str,
        dataset_ids: Sequence[str],
        principal: Principal,
        *,
        case_name: str | None = None,
    ) -> list[Dataset]: ...
    async def copy_case(self, from_investigation_id: str, to_investigation_id: str) -> None: ...
    #: ADR-143 decision 1: the case's layer, made if it has none (idempotent), and its id.
    async def ensure_layer(
        self, investigation_id: str, *, unit: str, created_by: str, case_name: str | None = None
    ) -> str: ...
    async def layer_of_case(self, investigation_id: str) -> str | None: ...
    #: What the case chose, a source or a composite, with no reader: for the seeds and the
    #: migration, never for a route (a route names datasets only through `of_case`).
    async def chosen_of_case(self, investigation_id: str) -> list[Dataset]: ...
    #: ADR-099 Amendment 12 item 2: a composite of the principal's unit's source datasets.
    async def create_composite(
        self,
        principal: Principal,
        name: str,
        member_ids: Sequence[str],
        *,
        suffix_if_taken: bool = False,
    ) -> Dataset: ...
    # ADR-136 decision 2: every dataset, for the Admin area; the egress of some; setting it.
    async def list_all(self) -> list[Dataset]: ...
    async def egress_of(self, dataset_ids: Sequence[str]) -> dict[str, Dataset]: ...
    async def set_egress(
        self, dataset_id: str, egress: DatasetEgress
    ) -> tuple[DatasetEgress, Dataset]: ...


class UnknownDatasetEgressError(Exception):
    """An administrator named a dataset that does not exist (a 404)."""


def _clean(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise DatasetRefusedError("a dataset needs a name")
    return cleaned[:MAX_DATASET_NAME]


def name_key(name: str) -> str:
    """What two names must differ in: case and spacing aside."""
    return " ".join(name.split()).casefold()


def _taken(name: str) -> DatasetRefusedError:
    return DatasetRefusedError(f"A dataset named {name!r} already exists in your unit.")


def _suffixed(name: str, n: int) -> str:
    suffix = f" ({n})"
    return name[: MAX_DATASET_NAME - len(suffix)] + suffix


def _ordered(dataset_ids: Sequence[str]) -> list[str]:
    ordered = list(dict.fromkeys(dataset_ids))
    if not ordered:
        raise DatasetRefusedError("a case reads at least one dataset")
    return ordered


def _one(dataset_ids: Sequence[str]) -> str:
    """ADR-099 Amendment 12 item 1: a case reads exactly one dataset (or one composite)."""
    ordered = _ordered(dataset_ids)
    if len(ordered) != 1:
        raise DatasetRefusedError("a case reads exactly one dataset, or one composite")
    return ordered[0]


def _members(member_ids: Sequence[str]) -> list[str]:
    ordered = list(dict.fromkeys(member_ids))
    if not 2 <= len(ordered) <= MAX_COMPOSITE_MEMBERS:
        raise DatasetRefusedError("a composite names at least two datasets")
    return ordered


def _members_of(dataset: Dataset) -> list[str]:
    return list(dataset.members) if dataset.kind == COMPOSITE else [dataset.id]


async def read_also(
    store: DatasetStore,
    investigation_id: str,
    dataset_id: str,
    principal: Principal,
    *,
    case_name: str | None = None,
) -> str:
    """The case reads `dataset_id` as well as whatever it read: where it read nothing, that
    dataset; where it read another, a composite of what it read and this one (ADR-099 Amendment 12:
    a case never names two). What a seed loaded into an existing case does; idempotent. Returns
    the id the case now chooses."""
    chosen = await store.chosen_of_case(investigation_id)
    reads = [m for d in chosen for m in _members_of(d)]
    if dataset_id in reads and len(chosen) == 1:
        return chosen[0].id
    members = list(dict.fromkeys([*reads, dataset_id]))
    if len(members) == 1:
        await store.set_for_case(investigation_id, members, principal, case_name=case_name)
        return members[0]
    return await compose_for_case(store, investigation_id, members, principal, case_name=case_name)


async def compose_for_case(
    store: DatasetStore,
    investigation_id: str,
    members: Sequence[str],
    principal: Principal,
    *,
    case_name: str | None = None,
) -> str:
    """A composite of `members`, named for them, chosen by the case. Its egress is the strictest
    of its members' (ADR-136), so a case reading it may send exactly what it sent before it read a
    composite; an administrator may change it afterwards like any dataset's."""
    held = await store.egress_of(members)
    label = " + ".join(held[m].name if m in held else m for m in members)
    composite = await store.create_composite(
        principal, label[:MAX_DATASET_NAME], members, suffix_if_taken=True
    )
    egress = strictest_egress([held[m].egress if m in held else "none" for m in members])
    _, composite = await store.set_egress(composite.id, egress)
    await store.set_for_case(investigation_id, [composite.id], principal, case_name=case_name)
    return composite.id


class InMemoryDatasetStore:
    """The same calls with no Postgres, for tests and a process without one."""

    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.cases: dict[str, list[str]] = {}

    def add(self, dataset: Dataset) -> Dataset:
        self.datasets[dataset.id] = dataset
        return dataset

    def _offered(self) -> list[Dataset]:
        return [d for d in self.datasets.values() if d.kind != ANALYST_LAYER]

    def _free_name(self, unit: str, name: str, *, suffix_if_taken: bool) -> str:
        # A layer's name takes no place in the unit's names (it is never shown).
        taken = {name_key(d.name) for d in self._offered() if d.owning_unit == unit}
        if name_key(name) not in taken:
            return name
        if not suffix_if_taken:
            raise _taken(name)
        n = 2
        while name_key(_suffixed(name, n)) in taken:
            n += 1
        return _suffixed(name, n)

    async def register(self, dataset: Dataset) -> Dataset:
        """A dataset with a chosen id; writing the same id again keeps the first record."""
        if dataset.id in self.datasets:
            return self.datasets[dataset.id]
        name = self._free_name(dataset.owning_unit, _clean(dataset.name), suffix_if_taken=True)
        return self.add(dataset.model_copy(update={"name": name}))

    async def create(
        self, principal: Principal, name: str, *, suffix_if_taken: bool = False
    ) -> Dataset:
        cleaned = self._free_name(principal.org_unit, _clean(name), suffix_if_taken=suffix_if_taken)
        return self.add(
            Dataset(
                id=new_id(),
                name=cleaned,
                owning_unit=principal.org_unit,
                created_at=datetime.now(UTC),
                created_by=principal.id,
            )
        )

    def _choosable(self, dataset_id: str, unit: str, *, kinds: Sequence[DatasetKind]) -> Dataset:
        held = self.datasets.get(dataset_id)
        if held is None or held.owning_unit != unit or held.kind not in kinds:
            raise DatasetRefusedError(dataset_id)
        return held

    async def create_composite(
        self,
        principal: Principal,
        name: str,
        member_ids: Sequence[str],
        *,
        suffix_if_taken: bool = False,
    ) -> Dataset:
        members = _members(member_ids)
        for member in members:
            self._choosable(member, principal.org_unit, kinds=(SOURCE,))
        cleaned = self._free_name(principal.org_unit, _clean(name), suffix_if_taken=suffix_if_taken)
        return self.add(
            Dataset(
                id=new_id(),
                name=cleaned,
                owning_unit=principal.org_unit,
                created_at=datetime.now(UTC),
                created_by=principal.id,
                kind=COMPOSITE,
                members=members,
            )
        )

    async def known(self, dataset_ids: Sequence[str]) -> set[str]:
        return {d for d in dataset_ids if d in self.datasets}

    async def list_for(self, reader: Principal) -> list[Dataset]:
        named = reads_dataset_names(reader)
        return sorted(
            (d for d in self._offered() if named and d.owning_unit == reader.org_unit),
            key=lambda d: d.name,
        )

    async def of_case(self, investigation_id: str, reader: Principal) -> list[Dataset]:
        named = reads_dataset_names(reader)
        return [self.datasets[i] for i in self.cases.get(investigation_id, []) if named]

    async def chosen_of_case(self, investigation_id: str) -> list[Dataset]:
        return [
            self.datasets[i] for i in self.cases.get(investigation_id, []) if i in self.datasets
        ]

    async def layer_of_case(self, investigation_id: str) -> str | None:
        for dataset in self.datasets.values():
            if dataset.kind == ANALYST_LAYER and dataset.layer_of == investigation_id:
                return dataset.id
        return None

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        # A test may give a case an id it never registered (Postgres's foreign key would refuse
        # it); such an id reads as a source dataset of that id, as it did before kinds existed.
        chosen = [
            self.datasets.get(i)
            or Dataset(id=i, name=i, owning_unit="", created_at=datetime.now(UTC), created_by="")
            for i in self.cases.get(investigation_id, [])
        ]
        return read_set(chosen, await self.layer_of_case(investigation_id))

    async def ensure_layer(
        self, investigation_id: str, *, unit: str, created_by: str, case_name: str | None = None
    ) -> str:
        held = await self.layer_of_case(investigation_id)
        if held is not None:
            return held
        layer = self.add(
            Dataset(
                id=new_id(),
                name=layer_name(case_name, investigation_id),
                owning_unit=unit,
                created_at=datetime.now(UTC),
                created_by=created_by,
                kind=ANALYST_LAYER,
                layer_of=investigation_id,
            )
        )
        return layer.id

    async def set_for_case(
        self,
        investigation_id: str,
        dataset_ids: Sequence[str],
        principal: Principal,
        *,
        case_name: str | None = None,
    ) -> list[Dataset]:
        chosen = _one(dataset_ids)
        self._choosable(chosen, principal.org_unit, kinds=(SOURCE, COMPOSITE))
        self.cases[investigation_id] = [chosen]
        await self.ensure_layer(
            investigation_id, unit=principal.org_unit, created_by=principal.id, case_name=case_name
        )
        return await self.of_case(investigation_id, principal)

    async def copy_case(self, from_investigation_id: str, to_investigation_id: str) -> None:
        """A branch reads its parent's chosen dataset, and has a layer of its own: a layer is
        never shared with another case (ADR-143 decision 1), a branch included."""
        chosen = list(self.cases.get(from_investigation_id, []))
        self.cases[to_investigation_id] = chosen
        if chosen:
            parent = self.datasets[chosen[0]]
            await self.ensure_layer(
                to_investigation_id, unit=parent.owning_unit, created_by=parent.created_by
            )

    async def list_all(self) -> list[Dataset]:
        return sorted(self._offered(), key=lambda d: (d.owning_unit, d.name))

    async def egress_of(self, dataset_ids: Sequence[str]) -> dict[str, Dataset]:
        held = {d: self.datasets[d] for d in dataset_ids if d in self.datasets}
        for dataset_id, dataset in held.items():
            if dataset.kind == ANALYST_LAYER and dataset.layer_of is not None:
                others = [
                    self.datasets[i].egress
                    for i in await self.ids_of_case(dataset.layer_of)
                    if i != dataset_id and i in self.datasets
                ]
                held[dataset_id] = dataset.model_copy(update={"egress": layer_egress(others)})
        return held

    async def set_egress(
        self, dataset_id: str, egress: DatasetEgress
    ) -> tuple[DatasetEgress, Dataset]:
        held = self.datasets.get(dataset_id)
        if held is None or held.kind == ANALYST_LAYER:
            raise UnknownDatasetEgressError(dataset_id)
        changed = held.model_copy(update={"egress": egress})
        self.datasets[dataset_id] = changed
        return held.egress, changed


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS datasets_unit_idx ON datasets (owning_unit, name);
-- ADR-136 decision 2: every dataset, those made before it included, starts at `none`.
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS egress TEXT NOT NULL DEFAULT 'none'
    CHECK (egress IN ('none', 'contracted', 'any'));
-- ADR-099 Amendments 12 and 13: the kind, and a layer's one case.
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'source'
    CHECK (kind IN ('source', 'composite', 'analyst_layer'));
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS layer_of TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS datasets_one_layer_per_case ON datasets (layer_of)
    WHERE layer_of IS NOT NULL;
CREATE TABLE IF NOT EXISTS composite_members (
    composite_id TEXT NOT NULL REFERENCES datasets (id),
    member_id TEXT NOT NULL REFERENCES datasets (id),
    position INTEGER NOT NULL,
    PRIMARY KEY (composite_id, member_id)
);
CREATE TABLE IF NOT EXISTS investigation_datasets (
    investigation_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets (id),
    position INTEGER NOT NULL,
    PRIMARY KEY (investigation_id, dataset_id)
);
"""

_MEMBERS_SQL = (
    "COALESCE((SELECT array_agg(m.member_id ORDER BY m.position) FROM composite_members m "
    "WHERE m.composite_id = d.id), '{}'::text[]) AS members"
)
_COLUMNS = (
    "d.id, d.name, d.owning_unit, d.created_at, d.created_by, d.egress, d.kind, d.layer_of, "
    + _MEMBERS_SQL
)

#: The name a unit's datasets may not share, case and spacing aside (`name_key`).
_NAME_KEY_SQL = "lower(regexp_replace(btrim(name), '\\s+', ' ', 'g'))"
#: Layers are left out of the names (module docstring): a refused name must not say one exists.
_NAME_INDEX_WHERE = "WHERE kind <> 'analyst_layer'"
#: ADR-099 Amendment 12: one row per case, built once no case names two.
_ONE_PER_CASE_INDEX = "investigation_datasets_one_per_case"


async def _tell_apart_and_index(conn: asyncpg.Connection) -> None:
    """Before the unique index: names a unit already holds twice are told apart, the earliest
    keeping its name and each later one a suffix, so a deployment made before ADR-099 Amendment 6
    starts rather than failing to build the index. An index built before layers existed covers
    every row; it is rebuilt to leave layers out."""
    indexdef = await conn.fetchval(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'datasets_unit_name_unique' "
        "AND schemaname = current_schema()"
    )
    if indexdef is not None and "analyst_layer" in indexdef:
        return
    if indexdef is not None:
        await conn.execute("DROP INDEX datasets_unit_name_unique")
    rows = await conn.fetch(
        f"SELECT id, name, owning_unit, {_NAME_KEY_SQL} AS key FROM datasets "
        f"{_NAME_INDEX_WHERE} ORDER BY owning_unit, created_at, id"
    )
    taken: dict[str, set[str]] = {}
    for row in rows:
        keys = taken.setdefault(row["owning_unit"], set())
        if row["key"] not in keys:
            keys.add(row["key"])
            continue
        n = 2
        while name_key(_suffixed(row["name"], n)) in keys:
            n += 1
        renamed = _suffixed(row["name"], n)
        keys.add(name_key(renamed))
        await conn.execute("UPDATE datasets SET name = $1 WHERE id = $2", renamed, row["id"])
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS datasets_unit_name_unique "
        f"ON datasets (owning_unit, {_NAME_KEY_SQL}) {_NAME_INDEX_WHERE}"
    )


async def index_one_dataset_per_case(conn: asyncpg.Connection) -> bool:
    """Builds the one-row-per-case index when no case names two datasets; says whether it is
    there. Run at every start and by the migration's real run, which is what makes it possible."""
    if await conn.fetchval(
        "SELECT 1 FROM pg_indexes WHERE indexname = $1 AND schemaname = current_schema()",
        _ONE_PER_CASE_INDEX,
    ):
        return True
    if await conn.fetchval(
        "SELECT 1 FROM investigation_datasets GROUP BY investigation_id HAVING count(*) > 1 LIMIT 1"
    ):
        return False
    await conn.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_ONE_PER_CASE_INDEX} "
        "ON investigation_datasets (investigation_id)"
    )
    return True


def _row(row: asyncpg.Record) -> Dataset:
    values = dict(row)
    values["members"] = list(values.get("members") or [])
    return Dataset(**values)


class PostgresDatasetStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresDatasetStore:
        # Bounded, as every store here is: the default ten-connection floor per store pushed the
        # lifespan past its ceiling
        # (`test_app_lifespan_does_not_reopen_the_unbounded_pool_ceiling`).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
            await _tell_apart_and_index(conn)
            await index_one_dataset_per_case(conn)
        return cls(pool)

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self, principal: Principal, name: str, *, suffix_if_taken: bool = False
    ) -> Dataset:
        dataset = Dataset(
            id=new_id(),
            name=_clean(name),
            owning_unit=principal.org_unit,
            created_at=datetime.now(UTC),
            created_by=principal.id,
        )
        return await self._insert(dataset, suffix_if_taken=suffix_if_taken)

    async def register(self, dataset: Dataset) -> Dataset:
        """A dataset with a chosen id (`scripts.stamp_datasets` names the seeds' datasets).
        Writing the same id again leaves the record as it is; a name another of the unit's
        datasets holds takes a suffix."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM datasets d WHERE d.id = $1", dataset.id
            )
        if row is not None:
            return _row(row)
        return await self._insert(
            dataset.model_copy(update={"name": _clean(dataset.name)}), suffix_if_taken=True
        )

    async def add(self, dataset: Dataset) -> Dataset:
        return await self.register(dataset)

    async def _insert(
        self, dataset: Dataset, *, suffix_if_taken: bool, conn: asyncpg.Connection | None = None
    ) -> Dataset:
        name, n = dataset.name, 2
        while True:
            try:
                async with self._maybe(conn) as c, c.transaction():
                    await c.execute(
                        "INSERT INTO datasets (id, name, owning_unit, created_at, created_by, "
                        "egress, kind, layer_of) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                        "ON CONFLICT (id) DO NOTHING",
                        dataset.id,
                        name,
                        dataset.owning_unit,
                        dataset.created_at,
                        dataset.created_by,
                        dataset.egress,
                        dataset.kind,
                        dataset.layer_of,
                    )
                    await c.executemany(
                        "INSERT INTO composite_members (composite_id, member_id, position) "
                        "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                        [(dataset.id, m, i) for i, m in enumerate(dataset.members)],
                    )
                return dataset.model_copy(update={"name": name})
            except asyncpg.UniqueViolationError as exc:
                if not suffix_if_taken:
                    raise _taken(dataset.name) from exc
                name, n = _suffixed(dataset.name, n), n + 1

    def _maybe(self, conn: asyncpg.Connection | None) -> Any:
        if conn is not None:
            return _Borrowed(conn)
        return self._pool.acquire()

    async def known(self, dataset_ids: Sequence[str]) -> set[str]:
        if not dataset_ids:
            return set()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM datasets WHERE id = ANY($1::text[])", list(set(dataset_ids))
            )
        return {r["id"] for r in rows}

    async def list_for(self, reader: Principal) -> list[Dataset]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM datasets d WHERE d.owning_unit = $1 AND $2::boolean "
                "AND d.kind <> 'analyst_layer' ORDER BY d.name",
                reader.org_unit,
                reads_dataset_names(reader),
            )
        return [_row(r) for r in rows]

    async def of_case(self, investigation_id: str, reader: Principal) -> list[Dataset]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id "
                "WHERE c.investigation_id = $1 AND $2::boolean AND d.kind <> 'analyst_layer' "
                "ORDER BY c.position",
                investigation_id,
                reads_dataset_names(reader),
            )
        return [_row(r) for r in rows]

    async def chosen_of_case(self, investigation_id: str) -> list[Dataset]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id "
                "WHERE c.investigation_id = $1 AND d.kind <> 'analyst_layer' ORDER BY c.position",
                investigation_id,
            )
        return [_row(r) for r in rows]

    async def layer_of_case(self, investigation_id: str) -> str | None:
        async with self._pool.acquire() as conn:
            found: str | None = await conn.fetchval(
                "SELECT id FROM datasets WHERE layer_of = $1 AND kind = 'analyst_layer'",
                investigation_id,
            )
        return found

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id "
                "WHERE c.investigation_id = $1 AND d.kind <> 'analyst_layer' ORDER BY c.position",
                investigation_id,
            )
        return read_set([_row(r) for r in rows], await self.layer_of_case(investigation_id))

    async def ensure_layer(
        self, investigation_id: str, *, unit: str, created_by: str, case_name: str | None = None
    ) -> str:
        held = await self.layer_of_case(investigation_id)
        if held is not None:
            return held
        layer = Dataset(
            id=new_id(),
            name=layer_name(case_name, investigation_id),
            owning_unit=unit,
            created_at=datetime.now(UTC),
            created_by=created_by,
            kind=ANALYST_LAYER,
            layer_of=investigation_id,
        )
        try:
            await self._insert(layer, suffix_if_taken=False)
        except DatasetRefusedError:
            # Two requests made the layer at once; the one-layer index kept the first.
            pass
        found = await self.layer_of_case(investigation_id)
        assert found is not None
        return found

    async def create_composite(
        self,
        principal: Principal,
        name: str,
        member_ids: Sequence[str],
        *,
        suffix_if_taken: bool = False,
    ) -> Dataset:
        members = _members(member_ids)
        async with self._pool.acquire() as conn:
            held = await conn.fetch(
                "SELECT id FROM datasets WHERE id = ANY($1::text[]) AND owning_unit = $2 "
                "AND kind = 'source'",
                members,
                principal.org_unit,
            )
        if {r["id"] for r in held} != set(members):
            raise DatasetRefusedError("not every member is one of this unit's datasets")
        composite = Dataset(
            id=new_id(),
            name=_clean(name),
            owning_unit=principal.org_unit,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            kind=COMPOSITE,
            members=members,
        )
        return await self._insert(composite, suffix_if_taken=suffix_if_taken)

    async def set_for_case(
        self,
        investigation_id: str,
        dataset_ids: Sequence[str],
        principal: Principal,
        *,
        case_name: str | None = None,
    ) -> list[Dataset]:
        chosen = _one(dataset_ids)
        async with self._pool.acquire() as conn, conn.transaction():
            held = await conn.fetchval(
                "SELECT 1 FROM datasets WHERE id = $1 AND owning_unit = $2 "
                "AND kind IN ('source', 'composite')",
                chosen,
                principal.org_unit,
            )
            if not held:
                raise DatasetRefusedError("not one of this unit's datasets")
            await conn.execute(
                "DELETE FROM investigation_datasets WHERE investigation_id = $1", investigation_id
            )
            await conn.execute(
                "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
                "VALUES ($1, $2, 0)",
                investigation_id,
                chosen,
            )
        await self.ensure_layer(
            investigation_id, unit=principal.org_unit, created_by=principal.id, case_name=case_name
        )
        return await self.of_case(investigation_id, principal)

    async def list_all(self) -> list[Dataset]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM datasets d WHERE d.kind <> 'analyst_layer' "
                "ORDER BY d.owning_unit, d.name"
            )
        return [_row(r) for r in rows]

    async def egress_of(self, dataset_ids: Sequence[str]) -> dict[str, Dataset]:
        if not dataset_ids:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM datasets d WHERE d.id = ANY($1::text[])",
                list(set(dataset_ids)),
            )
        held = {r["id"]: _row(r) for r in rows}
        for dataset_id, dataset in list(held.items()):
            if dataset.kind == ANALYST_LAYER and dataset.layer_of is not None:
                others = [i for i in await self.ids_of_case(dataset.layer_of) if i != dataset_id]
                async with self._pool.acquire() as conn:
                    egresses = await conn.fetch(
                        "SELECT egress FROM datasets WHERE id = ANY($1::text[])", others
                    )
                held[dataset_id] = dataset.model_copy(
                    update={
                        "egress": layer_egress([cast(DatasetEgress, r["egress"]) for r in egresses])
                    }
                )
        return held

    async def set_egress(
        self, dataset_id: str, egress: DatasetEgress
    ) -> tuple[DatasetEgress, Dataset]:
        async with self._pool.acquire() as conn, conn.transaction():
            before = await conn.fetchval(
                "SELECT egress FROM datasets WHERE id = $1 AND kind <> 'analyst_layer' FOR UPDATE",
                dataset_id,
            )
            if before is None:
                raise UnknownDatasetEgressError(dataset_id)
            row = await conn.fetchrow(
                f"UPDATE datasets d SET egress = $2 WHERE d.id = $1 RETURNING {_COLUMNS}",
                dataset_id,
                egress,
            )
        return cast(DatasetEgress, before), _row(row)

    async def copy_case(self, from_investigation_id: str, to_investigation_id: str) -> None:
        """A branch reads its parent's chosen dataset and has a layer of its own (ADR-143
        decision 1: a layer is never shared with another case)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
                "SELECT $2, c.dataset_id, c.position FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id "
                "WHERE c.investigation_id = $1 AND d.kind <> 'analyst_layer' "
                "ON CONFLICT DO NOTHING",
                from_investigation_id,
                to_investigation_id,
            )
            parent = await conn.fetchrow(
                "SELECT d.owning_unit, d.created_by FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id WHERE c.investigation_id = $1 "
                "ORDER BY c.position LIMIT 1",
                to_investigation_id,
            )
        if parent is not None:
            await self.ensure_layer(
                to_investigation_id, unit=parent["owning_unit"], created_by=parent["created_by"]
            )


class _Borrowed:
    """An `async with` over a connection already held, so `_insert` runs inside a caller's own
    connection (the migration's transaction) or a fresh one alike."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def __aenter__(self) -> asyncpg.Connection:
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        return None


__all__: Sequence[str] = (
    "ANALYST_LAYER",
    "COMPOSITE",
    "SOURCE",
    "CaseDatasetsRequest",
    "CreateCompositeRequest",
    "DatasetKind",
    "index_one_dataset_per_case",
    "layer_egress",
    "layer_name",
    "compose_for_case",
    "read_also",
    "read_set",
    "CreateDatasetRequest",
    "Dataset",
    "DatasetRefusedError",
    "DatasetStore",
    "InMemoryDatasetStore",
    "PostgresDatasetStore",
    "UnknownDatasetEgressError",
    "reads_dataset_names",
)
