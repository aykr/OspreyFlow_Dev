"""The `studio_recipes` registry — `spec/09_INGEST_STUDIO.md` §6's "recipe
registry, and how 'flags the affected recipes' actually happens" section.

Connect (Phase 5a) is the first stage to need this table: a draft spans
sessions and sometimes people (§6: "a draft is a row, not client state"), so
it has to be a Postgres row from the moment Connect creates it, not Glass-side
state. Persisted the same way `services/api/sites.py`'s `SiteStore` persists
site metadata — the same Postgres instance the Conduit's audit stream already
uses, idempotent bootstrap SQL, no migration framework.

Publish (this module's other half, alongside Connect/Map's own methods
above it) adds four things: `publish` itself (draft → published, requires a
prior successful verify), `update_schedule` (§8's "schedule it", kept
separate from `publish` so changing *when* a recipe runs never requires
re-verifying a mapping that hasn't changed), `create_new_version` (reopening
a published recipe for a further edit — the previous version is flipped to
`superseded`, never overwritten in place, so `load_id`/`recipe_version`
attribution on already-loaded elements keeps meaning what it said), and
`flag_stale` — the reverse index `§6`'s opening paragraph promises: "an
ontology edit flags every recipe that depends on the changed version." It is
deliberately not a separate index structure; `status='published'` with an
`ontology_version` other than the current one, or a pinned pack (`pack_versions`,
ADR-120 D10) at another version than the one loaded, over this same table already
answers "which recipes does this ontology version affect" in one statement, and
`create_new_version`'s own supersede step is what keeps that `WHERE
status='published'` scan meaning "the one live version of this recipe", not
every version that was ever published.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import asyncpg
import yaml
from services.ingest.pipeline import recipe_packs
from services.ingest.recipe_loader import load_recipe

from conduit_common.identity import new_id
from schemas.domain import OntologySchema, Principal
from schemas.ingest import (
    PipelineGraph,
    Recipe,
    RowTemplate,
    StudioRecipeDraft,
    StudioRecipeStatus,
    UnmappedField,
    check_source_declarations,
)

from .dataset_scope import made_in, reach_clause

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS studio_recipes (
    recipe_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    ontology_version INTEGER,
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    content TEXT NOT NULL,
    git_path TEXT,
    owning_unit TEXT NOT NULL,
    created_by TEXT NOT NULL,
    published_by TEXT,
    schedule_cron TEXT,
    schedule_watch TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    PRIMARY KEY (recipe_id, version)
);
-- ADR-099 Amendment 3: the dataset a recipe belongs to; none for one made before it.
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS dataset_id TEXT;
-- ADR-110: whose schedule it is, in which zone, since when, and whether it is paused.
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS schedule_timezone TEXT;
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS schedule_owner TEXT;
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS schedule_set_at TIMESTAMPTZ;
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS schedule_case TEXT;
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS schedule_paused BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS schedule_paused_reason TEXT;
-- ADR-120 D10, Amendment 1: the pack versions it was published against; NULL until published
-- (and for one published before pinning, until the start-up backfill stamps it).
ALTER TABLE studio_recipes ADD COLUMN IF NOT EXISTS pack_versions JSONB;
"""

#: ADR-120 Amendment 1, decision 4: the versions the packs stood at when pinning began, which is
#: what a recipe published before it was written against. Stamped by `backfill_pack_versions` and
#: never changed, so a later bump reads as a bump.
LEGACY_PACK_VERSIONS: dict[str, int] = {"niem": 2, "fibo": 1, "stix": 1}


class StudioRecipeNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the recipe exists but
    `principal.org_unit` does not match `owning_unit`: the same
    existence-leak discipline `SiteNotFoundError` (`services/api/sites.py`)
    already applies."""


class StudioRecipeNotADraftError(Exception):
    """Raised by `update_draft`/`update_row_template`/`publish` against a
    recipe whose `status` has already moved past `draft` — Connect and Map
    only ever edit a draft in place; a published/flagged/superseded row is
    immutable from here. Reopening one for further editing is
    `create_new_version`'s job, not a relaxed guard here."""


