"""Publish (`spec/09_INGEST_STUDIO.md` §6) end to end, against a live
Postgres (`StudioRecipeStore`) and a live ArcadeDB (`GraphPort`) — the two
things `tests/services/api/test_studio_publish_routes.py` deliberately
fakes away. Two things proven here that a route-level test with fakes
cannot: that a real run of a published recipe stamps every element with
`load_id`/`recipe_id`/`recipe_version` (`01_DOMAIN_MODEL.md` §2.4), and
that `StudioRecipeStore.flag_stale` (the ontology → dependent-recipe
reverse index, §6) doesn't just set a status column — it actually stops
`run_published_recipe` from running the recipe, via
`RecipeNotRunnableError`, before the engine's own `StaleRecipeError` would
otherwise be the only thing standing in the way.
"""

from __future__ import annotations

import csv
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from services.api.config import PostgresConfig
from services.api.studio_publish import (
    RecipeNotRunnableError,
    build_recipe,
    run_published_recipe,
    write_and_commit_recipe,
)
from services.api.studio_recipes import StudioRecipeStore

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology
from schemas.domain import OntologySchema, Principal
from schemas.ingest import (
    FieldBinding,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    RecipeEntity,
    RowTemplate,
)

AUTHOR = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_author"]
)
APPROVER = Principal(
    id="approver-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_approver"]
)
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["loader"])

_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def _row_template() -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Endpoint",
                match_on="value_normalised",
                on_match="reference",
                properties={
                    "value_normalised": FieldBinding(field="a_party"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
            )
        ]
    )


@pytest.fixture
async def store():
    s = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    return repo


def _pipeline_naming(pack: str) -> PipelineGraph:
    return PipelineGraph(
        nodes=[
            PipelineNode(
                id="domain",
                kind=PipelineNodeKind.DOMAIN_MODEL,
                label="Domain",
                config={"pack": pack},
            )
        ],
        edges=[],
    )


