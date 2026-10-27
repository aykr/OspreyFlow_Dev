"""`services/api/studio_recipes.py`'s `StudioRecipeStore` — direct,
live-Postgres correctness, mirroring `test_sites_store.py`'s own
discipline: the JSON-encoded `content` round trip and the existence-leak
behaviour deserve a direct proof rather than only exercise through
route-level fakes. `spec/09_INGEST_STUDIO.md` §2, §6."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.studio_recipes import (
    SeededRecipeAnotherPublished,
    SeededRecipeContentDiffers,
    StudioRecipeCannotVersionError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
    StudioRecipeStore,
)
from services.ingest.engine import StaleRecipeError
from services.ingest.recipe_loader import load_recipe

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    Recipe,
    RecipeEntity,
    RowTemplate,
    StudioRecipeDraft,
    StudioRecipeStatus,
    UnmappedField,
)

AUTHOR = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_author"])
OTHER_UNIT_AUTHOR = Principal(
    id="analyst-2", clearance="OFFICIAL", org_unit="unit-2", roles=["source_author"]
)


@pytest.fixture
async def store():
    s = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_created_draft_is_not_ready_for_profile(store: StudioRecipeStore) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    assert draft.status is StudioRecipeStatus.DRAFT
    assert draft.version == 1
    assert draft.owning_unit == "unit-1"
    assert draft.ready_for_profile is False

    fetched = await store.get(draft.recipe_id)
    assert fetched == draft


async def test_update_draft_merges_only_the_provided_fields(store: StudioRecipeStore) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )

    updated = await store.update_draft(
        draft.recipe_id, AUTHOR, source_location="s3://bucket/carrier-a.csv"
    )
    assert updated.source_location == "s3://bucket/carrier-a.csv"
    assert updated.connector_profile == "generic-csv"
    assert updated.label == "Carrier A — CDR"

    fully_answered = await store.update_draft(
        draft.recipe_id,
        AUTHOR,
        handling={
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    assert fully_answered.ready_for_profile is True


async def test_a_missing_recipe_id_raises_not_found(store: StudioRecipeStore) -> None:
    with pytest.raises(StudioRecipeNotFoundError):
        await store.get("no-such-recipe")


async def test_a_draft_owned_by_a_different_unit_is_not_found_not_forbidden(
    store: StudioRecipeStore,
) -> None:
    """Existence-leak discipline, matching `SiteNotFoundError`'s own
    doc comment: wrong unit and no-such-recipe collapse to the same
    error rather than a distinguishable 403."""
    draft = await store.create_draft(
        AUTHOR,
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    with pytest.raises(StudioRecipeNotFoundError):
        await store.get_authorized(draft.recipe_id, OTHER_UNIT_AUTHOR)


async def test_list_drafts_returns_only_the_principals_own_unit(store: StudioRecipeStore) -> None:
    # No table-truncation fixture exists for this store (matching
    # `test_sites_store.py`'s own no-cleanup convention against a real,
    # persistent local Postgres) — assert containment/exclusion rather than
    # an exact list, since earlier tests in the same run leave rows behind.
    not_mine = await store.create_draft(
        OTHER_UNIT_AUTHOR,
        label="Not mine",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    mine = await store.create_draft(
        AUTHOR,
        label="Mine",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )

    drafts = await store.list_drafts(AUTHOR)
    recipe_ids = [d.recipe_id for d in drafts]
    assert mine.recipe_id in recipe_ids
    assert not_mine.recipe_id not in recipe_ids


async def test_update_draft_rejects_once_the_recipe_is_no_longer_a_draft(
    store: StudioRecipeStore,
) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET status = $1 WHERE recipe_id = $2",
            "published",
            draft.recipe_id,
        )

    with pytest.raises(StudioRecipeNotADraftError):
        await store.update_draft(draft.recipe_id, AUTHOR, label="renamed")


# --- Map (09_INGEST_STUDIO.md §4) --------------------------------------------


async def test_update_row_template_round_trips_and_leaves_connect_fields_untouched(
    store: StudioRecipeStore,
) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location="s3://bucket/carrier-a.csv",
        handling={
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    row_template = RowTemplate(
        entities=[RecipeEntity(ref="a", pole_class="object", type="Endpoint")]
    )

    updated = await store.update_row_template(
        draft.recipe_id,
        AUTHOR,
        row_template=row_template,
        unmapped_fields=[UnmappedField(field="imei", note="not reliable in this feed")],
    )

    assert updated.row_template is not None
    assert updated.row_template.entities[0].ref == "a"
    assert updated.unmapped_fields[0].field == "imei"
    # Connect's own fields are exactly as they were before Map ever saved.
    assert updated.source_location == "s3://bucket/carrier-a.csv"
    assert updated.legal_basis == "RIPA s22 acquisition — authorisation 2026/0114"

    # A subsequent Connect-stage edit must not drop the row template Map
    # already saved (§4/§6: "a draft is a row" — `content` is the whole
    # draft, not just Connect's own fields).
    reconnected = await store.update_draft(draft.recipe_id, AUTHOR, label="renamed")
    assert reconnected.row_template is not None
    assert reconnected.row_template.entities[0].ref == "a"


async def test_update_row_template_rejects_once_the_recipe_is_no_longer_a_draft(
    store: StudioRecipeStore,
) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET status = $1 WHERE recipe_id = $2",
            "published",
            draft.recipe_id,
        )

    with pytest.raises(StudioRecipeNotADraftError):
        await store.update_row_template(
            draft.recipe_id,
            AUTHOR,
            row_template=RowTemplate(entities=[]),
            unmapped_fields=[],
        )


# --- Publish (09_INGEST_STUDIO.md §6) ----------------------------------------


async def _verified_draft(store: StudioRecipeStore, **overrides: object) -> StudioRecipeDraft:
    """A draft with a saved row template and `verified_at` set — the state
    `publish` requires. Mirrors what the real route does (Verify's own
    success, `services/api/studio_verify.py`) without going through Verify
    itself, since this module tests the store in isolation."""
    defaults: dict[str, object] = dict(
        label="Carrier A — CDR",
        connector_profile="generic-csv",
        source_location="s3://bucket/carrier-a.csv",
        handling={
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    defaults.update(overrides)
    draft = await store.create_draft(AUTHOR, **defaults)  # type: ignore[arg-type]
    draft = await store.update_row_template(
        draft.recipe_id,
        AUTHOR,
        row_template=RowTemplate(
            entities=[RecipeEntity(ref="a", pole_class="object", type="Endpoint")]
        ),
        unmapped_fields=[],
    )
    await store.mark_verified(draft.recipe_id, draft.version, now=datetime(2026, 1, 1, tzinfo=UTC))
    return await store.get(draft.recipe_id)


async def test_publish_rejects_a_draft_that_has_never_been_verified(
    store: StudioRecipeStore,
) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Unverified",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    with pytest.raises(StudioRecipeNotVerifiedError):
        await store.publish(
            draft.recipe_id,
            AUTHOR,
            ontology_version=3,
            pack_versions={},
            git_path="recipes/x.yaml",
            schedule_cron=None,
            schedule_watch=None,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )


async def test_editing_a_verified_draft_clears_verified_at_and_blocks_publish(
    store: StudioRecipeStore,
) -> None:
    draft = await _verified_draft(store)
    assert draft.verified_at is not None

    edited = await store.update_draft(draft.recipe_id, AUTHOR, label="renamed")
    assert edited.verified_at is None

    with pytest.raises(StudioRecipeNotVerifiedError):
        await store.publish(
            draft.recipe_id,
            AUTHOR,
            ontology_version=3,
            pack_versions={},
            git_path="recipes/x.yaml",
            schedule_cron=None,
            schedule_watch=None,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )


async def test_publish_flips_status_and_stamps_attribution(store: StudioRecipeStore) -> None:
    draft = await _verified_draft(store)
    published = await store.publish(
        draft.recipe_id,
        AUTHOR,
        ontology_version=3,
        pack_versions={},
        git_path="recipes/some-id.yaml",
        schedule_cron="0 6 * * *",
        schedule_watch="s3://ingest/carrier-a/*.csv",
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert published.status is StudioRecipeStatus.PUBLISHED
    assert published.ontology_version == 3
    assert published.git_path == "recipes/some-id.yaml"
    assert published.published_by == "analyst-1"
    assert published.published_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert published.schedule_cron == "0 6 * * *"
    assert published.schedule_watch == "s3://ingest/carrier-a/*.csv"

    # Publish is a one-way door from here — a second publish attempt on the
    # now-published row fails the same way any post-draft edit would.
    with pytest.raises(StudioRecipeNotADraftError):
        await store.publish(
            published.recipe_id,
            AUTHOR,
            ontology_version=3,
            pack_versions={},
            git_path="recipes/some-id.yaml",
            schedule_cron=None,
            schedule_watch=None,
            now=datetime(2026, 1, 3, tzinfo=UTC),
        )


async def test_update_schedule_rejects_a_draft_recipe(store: StudioRecipeStore) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Not yet published",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    with pytest.raises(StudioRecipeNotADraftError):
        await store.update_schedule(
            draft.recipe_id, AUTHOR, schedule_cron="0 6 * * *", schedule_watch=None
        )


async def test_update_schedule_changes_only_the_schedule(store: StudioRecipeStore) -> None:
    draft = await _verified_draft(store)
    published = await store.publish(
        draft.recipe_id,
        AUTHOR,
        ontology_version=3,
        pack_versions={},
        git_path="recipes/some-id.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    rescheduled = await store.update_schedule(
        published.recipe_id, AUTHOR, schedule_cron="0 7 * * *", schedule_watch=None
    )
    assert rescheduled.schedule_cron == "0 7 * * *"
    assert rescheduled.status is StudioRecipeStatus.PUBLISHED
    assert rescheduled.git_path == "recipes/some-id.yaml"


async def test_setting_a_schedule_makes_its_setter_the_owner_and_resumes_it(
    store: StudioRecipeStore,
) -> None:
    """ADR-110 decision 3: a scheduled run acts as whoever last set the schedule."""
    draft = await _verified_draft(store)
    published = await store.publish(
        draft.recipe_id, AUTHOR, ontology_version=3, pack_versions={}, git_path="recipes/x.yaml",
        schedule_cron=None, schedule_watch=None, now=datetime(2026, 1, 2, tzinfo=UTC),
    )  # fmt: skip
    assert published.schedule_owner is None
    await store.set_paused(published.recipe_id, paused=True, reason="three refusals")
    set_at = datetime(2026, 1, 3, 9, tzinfo=UTC)
    scheduled = await store.update_schedule(
        published.recipe_id, AUTHOR, schedule_cron="0 7 * * *", schedule_watch=None,
        schedule_timezone="Europe/Paris", now=set_at, schedule_case="case-7",
    )  # fmt: skip
    assert (scheduled.schedule_owner, scheduled.schedule_set_at) == (AUTHOR.id, set_at)
    assert (scheduled.schedule_timezone, scheduled.schedule_case) == ("Europe/Paris", "case-7")
    assert scheduled.schedule_paused is False and scheduled.schedule_paused_reason is None


async def test_the_scheduler_lists_scheduled_recipes_and_a_pause_keeps_its_reason(
    store: StudioRecipeStore,
) -> None:
    draft = await _verified_draft(store)
    await store.publish(
        draft.recipe_id, AUTHOR, ontology_version=3, pack_versions={}, git_path="recipes/y.yaml",
        schedule_cron="0 6 * * *", schedule_watch=None, now=datetime(2026, 1, 2, tzinfo=UTC),
    )  # fmt: skip
    listed = {r.recipe_id: r for r in await store.scheduled()}
    assert listed[draft.recipe_id].schedule_owner == AUTHOR.id
    await store.set_paused(draft.recipe_id, paused=True, reason="three refusals in a row")
    paused = {r.recipe_id: r for r in await store.scheduled()}[draft.recipe_id]
    assert (paused.schedule_paused, paused.schedule_paused_reason) == (
        True, "three refusals in a row",
    )  # fmt: skip
    await store.set_paused(draft.recipe_id, paused=False, reason="ignored when resuming")
    resumed = {r.recipe_id: r for r in await store.scheduled()}[draft.recipe_id]
    assert (resumed.schedule_paused, resumed.schedule_paused_reason) == (False, None)


_CONNECT: dict[str, object] = {
    "connector_profile": "generic-csv",
    "source_location": "s3://bucket/feed.csv",
    "handling": {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
                 "owning_unit": "unit-1"},
    "legal_basis": "synthetic test basis",
}  # fmt: skip


async def test_the_feeds_of_a_case_are_its_datasets_published_recipes_only(
    store: StudioRecipeStore,
) -> None:
    """ADR-110 decision 9: what feeds a case is read through the case's datasets."""
    from uuid import uuid4

    mine, theirs = f"ds-{uuid4().hex[:8]}", f"ds-{uuid4().hex[:8]}"
    published = []
    for dataset in (mine, theirs):
        author = AUTHOR.model_copy(update={"datasets": [dataset]})
        draft = await store.create_draft(author, label=f"Feed {dataset}", **_CONNECT)
        await store.mark_verified(
            draft.recipe_id, draft.version, now=datetime(2026, 1, 1, tzinfo=UTC)
        )
        published.append(await store.publish(
            draft.recipe_id, AUTHOR, ontology_version=3, pack_versions={},
            git_path="recipes/f.yaml", schedule_cron=None, schedule_watch=None,
            now=datetime(2026, 1, 2, tzinfo=UTC),
        ))  # fmt: skip
    still_a_draft = await store.create_draft(
        AUTHOR.model_copy(update={"datasets": [mine]}), label="Unpublished", **_CONNECT
    )
    feeding = [r.recipe_id for r in await store.feeding([mine])]
    assert feeding == [published[0].recipe_id]
    assert still_a_draft.recipe_id not in feeding
    assert await store.feeding([]) == []


