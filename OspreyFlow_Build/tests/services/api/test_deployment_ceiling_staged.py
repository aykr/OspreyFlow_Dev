"""A staged pipeline refused at the deployment's ceiling leaves nothing behind (ADR-148 Amendment 2
decision 2; studio-b's L1.10b, item 2).

A staged pipeline writes its step tables (`<bucket>/loads/<load_id>/staged/`) before `run_recipe`
judges its rows, since its rows are the last step's table. A marking a column sets is judged only
there, so a row marked above the ceiling is refused after those tables exist. Until L1.10b they were
left behind. They are the load's own and hold no graph data, but a refused load is one that wrote
nothing, so they are removed on the refusal.

What a mistake would do, and the case that catches it:
- the step tables left in the store after the ceiling refuses the run —
  `test_a_staged_run_refused_at_the_ceiling_leaves_no_step_table`;
- the removal reaching past the run's own load, into another run's tables —
  `test_the_removal_touches_no_other_run_s_tables`;
- a run the ceiling passes losing its step tables, which a re-map reads —
  `test_a_staged_run_within_the_ceiling_keeps_its_step_tables`;
- the staged engine's own load (`run_staged_recipe`) leaving them —
  `test_the_staged_engine_s_own_load_leaves_no_step_table_on_the_refusal`;
- a table the store will not remove turning the refusal into a store error, or stopping the rest
  being removed — `test_a_table_the_store_will_not_remove_leaves_the_refusal_as_it_was`;
- the backstop's later refusal ("write"), after the load's raw rows are staged, taken for the row
  check's — `test_only_the_row_check_s_refusals_remove_the_step_tables`.

The fixture is phase 7's staged pipeline (`test_staged_pipeline_run.py`, synthetic: rule 9), its
bookings given a `marking` column the booking's classification is bound to. The owners are marked
too, each as the bookings it joins (`marked_inputs`): the Join never puts a row under another's
differing marking (L1.7's `staging_catalogue.refuse_a_differing_marking`), so a SECRET booking meets
a SECRET owner, and its refusal is the ceiling's, not the join's.
"""

from __future__ import annotations

import csv
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.pipeline_run import run_published_pipeline
from services.api.studio_publish import write_and_commit_recipe
from services.ingest.ceiling import CEILING_ENV, AboveTheDeploymentCeiling
from services.ingest.staging_catalogue import source_table

from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.ingest.recipe_test_support import ValidatingGraph
from tests.ingest.test_staged_pipeline_run import HANDLING, LOADER, STORAGE, store  # noqa: F401
from tests.ingest.test_staged_run import ESTABLISHMENTS, ONTOLOGY, RECIPE, SCHEME, _rows, inputs
from tests.services.api.test_studio_staging_routes import _Models, _pipeline

# ruff: noqa: F811  (the imported fixture is every test's own same-named parameter)

#: The booking a SECRET marking is planted on, and the owner its number joins.
PLANTED = "VB-2605-002"
PLANTED_OWNER = "ELLERY"


def marked_bookings(planted: str) -> list[dict[str, str]]:
    """The bookings, each OFFICIAL but the planted one, which is `planted`."""
    return [
        {**row, "marking": planted if row["booking_id"] == PLANTED else "OFFICIAL"}
        for row in _rows("visit_bookings.csv")
    ]


def marked_owners(planted: str) -> list[dict[str, str]]:
    """The owners, each marked as the bookings its number joins: the planted booking's owner is
    `planted`, every other OFFICIAL (WHITLOW's number is two OFFICIAL bookings')."""
    return [
        {**row, "marking": planted if row["owner_family_name"] == PLANTED_OWNER else "OFFICIAL"}
        for row in _rows("number_owners.csv")
    ]


