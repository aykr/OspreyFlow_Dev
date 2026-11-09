"""A subscribed deployment-wide list read by a Lookup at every place a staged pipeline runs (ADR-140
Amendment 13 point 10; the studio lane's review of L1.5, carried into studio-b's L1.8).

`staging_catalogue.run_staging` judges its steps again, and refuses a Lookup of a deployment-wide list
the dataset does not subscribe to. Every caller must therefore hand it the dataset's subscriptions.
Three did not: the drawer's sample (`studio_staging.preview_staging`), Test
(`studio_verify` through `staged_run.dry_run_staged_recipe`) and the run (`pipeline_run` through
`staged_run.prepare_staged_load`). So a subscribed Lookup passed save and publish, then was refused at
each of them. It failed closed, so nothing leaked, but no subscribed Lookup could run.
`test_subscribed_lists_seam.py` stopped at `lists_for_run` and could not see it.

What a mistake would do, and the case that catches it:
- the drawer's sample refusing a subscribed list — `test_the_drawer_s_sample_reads_a_subscribed_list`;
- Test refusing it — `test_test_reads_a_subscribed_list`;
- the run refusing it — `test_the_run_reads_a_subscribed_list`;
- a fourth caller of the three that forgets the subscriptions —
  `test_every_caller_hands_the_staging_engine_the_subscriptions`;
- the subscriptions widening what a Lookup reads — `test_an_unsubscribed_list_is_still_refused_at_the_sample`.

The fixture is the Studio's own staged pipeline (`test_studio_staging_routes.py`, phase 7's visits
and contacts, synthetic: rule 9). Its establishments Lookup reads a deployment-wide list named
`establishments` that the dataset subscribes to, and the dataset's own model names no list. Shown red
at each call site before the fix (`process/lanes/studio-b/l1.8/red-carry-subscribed.txt`).
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_target_models
from services.api.list_connector import InMemoryListStore, ParquetListRows, deployment_reference

from schemas.ingest import PipelineGraph, StudioRecipeDraft, StudioRecipeStatus
from schemas.list_connector import BlankListMapping, DeploymentListInput
from schemas.staging import AddedColumn
from tests.ingest.test_staged_pipeline_run import HANDLING, LOADER
from tests.ingest.test_staged_run import FIXTURES, ONTOLOGY, RECIPE, SCHEME
from tests.services.api.test_studio_staging_routes import (  # noqa: F401  (fixtures)
    RECIPE_URL,
    STORAGE,
    _draft,
    _Models,
    _pipeline,
    _preview,
    _update,
    client,
    git_repo,
    graph_client,
    staged,
    store,
)

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"

#: The deployment-wide list's rows, in the screening shape: keyed on `ref`, named in `primary_name`.
ROWS = [
    {"ref": code, "primary_name": name, "aliases": None, "date_of_birth": None, "nationality": None,
     "identifiers": None, "programme": None, "listing": None, "entity_type": "Organisation"}
    for code, name in (("FMR", "HMP Fenwick Moor"), ("HBK", "HMP Halbeck"), ("ODE", "HMP Oakdene"))
]  # fmt: skip


async def _deployment_list(lists: InMemoryListStore, *, subscribe: bool) -> str:
    made = await lists.add(
        DeploymentListInput(name="establishments", template="blank", location="establishments.csv",
                            mapping=BlankListMapping(ref="ref", primary_name="primary_name")),
        "admin-1",
    )  # fmt: skip
    ParquetListRows(STORAGE).write(deployment_reference(made, 1), ROWS)
    assert await lists.apply_version(made.id, previous=0, version=1, digest="d", entries=len(ROWS),
                                     at=made.created_at)  # fmt: skip
    if subscribe:
        await lists.subscribe("pid", made.id, "author-1")
    return made.id


def _reading_the_deployment_list(pipeline: PipelineGraph) -> PipelineGraph:
    """The Lookup adds the deployment list's `primary_name`, as the establishment, where the dataset's
    own list had `name`."""
    graph = pipeline.model_copy(deep=True)
    lookup = next(n for n in graph.nodes if n.id == "with_establishment")
    lookup.config["add"] = [{"column": "primary_name", "as": "establishment"}]
    return graph


async def published(
    tmp_path: Path, change: Callable[[PipelineGraph], PipelineGraph]
) -> tuple[StudioRecipeDraft, Path]:
    """The exit's staged recipe, published to a throwaway repository, its pipeline `change`d (as
    `test_staged_pipeline_run.py`'s own `_published`)."""
    from services.api.studio_publish import write_and_commit_recipe

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    bookings = tmp_path / "visit_bookings.csv"
    shutil.copy(FIXTURES / "visit_bookings.csv", bookings)
    pipeline = change(_pipeline(tmp_path))
    assert RECIPE.staging
    staging = [
        s.model_copy(update={"add": [AddedColumn(column="primary_name", as_="establishment")]})
        if s.id == "with_establishment" else s
        for s in RECIPE.staging
    ]  # fmt: skip
    recipe = RECIPE.model_copy(update={"id": "recipe-1", "pipeline": pipeline, "staging": staging})
    git_path = await write_and_commit_recipe(recipe, repo_root=repo)
    draft = StudioRecipeDraft(
        recipe_id="recipe-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Visits",
        connector_profile="generic-csv", source_location=str(bookings), handling=HANDLING,
        legal_basis="Synthetic demonstration data", owning_unit="unit-1", created_by="author-1",
        created_at=datetime(2026, 11, 8, tzinfo=UTC), ready_for_profile=True,
        row_template=RECIPE.row_template, pipeline=pipeline, git_path=git_path,
        dataset_id="pid", pack_versions={},
    )  # fmt: skip
    return draft, repo


