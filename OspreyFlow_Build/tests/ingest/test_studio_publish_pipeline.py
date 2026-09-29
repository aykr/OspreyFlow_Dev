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
from schemas.domain import Principal
from schemas.ingest import FieldBinding, RecipeEntity, RowTemplate

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


async def _publish_a_verified_recipe(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path, *, ontology_version: int, label: str
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
        draft.recipe_id, AUTHOR, row_template=_row_template(), unmapped_fields=[]
    )
    await store.mark_verified(draft.recipe_id, draft.version, now=datetime.now(UTC))
    draft = await store.get(draft.recipe_id)

    built = build_recipe(
        draft, ontology_version=ontology_version, schedule_cron=None, schedule_watch=None
    )
    git_path = await write_and_commit_recipe(built, repo_root=git_repo)
    return await store.publish(
        draft.recipe_id,
        APPROVER,
        ontology_version=ontology_version,
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
    flagged_ids = await store.flag_stale(current_ontology_version=ontology.version + 1)
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