def marked_inputs(planted: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The staged engine's inputs with the bookings and owners marked alike where they join."""
    sources, lists = inputs()
    sources["visit_bookings"] = source_table(
        "visit_bookings", marked_bookings(planted), load_id="ld-vb-1", key=["booking_id"]
    )
    sources["number_owners"] = source_table(
        "number_owners", marked_owners(planted), load_id="ld-no-1", key=["number"]
    )
    return sources, lists


def joined_owners(graph: Any) -> set[str]:
    """The owners the Join met and the load committed: each a marked owner joined to a booking
    marked alike, so a control that commits them shows the guard was met and passed, not skipped
    by a left join that matched nothing."""
    return {
        n.properties["family_name"] for n in graph.committed_nodes if n.type == "Person"
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


async def _published(
    tmp_path: Path, planted: str, name: str = "run"
) -> tuple[StudioRecipeDraft, Path]:
    """The exit's staged recipe, its booking's classification bound to a `marking` column, every
    booking OFFICIAL but the planted one, which is `planted`."""
    repo = tmp_path / f"repo-{name}"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    bookings = tmp_path / f"visit_bookings_{name}.csv"
    _write_csv(bookings, marked_bookings(planted))
    owners = tmp_path / f"number_owners_{name}.csv"  # in the ingest folder, as a run requires
    _write_csv(owners, marked_owners(planted))
    pipeline = _pipeline(tmp_path)
    pipeline = pipeline.model_copy(
        update={
            "nodes": [
                n.model_copy(update={"config": {**n.config, "source_location": str(owners)}})
                if n.id == "number_owners" else n
                for n in pipeline.nodes
            ]
        }
    )  # fmt: skip
    entities = [
        e.model_copy(update={"handling": {"classification": {"field": "marking"}}})
        if e.ref == "booking" else e
        for e in RECIPE.row_template.entities
    ]  # fmt: skip
    template = RECIPE.row_template.model_copy(update={"entities": entities})
    recipe = RECIPE.model_copy(
        update={"id": "recipe-1", "pipeline": pipeline, "row_template": template}
    )
    git_path = await write_and_commit_recipe(recipe, repo_root=repo)
    draft = StudioRecipeDraft(
        recipe_id="recipe-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Visits",
        connector_profile="generic-csv", source_location=str(bookings), handling=HANDLING,
        legal_basis="Synthetic demonstration data", owning_unit="unit-1", created_by="author-1",
        created_at=datetime(2026, 11, 8, tzinfo=UTC), ready_for_profile=True,
        row_template=template, pipeline=pipeline, git_path=git_path,
        dataset_id="pid", pack_versions={},
    )  # fmt: skip
    return draft, repo


async def _run(draft: StudioRecipeDraft, repo: Path, load_id: str) -> tuple[Any, ValidatingGraph]:
    graph = ValidatingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
        load_id=load_id, investigation_scope="case-1", repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([ESTABLISHMENTS.id]),  # type: ignore[arg-type]
        staging_storage=STORAGE,
    )  # fmt: skip
    return report, graph


def _step_tables(root: Path, load_id: str) -> list[str]:
    return sorted(p.name for p in (root / STORAGE.bucket / "loads" / load_id).rglob("*.parquet"))


async def test_a_staged_run_refused_at_the_ceiling_leaves_no_step_table(
    tmp_path: Path, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    draft, repo = await _published(tmp_path, planted="SECRET")
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(AboveTheDeploymentCeiling) as refused:
        await run_published_pipeline(
            draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
            load_id="run-r", investigation_scope="case-1", repo_root=repo,
            recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
            target_models=_Models([ESTABLISHMENTS.id]),  # type: ignore[arg-type]
            staging_storage=STORAGE,
        )  # fmt: skip
    # The row check's kind ("load"; the fixed check before it has the same kind, so the step
    # tables' absence below, which plant 1 turns red, is what shows this is the row check's).
    assert refused.value.kind == "load"
    assert "SECRET" not in " ".join(refused.value.problems)
    assert _step_tables(store, "run-r") == [], "a refused run left its step tables behind"
    assert not graph.committed_nodes and not graph.committed_edges


async def test_the_removal_touches_no_other_run_s_tables(
    tmp_path: Path, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    kept, kept_repo = await _published(tmp_path, planted="OFFICIAL", name="kept")
    await _run(kept, kept_repo, "run-k")
    before = _step_tables(store, "run-k")
    assert before, "the run the ceiling passed staged nothing"
    refused, refused_repo = await _published(tmp_path, planted="SECRET", name="refused")
    with pytest.raises(AboveTheDeploymentCeiling) as refusal:
        await _run(refused, refused_repo, "run-r")
    assert refusal.value.kind == "load"
    assert _step_tables(store, "run-r") == [], "the refused run left its own step tables"
    assert _step_tables(store, "run-k") == before


async def test_a_staged_run_within_the_ceiling_keeps_its_step_tables(
    tmp_path: Path, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    draft, repo = await _published(tmp_path, planted="OFFICIAL")
    _, graph = await _run(draft, repo, "run-w")
    assert joined_owners(graph) == {"ELLERY", "WHITLOW"}, "the join met no marked owner"
    assert _step_tables(store, "run-w") == [
        "titled.parquet",
        "with_establishment.parquet",
        "with_owner.parquet",
    ]


async def test_the_staged_engine_s_own_load_leaves_no_step_table_on_the_refusal(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`staged_run.run_staged_recipe`, the staged load without the Conduit's pipeline around it,
    removes its step tables on the refusal as the pipeline's branch does."""
    from services.ingest.staged_run import run_staged_recipe

    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    sources, lists = marked_inputs("SECRET")
    entities = [
        e.model_copy(update={"handling": {"classification": {"field": "marking"}}})
        if e.ref == "booking" else e
        for e in RECIPE.row_template.entities
    ]  # fmt: skip
    recipe = RECIPE.model_copy(
        update={"row_template": RECIPE.row_template.model_copy(update={"entities": entities})}
    )
    graph = ValidatingGraph(ONTOLOGY)
    tx = await graph.begin_transaction()
    with pytest.raises(AboveTheDeploymentCeiling) as refused:
        await run_staged_recipe(
            recipe, sources=sources, lists=lists, dataset_id="pid",
            graph=graph, ontology=ONTOLOGY, tx=tx, principal=LOADER,  # type: ignore[arg-type]
            load_id="ld-run-r", investigation_scope="case-1", storage=STORAGE, scheme=SCHEME,
            subscribed=(),
        )  # fmt: skip
    assert refused.value.kind == "load"
    assert _step_tables(store, "ld-run-r") == [], "a refused staged load left its step tables"


def _staged_engine_load(store: Path, load_id: str) -> Any:
    from services.ingest.staged_run import run_staged_recipe

    sources, lists = marked_inputs("SECRET")
    entities = [
        e.model_copy(update={"handling": {"classification": {"field": "marking"}}})
        if e.ref == "booking" else e
        for e in RECIPE.row_template.entities
    ]  # fmt: skip
    recipe = RECIPE.model_copy(
        update={"row_template": RECIPE.row_template.model_copy(update={"entities": entities})}
    )
    graph = ValidatingGraph(ONTOLOGY)

    async def load() -> Any:
        tx = await graph.begin_transaction()
        return await run_staged_recipe(
            recipe, sources=sources, lists=lists, dataset_id="pid",
            graph=graph, ontology=ONTOLOGY, tx=tx, principal=LOADER,  # type: ignore[arg-type]
            load_id=load_id, investigation_scope="case-1", storage=STORAGE, scheme=SCHEME,
            subscribed=(),
        )  # fmt: skip

    return load()


async def test_a_table_the_store_will_not_remove_leaves_the_refusal_as_it_was(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.ingest.recipe_test_support import LocalStore

    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    removed = LocalStore.delete_file
    refused_once: list[str] = []

    def stubborn(self: LocalStore, path: str) -> None:
        if not refused_once:
            refused_once.append(path)
            raise RuntimeError("the store would not remove it")
        removed(self, path)

    monkeypatch.setattr(LocalStore, "delete_file", stubborn)
    with pytest.raises(AboveTheDeploymentCeiling) as refused:
        await _staged_engine_load(store, "ld-run-s")
    assert refused.value.kind == "load"
    assert refused_once, "the store was never asked"
    left = _step_tables(store, "ld-run-s")
    assert left == [refused_once[0].rsplit("/", 1)[1]], left


async def test_only_the_row_check_s_refusals_remove_the_step_tables(
    tmp_path: Path, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.ingest.staged_run import remove_step_tables_on

    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    draft, repo = await _published(tmp_path, planted="OFFICIAL")
    await _run(draft, repo, "run-k")
    held = _step_tables(store, "run-k")
    prepared = SimpleNamespace(
        paths={
            name.removesuffix(".parquet"): f"{STORAGE.bucket}/loads/run-k/staged/{name}"
            for name in held
        }
    )
    await remove_step_tables_on(
        AboveTheDeploymentCeiling("OFFICIAL", "write"),
        prepared,
        STORAGE,  # type: ignore[arg-type]
    )
    assert _step_tables(store, "run-k") == held
    await remove_step_tables_on(
        AboveTheDeploymentCeiling("OFFICIAL", "unreadable"),
        prepared,
        STORAGE,  # type: ignore[arg-type]
    )
    assert _step_tables(store, "run-k") == []
