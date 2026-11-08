"""A dataset's domain model, versioned (ADR-140 decisions 4 and 5, R12; `TargetModel`,
`01_DOMAIN_MODEL.md` §2.2b). Called the *domain model* on every screen (ADR-140 Amendment 9
decision 1).

**The rules, the store's own** (each a function below, so its test can remove it alone):

- Exactly one version is `live`, at most one is a `draft` (N+1, opened by the first edit), and every
  earlier one is `previous` and read-only. A second draft is refused in words
  (`_refuse_a_second_draft`); on Postgres a partial unique index holds both rules too.
- A draft opens as a copy of the live version (version 1, the POLE core alone, for a dataset with
  none). Editing it changes nothing that runs: only *Make live* does, and it names the draft
  version it was shown, so a draft changed since is refused (`_refuse_a_stale_make_live`).
- **An extension is retired, never deleted** (`_refuse_a_deleted_extension`): every extension of
  the live version is still in the draft, retired or not, and as it was but for its retirement. A
  new one is added in the draft's own version. A revert keeps an extension the reverted-to version
  never had, retired; one it had is in force again, as it was then.
- **A POLE core type cannot be an extension** (`_refuse_a_core_type`): the core is always on and
  cannot be removed or renamed.
- **A revert is a new draft, never a rewrite**: reverting to version N while N+1 is live makes the
  draft N+2, a copy of N (`reverted_from = N`); N itself is untouched.

Which pipelines a change affects, and pausing them, is `model_impact.py`'s; the routes are the
dataset's own (`/v1/datasets/{dataset_id}/model`), behind its gate and `edit_target_model` (ADR-112
Amendment 6).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg

from schemas.dataset_model import ModelExtension, TargetModel, TargetModelDraftInput
from schemas.domain import Principal

#: The POLE core's entity and link types as the default ontology loads them, for the tests; the
#: Conduit passes its own loaded core (`core_types_of`).
CORE_TYPES_FOR_TESTS = frozenset(
    {"Person", "Endpoint", "Device", "Location", "Organisation", "Event", "Document", "Vehicle",
     "Asset", "Alert", "COMMUNICATED_WITH", "USES", "PRESENT_AT", "MENTIONED_IN", "ALERTED_ON",
     "HOLDS", "DEPICTS", "VERIFIED_BY"}
)  # fmt: skip


class TargetModelRefused(Exception):
    """A change to a dataset's model refused, in words; nothing is written."""


class NoModelYet(TargetModelRefused):
    """A dataset with no model stored yet (one `scripts.seed_target_models` has not reached, or a
    new one whose first draft is not made live)."""

    def __init__(self) -> None:
        super().__init__("this dataset has no domain model yet: open a draft to make its first")


def core_types_of(entity_types: Iterable[str], edge_types: Iterable[str]) -> frozenset[str]:
    """The core's types, from the default ontology (which composes no pack)."""
    return frozenset({*entity_types, *edge_types})


class _ChosenOf(Protocol):
    async def chosen_of_case(self, investigation_id: str) -> list[Any]: ...


async def packs_of_case(
    investigation_id: str, datasets: _ChosenOf, models: TargetModelStore
) -> list[str] | None:
    """A case's packs, derived (ADR-126 Amendment 2): its chosen dataset's live model's (a
    composite's own). `None` while that dataset has no model yet (one `scripts.seed_target_models`
    has not reached, ADR-126 Amendment 3), when the case's stored packs still stand."""
    chosen = await datasets.chosen_of_case(investigation_id)
    if not chosen:
        return None
    live = await models.live(chosen[0].id)
    return sorted(live.packs) if live is not None else None


# --- the rules ----------------------------------------------------------------------------------


def _refuse_a_second_draft(draft: TargetModel | None) -> None:
    if draft is not None:
        raise TargetModelRefused(
            f"this dataset already has a draft, version {draft.version}: save or discard it first"
        )


def _refuse_a_stale_make_live(draft: TargetModel | None, version: int) -> None:
    if draft is None:
        raise TargetModelRefused("there is no draft to make live")
    if draft.version != version:
        raise TargetModelRefused(
            f"the draft is version {draft.version}, not {version}: it changed since it was "
            "opened, so read it again before making it live"
        )


def _refuse_a_core_type(extensions: Sequence[ModelExtension], core: frozenset[str]) -> None:
    for extension in extensions:
        if extension.name in core:
            raise TargetModelRefused(
                f"{extension.name} is a POLE core type: the core is always on and cannot be "
                "extended, removed or renamed"
            )


