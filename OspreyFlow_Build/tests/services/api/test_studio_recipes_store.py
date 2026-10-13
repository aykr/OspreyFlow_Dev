"""`services/api/studio_recipes.py`'s `StudioRecipeStore` — direct,
live-Postgres correctness, mirroring `test_sites_store.py`'s own
discipline: the JSON-encoded `content` round trip and the existence-leak
behaviour deserve a direct proof rather than only exercise through
route-level fakes. `spec/09_INGEST_STUDIO.md` §2, §6."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.studio_recipes import (
    StudioRecipeCannotVersionError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
    StudioRecipeStore,
)

from schemas.domain import Principal
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
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
        draft.recipe_id, AUTHOR, ontology_version=3, git_path="recipes/x.yaml",
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
        draft.recipe_id, AUTHOR, ontology_version=3, git_path="recipes/y.yaml",
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
            draft.recipe_id, AUTHOR, ontology_version=3, git_path="recipes/f.yaml",
            schedule_cron=None, schedule_watch=None, now=datetime(2026, 1, 2, tzinfo=UTC),
        ))  # fmt: skip
    still_a_draft = await store.create_draft(
        AUTHOR.model_copy(update={"datasets": [mine]}), label="Unpublished", **_CONNECT
    )
    feeding = [r.recipe_id for r in await store.feeding([mine])]
    assert feeding == [published[0].recipe_id]
    assert still_a_draft.recipe_id not in feeding
    assert await store.feeding([]) == []


async def test_create_new_version_supersedes_the_published_row_and_opens_a_draft(
    store: StudioRecipeStore,
) -> None:
    draft = await _verified_draft(store)
    published = await store.publish(
        draft.recipe_id,
        AUTHOR,
        ontology_version=3,
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
        git_path="recipes/current.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    flagged_ids = await store.flag_stale(current_ontology_version=4)
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
        ontology_version=16,
        git_path="recipes/p.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    with pytest.raises(StudioRecipeNotADraftError):
        await store.update_pipeline(made.recipe_id, AUTHOR, pipeline=_chain_pipeline())
