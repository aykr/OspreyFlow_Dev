"""Verify and Run read the same file (`spec/09_INGEST_STUDIO.md` §5; build order step 30, the owner,
4 November 2026).

The 3 November rehearsal (chapter 4): a file chosen at Connect passed Verify, and the run loaded
another — Verify read the draft's own `source_location` while a pipeline's run read its source
node's own location first (`pipeline_run.py`, the branch's `source_location`). The owner's rule:
Run uses exactly the file Verify checked, and says so in words if the source changed since, asking
for Verify again. Chosen here: **Run refuses** (409 `source_changed_since_verify`, nothing read into
a store) rather than quietly loading the old file, which would load something the person did not
choose.

Driven through the real routes — Verify, Publish, Run — so the check is proven where it is made.
What the run reads is recorded at the call that reads a branch's file
(`pipeline_run.run_published_recipe`), below the location resolution this step is about, so a
runner that chose a different file than Verify checked is seen. Each test names the invariant it
would catch broken.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import services.api.app as app_module
from fastapi.testclient import TestClient
from services.api.app import app, get_principal, get_recipe_runs, get_typology_rules
from services.ingest.pipeline import pipeline_from_recipe

from schemas.ingest import LoadReport, StudioRecipeStatus
from tests.services.api.any_case import AnyCase
from tests.services.api.test_studio_publish_routes import (
    CASE,
    _Empty,
    git_repo,  # noqa: F401  (fixture)
    publish_client,  # noqa: F401  (fixture)
)
from tests.services.api.test_studio_recipe_routes import (
    LOADER,
    SOURCE_APPROVER,
    SOURCE_AUTHOR,
    _ready_draft,
    client,  # noqa: F401  (fixture)
)
from tests.services.api.test_studio_verify_routes import (
    _create_only_row_template,
    _FakeRunKeys,
    graph_client,  # noqa: F401  (fixture)
)

# ruff: noqa: F811  (fixtures imported above are used by name)


class _Ledger(_FakeRunKeys):
    """The run ledger both routes read: Verify asks it for kept keys, a run is recorded in it."""

    async def start(self, **_: Any) -> str:
        return "run-1"

    async def finish(self, *_: Any, **__: Any) -> None:
        return None

    async def fail(self, *_: Any, **__: Any) -> None:
        return None


def _csv(path: Path, numbers: list[str]) -> str:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["a_party", "duration"])
        writer.writeheader()
        writer.writerows({"a_party": n, "duration": "42"} for n in numbers)
    return str(path)


@pytest.fixture
def studio(
    graph_client: TestClient, publish_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """One client with every dependency Verify, Publish and Run need, and a record of every file
    a run reads."""
    assert graph_client is publish_client
    app.dependency_overrides[get_recipe_runs] = lambda: _Ledger()
    app.dependency_overrides[app_module.get_investigations] = AnyCase
    for getter in (
        app_module.get_media, app_module.get_jobs, app_module.get_valkey,
        app_module.get_monitors_store, app_module.get_alerts_store,
        app_module.get_extraction_candidates, app_module.get_held_rows, app_module.get_kyc_expiries,
    ):  # fmt: skip
        app.dependency_overrides[getter] = lambda: _Empty()
    app.dependency_overrides[app_module.get_config] = lambda: SimpleNamespace(
        post_ingest_resolution=False
    )
    app.dependency_overrides[app_module.get_pipeline_recogniser_for] = lambda: lambda name: None
    app.dependency_overrides[app_module.get_online_geocode] = lambda: None
    read: list[str | None] = []

    async def reads(draft: Any, principal: Any, **kwargs: Any) -> LoadReport:
        read.append(kwargs["source_location"] or draft.source_location)
        return LoadReport(
            load_id=kwargs["load_id"], recipe_id=draft.recipe_id, recipe_version=draft.version
        )

    monkeypatch.setattr("services.api.pipeline_run.run_published_recipe", reads)
    return SimpleNamespace(client=graph_client, store=graph_client.studio_recipes, read=read)


def _pipeline_draft(tmp_path: Path, source_location: str, node_location: str | None = None) -> Any:
    draft = _ready_draft(
        tmp_path, source_location=source_location, row_template=_create_only_row_template()
    )
    pipeline = pipeline_from_recipe(draft)
    if node_location is not None:
        for node in pipeline.nodes:
            if node.kind.value == "source":
                node.config["source_location"] = node_location
    return draft.model_copy(update={"pipeline": pipeline})


def _verify(studio: Any) -> dict[str, Any]:
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR
    response = studio.client.post(f"{CASE}/ingest/recipes/recipe-1/verify")
    assert response.status_code == 200, response.text
    return response.json()


def _publish(studio: Any) -> None:
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    response = studio.client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})
    assert response.status_code == 200, response.text
    assert studio.store.draft.status is StudioRecipeStatus.PUBLISHED


def _run(studio: Any, source_location: str | None = None) -> Any:
    app.dependency_overrides[get_principal] = lambda: LOADER
    app.dependency_overrides[get_typology_rules] = lambda: _Empty()
    return studio.client.post(
        f"{CASE}/ingest/recipes/recipe-1/run", json={"source_location": source_location}
    )


def test_a_run_naming_another_file_than_verify_checked_is_refused_in_words(
    studio: Any, tmp_path: Path
) -> None:
    """The owner's case: choose A, Verify, re-choose B, Run. Red if the run loads B, or
    anything."""
    a = _csv(tmp_path / "reports.csv", ["07960112334"])
    b = _csv(tmp_path / "reports_corrected.csv", ["07960112334", "07700900718"])
    studio.store.draft = _pipeline_draft(tmp_path, a)
    _verify(studio)
    _publish(studio)

    response = _run(studio, source_location=b)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "source_changed_since_verify"
    assert body["detail"] == (
        "Verify checked reports.csv; this run would read reports_corrected.csv. Nothing was "
        "loaded. A run reads only the file Verify checked: choose this file as the source and run "
        "Verify again, then run."
    )
    assert str(tmp_path) not in body["detail"]  # file names, never the server's path (rule 7)
    assert studio.read == []


def test_a_run_reads_exactly_the_file_verify_checked(studio: Any, tmp_path: Path) -> None:
    a = _csv(tmp_path / "reports.csv", ["07960112334"])
    studio.store.draft = _pipeline_draft(tmp_path, a)
    _verify(studio)
    _publish(studio)

    response = _run(studio)

    assert response.status_code == 200, response.text
    assert studio.read == [a]
    # The answer does not repeat the server's path to the file it read (rule 7): a branch once
    # carried `source_location` back to the Glass, which never showed it.
    assert str(tmp_path) not in response.text


def test_a_file_changed_since_verify_is_refused_until_verify_runs_again(
    studio: Any, tmp_path: Path
) -> None:
    """Same name, other bytes (an operator's fresh copy over the checked one). Red if a run loads
    contents Verify never saw."""
    a = _csv(tmp_path / "reports.csv", ["07960112334"])
    studio.store.draft = _pipeline_draft(tmp_path, a)
    _verify(studio)
    _publish(studio)
    _csv(tmp_path / "reports.csv", ["07960112334", "07700900718"])

    response = _run(studio)

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        "reports.csv has changed since Verify checked it. Nothing was loaded. Run Verify again, "
        "then run."
    )
    assert studio.read == []

    _verify(studio)  # Verify on the published recipe records the file as it now is
    assert _run(studio).status_code == 200
    assert studio.read == [a]


def test_verify_reads_the_file_the_run_will_read_when_the_source_node_names_its_own(
    studio: Any, tmp_path: Path
) -> None:
    """The rehearsal's defect itself: the source node names B, the draft row A. Red if Verify
    checks A (one row) while the run loads B (two)."""
    a = _csv(tmp_path / "reports.csv", ["07960112334"])
    b = _csv(tmp_path / "reports_corrected.csv", ["07960112334", "07700900718"])
    studio.store.draft = _pipeline_draft(tmp_path, a, node_location=b)

    assert _verify(studio)["rows_read"] == 2
    _publish(studio)
    assert _run(studio).status_code == 200
    assert studio.read == [b]


def test_a_recipe_verify_never_recorded_runs_as_before(studio: Any, tmp_path: Path) -> None:
    """One published before this rule, or published by a seed with no Verify (ADR-127 Amendment
    34): nothing to compare against, so the run reads its recorded file as before."""
    a = _csv(tmp_path / "reports.csv", ["07960112334"])
    studio.store.draft = _pipeline_draft(tmp_path, a)
    studio.store.draft = studio.store.draft.model_copy(
        update={"verified_at": datetime(2026, 1, 1, tzinfo=UTC)}
    )
    _publish(studio)

    assert _run(studio).status_code == 200
    assert studio.read == [a]