def _refuse_a_deleted_extension(
    live: TargetModel | None, extensions: Sequence[ModelExtension], version: int
) -> None:
    """Every live extension is still there, the same but for its retirement; a new one is added
    in this draft's own version."""
    held = {e.name: e for e in (live.extensions if live is not None else [])}
    given = {e.name: e for e in extensions}
    if gone := sorted(set(held) - set(given)):
        raise TargetModelRefused(
            "an extension is retired, never deleted: retire "
            + ", ".join(gone)
            + " instead of removing it"
        )
    for name, extension in given.items():
        before = held.get(name)
        if before is None:
            if extension.added_in != version or extension.retired_in is not None:
                raise TargetModelRefused(
                    f"{name} is new, so it is added in this draft, version {version}, and not "
                    "retired"
                )
        elif extension.model_copy(update={"retired_in": before.retired_in}) != before:
            raise TargetModelRefused(
                f"{name} cannot be changed, only retired: add a new extension and retire this one"
            )
        elif extension.retired_in not in (None, before.retired_in, version):
            # Retired in this draft, kept as retired, or in force again (a revert to a version
            # that had it is a draft like any other).
            raise TargetModelRefused(f"{name} is retired in this draft, version {version}")


def _checked(
    live: TargetModel | None,
    draft: TargetModel,
    given: TargetModelDraftInput,
    core: frozenset[str],
) -> None:
    _refuse_a_core_type(given.extensions, core)
    _refuse_a_deleted_extension(live, given.extensions, draft.version)


def _reverted(
    to: TargetModel, live: TargetModel, version: int, principal: Principal, now: datetime
) -> TargetModel:
    """Version `to` again as draft `version`, keeping every later extension retired."""
    kept = {e.name for e in to.extensions}
    later = [
        e if e.retired_in is not None else e.model_copy(update={"retired_in": version})
        for e in live.extensions
        if e.name not in kept
    ]
    return TargetModel(
        dataset_id=to.dataset_id, version=version, state="draft", packs=dict(to.packs),
        extensions=[*to.extensions, *later], reference_lists=list(to.reference_lists),
        created_at=now, created_by=principal.id, reverted_from=to.version,
    )  # fmt: skip


class TargetModelStore(Protocol):
    async def live(self, dataset_id: str) -> TargetModel | None: ...
    async def draft(self, dataset_id: str) -> TargetModel | None: ...
    async def versions(self, dataset_id: str) -> list[TargetModel]: ...
    async def open_draft(self, dataset_id: str, principal: Principal) -> TargetModel: ...
    async def save_draft(
        self, dataset_id: str, given: TargetModelDraftInput, principal: Principal
    ) -> TargetModel: ...
    async def discard_draft(self, dataset_id: str) -> None: ...
    async def make_live(
        self, dataset_id: str, version: int, principal: Principal
    ) -> tuple[TargetModel, TargetModel | None]: ...
    async def revert(
        self, dataset_id: str, to_version: int, principal: Principal
    ) -> TargetModel: ...


def _first_or_copy(dataset_id: str, live: TargetModel | None, principal: Principal) -> TargetModel:
    now = datetime.now(UTC)
    if live is None:
        return TargetModel(
            dataset_id=dataset_id, version=1, state="draft", created_at=now, created_by=principal.id
        )
    return live.model_copy(
        update={"version": live.version + 1, "state": "draft", "created_at": now,
                "created_by": principal.id, "made_live_at": None, "made_live_by": None,
                "reverted_from": None}
    )  # fmt: skip