async def _publish_a_verified_recipe(
    store: StudioRecipeStore,
    tmp_path: Path,
    git_repo: Path,
    *,
    ontology_version: int,
    label: str,
    pipeline: PipelineGraph | None = None,
    ontology: OntologySchema | None = None,
    row_template: RowTemplate | None = None,
):
    csv_path = tmp_path / f"{label}.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["a_party"])
        writer.writeheader()
        writer.writerows([{"a_party": "07960112334"}])

    draft = await store.create_draft(
        AUTHOR,
        label=label,
        connector_profile="generic-csv",
        source_location=str(csv_path),
        handling=_HANDLING,
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    draft = await store.update_row_template(
        draft.recipe_id,
        AUTHOR,
        row_template=row_template or _row_template(),
        unmapped_fields=[],
    )
    if pipeline is not None:
        draft = await store.update_pipeline(draft.recipe_id, AUTHOR, pipeline=pipeline)
    await store.mark_verified(draft.recipe_id, draft.version, now=datetime.now(UTC))
    draft = await store.get(draft.recipe_id)

    from services.api.studio_publish import pack_versions_for

    # A recipe with no pipeline names no pack, so it pins none (ADR-120 D10).
    pack_versions = (
        pack_versions_for(draft.pipeline, draft.row_template, ontology)
        if ontology is not None
        else {}
    )
    built = build_recipe(
        draft,
        ontology_version=ontology_version,
        pack_versions=pack_versions,
        schedule_cron=None,
        schedule_watch=None,
    )
    git_path = await write_and_commit_recipe(built, repo_root=git_repo)
    return await store.publish(
        draft.recipe_id,
        APPROVER,
        ontology_version=ontology_version,
        pack_versions=pack_versions,
        git_path=git_path,
        schedule_cron=None,
        schedule_watch=None,
        now=datetime.now(UTC),
    )


async def test_running_a_published_recipe_attributes_load_id_recipe_id_and_version(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    published = await _publish_a_verified_recipe(
        store, tmp_path, git_repo, ontology_version=ontology.version, label="attribution"
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        report = await run_published_recipe(
            published,
            LOADER,
            graph=graph,
            ontology=ontology,
            load_id="load-attribution-1",
            investigation_scope="case-1",
            repo_root=git_repo,
        )
        assert report.nodes_created == 1
        assert report.recipe_id == published.recipe_id
        assert report.recipe_version == published.version

        node = await graph.find_node("Endpoint", "value_normalised", "07960112334", LOADER)
        assert node is not None
        assert node.audit.load_id == "load-attribution-1"
        assert node.audit.recipe_id == published.recipe_id
        assert node.audit.recipe_version == published.version


async def test_flagging_a_recipe_after_an_ontology_edit_actually_blocks_its_run(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    published = await _publish_a_verified_recipe(
        store, tmp_path, git_repo, ontology_version=ontology.version, label="flagging"
    )

    # The ontology "edits" (a new version ships) — the registry's reverse
    # index is what `services/api/app.py`'s `lifespan` runs on every
    # process start (the deployment's own "ontology reload" event).
    flagged_ids = await store.flag_stale(
        current_ontology_version=ontology.version + 1, current_pack_versions={}
    )
    assert published.recipe_id in flagged_ids

    flagged = await store.get(published.recipe_id)
    assert flagged.status.value == "flagged"

    async with arcadedb_adapter(ontology, scheme) as graph:
        with pytest.raises(RecipeNotRunnableError):
            await run_published_recipe(
                flagged,
                LOADER,
                graph=graph,
                ontology=ontology,
                load_id="load-flagged-1",
                investigation_scope="case-1",
                repo_root=git_repo,
            )

        # Never even reached `GraphPort` — nothing was written.
        node = await graph.find_node("Endpoint", "value_normalised", "07960112334", LOADER)
        assert node is None


async def test_publishing_stamps_the_pack_versions_in_the_row_and_the_committed_file(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 D10: the pin is in both places a run reads it from. Red if publish stamps the row
    but not the committed YAML (a run reads the file), or the file but not the row (the flagging
    reverse index reads the row), or pins a version other than the loaded one."""
    from services.ingest.recipe_loader import load_recipe

    ontology = load_deployment_ontology()
    published = await _publish_a_verified_recipe(
        store,
        tmp_path,
        git_repo,
        ontology_version=ontology.version,
        label="pinning",
        pipeline=_pipeline_naming("niem"),
        ontology=ontology,
    )

    assert published.pack_versions == {"niem": 3}
    assert (await store.get(published.recipe_id)).pack_versions == {"niem": 3}
    assert published.git_path is not None
    committed = load_recipe(git_repo / published.git_path)
    assert committed.pack_versions == {"niem": 3}


async def test_a_pack_bump_blocks_the_run_of_a_recipe_naming_that_pack(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 D10: a pack bump is an ontology edit as far as a pinned recipe is concerned. Red if
    `flag_stale` ignores the pins, or if a flagged recipe still reaches the graph."""
    ontology = load_deployment_ontology()
    scheme = load_uk_le_scheme()
    published = await _publish_a_verified_recipe(
        store,
        tmp_path,
        git_repo,
        ontology_version=ontology.version,
        label="pack-bump",
        pipeline=_pipeline_naming("niem"),
        ontology=ontology,
    )

    flagged_ids = await store.flag_stale(
        ontology.version, {**ontology.packs, "niem": ontology.packs["niem"] + 1}
    )
    assert published.recipe_id in flagged_ids

    flagged = await store.get(published.recipe_id)
    assert flagged.status.value == "flagged"

    async with arcadedb_adapter(ontology, scheme) as graph:
        with pytest.raises(RecipeNotRunnableError):
            await run_published_recipe(
                flagged,
                LOADER,
                graph=graph,
                ontology=ontology,
                load_id="load-pack-bump-1",
                investigation_scope="case-1",
                repo_root=git_repo,
            )

        # Never even reached `GraphPort` — nothing was written.
        node = await graph.find_node("Endpoint", "value_normalised", "07960112334", LOADER)
        assert node is None


def test_build_recipe_without_pack_versions_is_refused() -> None:
    """ADR-120 Amendment 1, decision 5: `build_recipe` takes `pack_versions` with no default, so a
    publish can never build a recipe that says nothing about its pins. Red if a default is added
    (a fresh recipe would then be mistaken for a legacy one at the next start's backfill)."""
    from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

    draft = StudioRecipeDraft(
        recipe_id="r-no-pins",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="No pins",
        connector_profile="generic-csv",
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        row_template=_row_template(),
    )
    with pytest.raises(TypeError, match="pack_versions"):
        build_recipe(draft, ontology_version=16, schedule_cron=None, schedule_watch=None)  # type: ignore[call-arg]


def _account_template() -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Account",
                match_on="account_number",
                on_match="reference",
                properties={"account_number": FieldBinding(field="a_party")},
            )
        ]
    )


async def _legacy_account_recipe(
    store: StudioRecipeStore,
    tmp_path: Path,
    git_repo: Path,
    *,
    label: str,
    file_pins: dict[str, int] | None,
    row_pins: dict[str, int] | None,
):
    """A recipe writing FIBO's `Account` under `pole`, published through the real helper (so it
    is pinned in both places), then made into what ADR-120 Amendment 2 describes: the committed
    file rewritten with `file_pins` (no key at all when None) and the row's pins set by direct SQL
    to `row_pins`, as the backfill would have."""
    import json

    import yaml

    ontology = load_deployment_ontology()
    published = await _publish_a_verified_recipe(
        store,
        tmp_path,
        git_repo,
        ontology_version=ontology.version,
        label=label,
        pipeline=_pipeline_naming("pole"),
        ontology=ontology,
        row_template=_account_template(),
    )
    assert published.pack_versions == {"fibo": 1}
    assert published.git_path is not None
    path = git_repo / published.git_path
    document = yaml.safe_load(path.read_text())
    document.pop("pack_versions", None)
    if file_pins is not None:
        document["pack_versions"] = file_pins
    path.write_text(yaml.safe_dump(document))
    async with store._pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE studio_recipes SET pack_versions = $1::jsonb WHERE recipe_id = $2",
            None if row_pins is None else json.dumps(row_pins),
            published.recipe_id,
        )
    return await store.get(published.recipe_id)


async def _run_legacy(row, git_repo: Path):  # type: ignore[no-untyped-def]
    ontology = load_deployment_ontology()
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await run_published_recipe(
            row,
            LOADER,
            graph=graph,
            ontology=ontology,
            load_id="load-legacy-pins",
            investigation_scope="case-1",
            repo_root=git_repo,
        )
        node = await graph.find_node("Account", "account_number", "07960112334", LOADER)
        return report, node


async def test_a_backfilled_row_whose_file_has_no_pins_runs(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 Amendment 2, decision 1: the backfill stamps the row, but a run loads the file. Red
    if a run takes only the file's pins, so every legacy recipe that writes FIBO types (its file
    committed before pinning) is refused while its row reads as published."""
    row = await _legacy_account_recipe(
        store, tmp_path, git_repo, label="legacy-no-file-pins", file_pins=None,
        row_pins={"fibo": 1},
    )  # fmt: skip

    report, node = await _run_legacy(row, git_repo)

    assert report.nodes_created == 1
    assert node is not None


async def test_a_file_with_its_own_pins_wins_over_the_row_s(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 Amendment 2, decision 1: pins written in the file always win. Red if the row's pins
    replace the file's (the row says fibo 9, which the deployment does not carry, so the run would
    be refused although the file is correct)."""
    row = await _legacy_account_recipe(
        store, tmp_path, git_repo, label="file-pins-win", file_pins={"fibo": 1},
        row_pins={"fibo": 9},
    )  # fmt: skip

    report, node = await _run_legacy(row, git_repo)

    assert report.nodes_created == 1
    assert node is not None


async def test_a_row_and_file_both_unpinned_writing_fibo_is_refused(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 Amendment 2, decision 2: nothing unpinned that writes a pack can run. Red if the
    fallback to the row's pins invents pins when the row has none either, or the engine lets an
    unpinned recipe writing FIBO's `Account` through."""
    from services.ingest.engine import StaleRecipeError

    row = await _legacy_account_recipe(
        store, tmp_path, git_repo, label="both-unpinned", file_pins=None, row_pins=None
    )
    assert row.pack_versions is None

    with pytest.raises(StaleRecipeError, match="not pinned"):
        await _run_legacy(row, git_repo)