async def test_retime_keeps_the_owner_case_and_pause_and_moves_the_set_time(
    store: StudioRecipeStore,
) -> None:
    """ADR-110 Amendment 3, point 2: the Admin area's *Change schedule* keeps the owner."""
    draft = await _verified_draft(store)
    await store.publish(
        draft.recipe_id, AUTHOR, ontology_version=3, pack_versions={}, git_path="recipes/r.yaml",
        schedule_cron="0 6 * * *", schedule_watch=None, now=datetime(2026, 1, 2, tzinfo=UTC),
        schedule_case="case-9",
    )  # fmt: skip
    await store.set_paused(draft.recipe_id, paused=True, reason="by hand")
    moved = datetime(2026, 2, 1, 9, tzinfo=UTC)
    await store.retime(draft.recipe_id, cron="30 7 * * 1-5", timezone="Europe/Paris", now=moved)
    after = await store.get(draft.recipe_id)
    assert (after.schedule_cron, after.schedule_timezone, after.schedule_set_at) == (
        "30 7 * * 1-5", "Europe/Paris", moved,
    )  # fmt: skip
    assert (after.schedule_owner, after.schedule_case, after.schedule_paused) == (
        AUTHOR.id, "case-9", True,
    )  # fmt: skip


async def test_create_new_version_supersedes_the_published_row_and_opens_a_draft(
    store: StudioRecipeStore,
) -> None:
    draft = await _verified_draft(store)
    published = await store.publish(
        draft.recipe_id,
        AUTHOR,
        ontology_version=3,
        pack_versions={},
        git_path="recipes/some-id.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    new_version = await store.create_new_version(
        published.recipe_id, AUTHOR, now=datetime(2026, 1, 3, tzinfo=UTC)
    )
    assert new_version.version == published.version + 1
    assert new_version.status is StudioRecipeStatus.DRAFT
    assert new_version.git_path is None
    assert new_version.published_by is None
    assert new_version.verified_at is None
    # Content carried over from the version it reopened.
    assert new_version.row_template is not None
    assert new_version.row_template.entities[0].ref == "a"

    # `get` always returns the highest version — the superseded row is
    # only reachable directly, not via the ordinary lookup path.
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        old_status = await conn.fetchval(
            "SELECT status FROM studio_recipes WHERE recipe_id = $1 AND version = $2",
            published.recipe_id,
            published.version,
        )
    assert old_status == StudioRecipeStatus.SUPERSEDED.value


async def test_create_new_version_rejects_a_draft_or_superseded_recipe(
    store: StudioRecipeStore,
) -> None:
    draft = await store.create_draft(
        AUTHOR,
        label="Still a draft",
        connector_profile="generic-csv",
        source_location=None,
        handling={},
        legal_basis=None,
    )
    with pytest.raises(StudioRecipeCannotVersionError):
        await store.create_new_version(
            draft.recipe_id, AUTHOR, now=datetime(2026, 1, 1, tzinfo=UTC)
        )


