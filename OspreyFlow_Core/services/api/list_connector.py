"""The screening-list connector in Studio › Sources (`06_DECISIONS.md` ADR-140 Amendment 9
decision 3; Amendment 13), and a dataset's own reference list's rows imported from its own files
(replacing L1.4's stand-in, `services.ingest.reference_list_import`).

**Imported once for the deployment.** A screening list is a file in the ingest folder read through
its **template** (`services.ingest.connectors.screening_templates`): a known format's, or the blank
template's column picks. Every import that changes the list's rows is a **new version**, its rows
kept at `<bucket>/reference_lists/deployment/<name>@v<version>.parquet`
(`staging_catalogue.list_rows_path`; Amendment 11), written once and never replaced. **The same rows
again are no new version** (`unchanged`), so an import is idempotent per version. Every attempt is
recorded, updated, unchanged, refused or failed, in words; a refused or failed one is the list's
failure until a later import succeeds, and nothing of it is kept.

**Rule 9, before anything is read into a version.** As ADR-133's lists: a list is synthetic only
when every file it is read from is one of the repository's own synthetic files, by SHA-256 (the
screening manifest, and this connector's own for the blank template's file). Any other list is
real: it names its dataset, which this device's `real_data_exceptions.yaml` must admit for its use,
and a connector whose licence is not confirmed (UN, OpenSanctions) reads synthetic lists only.

**Subscribed to per dataset, by id** (L1.3's finding: never by name). The lists a dataset's rule or
Lookup is offered (`offered_lists`) are exactly those the staging save gate lets it read
(`staging_catalogue.readable_lists`): its own lists, and the deployment-wide lists it subscribes
to. Another dataset's list is never offered, whatever its kind, name or id.

**Refreshed** by hand (*Refresh now*) or on the list's schedule, each slot once (Valkey `SET NX`,
then marked on the list), run as the person who set it, who must still hold `load_screening_lists`.
Re-screening a dataset's customers against the changed entries is the rules' (rule 5: a match stays
`inferred`); an import records how many entries it added, changed and delisted for them.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import asyncpg
from services.ingest.connectors import reads
from services.ingest.connectors.screening_templates import (
    TemplateRefused,
    screening_rows,
)
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import (
    DEPLOYMENT_WIDE,
    SCREENING_COLUMNS,
    StagingError,
    _text,
    list_rows_path,
    read_staged_table,
    readable_lists,
    reference_table,
    stage_sources_and_lists,
)

from conduit_common.identity import new_id
from schemas.dataset_model import ReferenceList
from schemas.list_connector import (
    BlankListMapping,
    DeploymentList,
    DeploymentListInput,
    ListImport,
    ListImportOutcome,
    OfferedList,
)
from schemas.monitoring import ListSchedule
from schemas.screening import ScreeningListStatus

from .rule_schedule import cron_of, schedule_words
from .scheduler import DEFAULT_TIMEZONE, due_slots, next_slot
from .screening_refresh import (
    LICENCE_NOT_CONFIRMED,
    LICENCES,
    ListRefused,
    check_location,
    read_files,
    synthetic_digests,
)

log = logging.getLogger(__name__)

#: This connector's own synthetic files (the blank template's golden list), by SHA-256 (rule 9).
CONNECTOR_SYNTHETIC = (
    Path(__file__).resolve().parents[2] / "connectors" / "screening" / ("synthetic.sha256")
)
BLANK_LICENCE = "the client's own list: its terms are the client's"


class ListConnectorRefused(Exception):
    """Refused in words: nothing was read or kept."""


class ListNotFound(Exception):
    """No deployment-wide list has that id."""


# --- the store -----------------------------------------------------------------------------------


@dataclass
class _Held:
    """One list as the store keeps it: its record, and what the record does not show."""

    record: DeploymentList
    use: str
    digest: str | None = None
    schedule_owner: str | None = None
    schedule_set_at: datetime | None = None
    last_slot: datetime | None = None


@dataclass(frozen=True)
class ScheduledDeploymentList:
    list_id: str
    schedule: ListSchedule
    owner: str
    set_at: datetime
    last_slot: datetime | None


class ListStore(Protocol):
    async def lists(self) -> list[DeploymentList]: ...
    async def get(self, list_id: str) -> DeploymentList: ...
    async def held(self, list_id: str) -> _Held: ...
    async def add(self, body: DeploymentListInput, principal_id: str) -> DeploymentList: ...
    async def apply_version(
        self, list_id: str, *, previous: int, version: int, digest: str, entries: int, at: datetime
    ) -> bool: ...
    async def record_import(
        self, record: ListImport, *, at: datetime, failure: str | None
    ) -> None: ...
    async def imports(self, list_id: str, limit: int = 20) -> list[ListImport]: ...
    async def set_schedule(
        self, list_id: str, schedule: ListSchedule | None, owner: str, at: datetime
    ) -> DeploymentList: ...
    async def scheduled(self) -> list[ScheduledDeploymentList]: ...
    async def mark_slot(self, list_id: str, slot: datetime) -> bool: ...
    async def subscribe(self, dataset_id: str, list_id: str, principal_id: str) -> None: ...
    async def unsubscribe(self, dataset_id: str, list_id: str) -> None: ...
    async def subscribed(self, dataset_id: str) -> list[str]: ...


def _licence(template: str) -> tuple[str, bool, str | None]:
    if template == "blank":
        return BLANK_LICENCE, True, None
    note = LICENCE_NOT_CONFIRMED.get(template)
    return LICENCES[template], note is None, note


def _record(body: DeploymentListInput, list_id: str, principal_id: str, at: datetime) -> _Held:
    licence, confirmed, note = _licence(body.template)
    return _Held(
        record=DeploymentList(
            id=list_id, name=body.name, template=body.template, location=body.location,
            mapping=body.mapping, dataset=body.dataset, synthetic=body.dataset is None,
            licence=licence, licence_confirmed=confirmed, licence_note=note,
            created_by=principal_id, created_at=at,
        ),
        use=body.use,
    )  # fmt: skip


def _with_schedule_words(held: _Held) -> DeploymentList:
    record = held.record
    if record.schedule is None or held.schedule_set_at is None:
        return record.model_copy(update={"schedule_words": None, "next_refresh": None})
    after = held.last_slot or held.schedule_set_at
    return record.model_copy(
        update={
            "schedule_words": schedule_words(record.schedule),
            "next_refresh": next_slot(cron_of(record.schedule), DEFAULT_TIMEZONE, after=after),
        }
    )


class InMemoryListStore:
    """The store's twin for route tests: it refuses what the Postgres store refuses (rule 15): a
    second list of one name, a version applied over a version it did not start from, a
    subscription to a list that does not exist."""

    def __init__(self) -> None:
        self._lists: dict[str, _Held] = {}
        self._imports: list[ListImport] = []
        self._subscriptions: dict[str, set[str]] = {}

    async def lists(self) -> list[DeploymentList]:
        return sorted(
            (_with_schedule_words(h) for h in self._lists.values()), key=lambda r: r.name.lower()
        )

    async def get(self, list_id: str) -> DeploymentList:
        return _with_schedule_words(await self.held(list_id))

    async def held(self, list_id: str) -> _Held:
        if list_id not in self._lists:
            raise ListNotFound(list_id)
        return self._lists[list_id]

    async def add(self, body: DeploymentListInput, principal_id: str) -> DeploymentList:
        if any(h.record.name == body.name for h in self._lists.values()):
            raise ListConnectorRefused(f"a list named “{body.name}” is already imported")
        held = _record(body, new_id(), principal_id, datetime.now(UTC))
        self._lists[held.record.id] = held
        return held.record

    async def apply_version(
        self, list_id: str, *, previous: int, version: int, digest: str, entries: int, at: datetime
    ) -> bool:
        held = await self.held(list_id)
        if held.record.version != previous:
            return False
        held.record = held.record.model_copy(
            update={"version": version, "entries": entries, "updated_at": at}
        )
        held.digest = digest
        return True

    async def record_import(self, record: ListImport, *, at: datetime, failure: str | None) -> None:
        held = await self.held(record.list_id)
        held.record = held.record.model_copy(update={"attempted_at": at, "failure": failure})
        self._imports.insert(0, record)

    async def imports(self, list_id: str, limit: int = 20) -> list[ListImport]:
        return [r for r in self._imports if r.list_id == list_id][:limit]

    async def set_schedule(
        self, list_id: str, schedule: ListSchedule | None, owner: str, at: datetime
    ) -> DeploymentList:
        held = await self.held(list_id)
        held.record = held.record.model_copy(update={"schedule": schedule})
        held.schedule_owner = owner if schedule else None
        held.schedule_set_at = at if schedule else None
        held.last_slot = None
        return _with_schedule_words(held)

    async def scheduled(self) -> list[ScheduledDeploymentList]:
        return [
            ScheduledDeploymentList(
                h.record.id, h.record.schedule, h.schedule_owner, h.schedule_set_at, h.last_slot
            )
            for h in self._lists.values()
            if h.record.schedule and h.schedule_owner and h.schedule_set_at
        ]

    async def mark_slot(self, list_id: str, slot: datetime) -> bool:
        held = await self.held(list_id)
        if held.last_slot is not None and held.last_slot >= slot:
            return False
        held.last_slot = slot
        return True

    async def subscribe(self, dataset_id: str, list_id: str, principal_id: str) -> None:
        await self.held(list_id)
        self._subscriptions.setdefault(dataset_id, set()).add(list_id)

    async def unsubscribe(self, dataset_id: str, list_id: str) -> None:
        self._subscriptions.get(dataset_id, set()).discard(list_id)

    async def subscribed(self, dataset_id: str) -> list[str]:
        return sorted(self._subscriptions.get(dataset_id, set()))


_DDL = """
CREATE TABLE IF NOT EXISTS deployment_lists (
    id text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    template text NOT NULL,
    location text NOT NULL,
    mapping jsonb,
    dataset text,
    use_for text NOT NULL,
    version integer NOT NULL DEFAULT 0,
    digest text,
    entries integer NOT NULL DEFAULT 0,
    updated_at timestamptz,
    attempted_at timestamptz,
    failure text,
    schedule jsonb,
    schedule_owner text,
    schedule_set_at timestamptz,
    last_slot timestamptz,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS deployment_list_imports (
    id text PRIMARY KEY,
    list_id text NOT NULL REFERENCES deployment_lists(id) ON DELETE CASCADE,
    at timestamptz NOT NULL,
    record jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS deployment_list_imports_by_list
    ON deployment_list_imports (list_id, at DESC);
CREATE TABLE IF NOT EXISTS dataset_list_subscriptions (
    dataset_id text NOT NULL,
    list_id text NOT NULL REFERENCES deployment_lists(id) ON DELETE CASCADE,
    subscribed_by text NOT NULL,
    subscribed_at timestamptz NOT NULL,
    PRIMARY KEY (dataset_id, list_id)
);
"""


def _held_of(row: asyncpg.Record) -> _Held:
    licence, confirmed, note = _licence(row["template"])
    mapping = row["mapping"]
    schedule = row["schedule"]
    return _Held(
        record=DeploymentList(
            id=row["id"], name=row["name"], template=row["template"], location=row["location"],
            mapping=BlankListMapping.model_validate(json.loads(mapping)) if mapping else None,
            dataset=row["dataset"], synthetic=row["dataset"] is None, licence=licence,
            licence_confirmed=confirmed, licence_note=note, version=row["version"],
            entries=row["entries"], updated_at=row["updated_at"],
            attempted_at=row["attempted_at"], failure=row["failure"],
            schedule=ListSchedule.model_validate(json.loads(schedule)) if schedule else None,
            created_by=row["created_by"], created_at=row["created_at"],
        ),
        use=row["use_for"], digest=row["digest"], schedule_owner=row["schedule_owner"],
        schedule_set_at=row["schedule_set_at"], last_slot=row["last_slot"],
    )  # fmt: skip


class PostgresListStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresListStore:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_DDL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def lists(self) -> list[DeploymentList]:
        rows = await self._pool.fetch("SELECT * FROM deployment_lists ORDER BY lower(name)")
        return [_with_schedule_words(_held_of(r)) for r in rows]

    async def get(self, list_id: str) -> DeploymentList:
        return _with_schedule_words(await self.held(list_id))

    async def held(self, list_id: str) -> _Held:
        row = await self._pool.fetchrow("SELECT * FROM deployment_lists WHERE id = $1", list_id)
        if row is None:
            raise ListNotFound(list_id)
        return _held_of(row)

    async def add(self, body: DeploymentListInput, principal_id: str) -> DeploymentList:
        held = _record(body, new_id(), principal_id, datetime.now(UTC))
        try:
            await self._pool.execute(
                "INSERT INTO deployment_lists (id, name, template, location, mapping, dataset, "
                "use_for, created_by, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                held.record.id, body.name, body.template, body.location,
                body.mapping.model_dump_json() if body.mapping else None, body.dataset, body.use,
                principal_id, held.record.created_at,
            )  # fmt: skip
        except asyncpg.UniqueViolationError as exc:
            raise ListConnectorRefused(f"a list named “{body.name}” is already imported") from exc
        return held.record

    async def apply_version(
        self, list_id: str, *, previous: int, version: int, digest: str, entries: int, at: datetime
    ) -> bool:
        done = await self._pool.execute(
            "UPDATE deployment_lists SET version = $3, digest = $4, entries = $5, updated_at = $6 "
            "WHERE id = $1 AND version = $2",
            list_id, previous, version, digest, entries, at,
        )  # fmt: skip
        return str(done).endswith(" 1")

    async def record_import(self, record: ListImport, *, at: datetime, failure: str | None) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO deployment_list_imports (id, list_id, at, record) "
                "VALUES ($1, $2, $3, $4)",
                new_id(), record.list_id, at, record.model_dump_json(),
            )  # fmt: skip
            await conn.execute(
                "UPDATE deployment_lists SET attempted_at = $2, failure = $3 WHERE id = $1",
                record.list_id, at, failure,
            )  # fmt: skip

    async def imports(self, list_id: str, limit: int = 20) -> list[ListImport]:
        rows = await self._pool.fetch(
            "SELECT record FROM deployment_list_imports WHERE list_id = $1 "
            "ORDER BY at DESC LIMIT $2",
            list_id, limit,
        )  # fmt: skip
        return [ListImport.model_validate_json(r["record"]) for r in rows]

    async def set_schedule(
        self, list_id: str, schedule: ListSchedule | None, owner: str, at: datetime
    ) -> DeploymentList:
        done = await self._pool.execute(
            "UPDATE deployment_lists SET schedule = $2, schedule_owner = $3, "
            "schedule_set_at = $4, last_slot = NULL WHERE id = $1",
            list_id, schedule.model_dump_json() if schedule else None,
            owner if schedule else None, at if schedule else None,
        )  # fmt: skip
        if not done.endswith(" 1"):
            raise ListNotFound(list_id)
        return await self.get(list_id)

    async def scheduled(self) -> list[ScheduledDeploymentList]:
        rows = await self._pool.fetch(
            "SELECT * FROM deployment_lists WHERE schedule IS NOT NULL "
            "AND schedule_owner IS NOT NULL AND schedule_set_at IS NOT NULL"
        )
        out = []
        for row in rows:
            held = _held_of(row)
            assert held.record.schedule and held.schedule_owner and held.schedule_set_at
            out.append(
                ScheduledDeploymentList(
                    held.record.id,
                    held.record.schedule,
                    held.schedule_owner,
                    held.schedule_set_at,
                    held.last_slot,
                )  # fmt: skip
            )
        return out

    async def mark_slot(self, list_id: str, slot: datetime) -> bool:
        done = await self._pool.execute(
            "UPDATE deployment_lists SET last_slot = $2 WHERE id = $1 "
            "AND (last_slot IS NULL OR last_slot < $2)",
            list_id, slot,
        )  # fmt: skip
        return str(done).endswith(" 1")

    async def subscribe(self, dataset_id: str, list_id: str, principal_id: str) -> None:
        try:
            await self._pool.execute(
                "INSERT INTO dataset_list_subscriptions VALUES ($1, $2, $3, $4) "
                "ON CONFLICT DO NOTHING",
                dataset_id, list_id, principal_id, datetime.now(UTC),
            )  # fmt: skip
        except asyncpg.ForeignKeyViolationError as exc:
            raise ListNotFound(list_id) from exc

    async def unsubscribe(self, dataset_id: str, list_id: str) -> None:
        await self._pool.execute(
            "DELETE FROM dataset_list_subscriptions WHERE dataset_id = $1 AND list_id = $2",
            dataset_id, list_id,
        )  # fmt: skip

    async def subscribed(self, dataset_id: str) -> list[str]:
        rows = await self._pool.fetch(
            "SELECT list_id FROM dataset_list_subscriptions WHERE dataset_id = $1 "
            "ORDER BY list_id",
            dataset_id,
        )  # fmt: skip
        return [r["list_id"] for r in rows]


# --- where a version's rows are kept -------------------------------------------------------------


class ListRows(Protocol):
    def write(self, reference: ReferenceList, rows: Sequence[dict[str, object]]) -> str: ...
    def read(self, reference: ReferenceList) -> list[dict[str, object]] | None: ...
    def kept(self, dataset_id: str) -> list[ReferenceList]: ...


def _table(reference: ReferenceList, rows: Sequence[dict[str, object]]) -> Any:
    table = reference_table(reference, rows)
    if reference.kind == "screening":
        table.columns = list(SCREENING_COLUMNS)
    return table


class ParquetListRows:
    """A version's rows in the object store, at Amendment 11's path, written once and never
    replaced: the same rows again change nothing, other rows at that version are refused."""

    def __init__(self, storage: ObjectStorageConfig) -> None:
        self.storage = storage

    def write(self, reference: ReferenceList, rows: Sequence[dict[str, object]]) -> str:
        stage_sources_and_lists({}, {reference.name: _table(reference, rows)}, storage=self.storage)
        return list_rows_path(reference, storage=self.storage)

    def read(self, reference: ReferenceList) -> list[dict[str, object]] | None:
        import pyarrow.fs as pa_fs
        from services.ingest import staging as _staging

        path = list_rows_path(reference, storage=self.storage)
        if _staging.filesystem(self.storage).get_file_info(path).type == pa_fs.FileType.NotFound:
            return None
        table = read_staged_table(path, storage=self.storage)
        if table.reference != reference:
            raise StagingError([f"the rows kept for {reference.name!r} are another list's"])
        return [dict(r.cells) for r in table.rows]

    def kept(self, dataset_id: str) -> list[ReferenceList]:
        """The lists kept for a dataset, each at its highest version, by the record its own file
        carries (Amendment 12). Read from each file's schema alone, never its rows."""
        import pyarrow.fs as pa_fs
        import pyarrow.parquet as pq
        from services.ingest import staging as _staging
        from services.ingest.staging_catalogue import _META

        fs = _staging.filesystem(self.storage)
        folder = f"{self.storage.bucket}/reference_lists/{quote(dataset_id, safe='')}"
        if fs.get_file_info(folder).type == pa_fs.FileType.NotFound:
            return []
        newest: dict[str, ReferenceList] = {}
        for info in fs.get_file_info(pa_fs.FileSelector(folder)):
            if info.type != pa_fs.FileType.File or not info.path.endswith(".parquet"):
                continue
            with fs.open_input_file(info.path) as source:
                meta = pq.read_schema(source).metadata or {}
            record = json.loads(meta.get(_META, b"{}")).get("reference")
            if record is None:
                continue
            found = ReferenceList.model_validate(record)
            if found.dataset_id == dataset_id and (
                found.id not in newest or newest[found.id].version < found.version
            ):
                newest[found.id] = found
        return sorted(newest.values(), key=lambda r: (r.name, r.id))


class InMemoryListRows:
    """The object store's twin: written once and never replaced, as the Parquet keeper is."""

    def __init__(self) -> None:
        self.files: dict[tuple[str, str, int], tuple[ReferenceList, list[dict[str, object]]]] = {}

    def write(self, reference: ReferenceList, rows: Sequence[dict[str, object]]) -> str:
        # The same refusals (a key column missing, a key on two rows), and the cells as the real
        # keeper keeps them: a blank or space-only cell read back empty (review item 7).
        kept: list[dict[str, object]] = [dict(r.cells) for r in _table(reference, rows).rows]
        key = (reference.dataset_id, reference.name, reference.version)
        held = self.files.get(key)
        if held is not None and (held[0] != reference or held[1] != kept):
            raise StagingError(
                [f"the list {reference.name!r} (version {reference.version}) is already kept "
                 "with other rows; a version's rows are never replaced"]
            )  # fmt: skip
        self.files[key] = (reference, kept)
        return f"reference_lists/{reference.dataset_id}/{reference.name}@v{reference.version}"

    def read(self, reference: ReferenceList) -> list[dict[str, object]] | None:
        held = self.files.get((reference.dataset_id, reference.name, reference.version))
        if held is None:
            return None
        if held[0] != reference:
            raise StagingError([f"the rows kept for {reference.name!r} are another list's"])
        return [dict(r) for r in held[1]]

    def kept(self, dataset_id: str) -> list[ReferenceList]:
        newest: dict[str, ReferenceList] = {}
        for ref, _rows in self.files.values():
            if ref.dataset_id == dataset_id and (
                ref.id not in newest or newest[ref.id].version < ref.version
            ):
                newest[ref.id] = ref
        return sorted(newest.values(), key=lambda r: (r.name, r.id))


# --- rule 9, and reading the files ---------------------------------------------------------------


def _digests() -> set[str]:
    return synthetic_digests() | synthetic_digests(CONNECTOR_SYNTHETIC)


def admit_list(
    files: dict[str, bytes],
    *,
    template: str,
    dataset: str | None,
    use: str,
    known: Collection[str] | None = None,
    exceptions_path: Path | None = None,
) -> bool:
    """Whether the list is synthetic (`True`) or a real list this device admits (`False`); refused
    otherwise (rule 9). Synthetic means every file is one of the repository's own, by content."""
    known = _digests() if known is None else known
    if files and all(hashlib.sha256(c).hexdigest() in known for c in files.values()):
        return True
    if not dataset:
        raise ListConnectorRefused(
            "this is not one of OspreyFlow's synthetic lists, so it is real data and must name its "
            "dataset; nothing was kept (rule 9)"
        )
    from scripts.real_data_exceptions import is_permitted

    permitted = (
        is_permitted(dataset, use)
        if exceptions_path is None
        else is_permitted(dataset, use, config_path=exceptions_path)
    )
    if not permitted:
        raise ListConnectorRefused(
            f"“{dataset}” is real data and is not in this device's real_data_exceptions.yaml for "
            f"{use.replace('_', ' ')}; nothing was kept (rule 9)"
        )
    unconfirmed = LICENCE_NOT_CONFIRMED.get(template)
    if unconfirmed is not None:
        raise ListConnectorRefused(
            f"this list's licence is not confirmed: {unconfirmed}. Until it is, only OspreyFlow's "
            "synthetic list may be read through this template; nothing was kept"
        )
    return False


def read_list_files(record: DeploymentList, root: Path | None = None) -> dict[str, bytes]:
    """The list's file, and for OFAC its companions, read from inside the ingest folder only, by
    ADR-133's own reader (`screening_refresh.read_files`, review item 14); a location outside it is
    refused in words that do not say whether anything is there. A blank template's list is one
    file, read through the same location check."""
    try:
        if record.template != "blank":
            status = ScreeningListStatus(
                list_name=record.name, source=record.template, location=record.location,
                synthetic=record.synthetic, licence=record.licence,
            )  # fmt: skip
            return read_files(status, root)
        main = check_location(record.location, root)
        if not main.is_file():
            raise ListRefused(f"there is no file at {record.location} in the ingest folder")
        return {"main": main.read_bytes()}
    except ListRefused as refused:
        raise ListConnectorRefused(str(refused)) from refused


def check_list_location(location: str, root: Path | None = None) -> None:
    try:
        check_location(location, root)
    except ListRefused as refused:
        raise ListConnectorRefused(str(refused)) from refused


# --- an import -----------------------------------------------------------------------------------


def rows_digest(rows: Sequence[dict[str, object]]) -> str:
    """The rows' identity: equal rows, in any order, give one digest (a version is its rows). Each
    cell is taken as the keeper keeps it (`staging_catalogue._text`: a blank cell is empty), so a
    file and the version kept from it agree (review item 7)."""
    canonical = sorted(
        json.dumps({k: _text(v) for k, v in r.items()}, sort_keys=True, ensure_ascii=False)
        for r in rows
    )
    return hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()


def deployment_reference(record: DeploymentList, version: int | None = None) -> ReferenceList:
    """The list's record as the staging catalogue reads it: deployment-wide, a screening list keyed
    on the publisher's reference, at `version` (its current one by default)."""
    # Not its schedule: a version's record is what its rows are, and a schedule set after a version
    # was kept must not make that version read as another list's (review item 3).
    return ReferenceList(
        id=record.id, dataset_id=DEPLOYMENT_WIDE, name=record.name, kind="screening",
        key_column="ref", version=version if version is not None else record.version,
    )  # fmt: skip


def _diff(
    before: Sequence[dict[str, object]], after: Sequence[dict[str, object]]
) -> tuple[int, int, int]:
    was = {str(r["ref"]): r for r in before}
    now = {str(r["ref"]): r for r in after}
    added = sum(1 for k in now if k not in was)
    changed = sum(1 for k in now if k in was and was[k] != now[k])
    delisted = sum(1 for k in was if k not in now)
    return added, changed, delisted


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


async def import_list(
    list_id: str,
    *,
    store: ListStore,
    rows_kept: ListRows,
    trigger: str = "manual",
    root: Path | None = None,
    known: Collection[str] | None = None,
    now: datetime | None = None,
) -> ListImport:
    """Read the list through its template and keep it as a new version if its rows changed. Every
    attempt is recorded, in words; a refused or failed one keeps nothing."""
    at = now or datetime.now(UTC)
    held = await store.held(list_id)
    record = held.record

    async def done(
        outcome: ListImportOutcome, words: str, *, failure: bool = False, **counts: int | None
    ) -> ListImport:
        result = ListImport(
            list_id=list_id,
            outcome=outcome,
            trigger=trigger,  # type: ignore[arg-type]
            words=words,
            **counts,  # type: ignore[arg-type]
        )
        await store.record_import(result, at=at, failure=words if failure else None)
        return result

    try:
        files = read_list_files(record, root)
        admit_list(files, template=record.template, dataset=record.dataset, use=held.use,
                   known=known)  # fmt: skip
    except ListConnectorRefused as refused:
        return await done("refused", str(refused), failure=True)
    try:
        mapped = screening_rows(record.template, files, record.mapping)
    except TemplateRefused as refused:
        return await done("failed", str(refused), failure=True)
    digest = rows_digest(mapped.rows)
    if record.version and digest == held.digest:
        return await done(
            "unchanged",
            f"{record.name} is unchanged at version {record.version}: no new version was kept",
            version=record.version, previous_version=record.version,
        )  # fmt: skip
    # A version file an import kept but never applied (the process stopped between the two) was
    # never live, so no element names it: it is stepped over, never replaced (review item 16).
    kept = [r.version for r in rows_kept.kept(DEPLOYMENT_WIDE) if r.id == record.id]
    version = max([record.version, *kept]) + 1
    try:
        before = rows_kept.read(deployment_reference(record)) if record.version else []
        rows_kept.write(deployment_reference(record, version), mapped.rows)
    except StagingError as refused:
        return await done("failed", "; ".join(refused.problems), failure=True)
    if not await store.apply_version(
        list_id, previous=record.version, version=version, digest=digest,
        entries=len(mapped.rows), at=at,
    ):  # fmt: skip
        return await done(
            "failed",
            "another import of this list finished first; nothing of this one was kept",
            failure=True,
        )
    added, changed, delisted = _diff(before or [], mapped.rows)
    words = (
        f"{record.name} is now version {version}: "
        f"{_plural(len(mapped.rows), 'entry', 'entries')}; "
        f"{added} added, {changed} changed, {delisted} delisted"
    )
    if mapped.skipped:
        words += f"; {mapped.skipped} neither a person nor an organisation not read"
    return await done(
        "updated", words, version=version,
        previous_version=record.version or None, added=added, changed=changed, delisted=delisted,
    )  # fmt: skip


# --- what a dataset is offered -------------------------------------------------------------------


async def deployment_references(store: ListStore) -> list[ReferenceList]:
    """Every deployment-wide list with a version kept, as the staging catalogue reads it."""
    return [deployment_reference(r) for r in await store.lists() if r.version > 0]


async def subscribed_list_ids(store: ListStore, dataset_id: str) -> list[str]:
    """The deployment-wide lists `dataset_id` subscribes to, by id: the staging gate's and a run's
    `subscribed` (Amendment 12's seam)."""
    return await store.subscribed(dataset_id)


async def offered_lists(
    dataset_id: str, *, store: ListStore, own: Sequence[ReferenceList]
) -> list[OfferedList]:
    """The lists a dataset's rule or Lookup is offered: exactly those the save gate lets it read
    (`readable_lists`), its own and the deployment-wide lists it subscribes to. `own` is the
    dataset's lists as kept; anything else in it is never offered."""
    every = [*own, *await deployment_references(store)]
    readable, clashes = readable_lists(
        every, dataset_id=dataset_id, subscribed=await store.subscribed(dataset_id)
    )
    # A name two readable lists share is refused by the gate, so it is offered as neither (review
    # item 15).
    return sorted(
        (
            OfferedList(
                id=r.id,
                name=r.name,
                kind=r.kind,
                version=r.version,
                deployment_wide=r.dataset_id == DEPLOYMENT_WIDE,
            )  # fmt: skip
            for r in readable.values()
            if r.name not in clashes
        ),
        key=lambda o: (o.deployment_wide, o.name.lower()),
    )


# --- a dataset's own list ------------------------------------------------------------------------


def import_own_list(
    dataset_id: str,
    list_id: str,
    csv_bytes: bytes,
    *,
    rows_kept: ListRows,
    named: Collection[str],
    name: str | None = None,
    key_column: str | None = None,
) -> tuple[ReferenceList, ListImportOutcome]:
    """A dataset's own reference list's rows, from one of its own files, kept as a new version at
    Amendment 12's path when they differ from the highest version kept. The list must be one the
    dataset's live domain model names (`named`); its record is the highest kept file's, or, for its
    first import, the name and key given."""
    import csv
    import io

    if list_id not in named:
        raise ListConnectorRefused(
            "the dataset's live domain model names no list of that id; add it to the model first"
        )
    kept = {r.id: r for r in rows_kept.kept(dataset_id)}
    latest = kept.get(list_id)
    if latest is None and not (name and key_column):
        raise ListConnectorRefused("a list's first import needs its name and its key column")
    try:
        if len(csv_bytes) > reads.MAX_BYTES:
            raise ListConnectorRefused(
                f"the file is more than {reads.MAX_BYTES} bytes, more than one import may take; "
                "nothing was kept (rule 2)"
            )
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ListConnectorRefused("the file is not UTF-8 text; nothing was kept") from exc
    rows: list[dict[str, object]] = [dict(r) for r in csv.DictReader(io.StringIO(text))]
    if len(rows) > reads.MAX_ROWS:
        raise ListConnectorRefused(
            f"the file holds more than {reads.MAX_ROWS} rows, more than one import may take; "
            "nothing was kept (rule 2)"
        )
    base = latest or ReferenceList(
        id=list_id, dataset_id=dataset_id, name=name or "", kind="reference",
        key_column=key_column or "", version=1,
    )  # fmt: skip
    if latest is not None:
        before = rows_kept.read(latest) or []
        if rows_digest(before) == rows_digest(rows):
            return latest, "unchanged"
        base = latest.model_copy(update={"version": latest.version + 1})
    try:
        rows_kept.write(base, rows)
    except StagingError as refused:
        raise ListConnectorRefused("; ".join(refused.problems)) from refused
    return base, "updated"


# --- the schedule --------------------------------------------------------------------------------


@dataclass
class DeploymentListScheduler:
    """Each scheduled list's due slot, once: claimed in Valkey, then marked on the list; after
    downtime only the latest slot runs; run as the person who set it, who must still be allowed."""

    store: ListStore
    claim: Callable[[str], Awaitable[bool]]
    may_run: Callable[[str], Awaitable[str | None]]
    #: The import, run as the schedule's owner (given by id, for the audit).
    run: Callable[[str, str], Awaitable[ListImport]]
    seen: list[str] = field(default_factory=list)

    async def tick(self, now: datetime) -> None:
        for scheduled in await self.store.scheduled():
            try:
                await self._consider(scheduled, now)
            except Exception:  # noqa: BLE001 - one list's trouble never stops the others
                log.exception("the schedule of list %s could not be judged", scheduled.list_id)

    async def _consider(self, scheduled: ScheduledDeploymentList, now: datetime) -> None:
        after = scheduled.last_slot or scheduled.set_at
        slots = due_slots(cron_of(scheduled.schedule), DEFAULT_TIMEZONE, after=after, until=now)
        if not slots:
            return
        latest = slots[-1]
        if not await self.claim(f"lists:claim:{scheduled.list_id}:{latest.isoformat()}"):
            return
        if not await self.store.mark_slot(scheduled.list_id, latest):
            return
        refused = await self.may_run(scheduled.owner)
        if refused is not None:
            await self.store.record_import(
                ListImport(list_id=scheduled.list_id, outcome="refused", trigger="schedule",
                           words=f"the scheduled refresh was refused: {refused}"),
                at=now, failure=f"the scheduled refresh was refused: {refused}",
            )  # fmt: skip
            return
        self.seen.append(scheduled.list_id)
        await self.run(scheduled.list_id, scheduled.owner)
