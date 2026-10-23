"""ADR-120 Amendment 1, decision 6: a real Conduit start-up stamps a legacy recipe's pins from its
file, and only then flags it against the packs it serves. `reconcile_recipe_pins` is proved against
a store in `test_studio_recipes_store.py`; this starts the real process, because only a real
start-up shows the application actually calls it, with the recipe repository root it publishes to
and the packs the deployment composes.

What the test checks, and the violation that fails it: a start-up that still ran the bare
`flag_stale` (the row would stay unpinned and published, and a pack bump would never reach it),
that flagged before it stamped (the row has no pins, so `flag_stale` leaves it published, and
the backfill then stamps it too late to be flagged), that read the file from another root than
`OSPREY_RECIPE_REPO_ROOT` (the row would be flagged as unreadable, with no pins stamped), or that
passed no pack versions to `flag_stale`. A second row, already pinned at the version the Conduit
serves, must stay published: a start-up that flagged every pinned row would fail.

Every real start-up also flags the unreadable NULL-pinned rows other tests leave in the shared
database; this test looks only at its own two rows.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from services.api.config import PostgresConfig
from services.api.studio_recipes import StudioRecipeStore

from conduit_common.identity import new_id
from ontology.loader import load_default_ontology
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.services.api.test_statelessness import _ConduitInstance

_FIXTURES = Path(__file__).resolve().parents[2] / "scenarios" / "fixtures"

HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "owning_unit": "unit-1",
    "originator": "unit-1",
}


def _write_legacy_niem_recipe(repo_root: Path, recipe_id: str) -> str:
    """A recipe whose pipeline names NIEM, as published before pinning: no `pack_versions`."""
    document = yaml.safe_load((_FIXTURES / "cdr_recipe.yaml").read_text())
    document["id"] = recipe_id
    document["pipeline"] = {
        "nodes": [
            {"id": "domain", "kind": "domain_model", "label": "D", "config": {"pack": "niem"}}
        ],
        "edges": [],
    }
    git_path = f"recipes/{recipe_id}.yaml"
    (repo_root / "recipes").mkdir(parents=True, exist_ok=True)
    (repo_root / git_path).write_text(yaml.safe_dump(document))
    return git_path


async def _seed_published_rows(legacy_id: str, git_path: str, pinned_id: str) -> None:
    store = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)  # makes the columns
    await store.close()
    import asyncpg

    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        now = datetime.now(UTC)
        await conn.execute(
            "INSERT INTO studio_recipes (recipe_id, version, ontology_version, label, status, "
            "content, git_path, owning_unit, created_by, published_by, created_at, published_at) "
            "VALUES ($1, 1, $2, 'Legacy NIEM, before pinning', 'published', $3, $4, 'unit-1', "
            "'author-1', 'approver-1', $5, $5)",
            legacy_id,
            # The version the Conduit serves, so only the packs can differ.
            load_default_ontology().version,
            json.dumps({"handling": HANDLING}),
            git_path,
            now,
        )
        # A published row pinned at the version the Conduit serves, with no file to read: the
        # start-up must neither read it nor flag it.
        await conn.execute(
            "INSERT INTO studio_recipes (recipe_id, version, ontology_version, label, status, "
            "content, git_path, owning_unit, created_by, published_by, created_at, published_at, "
            "pack_versions) VALUES ($1, 1, $2, 'Pinned NIEM at the served version', 'published', "
            "$3, 'recipes/never-read.yaml', 'unit-1', 'author-1', 'approver-1', $4, $4, "
            "$5::jsonb)",
            pinned_id,
            load_default_ontology().version,
            json.dumps({"handling": HANDLING}),
            now,
            json.dumps({"niem": 3}),
        )
    finally:
        await conn.close()


async def _read(recipe_id: str) -> StudioRecipeDraft:
    store = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    try:
        return await store.get(recipe_id)
    finally:
        await store.close()


def test_starting_the_conduit_stamps_legacy_pins_before_it_flags(
    jwks_url: str, tmp_path: Path
) -> None:
    repo_root = tmp_path / "recipe-repo"
    recipe_id, pinned_id = new_id(), new_id()
    git_path = _write_legacy_niem_recipe(repo_root, recipe_id)
    asyncio.run(_seed_published_rows(recipe_id, git_path, pinned_id))

    # `_ConduitInstance` returns once the process answers, which is after its lifespan start-up.
    conduit = _ConduitInstance(jwks_url, extra_env={"OSPREY_RECIPE_REPO_ROOT": str(repo_root)})
    try:
        row = asyncio.run(_read(recipe_id))
        pinned = asyncio.run(_read(pinned_id))
    finally:
        conduit.kill()

    assert row.pack_versions == {"niem": 2}, "the start-up did not stamp the legacy pins"
    assert row.status is StudioRecipeStatus.FLAGGED, "the start-up did not flag it afterwards"
    assert pinned.pack_versions == {"niem": 3}
    assert pinned.status is StudioRecipeStatus.PUBLISHED, "a pinned, current row was flagged"