async def test_flag_stale_flags_only_published_recipes_targeting_a_different_ontology_version(
    store: StudioRecipeStore,
) -> None:
    stale_draft = await _verified_draft(store, label="Stale")
    stale_published = await store.publish(
        stale_draft.recipe_id,
        AUTHOR,
        ontology_version=3,
        pack_versions={},
        git_path="recipes/stale.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    current_draft = await _verified_draft(store, label="Current")
    current_published = await store.publish(
        current_draft.recipe_id,
        AUTHOR,
        ontology_version=4,
        pack_versions={},
        git_path="recipes/current.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    flagged_ids = await store.flag_stale(current_ontology_version=4, current_pack_versions={})
    assert stale_published.recipe_id in flagged_ids
    assert current_published.recipe_id not in flagged_ids

    refetched_stale = await store.get(stale_published.recipe_id)
    assert refetched_stale.status is StudioRecipeStatus.FLAGGED
    refetched_current = await store.get(current_published.recipe_id)
    assert refetched_current.status is StudioRecipeStatus.PUBLISHED


def _chain_pipeline() -> PipelineGraph:
    nodes = [
        PipelineNode(
            id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="D", config={"pack": "fibo"}
        ),
        PipelineNode(id="source", kind=PipelineNodeKind.SOURCE, label="S"),
        PipelineNode(id="profile", kind=PipelineNodeKind.PROFILE, label="P"),
        PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="M"),
        PipelineNode(id="load", kind=PipelineNodeKind.LOAD, label="L"),
    ]
    chain = ["domain", "source", "profile", "map", "load"]
    return PipelineGraph(
        nodes=nodes,
        edges=[PipelineEdge(source=a, target=b) for a, b in zip(chain, chain[1:], strict=False)],
    )


async def test_a_saved_pipeline_round_trips_and_survives_a_connect_edit(
    store: StudioRecipeStore,
) -> None:
    """ADR-108 phase B: the pipeline is part of the draft's one content document, so an edit to any
    other part must carry it — the same sibling-field rule `update_draft`'s own row-template
    comment states."""
    made = await store.create_draft(AUTHOR, label="Pipelined", connector_profile="generic-csv",
                                    source_location=None, handling={}, legal_basis=None)
    saved = await store.update_pipeline(made.recipe_id, AUTHOR, pipeline=_chain_pipeline())
    assert saved.pipeline is not None
    assert [n.kind for n in saved.pipeline.nodes][0] == PipelineNodeKind.DOMAIN_MODEL
    edited = await store.update_draft(made.recipe_id, AUTHOR, label="Renamed")
    assert edited.pipeline is not None, "a Connect edit dropped the pipeline"
    assert edited.pipeline == saved.pipeline
    read = await store.get_authorized(made.recipe_id, AUTHOR)
    assert read.pipeline == saved.pipeline


async def test_update_pipeline_rejects_once_the_recipe_is_no_longer_a_draft(
    store: StudioRecipeStore,
) -> None:
    made = await store.create_draft(AUTHOR, label="P", connector_profile="generic-csv",
                                    source_location=None, handling={}, legal_basis=None)
    await store.mark_verified(made.recipe_id, made.version, now=datetime(2026, 1, 1, tzinfo=UTC))
    await store.publish(
        made.recipe_id,
        AUTHOR,
        ontology_version=17,
        pack_versions={},
        git_path="recipes/p.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    with pytest.raises(StudioRecipeNotADraftError):
        await store.update_pipeline(made.recipe_id, AUTHOR, pipeline=_chain_pipeline())


# --- Pack pins (ADR-120 D10, Amendment 1) -------------------------------------
#
# What each test checks, and the violation that fails it:
# - `test_publish_records_the_pack_versions`: `publish` not storing the map, or `get` not mapping
#   the column back onto the draft.
# - `test_a_pack_bump_flags_only_recipes_pinning_that_pack`: a bump flagging a recipe that pins a
#   different pack, or one that pins none (`{}`), or failing to flag the one that pins the bumped
#   pack.
# - `test_a_pinned_pack_that_is_no_longer_loaded_flags_its_recipe`: a pin on a pack missing from
#   the current ontology being read as "no change".
# - `test_the_backfill_stamps_legacy_recipes_at_the_last_version_before_pinning`: the backfill
#   stamping the current versions (which would hide the bump), skipping a row, reading or changing
#   a row that is pinned, a draft, flagged or superseded, stamping a row it could not read, or
#   missing a pack written under the core (`fibo-under-pole`).
# - `test_a_null_pinned_row_at_the_current_core_version_is_never_flagged`: an unstamped row being
#   flagged by `flag_stale` before the backfill has judged it.
# - `test_publish_without_pack_versions_is_refused`: `publish` growing a default, so a fresh publish
#   could store "not pinned" and be mistaken for a legacy row at the next start.
# - `test_publish_with_pack_versions_none_is_refused`: a fresh publish storing "not pinned", which
#   the next start's backfill would mistake for a legacy row and stamp at the last pre-pinning
#   versions (ADR-120 Amendment 2, decision 3).
# - `test_reconcile_recipe_pins_writes_nothing_under_the_recipe_root`: a start-up that stamps a
#   file as well as a row (Amendment 2: nothing at start-up writes to the recipe repository).
# - `test_a_non_object_pack_versions_value_reads_as_unpinned_and_does_not_break_flagging`: a JSON
#   `null` or array in the column crashing the read or `flag_stale`, so the Conduit would not start,
#   or the backfill not stamping such a row as legacy.
# - `test_the_backfill_leaves_a_row_superseded_while_it_was_being_read_unchanged`: the stamp being
#   written on the strength of an earlier read, so a row superseded in the gap gets pins.
# - `test_a_pin_object_with_a_non_integer_value_reads_as_unpinned_and_is_flagged_at_start_up`: a
#   pin object holding a non-integer being read as a pin, stamped over, or left published.
# - `test_a_pin_stored_as_a_numeric_string_is_flagged_at_start_up`: a text comparison reading the
#   string "1" as FIBO's loaded version 1, so a corrupted pin passes as a current one.
# - `test_a_pin_stored_as_a_decimal_one_is_flagged_at_start_up`: a pin of 1.0 being read as the
#   integer 1 (Postgres compares jsonb numbers by value), so a non-integer pin passes as current.
# - `test_reconcile_recipe_pins_stamps_then_flags_against_real_files`: start-up flagging before it
#   stamps (the legacy NIEM row has no pins, so it would stay published), reading a file the
#   wrong way, or treating a missing, malformed or invalid file as readable.

_CORE_VERSION = load_default_ontology().version
_ALL_PACKS = {"niem": 3, "fibo": 1, "stix": 1}


async def _published_with_pins(
    store: StudioRecipeStore,
    label: str,
    pins: dict[str, int],
    git_path: str = "recipes/pins.yaml",
) -> StudioRecipeDraft:
    draft = await _verified_draft(store, label=label)
    return await store.publish(
        draft.recipe_id,
        AUTHOR,
        ontology_version=_CORE_VERSION,
        pack_versions=pins,
        git_path=git_path,
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )


async def _unpin(store: StudioRecipeStore, *recipe_ids: str) -> None:
    """A recipe published before pinning existed: no map at all, not an empty one."""
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = NULL WHERE recipe_id = ANY($1::text[])",
            list(recipe_ids),
        )


def _write_legacy_recipe(
    directory: Path, name: str, *, pack: str | None, writes: str | None = None
) -> Recipe:
    """A recipe on disk, round-tripped through the real loader: its pipeline names `pack` (or has
    none), and its row template writes one `writes` entity (or an `Endpoint`)."""
    import yaml
    from services.ingest.recipe_loader import load_recipe

    document = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2] / "scenarios" / "fixtures" / "cdr_recipe.yaml"
        ).read_text()
    )
    document.pop("deduplicate", None)
    document["id"] = name
    document["row_template"] = {
        "entities": [{"ref": "e", "pole_class": "object", "type": writes or "Endpoint"}]
    }
    if pack is not None:
        document["pipeline"] = {
            "nodes": [
                {"id": "domain", "kind": "domain_model", "label": "D", "config": {"pack": pack}}
            ],
            "edges": [],
        }
    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(document))
    return load_recipe(path)


async def test_publish_records_the_pack_versions(store: StudioRecipeStore) -> None:
    published = await _published_with_pins(store, "Pinned", {"niem": 3})
    assert published.pack_versions == {"niem": 3}
    assert (await store.get(published.recipe_id)).pack_versions == {"niem": 3}