class StudioRecipeNotVerifiedError(Exception):
    """Raised by `publish` against a draft whose `verified_at` is unset —
    `09_INGEST_STUDIO.md` §5: "Verify must pass before publish. Not 'verify
    is recommended'." A run with rejections still sets `verified_at` (§5:
    "A run with rejections can be published") — this guards against
    publishing a mapping nobody has ever dry-run at all, or one edited
    since its last dry run (`update_draft`/`update_row_template` both clear
    the flag), not against rejections themselves."""


class StudioRecipeCannotVersionError(Exception):
    """Raised by `create_new_version` against a recipe whose latest version
    is not `published`/`flagged` — there is nothing to "reopen": a `draft`
    is already open, and a `superseded` version is a dead end by
    definition (its own successor already exists)."""


def _content_json(draft: StudioRecipeDraft, **overrides: object) -> str:
    """The draft's one content document, every sibling field carried — the rule `update_draft`'s
    row-template comment states, now in one place so no writer can forget a field (ADR-108 phase B:
    the first dropped-sibling was nearly `pipeline`)."""
    whole: dict[str, object] = {
        "connector_profile": draft.connector_profile,
        "source_location": draft.source_location,
        "handling": draft.handling,
        "legal_basis": draft.legal_basis,
        "row_template": draft.row_template.model_dump(by_alias=True)
        if draft.row_template is not None
        else None,
        "unmapped_fields": [f.model_dump() for f in draft.unmapped_fields],
        "pipeline": draft.pipeline.model_dump(by_alias=True) if draft.pipeline else None,
    }
    whole.update(overrides)
    return json.dumps(whole)


def _pins_from_column(raw: object) -> dict[str, int] | None:
    """The `pack_versions` column as a map: asyncpg hands JSONB back as text unless a codec is
    set, and this pool sets none, as `content` above is read the same way. A value that is not a
    JSON object (a `null`, a scalar, an array), or whose versions are not integers, is no pins at
    all, exactly as SQL NULL (ADR-120 Amendment 3, decision 1; an object of that kind is flagged
    by `flag_stale`, not re-stamped): nothing that reads the column can
    be stopped by it."""
    if raw is None:
        return None
    decoded = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(decoded, dict):
        return None
    pins: dict[str, int] = {}
    for pack, version in decoded.items():
        # A whole number only, as `flag_stale`'s `p.v::text ~ '^[0-9]+$'` reads it: not a bool, a
        # float (a JSON `1.0`), a string or a negative.
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            return None
        pins[str(pack)] = version
    return pins


def _row_to_draft(row: asyncpg.Record) -> StudioRecipeDraft:
    data = dict(row)
    content = json.loads(data.pop("content"))
    row_template = content.get("row_template")
    # `ready_for_profile` is computed by `StudioRecipeDraft`'s own
    # `model_validator(mode="before")`, never accepted as a caller-supplied
    # value (`schemas/ingest.py`'s own doc comment on the field) — mypy
    # cannot see that a "before" validator supplies a field the `__init__`
    # signature otherwise requires, hence the ignore, matching every other
    # direct construction of this model in this codebase (e.g. `tests/
    # services/api/test_studio_recipe_routes.py`'s own fake store).
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=data["recipe_id"],
        version=data["version"],
        status=StudioRecipeStatus(data["status"]),
        label=data["label"],
        connector_profile=content.get("connector_profile"),
        source_location=content.get("source_location"),
        handling=content.get("handling", {}),
        legal_basis=content.get("legal_basis"),
        owning_unit=data["owning_unit"],
        created_by=data["created_by"],
        created_at=data["created_at"],
        row_template=RowTemplate.model_validate(row_template) if row_template else None,
        unmapped_fields=[
            UnmappedField.model_validate(f) for f in content.get("unmapped_fields", [])
        ],
        pipeline=PipelineGraph.model_validate(content["pipeline"])
        if content.get("pipeline")
        else None,
        verified_at=data["verified_at"],
        ontology_version=data["ontology_version"],
        pack_versions=_pins_from_column(data.get("pack_versions")),
        git_path=data["git_path"],
        published_by=data["published_by"],
        published_at=data["published_at"],
        schedule_cron=data["schedule_cron"],
        schedule_watch=data["schedule_watch"],
        schedule_timezone=data.get("schedule_timezone"),
        schedule_owner=data.get("schedule_owner"),
        schedule_set_at=data.get("schedule_set_at"),
        schedule_case=data.get("schedule_case"),
        schedule_paused=bool(data.get("schedule_paused") or False),
        schedule_paused_reason=data.get("schedule_paused_reason"),
        dataset_id=data.get("dataset_id"),
    )