@pytest.fixture
async def subscribed(staged: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    lists = InMemoryListStore()
    monkeypatch.setattr(app.state, "list_store", lists, raising=False)
    await _deployment_list(lists, subscribe=True)
    # The dataset's own model names no list: the only `establishments` it reads is the subscribed one.
    app.dependency_overrides[get_target_models] = lambda: _Models([])
    _update(staged, pipeline=_reading_the_deployment_list(_draft(staged).pipeline))
    staged.lists = lists  # type: ignore[attr-defined]
    return staged


def test_the_drawer_s_sample_reads_a_subscribed_list(subscribed: TestClient) -> None:
    response = _preview(subscribed, "with_establishment")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["problems"] == [], body["problems"]
    names = {row["establishment"] for row in body["rows"]}
    assert {"HMP Fenwick Moor", "HMP Halbeck"} <= names, names


def test_test_reads_a_subscribed_list(subscribed: TestClient) -> None:
    response = subscribed.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 200, response.text
    assert response.json()["rows_read"] == 10


async def test_the_run_reads_a_subscribed_list(
    subscribed: TestClient, tmp_path: Path
) -> None:
    from services.api.pipeline_run import run_published_pipeline
    from tests.ingest.recipe_test_support import ValidatingGraph

    draft, repo = await published(tmp_path, _reading_the_deployment_list)
    graph = ValidatingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
        load_id="run-s", investigation_scope="case-1", repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([]), staging_storage=STORAGE,  # type: ignore[arg-type]
        list_store=subscribed.lists,  # type: ignore[attr-defined]
    )  # fmt: skip
    [branch] = report.branches
    lookup = next(s for s in branch.report.staging_steps if s.step == "with_establishment")
    assert lookup.rows_in == 6 and lookup.unmatched == 1  # XXX, kept with no establishment
    assert graph.committed_nodes


async def test_an_unsubscribed_list_is_still_refused_at_the_sample(
    staged: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lists = InMemoryListStore()
    monkeypatch.setattr(app.state, "list_store", lists, raising=False)
    await _deployment_list(lists, subscribe=False)
    app.dependency_overrides[get_target_models] = lambda: _Models([])
    _update(staged, pipeline=_reading_the_deployment_list(_draft(staged).pipeline))
    body = _preview(staged, "with_establishment").json()
    assert body["problems"] == [
        "step 'with_establishment' looks up 'establishments', which names no list this dataset "
        "holds or subscribes to"
    ]
    assert not body.get("rows")


#: Each entry into the staging engine that judges a Lookup, and so needs the dataset's subscriptions.
ENGINE = {"run_staging", "dry_run_staged_recipe", "prepare_staged_load", "lists_for_run"}


def _calls_without_subscriptions(path: Path, root: Path = CORE) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in ENGINE and not any(k.arg == "subscribed" for k in node.keywords):
            missing.append(f"{path.relative_to(root)}:{node.lineno} {name}")
        # `asyncio.to_thread(lists_for_run, ...)` hands the function on; its keywords still count.
        if name == "to_thread" and node.args:
            first = node.args[0]
            handed = first.id if isinstance(first, ast.Name) else getattr(first, "attr", None)
            if handed in ENGINE and not any(k.arg == "subscribed" for k in node.keywords):
                missing.append(f"{path.relative_to(root)}:{node.lineno} {handed} (to_thread)")
    return missing


def test_every_caller_hands_the_staging_engine_the_subscriptions() -> None:
    """Every call in the Conduit and the ingest service names `subscribed=`. The engine's own
    module, where the default lives, is the one not asked."""
    missing: list[str] = []
    scanned = [p for p in sorted((CORE / "services").rglob("*.py")) if p.name != "staging_catalogue.py"]
    # Non-vacuous: the three modules the reviewer named are among those read (a wrong root read none).
    assert {"studio_staging.py", "studio_verify.py", "pipeline_run.py"} <= {p.name for p in scanned}
    for path in scanned:
        missing.extend(_calls_without_subscriptions(path))
    assert missing == [], missing


def test_the_caller_check_finds_a_call_that_forgets_them(tmp_path: Path) -> None:
    """Rule 15: the check above, planted at the shapes the real callers take."""
    planted = tmp_path / "plant.py"
    planted.write_text(
        "import asyncio\n"
        "async def a(s):\n    return run_staging(s, sources={}, lists={}, dataset_id='d')\n"
        "async def b(s):\n    return await dry_run_staged_recipe(s, sources={}, lists={})\n"
        "async def c(s):\n    return await asyncio.to_thread(lists_for_run, s, [], dataset_id='d')\n",
        encoding="utf-8",
    )
    assert len(_calls_without_subscriptions(planted, tmp_path)) == 3