class InMemoryTargetModelStore:
    """The same rules with no Postgres, for tests and a process without one."""

    def __init__(self, *, core_types: frozenset[str]) -> None:
        self._core = core_types
        self._held: dict[str, list[TargetModel]] = {}

    def _of(self, dataset_id: str) -> list[TargetModel]:
        return self._held.setdefault(dataset_id, [])

    def _in(self, dataset_id: str, state: str) -> TargetModel | None:
        return next((m for m in self._of(dataset_id) if m.state == state), None)

    async def live(self, dataset_id: str) -> TargetModel | None:
        return self._in(dataset_id, "live")

    async def draft(self, dataset_id: str) -> TargetModel | None:
        return self._in(dataset_id, "draft")

    async def versions(self, dataset_id: str) -> list[TargetModel]:
        return sorted(self._of(dataset_id), key=lambda m: m.version)

    async def open_draft(self, dataset_id: str, principal: Principal) -> TargetModel:
        _refuse_a_second_draft(await self.draft(dataset_id))
        made = _first_or_copy(dataset_id, await self.live(dataset_id), principal)
        self._of(dataset_id).append(made)
        return made

    async def save_draft(
        self, dataset_id: str, given: TargetModelDraftInput, principal: Principal
    ) -> TargetModel:
        draft = await self.draft(dataset_id)
        if draft is None:
            raise TargetModelRefused("there is no draft to save: open one first")
        _checked(await self.live(dataset_id), draft, given, self._core)
        saved = draft.model_copy(update=_fields_of(given))
        held = self._of(dataset_id)
        held[held.index(draft)] = saved
        return saved

    async def discard_draft(self, dataset_id: str) -> None:
        draft = await self.draft(dataset_id)
        if draft is None:
            raise TargetModelRefused("there is no draft to discard")
        self._of(dataset_id).remove(draft)

    async def make_live(
        self, dataset_id: str, version: int, principal: Principal
    ) -> tuple[TargetModel, TargetModel | None]:
        draft = await self.draft(dataset_id)
        _refuse_a_stale_make_live(draft, version)
        assert draft is not None
        held = self._of(dataset_id)
        before = await self.live(dataset_id)
        if before is not None:
            before = before.model_copy(update={"state": "previous"})
            held[next(i for i, m in enumerate(held) if m.state == "live")] = before
        live = draft.model_copy(
            update={"state": "live", "made_live_at": datetime.now(UTC),
                    "made_live_by": principal.id}
        )  # fmt: skip
        held[held.index(draft)] = live
        return live, before

    async def revert(self, dataset_id: str, to_version: int, principal: Principal) -> TargetModel:
        _refuse_a_second_draft(await self.draft(dataset_id))
        live = await self.live(dataset_id)
        to = next((m for m in self._of(dataset_id) if m.version == to_version), None)
        if live is None or to is None or to.state != "previous":
            raise TargetModelRefused(f"there is no earlier version {to_version} to revert to")
        made = _reverted(to, live, live.version + 1, principal, datetime.now(UTC))
        self._of(dataset_id).append(made)
        return made