_SOURCE_DECLARATIONS = ("units", "handling_columns")


class SourceDeclarationsInvalidError(ValueError):
    """The handling a draft would hold after a PATCH declares what the source cannot support: a
    unit column with no units, or malformed `units` or `handling_columns` (ADR-127 decision 3)."""


def carry_source_declarations(
    old: dict[str, object], new: dict[str, object] | None
) -> dict[str, object] | None:
    """A new handling replaces the old whole, and what the source declares beside its marking
    (ADR-127 decision 3: the `units` its rows may name, the `handling_columns` that carry each
    part) rides inside it: a handling that does not mention one keeps the draft's own, so editing
    the marking in Connect does not silently drop them. An explicit empty value clears it."""
    if new is None:
        return new
    carried = {k: old[k] for k in _SOURCE_DECLARATIONS if k in old and k not in new}
    merged = {**new, **carried} if carried else new
    # What was kept is judged as Connect judges a handling: a unit column needs the units a PATCH
    # may have just emptied. Refused here, before `update_draft` writes anything.
    try:
        check_source_declarations(dict(merged))
    except ValueError as exc:
        raise SourceDeclarationsInvalidError(str(exc)) from exc
    return merged


class StudioRecipeStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> StudioRecipeStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create_draft(
        self,
        principal: Principal,
        *,
        label: str,
        connector_profile: str,
        source_location: str | None,
        handling: dict[str, object],
        legal_basis: str | None,
    ) -> StudioRecipeDraft:
        recipe_id = new_id()
        content = json.dumps(
            {
                "connector_profile": connector_profile,
                "source_location": source_location,
                "handling": handling,
                "legal_basis": legal_basis,
            }
        )
        created_at = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO studio_recipes (recipe_id, version, label, status, content, "
                "owning_unit, created_by, created_at, dataset_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                recipe_id,
                1,
                label,
                StudioRecipeStatus.DRAFT.value,
                content,
                principal.org_unit,
                principal.id,
                created_at,
                made_in(principal),
            )
        return await self.get(recipe_id)

    async def get(self, recipe_id: str) -> StudioRecipeDraft:
        """No authorization check here — the raw record lookup, exactly
        like `SiteStore.get`. `get_authorized` below is what every route
        actually calls."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                # A recipe id may have more than one version once Publish
                # (via `create_new_version`) reopens a published recipe for
                # a further edit — the highest version is always the
                # current one, since `create_new_version` flips the
                # previous version to `superseded` rather than leaving two
                # rows both claiming to be current.
                "SELECT * FROM studio_recipes WHERE recipe_id = $1 ORDER BY version DESC LIMIT 1",
                recipe_id,
            )
        if row is None:
            raise StudioRecipeNotFoundError(recipe_id)
        return _row_to_draft(row)

    async def get_authorized(self, recipe_id: str, principal: Principal) -> StudioRecipeDraft:
        """`owning_unit` filtered in the query itself, not after fetch — `06_DECISIONS.md`
        ADR-041's own fix, the same shape `review.py`'s `get_authorized`/`get_document_text` and
        `pattern_store.py`'s `get_authorized` already use. A hazard, not a leak, before this fix:
        the Python-side check below it replaced correctly rejected a mismatched principal
        (checked directly — no caller of `get()` elsewhere bypasses it), it just pulled the full
        row into process memory first."""
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM studio_recipes WHERE recipe_id = $1 AND owning_unit = $2"
                f"{reach} ORDER BY version DESC LIMIT 1",
                recipe_id,
                principal.org_unit,
                *extra,
            )
        if row is None:
            raise StudioRecipeNotFoundError(recipe_id)
        return _row_to_draft(row)

    async def update_draft(
        self,
        recipe_id: str,
        principal: Principal,
        *,
        label: str | None = None,
        connector_profile: str | None = None,
        source_location: str | None = None,
        handling: dict[str, object] | None = None,
        legal_basis: str | None = None,
    ) -> StudioRecipeDraft:
        draft = await self.get_authorized(recipe_id, principal)
        if draft.status is not StudioRecipeStatus.DRAFT:
            raise StudioRecipeNotADraftError(recipe_id)
        content = _content_json(
            draft,
            **{
                k: v
                for k, v in {
                    "connector_profile": connector_profile,
                    "source_location": source_location,
                    "handling": carry_source_declarations(draft.handling, handling),
                    "legal_basis": legal_basis,
                }.items()
                if v is not None
            },
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET label = $1, content = $2, verified_at = NULL "
                "WHERE recipe_id = $3 AND version = $4",
                label if label is not None else draft.label,
                content,
                recipe_id,
                draft.version,
            )
        return await self.get(recipe_id)

    async def update_pipeline(
        self,
        recipe_id: str,
        principal: Principal,
        *,
        pipeline: PipelineGraph,
    ) -> StudioRecipeDraft:
        """The pipeline's own save (ADR-108 phase B) — draft-only, like every other edit; an edit
        clears `verified_at`, since what was dry-run is no longer what would run."""
        draft = await self.get_authorized(recipe_id, principal)
        if draft.status is not StudioRecipeStatus.DRAFT:
            raise StudioRecipeNotADraftError(recipe_id)
        content = _content_json(draft, pipeline=pipeline.model_dump(by_alias=True))
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET content = $1, verified_at = NULL "
                "WHERE recipe_id = $2 AND version = $3",
                content,
                recipe_id,
                draft.version,
            )
        return await self.get(recipe_id)

    async def update_row_template(
        self,
        recipe_id: str,
        principal: Principal,
        *,
        row_template: RowTemplate,
        unmapped_fields: list[UnmappedField],
    ) -> StudioRecipeDraft:
        """Map's own save (§4) — mirrors `update_draft` above (draft-only
        guard included) but touches only the row-template half of `content`,
        leaving Connect's own fields exactly as they were."""
        draft = await self.get_authorized(recipe_id, principal)
        if draft.status is not StudioRecipeStatus.DRAFT:
            raise StudioRecipeNotADraftError(recipe_id)
        content = _content_json(
            draft,
            row_template=row_template.model_dump(by_alias=True),
            unmapped_fields=[f.model_dump() for f in unmapped_fields],
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET content = $1, verified_at = NULL "
                "WHERE recipe_id = $2 AND version = $3",
                content,
                recipe_id,
                draft.version,
            )
        return await self.get(recipe_id)

    async def list_drafts(self, principal: Principal) -> list[StudioRecipeDraft]:
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM studio_recipes WHERE owning_unit = $1 AND status = $2"
                f"{reach} ORDER BY created_at DESC",
                principal.org_unit,
                StudioRecipeStatus.DRAFT.value,
                *extra,
            )
        return [_row_to_draft(row) for row in rows]

    async def list_all(self, principal: Principal) -> list[StudioRecipeDraft]:
        """Publish's own listing — every recipe the principal's unit owns,
        at whatever status, one row per `recipe_id` (its latest version
        only — an older `superseded` version is reachable only by
        `get`/`get_authorized` naming its own `recipe_id`, not by this
        list). `list_drafts` above stays draft-only for Connect's "resume a
        draft" list; this is the Publish screen's own broader view."""
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ON (recipe_id) * FROM studio_recipes "
                f"WHERE owning_unit = $1{reach} ORDER BY recipe_id, version DESC",
                principal.org_unit,
                *extra,
            )
        drafts = [_row_to_draft(row) for row in rows]
        drafts.sort(key=lambda d: d.created_at, reverse=True)
        return drafts

    async def mark_verified(self, recipe_id: str, version: int, *, now: datetime) -> None:
        """Called once by the Verify route after `run_verify` (`services/
        api/studio_verify.py`) completes without raising — never from here
        on the report's own rejection count, since §5 is explicit that a
        run with rejections still passes. `publish` below is the only
        thing that reads this."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET verified_at = $1 WHERE recipe_id = $2 AND version = $3",
                now,
                recipe_id,
                version,
            )

    async def publish(
        self,
        recipe_id: str,
        principal: Principal,
        *,
        ontology_version: int,
        pack_versions: dict[str, int],
        git_path: str,
        schedule_cron: str | None,
        schedule_watch: str | None,
        now: datetime,
        schedule_timezone: str | None = None,
        schedule_case: str | None = None,
    ) -> StudioRecipeDraft:
        """§6: draft → published. The caller (`services/api/app.py`'s
        publish route) has already serialised `content` to YAML and
        committed it at `git_path` by the time this is called — this
        method only flips the registry row, and is the single place that
        enforces "Verify must pass before publish" (§5) mechanically,
        against `verified_at` rather than by re-running a dry run here. `pack_versions` has no
        default and refuses `None` (ADR-120 Amendment 1, decision 5; Amendment 2, decision 3): a
        fresh publish can never store "not pinned" and be mistaken for a legacy row by the next
        start's backfill."""
        if pack_versions is None:
            raise ValueError("pack_versions is required to publish; pass {} for a recipe with none")
        draft = await self.get_authorized(recipe_id, principal)
        if draft.status is not StudioRecipeStatus.DRAFT:
            raise StudioRecipeNotADraftError(recipe_id)
        if draft.verified_at is None:
            raise StudioRecipeNotVerifiedError(recipe_id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET status = $1, ontology_version = $2, git_path = $3, "
                "published_by = $4, published_at = $5, schedule_cron = $6, schedule_watch = $7, "
                "schedule_timezone = $10, schedule_owner = $11, schedule_set_at = $12, "
                "schedule_case = $13, schedule_paused = FALSE, schedule_paused_reason = NULL, "
                "pack_versions = $14::jsonb "
                "WHERE recipe_id = $8 AND version = $9",
                StudioRecipeStatus.PUBLISHED.value,
                ontology_version,
                git_path,
                principal.id,
                now,
                schedule_cron,
                schedule_watch,
                recipe_id,
                draft.version,
                schedule_timezone,
                principal.id if (schedule_cron or schedule_watch) else None,
                now if (schedule_cron or schedule_watch) else None,
                schedule_case if (schedule_cron or schedule_watch) else None,
                json.dumps(pack_versions),
            )
        return await self.get(recipe_id)

    async def update_schedule(
        self,
        recipe_id: str,
        principal: Principal,
        *,
        schedule_cron: str | None,
        schedule_watch: str | None,
        schedule_timezone: str | None = None,
        now: datetime | None = None,
        schedule_case: str | None = None,
    ) -> StudioRecipeDraft:
        """§8: "schedule it" — a source approver action distinct from
        `publish`, so pausing or retiming a recipe's own schedule never
        requires touching its mapping or version. Allowed against
        `published` or `flagged` (pausing a flagged recipe's schedule
        while someone fixes the mapping is a real use of this, not an
        oversight) — never `draft` (nothing to schedule yet) or
        `superseded` (a dead version)."""
        draft = await self.get_authorized(recipe_id, principal)
        if draft.status not in (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED):
            raise StudioRecipeNotADraftError(recipe_id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                # ADR-110 decision 3: whoever sets the schedule becomes its owner; setting it
                # resumes it.
                "UPDATE studio_recipes SET schedule_cron = $1, schedule_watch = $2, "
                "schedule_timezone = $5, schedule_owner = $6, schedule_set_at = $7, "
                "schedule_case = $8, schedule_paused = FALSE, schedule_paused_reason = NULL "
                "WHERE recipe_id = $3 AND version = $4",
                schedule_cron,
                schedule_watch,
                recipe_id,
                draft.version,
                schedule_timezone,
                principal.id if (schedule_cron or schedule_watch) else None,
                (now or datetime.now(UTC)) if (schedule_cron or schedule_watch) else None,
                schedule_case if (schedule_cron or schedule_watch) else None,
            )
        return await self.get(recipe_id)

    async def scheduled(self) -> list[StudioRecipeDraft]:
        """Every recipe with a schedule, at its current version (published or flagged), paused or
        not — read by the scheduler (ADR-110 decision 2), a backend pass like the KYC sweep, so it
        takes no principal; what it does with each is judged as the schedule's owner."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM studio_recipes "
                "WHERE status = ANY($1::text[]) "
                "AND (schedule_cron IS NOT NULL OR schedule_watch IS NOT NULL) "
                "ORDER BY recipe_id",
                [StudioRecipeStatus.PUBLISHED.value, StudioRecipeStatus.FLAGGED.value],
            )
        return [_row_to_draft(r) for r in rows]

    async def feeding(self, dataset_ids: Sequence[str]) -> list[StudioRecipeDraft]:
        """The published (or flagged) recipes that load into any of `dataset_ids` — the pipelines
        feeding a case (ADR-110 decision 9), read through the case's own datasets."""
        if not dataset_ids:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM studio_recipes WHERE status = ANY($1::text[]) "
                "AND dataset_id = ANY($2::text[]) ORDER BY label, recipe_id",
                [StudioRecipeStatus.PUBLISHED.value, StudioRecipeStatus.FLAGGED.value],
                list(dataset_ids),
            )
        return [_row_to_draft(r) for r in rows]

    async def retime(self, recipe_id: str, *, cron: str, timezone: str, now: datetime) -> None:
        """A new time for an existing schedule (ADR-110 Amendment 3, point 2: the Admin area's
        *Change schedule*): the owner, the case and the paused state are kept; the time it was set
        moves to now, so slots before the change are not counted as missed."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET schedule_cron = $2, schedule_timezone = $3, "
                "schedule_set_at = $4 WHERE recipe_id = $1 AND status = ANY($5::text[]) "
                "AND (schedule_cron IS NOT NULL OR schedule_watch IS NOT NULL)",
                recipe_id,
                cron,
                timezone,
                now,
                [StudioRecipeStatus.PUBLISHED.value, StudioRecipeStatus.FLAGGED.value],
            )

    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None:
        """Pause (with the reason) or resume a schedule, at the recipe's current version."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE studio_recipes SET schedule_paused = $2, schedule_paused_reason = $3 "
                "WHERE recipe_id = $1 AND status = ANY($4::text[])",
                recipe_id,
                paused,
                reason if paused else None,
                [StudioRecipeStatus.PUBLISHED.value, StudioRecipeStatus.FLAGGED.value],
            )

    async def create_new_version(
        self, recipe_id: str, principal: Principal, *, now: datetime
    ) -> StudioRecipeDraft:
        """Reopens a published (or already-flagged) recipe for a further
        edit — §8's "approve a mapping that changes an existing recipe's
        semantics" starts here: this creates the new draft version
        (`SOURCE_AUTHOR` may call this, the same role that edits any other
        draft), but that new version is inert — Map's own routes only ever
        write to a `status='draft'` row — until a `SOURCE_APPROVER`
        publishes it, which is where the actual sign-off happens (the same
        `publish` gate every other publish goes through, not a second
        "approve" action). The previous version is flipped to `superseded`
        in the same breath, so at most one version of a recipe is ever
        `published`/`flagged` at once — the invariant `flag_stale` below
        relies on."""
        draft = await self.get_authorized(recipe_id, principal)
        if draft.status not in (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED):
            raise StudioRecipeCannotVersionError(recipe_id)
        content = _content_json(draft)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE studio_recipes SET status = $1 WHERE recipe_id = $2 AND version = $3",
                    StudioRecipeStatus.SUPERSEDED.value,
                    recipe_id,
                    draft.version,
                )
                await conn.execute(
                    "INSERT INTO studio_recipes (recipe_id, version, label, status, content, "
                    "owning_unit, created_by, created_at, dataset_id) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    recipe_id,
                    draft.version + 1,
                    draft.label,
                    StudioRecipeStatus.DRAFT.value,
                    content,
                    principal.org_unit,
                    principal.id,
                    now,
                    # A new version stays in its recipe's dataset (one made before keeps none).
                    draft.dataset_id,
                )
        return await self.get(recipe_id)

    async def flag_stale(
        self, current_ontology_version: int, current_pack_versions: dict[str, int]
    ) -> list[str]:
        """The reverse index `09_INGEST_STUDIO.md` §6 promises: run once
        whenever the ontology reloads (`services/api/app.py`'s `lifespan`
        — this deployment's only "reload" trigger today is a process
        restart after a new `packages/ontology/default.yaml` ships, there
        being no live-reload admin action yet, Phase 8's own territory).
        `WHERE status = 'published'` is safe against every version of a
        recipe, not just its latest, because `create_new_version` already
        guarantees at most one version of a given `recipe_id` is ever
        `published` at a time — an older version is `superseded` the
        moment a newer one is opened, never left `published` alongside it.
        A recipe is also flagged when any pack it pins is at another version, or no longer
        loaded, than `current_pack_versions` (ADR-120 D10); a row with no pins is never flagged on
        packs, only on the core version. One statement, so the two tests cannot disagree about
        which rows they saw. An object with a pinned value that is not a JSON whole number
        (`"1"`, `1.5`, `true`) is flagged too, however it reads against the loaded version
        (ADR-120 Amendment 3, decision 1). Returns the flagged `recipe_id`s, for the caller to
        log/audit."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE studio_recipes SET status = $1 "
                "WHERE status = $2 AND ("
                "(ontology_version IS NOT NULL AND ontology_version != $3) "
                "OR (pack_versions IS NOT NULL AND jsonb_typeof(pack_versions) = 'object' "
                "AND EXISTS ("
                "SELECT 1 FROM jsonb_each(pack_versions) AS p(k, v) "
                "WHERE jsonb_typeof(p.v) <> 'number' OR p.v::text !~ '^[0-9]+$' "
                "OR ($4::jsonb -> p.k) IS DISTINCT FROM p.v))"
                ") RETURNING recipe_id",
                StudioRecipeStatus.FLAGGED.value,
                StudioRecipeStatus.PUBLISHED.value,
                current_ontology_version,
                json.dumps(current_pack_versions),
            )
        return [row["recipe_id"] for row in rows]

    async def backfill_pack_versions(
        self,
        read_recipe: Callable[[str], Recipe | None],
        ontology: OntologySchema,
    ) -> list[str]:
        """Stamp the pins of every published recipe that has none (ADR-120 Amendment 1, decisions
        4 and 6): each is read from its committed file and given the legacy version of every pack
        it names or writes (`{}` when it names and writes none, so it is not read again at the
        next start). A recipe whose file cannot be read, or that names or writes a pack with no
        legacy version, is flagged, never stamped with a guess, and its id returned. Only
        published rows with no pins are read (a column holding a JSON value that is not an object
        counts as none, ADR-120 Amendment 3); any other row is left exactly as it is. No row lock
        is held while a file is read, so each write re-checks that its row is still published and
        unpinned, and a row superseded or pinned meanwhile is left unchanged."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT recipe_id, version, git_path FROM studio_recipes "
                "WHERE status = $1 AND (pack_versions IS NULL "
                "OR jsonb_typeof(pack_versions) <> 'object') ORDER BY recipe_id, version",
                StudioRecipeStatus.PUBLISHED.value,
            )
        flagged: list[str] = []
        for row in rows:
            git_path = row["git_path"]
            recipe = read_recipe(git_path) if isinstance(git_path, str) else None
            pins: dict[str, int] | None = None
            if recipe is not None:
                packs = recipe_packs(recipe.pipeline, recipe.row_template, ontology)
                if all(pack in LEGACY_PACK_VERSIONS for pack in packs):
                    pins = {pack: LEGACY_PACK_VERSIONS[pack] for pack in packs}
            async with self._pool.acquire() as conn:
                if pins is None:
                    # A file that cannot be read, or a pack with no legacy version: no guess.
                    done = await conn.execute(
                        "UPDATE studio_recipes SET status = $1 "
                        "WHERE recipe_id = $2 AND version = $3 AND status = $4 "
                        "AND (pack_versions IS NULL OR jsonb_typeof(pack_versions) <> 'object')",
                        StudioRecipeStatus.FLAGGED.value,
                        row["recipe_id"],
                        row["version"],
                        StudioRecipeStatus.PUBLISHED.value,
                    )
                    if done.endswith(" 1"):
                        flagged.append(row["recipe_id"])
                    continue
                await conn.execute(
                    "UPDATE studio_recipes SET pack_versions = $1::jsonb "
                    "WHERE recipe_id = $2 AND version = $3 AND status = $4 "
                    "AND (pack_versions IS NULL OR jsonb_typeof(pack_versions) <> 'object')",
                    json.dumps(pins),
                    row["recipe_id"],
                    row["version"],
                    StudioRecipeStatus.PUBLISHED.value,
                )
        return flagged