async def test_a_pack_bump_flags_only_recipes_pinning_that_pack(
    store: StudioRecipeStore,
) -> None:
    pins_niem = await _published_with_pins(store, "Pins niem", {"niem": 2})
    pins_fibo = await _published_with_pins(store, "Pins fibo", {"fibo": 1})
    pins_none = await _published_with_pins(store, "Pins nothing", {})

    flagged = await store.flag_stale(_CORE_VERSION, _ALL_PACKS)

    assert pins_niem.recipe_id in flagged
    assert pins_fibo.recipe_id not in flagged
    assert pins_none.recipe_id not in flagged
    assert (await store.get(pins_niem.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert (await store.get(pins_fibo.recipe_id)).status is StudioRecipeStatus.PUBLISHED
    assert (await store.get(pins_none.recipe_id)).status is StudioRecipeStatus.PUBLISHED


async def test_a_pinned_pack_that_is_no_longer_loaded_flags_its_recipe(
    store: StudioRecipeStore,
) -> None:
    pins_stix = await _published_with_pins(store, "Pins stix", {"stix": 1})

    flagged = await store.flag_stale(_CORE_VERSION, {"niem": 3})

    assert pins_stix.recipe_id in flagged
    assert (await store.get(pins_stix.recipe_id)).status is StudioRecipeStatus.FLAGGED


async def test_the_backfill_stamps_legacy_recipes_at_the_last_version_before_pinning(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    from uuid import uuid4

    paths = {
        "niem": "legacy/niem.yaml",
        "fibo": "legacy/fibo.yaml",
        "none": "legacy/none.yaml",
        "missing": "legacy/missing.yaml",
        "stix": "legacy/stix.yaml",
        "fibo-under-pole": "legacy/fibo-under-pole.yaml",
    }
    rows = {
        key: await _published_with_pins(store, f"Legacy {key}", {}, git_path=path)
        for key, path in paths.items()
    }
    # Rows the backfill must neither read nor change: already pinned, and a draft with no pins.
    pinned_path = f"legacy/pinned-{uuid4().hex[:8]}.yaml"
    draft_path = f"legacy/draft-{uuid4().hex[:8]}.yaml"
    pinned = await _published_with_pins(store, "Pinned", {"niem": 3}, git_path=pinned_path)
    draft = await _verified_draft(store, label="Draft with no pins")
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET git_path = $1 WHERE recipe_id = $2",
            draft_path,
            draft.recipe_id,
        )
    # Legacy rows that are no longer published: flagged and superseded rows are never read either.
    flagged_path = f"legacy/flagged-{uuid4().hex[:8]}.yaml"
    superseded_path = f"legacy/superseded-{uuid4().hex[:8]}.yaml"
    already_flagged = await _published_with_pins(store, "Flagged", {}, git_path=flagged_path)
    superseded = await _published_with_pins(store, "Superseded", {}, git_path=superseded_path)
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET status = $1 WHERE recipe_id = $2",
            StudioRecipeStatus.FLAGGED.value,
            already_flagged.recipe_id,
        )
        await conn.execute(
            "UPDATE studio_recipes SET status = $1 WHERE recipe_id = $2",
            StudioRecipeStatus.SUPERSEDED.value,
            superseded.recipe_id,
        )
    await _unpin(
        store,
        *(row.recipe_id for row in rows.values()),
        draft.recipe_id,
        already_flagged.recipe_id,
        superseded.recipe_id,
    )

    legacy = {
        paths["niem"]: _write_legacy_recipe(tmp_path, "niem", pack="niem"),
        paths["fibo"]: _write_legacy_recipe(tmp_path, "fibo", pack="fibo"),
        paths["none"]: _write_legacy_recipe(tmp_path, "none", pack=None),
        paths["stix"]: _write_legacy_recipe(tmp_path, "stix", pack="stix"),
        paths["fibo-under-pole"]: _write_legacy_recipe(
            tmp_path, "fibo-under-pole", pack="pole", writes="Account"
        ),
    }
    requested: list[object] = []

    def read_recipe(git_path: str) -> Recipe | None:
        requested.append(git_path)
        if git_path == paths["missing"]:
            return None
        # Rows other tests left behind with no pin are stamped too; they name and write no pack.
        return legacy.get(git_path) or _write_legacy_recipe(tmp_path, "other", pack=None)

    from ontology.packs import load_deployment_ontology

    flagged_by_backfill = await store.backfill_pack_versions(
        read_recipe, load_deployment_ontology()
    )

    assert all(isinstance(path, str) for path in requested)
    assert pinned_path not in requested
    assert draft_path not in requested
    assert flagged_path not in requested
    assert superseded_path not in requested
    assert (await store.get(rows["niem"].recipe_id)).pack_versions == {"niem": 2}
    assert (await store.get(rows["fibo"].recipe_id)).pack_versions == {"fibo": 1}
    assert (await store.get(rows["none"].recipe_id)).pack_versions == {}
    assert (await store.get(rows["stix"].recipe_id)).pack_versions == {"stix": 1}
    assert (await store.get(rows["fibo-under-pole"].recipe_id)).pack_versions == {"fibo": 1}
    missing = await store.get(rows["missing"].recipe_id)
    assert missing.pack_versions is None, "an unreadable recipe was stamped with a guess"
    assert missing.status is StudioRecipeStatus.FLAGGED
    assert rows["missing"].recipe_id in flagged_by_backfill
    assert (await store.get(pinned.recipe_id)).pack_versions == {"niem": 3}
    assert (await store.get(pinned.recipe_id)).status is StudioRecipeStatus.PUBLISHED
    still_draft = await store.get(draft.recipe_id)
    assert still_draft.pack_versions is None
    assert still_draft.status is StudioRecipeStatus.DRAFT
    untouched_flagged = await store.get(already_flagged.recipe_id)
    assert untouched_flagged.pack_versions is None
    assert untouched_flagged.status is StudioRecipeStatus.FLAGGED
    untouched_superseded = await store.get(superseded.recipe_id)
    assert untouched_superseded.pack_versions is None
    assert untouched_superseded.status is StudioRecipeStatus.SUPERSEDED

    flagged = await store.flag_stale(_CORE_VERSION, _ALL_PACKS)

    assert rows["niem"].recipe_id in flagged
    for key in ("fibo", "stix", "fibo-under-pole", "none"):
        assert rows[key].recipe_id not in flagged
        assert (await store.get(rows[key].recipe_id)).status is StudioRecipeStatus.PUBLISHED


async def test_a_null_pinned_row_at_the_current_core_version_is_never_flagged(
    store: StudioRecipeStore,
) -> None:
    row = await _published_with_pins(store, "Unstamped", {})
    await _unpin(store, row.recipe_id)

    flagged = await store.flag_stale(_CORE_VERSION, _ALL_PACKS)

    assert row.recipe_id not in flagged
    assert (await store.get(row.recipe_id)).status is StudioRecipeStatus.PUBLISHED


async def test_publish_without_pack_versions_is_refused(store: StudioRecipeStore) -> None:
    draft = await _verified_draft(store, label="No pins given")
    with pytest.raises(TypeError, match="pack_versions"):
        await store.publish(  # type: ignore[call-arg]
            draft.recipe_id,
            AUTHOR,
            ontology_version=_CORE_VERSION,
            git_path="recipes/x.yaml",
            schedule_cron=None,
            schedule_watch=None,
            now=datetime(2026, 1, 2, tzinfo=UTC),
        )
    assert (await store.get(draft.recipe_id)).status is StudioRecipeStatus.DRAFT


async def test_reconcile_recipe_pins_stamps_then_flags_against_real_files(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    from services.api.studio_recipes import recipe_reader, reconcile_recipe_pins

    from ontology.packs import load_deployment_ontology

    root = tmp_path / "recipes-repo"
    (root / "recipes").mkdir(parents=True)
    _write_legacy_recipe(root / "recipes", "legacy-niem", pack="niem")
    (root / "recipes" / "malformed.yaml").write_text("id: [unclosed\nrow_template: : :\n")
    # Not text at all, and a recipe whose pipeline names a pack that does not exist.
    (root / "recipes" / "binary.yaml").write_bytes(b"\xff\xfe\x00")
    _write_legacy_recipe(root / "recipes", "unknown-pack", pack="nosuchpack")
    # Parses as YAML but is no recipe: it has no `row_template`.
    (root / "recipes" / "invalid.yaml").write_text("id: invalid\nlabel: Not a recipe\n")

    legacy_niem = await _published_with_pins(
        store, "Legacy NIEM", {}, git_path="recipes/legacy-niem.yaml"
    )
    pinned = await _published_with_pins(store, "Pinned", {"niem": 3}, git_path="recipes/none.yaml")
    missing = await _published_with_pins(store, "Missing", {}, git_path="recipes/gone.yaml")
    malformed = await _published_with_pins(
        store, "Malformed", {}, git_path="recipes/malformed.yaml"
    )
    invalid = await _published_with_pins(store, "Invalid", {}, git_path="recipes/invalid.yaml")
    binary = await _published_with_pins(store, "Binary", {}, git_path="recipes/binary.yaml")
    unknown_pack = await _published_with_pins(
        store, "Unknown pack", {}, git_path="recipes/unknown-pack.yaml"
    )
    await _unpin(
        store,
        legacy_niem.recipe_id,
        missing.recipe_id,
        malformed.recipe_id,
        invalid.recipe_id,
        binary.recipe_id,
        unknown_pack.recipe_id,
    )

    flagged = await reconcile_recipe_pins(store, load_deployment_ontology(), recipe_reader(root))

    assert (await store.get(legacy_niem.recipe_id)).pack_versions == {"niem": 2}
    assert (await store.get(legacy_niem.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert (await store.get(pinned.recipe_id)).status is StudioRecipeStatus.PUBLISHED
    assert (await store.get(missing.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert (await store.get(malformed.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert (await store.get(invalid.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert (await store.get(binary.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert (await store.get(unknown_pack.recipe_id)).status is StudioRecipeStatus.FLAGGED
    assert {
        legacy_niem.recipe_id,
        missing.recipe_id,
        malformed.recipe_id,
        invalid.recipe_id,
        binary.recipe_id,
        unknown_pack.recipe_id,
    } <= set(flagged)
    assert pinned.recipe_id not in flagged


async def test_publish_with_pack_versions_none_is_refused(store: StudioRecipeStore) -> None:
    draft = await _verified_draft(store, label="Not pinned")
    with pytest.raises(ValueError, match="pack_versions"):
        await store.publish(
            draft.recipe_id,
            AUTHOR,
            ontology_version=_CORE_VERSION,
            pack_versions=None,  # type: ignore[arg-type]
            git_path="recipes/x.yaml",
            schedule_cron=None,
            schedule_watch=None,
            now=datetime(2026, 1, 2, tzinfo=UTC),
        )
    assert (await store.get(draft.recipe_id)).status is StudioRecipeStatus.DRAFT


async def test_reconcile_recipe_pins_writes_nothing_under_the_recipe_root(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    from services.api.studio_recipes import recipe_reader, reconcile_recipe_pins

    from ontology.packs import load_deployment_ontology

    root = tmp_path / "recipes-repo"
    (root / "recipes").mkdir(parents=True)
    _write_legacy_recipe(root / "recipes", "legacy-niem", pack="niem")
    row = await _published_with_pins(store, "Legacy", {}, git_path="recipes/legacy-niem.yaml")
    await _unpin(store, row.recipe_id)

    def snapshot() -> dict[str, tuple[bytes, int]]:
        return {
            str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    before = snapshot()
    await reconcile_recipe_pins(store, load_deployment_ontology(), recipe_reader(root))

    assert (await store.get(row.recipe_id)).pack_versions == {"niem": 2}, "the row was not stamped"
    assert snapshot() == before


async def test_a_non_object_pack_versions_value_reads_as_unpinned_and_does_not_break_flagging(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    """A JSON `null` or array in the column is treated exactly as SQL NULL (ADR-120 Amendment 3):
    read as `None`, and stamped by the backfill as a legacy row. Red if the read or `flag_stale`
    crashes on it (the Conduit would not start), if it is read as a pin, or if the backfill leaves
    it unstamped so it is never judged."""
    from uuid import uuid4

    from services.api.studio_recipes import reconcile_recipe_pins

    from ontology.packs import load_deployment_ontology

    null_row = await _published_with_pins(
        store, "JSON null", {}, git_path=f"legacy/json-null-{uuid4().hex[:8]}.yaml"
    )
    array_row = await _published_with_pins(
        store, "JSON array", {}, git_path=f"legacy/json-array-{uuid4().hex[:8]}.yaml"
    )
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = 'null'::jsonb WHERE recipe_id = $1",
            null_row.recipe_id,
        )
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = '[1]'::jsonb WHERE recipe_id = $1",
            array_row.recipe_id,
        )

    assert (await store.get(null_row.recipe_id)).pack_versions is None
    assert (await store.get(array_row.recipe_id)).pack_versions is None
    await store.flag_stale(_CORE_VERSION, _ALL_PACKS)  # does not raise
    for row in (null_row, array_row):
        assert (await store.get(row.recipe_id)).status is StudioRecipeStatus.PUBLISHED

    def read_recipe(git_path: str) -> Recipe | None:
        return _write_legacy_recipe(tmp_path, "no-pack", pack=None)

    await reconcile_recipe_pins(store, load_deployment_ontology(), read_recipe)

    for row in (null_row, array_row):
        stamped = await store.get(row.recipe_id)
        assert stamped.pack_versions == {}
        assert stamped.status is StudioRecipeStatus.PUBLISHED


async def test_the_backfill_leaves_a_row_superseded_while_it_was_being_read_unchanged(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    """The backfill reads a recipe's file between choosing the row and stamping it, and a row can
    be superseded in that gap (a new version opened). Red if the stamp is written on the strength
    of the earlier read, giving a superseded row pins, or flags or reopens it."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    import asyncpg
    from services.api.config import PostgresConfig

    from ontology.packs import load_deployment_ontology

    path = f"legacy/superseded-mid-read-{uuid4().hex[:8]}.yaml"
    row = await _published_with_pins(store, "Superseded mid-read", {}, git_path=path)
    await _unpin(store, row.recipe_id)

    async def supersede() -> None:
        conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
        try:
            await conn.execute(
                "UPDATE studio_recipes SET status = $1 WHERE recipe_id = $2",
                StudioRecipeStatus.SUPERSEDED.value,
                row.recipe_id,
            )
        finally:
            await conn.close()

    def read_recipe(git_path: str) -> Recipe | None:
        if git_path == path:
            # The callback is synchronous, so the other writer runs on its own loop and thread.
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(lambda: asyncio.run(supersede())).result(timeout=20)
        return _write_legacy_recipe(tmp_path, "no-pack", pack=None)

    await store.backfill_pack_versions(read_recipe, load_deployment_ontology())

    after = await store.get(row.recipe_id)
    assert after.status is StudioRecipeStatus.SUPERSEDED
    assert after.pack_versions is None


async def test_a_pin_object_with_a_non_integer_value_reads_as_unpinned_and_is_flagged_at_start_up(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    """ADR-120 Amendment 3, decision 1: a pin object holding a value that is not an integer is not
    a pin and not a legacy row either; it is read as `None` and start-up flags the row, leaving
    the stored value as found. Red if `get` raises or reads it as a pin, if the backfill stamps
    over it (hiding that something wrote it), or if the row is left published."""
    import json
    from uuid import uuid4

    from services.api.studio_recipes import reconcile_recipe_pins

    from ontology.packs import load_deployment_ontology

    row = await _published_with_pins(
        store, "Pin value not an integer", {}, git_path=f"legacy/bad-pin-{uuid4().hex[:8]}.yaml"
    )
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = $1::jsonb WHERE recipe_id = $2",
            json.dumps({"fibo": "x"}),
            row.recipe_id,
        )
    assert (await store.get(row.recipe_id)).pack_versions is None

    def read_recipe(git_path: str) -> Recipe | None:
        return _write_legacy_recipe(tmp_path, "no-pack", pack=None)

    flagged = await reconcile_recipe_pins(store, load_deployment_ontology(), read_recipe)

    assert row.recipe_id in flagged
    assert (await store.get(row.recipe_id)).status is StudioRecipeStatus.FLAGGED
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        stored = await conn.fetchval(
            "SELECT pack_versions FROM studio_recipes WHERE recipe_id = $1", row.recipe_id
        )
    assert (json.loads(stored) if isinstance(stored, str) else stored) == {"fibo": "x"}


async def test_a_pin_stored_as_a_numeric_string_is_flagged_at_start_up(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    """ADR-120 Amendment 3, decision 1: a pin that is the string "1" is not the integer 1, though
    FIBO's loaded version is 1 and a text comparison would match. Red if `get` reads it as a pin
    (the row would then look current and never be flagged), or the backfill stamps over it."""
    import json
    from uuid import uuid4

    from services.api.studio_recipes import reconcile_recipe_pins

    from ontology.packs import load_deployment_ontology

    row = await _published_with_pins(
        store, "Pin is a numeric string", {}, git_path=f"legacy/string-pin-{uuid4().hex[:8]}.yaml"
    )
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = $1::jsonb WHERE recipe_id = $2",
            json.dumps({"fibo": "1"}),
            row.recipe_id,
        )
    assert load_deployment_ontology().packs["fibo"] == 1, "the premise: the string matches as text"
    assert (await store.get(row.recipe_id)).pack_versions is None

    def read_recipe(git_path: str) -> Recipe | None:
        return _write_legacy_recipe(tmp_path, "no-pack", pack=None)

    flagged = await reconcile_recipe_pins(store, load_deployment_ontology(), read_recipe)

    assert row.recipe_id in flagged
    assert (await store.get(row.recipe_id)).status is StudioRecipeStatus.FLAGGED
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        stored = await conn.fetchval(
            "SELECT pack_versions FROM studio_recipes WHERE recipe_id = $1", row.recipe_id
        )
    assert (json.loads(stored) if isinstance(stored, str) else stored) == {"fibo": "1"}


async def test_a_pin_stored_as_a_decimal_one_is_flagged_at_start_up(
    store: StudioRecipeStore, tmp_path: Path
) -> None:
    """ADR-120 Amendment 3, decision 1: a pin of 1.0 is not the integer 1. Postgres compares jsonb
    numbers by value, so 1.0 equals FIBO's loaded 1 there and only the whole-number check on read
    catches it. Red if `get` reads it as a pin (the row would look current), or the backfill
    stamps over it. The stored text is compared, since Python reads 1.0 and 1 as equal."""
    from uuid import uuid4

    from services.api.studio_recipes import reconcile_recipe_pins

    from ontology.packs import load_deployment_ontology

    row = await _published_with_pins(
        store, "Pin is a decimal one", {}, git_path=f"legacy/decimal-pin-{uuid4().hex[:8]}.yaml"
    )
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = '{\"fibo\": 1.0}'::jsonb "
            "WHERE recipe_id = $1",
            row.recipe_id,
        )
    assert load_deployment_ontology().packs["fibo"] == 1, "the premise: 1.0 equals it by value"
    assert (await store.get(row.recipe_id)).pack_versions is None

    def read_recipe(git_path: str) -> Recipe | None:
        return _write_legacy_recipe(tmp_path, "no-pack", pack=None)

    flagged = await reconcile_recipe_pins(store, load_deployment_ontology(), read_recipe)

    assert row.recipe_id in flagged
    assert (await store.get(row.recipe_id)).status is StudioRecipeStatus.FLAGGED
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        stored = await conn.fetchval(
            "SELECT pack_versions::text FROM studio_recipes WHERE recipe_id = $1", row.recipe_id
        )
    assert stored == '{"fibo": 1.0}'


# --- ADR-127 decision 5 (B2-5): a draft carries `deduplicate` ------------------------------------


def _dedupe() -> object:
    from schemas.ingest import DeduplicateConfig, FieldBinding

    return DeduplicateConfig(key=[FieldBinding(field="a_party"), FieldBinding(field="b_party")])


async def test_a_deduplicate_is_saved_with_the_draft_read_back_and_left_alone_by_other_edits(
    store: StudioRecipeStore,
) -> None:
    draft = await store.create_draft(
        AUTHOR, label="x", connector_profile="generic-csv", source_location=None, handling={},
        legal_basis=None, deduplicate=_dedupe(),  # type: ignore[arg-type]
    )  # fmt: skip
    assert draft.deduplicate == _dedupe()
    # Another edit (a new label) leaves it: `None` is "unchanged".
    again = await store.update_draft(draft.recipe_id, AUTHOR, label="renamed")
    assert again.deduplicate == _dedupe()
    # Map's save carries it too (it rewrites the row template's half of the content).
    from schemas.ingest import RowTemplate

    after_map = await store.update_row_template(
        draft.recipe_id, AUTHOR, row_template=RowTemplate(entities=[]), unmapped_fields=[]
    )
    assert after_map.deduplicate == _dedupe()


async def test_a_deduplicate_is_replaced_and_an_empty_key_clears_it(
    store: StudioRecipeStore,
) -> None:
    from schemas.ingest import DeduplicateConfig, FieldBinding

    draft = await store.create_draft(
        AUTHOR, label="x", connector_profile="generic-csv", source_location=None, handling={},
        legal_basis=None,
    )  # fmt: skip
    assert draft.deduplicate is None
    changed = DeduplicateConfig(key=[FieldBinding(field="seq")])
    assert (
        await store.update_draft(draft.recipe_id, AUTHOR, deduplicate=changed)
    ).deduplicate == changed
    cleared = await store.update_draft(
        draft.recipe_id, AUTHOR, deduplicate=DeduplicateConfig(key=[])
    )
    assert cleared.deduplicate is None


async def test_a_deduplicate_is_kept_on_a_new_version(store: StudioRecipeStore) -> None:
    draft = await _verified_draft(store, deduplicate=_dedupe())
    assert draft.deduplicate == _dedupe()
    published = await store.publish(
        draft.recipe_id, AUTHOR, ontology_version=3, pack_versions={},
        git_path="recipes/some-id.yaml", schedule_cron=None, schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )  # fmt: skip
    assert published.deduplicate == _dedupe()
    new_version = await store.create_new_version(
        published.recipe_id, AUTHOR, now=datetime(2026, 1, 3, tzinfo=UTC)
    )
    assert new_version.deduplicate == _dedupe(), "as `units` and `handling_columns` are kept"


# --- ADR-127 Amendment 23, B2-10a: the two methods the Prison Intelligence seed uses --------------
# (`enter_published_for_seed`, `restore_to_draft`); the refusals that run before any write are in
# `test_studio_recipes_seed_refusals.py` (pure). Live: the rows, the status flips and the
# transaction are the subject. What a mistake would do, and the case that catches it:
#
# Entering a committed recipe as published:
# - the id or the version not kept (`test_the_recipe_is_entered_published_keeping_its_id_and_version`);
# - the content not the file's (`test_the_content_is_the_files_and_reads_back_as_it_runs`);
# - a schedule set, so the scheduler runs it on its own
#   (`test_no_schedule_is_set_and_the_recipe_feeds_its_dataset`);
# - the same content entered again changing the row, or refused
#   (`test_the_same_content_again_leaves_the_row_as_it_was`);
# - different content at the same version overwriting the row, or accepted silently
#   (`test_different_content_at_the_same_version_is_refused_by_name_and_the_row_is_kept`);
# - a refused recipe leaving a row behind (`test_a_refused_recipe_leaves_no_row`).
#
# Restoring a recipe to a draft:
# - the draft not at the next version, not in the unit `verify`, or still mapped
#   (`test_the_restored_draft_is_unmapped_at_the_next_version_in_the_unit`);
# - the previous version left published, so `feeding` still lists the recipe
#   (`test_after_a_restore_feeding_lists_none_and_the_drafts_list_has_exactly_one`);
# - the previous version superseded in a transaction of its own, so a failure between the two leaves
#   a recipe that is superseded with no draft
#   (`test_a_restore_that_fails_leaves_the_previous_version_as_it_was`);
# - a restore that only works for a published version
#   (`test_a_flagged_version_and_a_draft_are_restored_too`).

SEED_FIXTURES = Path(__file__).resolve().parents[4] / "OspreyFlow_Core/packages/demo_fixtures"
SEED_ONTOLOGY = load_deployment_ontology()
SEED_SCHEME = load_uk_le_scheme()
SEED_NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)
SEED_LOCATION = "uploaded/prison-intelligence/pid_conflicts.csv"


def fresh_recipe() -> Recipe:
    """The committed R15, under an id of its own so each case has its own row."""
    return load_recipe(SEED_FIXTURES / "pid_conflicts_recipe.yaml").model_copy(update={"id": new_id()})


def reader_of(dataset: str, unit: str = "verify") -> Principal:
    return Principal(
        id="osprey-demo-engineer", clearance="OFFICIAL", org_unit=unit, roles=["data_engineer"],
        datasets=[dataset],
    )  # fmt: skip


async def enter(
    store: StudioRecipeStore, rec: Recipe, *, dataset: str = "prison-intelligence", now: datetime = SEED_NOW
):  # type: ignore[no-untyped-def]
    return await store.enter_published_for_seed(
        rec, source_location=SEED_LOCATION, git_path=f"recipes/{rec.id}.yaml", dataset_id=dataset,
        owning_unit="verify", published_by="osprey-demo-engineer", now=now, ontology=SEED_ONTOLOGY,
        scheme=SEED_SCHEME,
    )


# --- entering a committed recipe as published ---------------------------------------------------


async def test_the_recipe_is_entered_published_keeping_its_id_and_version(
    store: StudioRecipeStore,
) -> None:
    rec = fresh_recipe()
    entered = await enter(store, rec)
    assert (entered.recipe_id, entered.version) == (rec.id, rec.version)
    assert entered.status is StudioRecipeStatus.PUBLISHED
    assert entered.dataset_id == "prison-intelligence" and entered.owning_unit == "verify"
    assert entered.git_path == f"recipes/{rec.id}.yaml"
    assert entered.ontology_version == SEED_ONTOLOGY.version == rec.ontology_version
    assert entered.pack_versions == rec.pack_versions == {"niem": SEED_ONTOLOGY.packs["niem"]}
    assert entered.published_by == "osprey-demo-engineer" and entered.published_at == SEED_NOW
    assert entered.verified_at == SEED_NOW and entered.label == rec.label
    assert (await store.get(rec.id)) == entered


async def test_the_content_is_the_files_and_reads_back_as_it_runs(store: StudioRecipeStore) -> None:
    rec = fresh_recipe()
    entered = await enter(store, rec)
    assert entered.connector_profile == rec.connector.profile
    assert entered.source_location == SEED_LOCATION
    assert entered.legal_basis == rec.defaults.legal_basis
    assert entered.row_template == rec.row_template
    assert entered.unmapped_fields == rec.unmapped_fields
    assert entered.deduplicate == rec.deduplicate and entered.deduplicate is not None
    assert entered.pipeline is None
    expected_handling = {
        **rec.defaults.handling,
        "units": rec.defaults.units,
        "handling_columns": rec.defaults.handling_columns,
    }
    assert entered.handling == expected_handling
    assert entered.ready_for_profile is True


async def test_no_schedule_is_set_and_the_recipe_feeds_its_dataset(store: StudioRecipeStore) -> None:
    rec = fresh_recipe()
    entered = await enter(store, rec)
    assert (entered.schedule_cron, entered.schedule_watch, entered.schedule_owner) == (None,) * 3
    assert entered.schedule_case is None and entered.schedule_paused is False
    assert rec.id not in [r.recipe_id for r in await store.scheduled()]
    fed = [r.recipe_id for r in await store.feeding(["prison-intelligence"])]
    assert fed.count(rec.id) == 1
    assert rec.id not in [r.recipe_id for r in await store.feeding(["another-dataset"])]


async def test_the_same_content_again_leaves_the_row_as_it_was(store: StudioRecipeStore) -> None:
    rec = fresh_recipe()
    first = await enter(store, rec)
    again = await enter(store, rec, now=SEED_NOW + timedelta(days=1))
    assert again == first
    assert again.published_at == SEED_NOW, "the row was not rewritten"
    async with store._pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM studio_recipes WHERE recipe_id = $1", rec.id) == 1


async def test_different_content_at_the_same_version_is_refused_by_name_and_the_row_is_kept(
    store: StudioRecipeStore,
) -> None:
    rec = fresh_recipe()
    first = await enter(store, rec)
    changed = rec.model_copy(update={"label": "A different label"})
    with pytest.raises(SeededRecipeContentDiffers) as refused:
        await enter(store, changed)
    assert rec.id in str(refused.value) and str(rec.version) in str(refused.value)
    # a different source file is different content too
    with pytest.raises(SeededRecipeContentDiffers):
        await store.enter_published_for_seed(
            rec, source_location="uploaded/prison-intelligence/elsewhere.csv",
            git_path=f"recipes/{rec.id}.yaml", dataset_id="prison-intelligence",
            owning_unit="verify", published_by="osprey-demo-engineer", now=SEED_NOW, ontology=SEED_ONTOLOGY,
            scheme=SEED_SCHEME,
        )  # fmt: skip
    # and so is a different duplicate key
    with pytest.raises(SeededRecipeContentDiffers):
        await enter(store, rec.model_copy(update={"deduplicate": None}))
    assert (await store.get(rec.id)) == first


async def test_a_refused_recipe_leaves_no_row(store: StudioRecipeStore) -> None:
    rec = fresh_recipe().model_copy(update={"pack_versions": {"niem": 0}})
    with pytest.raises(StaleRecipeError):
        await enter(store, rec)
    with pytest.raises(StudioRecipeNotFoundError):
        await store.get(rec.id)


# --- restoring a recipe to a draft ---------------------------------------------------------------


def starting_pipeline(location: str = SEED_LOCATION) -> PipelineGraph:
    """R9's starting pipeline as the seed writes it (ADR-127 Amendment 25): a `domain_model` node
    for NIEM and one source at the reports file through `generic-csv`."""
    return PipelineGraph(
        nodes=[
            PipelineNode(
                id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model",
                config={"pack": "niem"},
            ),
            PipelineNode(
                id="source", kind=PipelineNodeKind.SOURCE, label="Intelligence reports",
                config={"connector_profile": "generic-csv", "source_location": location},
            ),
        ],
        edges=[PipelineEdge(source="domain", target="source")],
    )


async def test_the_restored_draft_is_unmapped_at_the_next_version_in_the_unit(
    store: StudioRecipeStore,
) -> None:
    rec = fresh_recipe()
    published = await enter(store, rec)
    assert published.row_template is not None and published.deduplicate is not None
    draft = await store.restore_to_draft(rec.id, created_by="osprey-demo-engineer", owning_unit="verify", now=SEED_NOW,
        pipeline=starting_pipeline())
    assert (draft.recipe_id, draft.version) == (rec.id, rec.version + 1)
    assert draft.status is StudioRecipeStatus.DRAFT and draft.owning_unit == "verify"
    assert draft.row_template is None and draft.unmapped_fields == [] and draft.deduplicate is None
    assert draft.verified_at is None and draft.git_path is None and draft.published_at is None
    assert draft.created_by == "osprey-demo-engineer"
    # what Connect holds is kept: the source, the connector, the marking and its declarations
    assert draft.connector_profile == published.connector_profile
    assert draft.source_location == published.source_location
    assert draft.handling == published.handling and draft.legal_basis == published.legal_basis
    assert draft.dataset_id == "prison-intelligence"
    assert (await store.get(rec.id)) == draft
    # the pipeline is the one the caller gave, whatever the previous version held (this one, entered
    # from a file, held none)
    assert published.pipeline is None
    assert draft.pipeline == starting_pipeline()


async def test_the_restored_draft_holds_exactly_the_pipeline_it_is_given(
    store: StudioRecipeStore,
) -> None:
    """A second restore, over a draft that holds another pipeline, replaces it whole: it is never
    copied forward from the version before."""
    rec = fresh_recipe()
    await enter(store, rec)
    other = starting_pipeline("uploaded/prison-intelligence/elsewhere.csv")
    first = await store.restore_to_draft(
        rec.id, created_by="w", owning_unit="verify", now=SEED_NOW, pipeline=other
    )
    assert first.pipeline == other
    second = await store.restore_to_draft(
        rec.id, created_by="w", owning_unit="verify", now=SEED_NOW, pipeline=starting_pipeline()
    )
    assert second.pipeline == starting_pipeline() and second.pipeline != other


async def test_after_a_restore_feeding_lists_none_and_the_drafts_list_has_exactly_one(
    store: StudioRecipeStore,
) -> None:
    rec = fresh_recipe()
    await enter(store, rec)
    assert [r.recipe_id for r in await store.feeding(["prison-intelligence"])].count(rec.id) == 1
    await store.restore_to_draft(rec.id, created_by="osprey-demo-engineer", owning_unit="verify", now=SEED_NOW,
        pipeline=starting_pipeline())
    assert rec.id not in [r.recipe_id for r in await store.feeding(["prison-intelligence"])]
    drafts = [d for d in await store.list_drafts(reader_of("prison-intelligence")) if d.recipe_id == rec.id]
    assert len(drafts) == 1 and drafts[0].version == rec.version + 1
    async with store._pool.acquire() as conn:
        statuses = {
            r["version"]: r["status"]
            for r in await conn.fetch("SELECT version, status FROM studio_recipes WHERE recipe_id = $1", rec.id)
        }
    assert statuses == {rec.version: "superseded", rec.version + 1: "draft"}


async def test_a_restore_that_fails_leaves_the_previous_version_as_it_was(
    store: StudioRecipeStore,
) -> None:
    """The draft's insert fails (a unit the table refuses): the previous version's flip to
    superseded was in the same transaction, so it is rolled back and the recipe still feeds."""
    rec = fresh_recipe()
    await enter(store, rec)
    with pytest.raises(asyncpg.PostgresError):
        await store.restore_to_draft(
            rec.id, created_by="osprey-demo-engineer", owning_unit=None, now=SEED_NOW,  # type: ignore[arg-type]
            pipeline=starting_pipeline(),
        )
    current = await store.get(rec.id)
    assert (current.version, current.status) == (rec.version, StudioRecipeStatus.PUBLISHED)
    assert [r.recipe_id for r in await store.feeding(["prison-intelligence"])].count(rec.id) == 1


async def test_a_flagged_version_and_a_draft_are_restored_too(store: StudioRecipeStore) -> None:
    flagged = fresh_recipe()
    await enter(store, flagged)
    async with store._pool.acquire() as conn:
        await conn.execute(
            "UPDATE studio_recipes SET status = 'flagged' WHERE recipe_id = $1", flagged.id
        )
    again = await store.restore_to_draft(flagged.id, created_by="w", owning_unit="verify", now=SEED_NOW,
        pipeline=starting_pipeline())
    assert again.version == 2 and again.status is StudioRecipeStatus.DRAFT
    # a draft restored: the draft is superseded, and a fresh one stands, so there is exactly one
    twice = await store.restore_to_draft(flagged.id, created_by="w", owning_unit="verify", now=SEED_NOW,
        pipeline=starting_pipeline())
    assert twice.version == 3 and twice.status is StudioRecipeStatus.DRAFT
    drafts = [d for d in await store.list_drafts(reader_of("prison-intelligence")) if d.recipe_id == flagged.id]
    assert [d.version for d in drafts] == [3]
    async with store._pool.acquire() as conn:
        statuses = {
            r["version"]: r["status"]
            for r in await conn.fetch("SELECT version, status FROM studio_recipes WHERE recipe_id = $1", flagged.id)
        }
    assert statuses == {1: "superseded", 2: "superseded", 3: "draft"}


async def test_restoring_a_recipe_that_does_not_exist_is_refused(store: StudioRecipeStore) -> None:
    with pytest.raises(StudioRecipeNotFoundError):
        await store.restore_to_draft(new_id(), created_by="w", owning_unit="verify", now=SEED_NOW,
        pipeline=starting_pipeline())


# --- Amendment 26: "the same content" is the whole row ---------------------------------------------


@pytest.mark.parametrize(
    ("column", "stale", "named"),
    [
        ("pack_versions", "'{\"niem\": 2}'::jsonb", "pack_versions"),
        ("ontology_version", "15", "ontology_version"),
        ("dataset_id", "'another-dataset'", "dataset_id"),
        ("owning_unit", "'another-unit'", "owning_unit"),
        ("git_path", "'recipes/elsewhere.yaml'", "git_path"),
        ("status", "'flagged'", "status"),
    ],
)
async def test_a_reseed_over_a_row_that_differs_in_any_column_is_refused_by_name(
    store: StudioRecipeStore, column: str, stale: str, named: str
) -> None:
    rec = fresh_recipe()
    await enter(store, rec)
    async with store._pool.acquire() as conn:
        await conn.execute(f"UPDATE studio_recipes SET {column} = {stale} WHERE recipe_id = $1", rec.id)
        before = await conn.fetchrow("SELECT * FROM studio_recipes WHERE recipe_id = $1", rec.id)
    with pytest.raises(SeededRecipeContentDiffers) as refused:
        await enter(store, rec)
    assert named in str(refused.value) and rec.id in str(refused.value)
    async with store._pool.acquire() as conn:
        assert await conn.fetchrow("SELECT * FROM studio_recipes WHERE recipe_id = $1", rec.id) == before


async def test_a_second_published_version_of_a_recipe_is_refused(store: StudioRecipeStore) -> None:
    rec = fresh_recipe()
    await enter(store, rec)
    with pytest.raises(SeededRecipeAnotherPublished) as refused:
        await enter(store, rec.model_copy(update={"version": 2}))
    assert rec.id in str(refused.value)
    async with store._pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM studio_recipes WHERE recipe_id = $1", rec.id)
    assert count == 1


async def test_entering_returns_the_version_entered_and_not_the_latest(
    store: StudioRecipeStore,
) -> None:
    rec = fresh_recipe()
    await enter(store, rec)
    async with store._pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO studio_recipes (recipe_id, version, label, status, content, owning_unit, "
            "created_by, created_at, dataset_id) SELECT recipe_id, 2, label, 'draft', content, "
            "owning_unit, created_by, created_at, dataset_id FROM studio_recipes "
            "WHERE recipe_id = $1 AND version = 1",
            rec.id,
        )
    again = await enter(store, rec)
    assert again.version == rec.version == 1 and again.status is StudioRecipeStatus.PUBLISHED


# --- `check_seeded_row`: the comparison on its own (ADR-127 Amendment 30) -------------------------
# The seed makes it before it commits a recipe's file, so a committed file never differs from its row.
# It reads, refuses by name exactly as `enter_published_for_seed` does, and writes nothing.


async def compare(store: StudioRecipeStore, rec: Recipe, **changes: str) -> None:
    arguments = {
        "source_location": SEED_LOCATION, "git_path": f"recipes/{rec.id}.yaml",
        "dataset_id": "prison-intelligence", "owning_unit": "verify",
    } | changes  # fmt: skip
    await store.check_seeded_row(rec, **arguments)


async def test_the_comparison_passes_for_no_row_and_for_the_same_row_and_writes_nothing(
    store: StudioRecipeStore,
) -> None:
    rec = fresh_recipe()
    await compare(store, rec)  # no row yet
    with pytest.raises(StudioRecipeNotFoundError):
        await store.get(rec.id)
    first = await enter(store, rec)
    await compare(store, rec)  # the row it would write
    assert (await store.get(rec.id)) == first
    async with store._pool.acquire() as conn:
        assert (
            await conn.fetchval("SELECT count(*) FROM studio_recipes WHERE recipe_id = $1", rec.id)
            == 1
        )


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"source_location": "uploaded/prison-intelligence/elsewhere.csv"}, "content"),
        ({"git_path": "recipes/elsewhere.yaml"}, "git_path"),
        ({"owning_unit": "another-unit"}, "owning_unit"),
        ({"dataset_id": "another-dataset"}, "dataset_id"),
    ],
)
async def test_the_comparison_refuses_a_row_that_differs_by_name_and_leaves_it_as_it_is(
    store: StudioRecipeStore, change: dict[str, str], named: str
) -> None:
    rec = fresh_recipe()
    first = await enter(store, rec)
    with pytest.raises(SeededRecipeContentDiffers) as refused:
        await compare(store, rec, **change)
    assert named in str(refused.value) and rec.id in str(refused.value)
    assert (await store.get(rec.id)) == first


async def test_the_comparison_refuses_what_entering_refuses(store: StudioRecipeStore) -> None:
    rec = fresh_recipe()
    await enter(store, rec)
    with pytest.raises(SeededRecipeContentDiffers):
        await compare(store, rec.model_copy(update={"label": "A different label"}))
    with pytest.raises(SeededRecipeAnotherPublished):
        await compare(store, rec.model_copy(update={"version": 2}))
    # whatever the comparison refuses, entering refuses too, and what it passes, entering writes
    with pytest.raises(SeededRecipeContentDiffers):
        await enter(store, rec.model_copy(update={"label": "A different label"}))
    with pytest.raises(SeededRecipeAnotherPublished):
        await enter(store, rec.model_copy(update={"version": 2}))
    async with store._pool.acquire() as conn:
        assert (
            await conn.fetchval("SELECT count(*) FROM studio_recipes WHERE recipe_id = $1", rec.id)
            == 1
        )


# --- `enter_draft_for_seed`: R9's first draft (ADR-127 Amendment 23, "R9's draft") ----------------
# The refusals and the "left as it is" case are pure (`test_studio_recipes_seed_refusals.py`); live,
# the row itself, what `feeding` and `list_drafts` then say, and the restore that follows it.


def reports_recipe() -> Recipe:
    """The committed reports recipe, under an id of its own so each case has its own row."""
    return load_recipe(SEED_FIXTURES / "pid_intel_reports_recipe.yaml").model_copy(
        update={"id": new_id()}
    )


async def test_the_first_draft_is_an_unmapped_draft_that_the_drafts_list_has_and_feeding_has_not(
    store: StudioRecipeStore,
) -> None:
    rec = reports_recipe()
    draft = await store.enter_draft_for_seed(
        rec, source_location=SEED_LOCATION, dataset_id="prison-intelligence",
        owning_unit="verify", created_by="osprey-demo-engineer", now=SEED_NOW,
        pipeline=starting_pipeline(),
    )  # fmt: skip
    assert (draft.recipe_id, draft.version, draft.status) == (
        rec.id, rec.version, StudioRecipeStatus.DRAFT,
    )  # fmt: skip
    assert draft.row_template is None and draft.unmapped_fields == [] and draft.deduplicate is None
    assert draft.pipeline == starting_pipeline() and draft.ready_for_profile
    assert draft.dataset_id == "prison-intelligence" and draft.owning_unit == "verify"
    assert rec.id not in [r.recipe_id for r in await store.feeding(["prison-intelligence"])]
    drafts = [
        d for d in await store.list_drafts(reader_of("prison-intelligence")) if d.recipe_id == rec.id
    ]
    assert len(drafts) == 1
    assert await store.get(rec.id) == draft


async def test_a_second_entry_leaves_the_row_and_a_restore_then_follows_it(
    store: StudioRecipeStore,
) -> None:
    rec = reports_recipe()

    async def once() -> Any:
        return await store.enter_draft_for_seed(
            rec, source_location=SEED_LOCATION, dataset_id="prison-intelligence",
            owning_unit="verify", created_by="osprey-demo-engineer", now=SEED_NOW,
            pipeline=starting_pipeline(),
        )  # fmt: skip

    first = await once()
    again = await once()
    assert again == first
    async with store._pool.acquire() as conn:
        rows = await conn.fetch("SELECT version FROM studio_recipes WHERE recipe_id = $1", rec.id)
    assert [r["version"] for r in rows] == [rec.version]
    restored = await store.restore_to_draft(
        rec.id, created_by="osprey-demo-engineer", owning_unit="verify", now=SEED_NOW,
        pipeline=starting_pipeline(),
    )
    assert restored.version == rec.version + 1
    assert (await once()).version == rec.version + 1, "a reseed after a reset leaves the restore"