# --- Postgres -----------------------------------------------------------------------------------

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS target_models (
    dataset_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('draft', 'live', 'previous')),
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    made_live_at TIMESTAMPTZ,
    made_live_by TEXT,
    reverted_from INTEGER,
    PRIMARY KEY (dataset_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS target_models_one_live
    ON target_models (dataset_id) WHERE state = 'live';
CREATE UNIQUE INDEX IF NOT EXISTS target_models_one_draft
    ON target_models (dataset_id) WHERE state = 'draft';
"""

_COLUMNS = (
    "dataset_id, version, state, content, created_at, created_by, made_live_at, made_live_by, "
    "reverted_from"
)


def _row(row: Any) -> TargetModel:
    content = row["content"]
    content = json.loads(content) if isinstance(content, str) else content
    return TargetModel(
        dataset_id=row["dataset_id"], version=row["version"], state=row["state"],
        packs=content.get("packs", {}), extensions=content.get("extensions", []),
        reference_lists=content.get("reference_lists", []), created_at=row["created_at"],
        created_by=row["created_by"], made_live_at=row["made_live_at"],
        made_live_by=row["made_live_by"], reverted_from=row["reverted_from"],
    )  # fmt: skip


def _fields_of(given: TargetModelDraftInput) -> dict[str, Any]:
    """The draft's edited fields, as models, for `model_copy` (which validates nothing)."""
    return {
        "packs": dict(given.packs),
        "extensions": list(given.extensions),
        "reference_lists": list(given.reference_lists),
    }


def _content(model: TargetModel | TargetModelDraftInput) -> str:
    return json.dumps(
        model.model_dump(mode="json", include={"packs", "extensions", "reference_lists"})
    )


class PostgresTargetModelStore:
    """The rules above, each change in one transaction holding the dataset's rows, and the one-live
    and one-draft indexes behind them, so two requests at once cannot both win."""

    def __init__(self, pool: asyncpg.Pool, *, core_types: frozenset[str]) -> None:
        self._pool = pool
        self._core = core_types

    @classmethod
    async def connect(cls, dsn: str, *, core_types: frozenset[str]) -> PostgresTargetModelStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool, core_types=core_types)

    async def close(self) -> None:
        await self._pool.close()

    async def _in(self, conn: Any, dataset_id: str, state: str) -> TargetModel | None:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM target_models WHERE dataset_id = $1 AND state = $2",
            dataset_id,
            state,
        )
        return _row(row) if row is not None else None

    async def _locked(self, conn: Any, dataset_id: str) -> None:
        """Serialises changes to one dataset's model: a transaction-scoped advisory lock."""
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('target_models:' || $1))", dataset_id
        )

    async def live(self, dataset_id: str) -> TargetModel | None:
        async with self._pool.acquire() as conn:
            return await self._in(conn, dataset_id, "live")

    async def draft(self, dataset_id: str) -> TargetModel | None:
        async with self._pool.acquire() as conn:
            return await self._in(conn, dataset_id, "draft")

    async def versions(self, dataset_id: str) -> list[TargetModel]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM target_models WHERE dataset_id = $1 ORDER BY version",
                dataset_id,
            )
        return [_row(r) for r in rows]

    async def _insert(self, conn: Any, model: TargetModel) -> None:
        await conn.execute(
            f"INSERT INTO target_models ({_COLUMNS}) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, "
            "$8, $9)",
            model.dataset_id, model.version, model.state, _content(model), model.created_at,
            model.created_by, model.made_live_at, model.made_live_by, model.reverted_from,
        )  # fmt: skip

    async def open_draft(self, dataset_id: str, principal: Principal) -> TargetModel:
        async with self._pool.acquire() as conn, conn.transaction():
            await self._locked(conn, dataset_id)
            _refuse_a_second_draft(await self._in(conn, dataset_id, "draft"))
            made = _first_or_copy(dataset_id, await self._in(conn, dataset_id, "live"), principal)
            await self._insert(conn, made)
        return made

    async def save_draft(
        self, dataset_id: str, given: TargetModelDraftInput, principal: Principal
    ) -> TargetModel:
        async with self._pool.acquire() as conn, conn.transaction():
            await self._locked(conn, dataset_id)
            draft = await self._in(conn, dataset_id, "draft")
            if draft is None:
                raise TargetModelRefused("there is no draft to save: open one first")
            _checked(await self._in(conn, dataset_id, "live"), draft, given, self._core)
            await conn.execute(
                "UPDATE target_models SET content = $3::jsonb "
                "WHERE dataset_id = $1 AND version = $2 AND state = 'draft'",
                dataset_id,
                draft.version,
                _content(given),
            )
        return draft.model_copy(update=_fields_of(given))

    async def discard_draft(self, dataset_id: str) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await self._locked(conn, dataset_id)
            gone = await conn.fetchval(
                "DELETE FROM target_models WHERE dataset_id = $1 AND state = 'draft' "
                "RETURNING version",
                dataset_id,
            )
        if gone is None:
            raise TargetModelRefused("there is no draft to discard")

    async def make_live(
        self, dataset_id: str, version: int, principal: Principal
    ) -> tuple[TargetModel, TargetModel | None]:
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await self._locked(conn, dataset_id)
            draft = await self._in(conn, dataset_id, "draft")
            _refuse_a_stale_make_live(draft, version)
            assert draft is not None
            before = await self._in(conn, dataset_id, "live")
            await conn.execute(
                "UPDATE target_models SET state = 'previous' "
                "WHERE dataset_id = $1 AND state = 'live'",
                dataset_id,
            )
            await conn.execute(
                "UPDATE target_models SET state = 'live', made_live_at = $3, made_live_by = $4 "
                "WHERE dataset_id = $1 AND version = $2",
                dataset_id,
                version,
                now,
                principal.id,
            )
        live = draft.model_copy(
            update={"state": "live", "made_live_at": now, "made_live_by": principal.id}
        )
        return live, (before.model_copy(update={"state": "previous"}) if before else None)

    async def revert(self, dataset_id: str, to_version: int, principal: Principal) -> TargetModel:
        async with self._pool.acquire() as conn, conn.transaction():
            await self._locked(conn, dataset_id)
            _refuse_a_second_draft(await self._in(conn, dataset_id, "draft"))
            live = await self._in(conn, dataset_id, "live")
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM target_models WHERE dataset_id = $1 AND version = $2",
                dataset_id,
                to_version,
            )
            to = _row(row) if row is not None else None
            if live is None or to is None or to.state != "previous":
                raise TargetModelRefused(f"there is no earlier version {to_version} to revert to")
            made = _reverted(to, live, live.version + 1, principal, datetime.now(UTC))
            await self._insert(conn, made)
        return made