class _PinStore(Protocol):
    """What `reconcile_recipe_pins` needs of the registry; the real store satisfies it."""

    def backfill_pack_versions(
        self, read_recipe: Callable[[str], Recipe | None], ontology: OntologySchema
    ) -> Awaitable[list[str]]: ...

    def flag_stale(
        self, current_ontology_version: int, current_pack_versions: dict[str, int]
    ) -> Awaitable[list[str]]: ...


async def reconcile_recipe_pins(
    store: _PinStore,
    ontology: OntologySchema,
    read_recipe: Callable[[str], Recipe | None],
) -> list[str]:
    """Start-up's one step (ADR-120 Amendment 1, decision 6): stamp the legacy recipes' pins,
    then flag every published recipe whose core version or pinned packs differ from the ontology
    in force. Stamping first matters: a row with no pins is not flagged on packs, so flagging
    first would leave a legacy NIEM recipe published past a bump. Returns every id flagged by
    either pass, once each."""
    unreadable = await store.backfill_pack_versions(read_recipe, ontology)
    stale = await store.flag_stale(ontology.version, ontology.packs)
    return list(dict.fromkeys([*unreadable, *stale]))


def recipe_reader(repo_root: Path) -> Callable[[str], Recipe | None]:
    """Reads a recipe from the recipe repository by its row's `git_path`; a missing, unreadable
    or malformed file is `None`, which the backfill takes as "flag it" (ADR-120 Amendment 1,
    decision 6). A file that is not text (`UnicodeDecodeError`) or any other `ValueError` from
    reading it is unreadable too, so a bad row can never stop the start-up (the same rule)."""

    def read(git_path: str) -> Recipe | None:
        try:
            return load_recipe(repo_root / git_path)
        except (OSError, ValueError, yaml.YAMLError):
            # `ValueError` covers `UnicodeDecodeError` and pydantic's `ValidationError`.
            return None

    return read
