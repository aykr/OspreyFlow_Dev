"""A pipeline's staging steps at the Studio's routes (ADR-140 Amendment 12; redesign phase 7b).

The drawers save steps as nodes of the pipeline (`PUT …/pipeline`), preview a step's output
(`POST …/staging-preview`, Q4 (a)), and Test and Deploy judge them. What a mistake would do, and the
case that catches it:

- a drawer accepting what the save gate refuses, or refusing it in other words
  (`test_a_drawer_refuses_what_the_save_gate_refuses_in_the_same_words`);
- the save taking steps unjudged (`test_the_save_refuses_a_step_the_gate_refuses`);
- a publish committing steps unjudged (`test_a_publish_refuses_steps_the_gate_refuses`);
- the preview writing anything (`test_a_preview_writes_nothing`);
- the preview not being the step's output over the sources' first rows
  (`test_a_preview_shows_the_step_s_rows_and_counts`);
- the preview widening who may read a source's rows (rules 3 and 4):
  `test_a_preview_needs_the_right_to_edit_pipelines`,
  `test_a_preview_of_another_units_recipe_is_not_found`,
  `test_a_reader_not_cleared_for_the_source_sees_its_rows_masked`;
- Test of a staged pipeline not running its steps, or rejecting other rows than the load
  (`test_test_runs_the_steps_and_names_each_rejection_s_rows`);
- a Lookup of a list the dataset's live model does not name being read
  (`test_a_list_the_live_model_does_not_name_is_not_read`).
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_principal, get_staging_storage, get_target_models
from services.ingest.pipeline import pipeline_with_staging
from services.ingest.reference_list_import import import_list
from services.ingest.staging import ObjectStorageConfig

from schemas.dataset_model import TargetModel
from schemas.ingest import PipelineEdge, PipelineGraph, PipelineNode, PipelineNodeKind
from tests.ingest.recipe_test_support import LocalStore
from tests.ingest.test_staged_run import ESTABLISHMENTS, FIXTURES, RECIPE
from tests.services.api.test_studio_publish_routes import git_repo  # noqa: F401  (a fixture)
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    NO_ROLE_ANALYST,
    SOURCE_APPROVER,
    SOURCE_AUTHOR,
    _ready_draft,
)
from tests.services.api.test_studio_verify_routes import (  # noqa: F401  (fixtures)
    client,
    graph_client,
)

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

RECIPE_URL = "/v1/investigations/inv-1/ingest/recipes/recipe-1"
STORAGE = ObjectStorageConfig(bucket="staging")


class _Models:
    """A dataset whose live domain model names `names` (ADR-140 decision 4)."""

    def __init__(self, names: list[str]) -> None:
        self.names = names

    async def live(self, dataset_id: str) -> TargetModel | None:
        if dataset_id != "pid":
            return None
        return TargetModel(
            dataset_id="pid", version=1, state="live", reference_lists=self.names,
            created_at=datetime(2026, 11, 8, tzinfo=UTC), created_by="owner-1",
        )  # fmt: skip


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A local object store for staged Parquet and lists' rows, with the exit's list kept."""
    from services.ingest import staging

    root = tmp_path / "store"
    root.mkdir()
    monkeypatch.setattr(staging, "filesystem", lambda config: LocalStore(root))
    import_list(ESTABLISHMENTS, FIXTURES / "establishments.csv", storage=STORAGE)
    return root


def _pipeline(tmp_path: Path) -> PipelineGraph:
    owners = tmp_path / "number_owners.csv"
    shutil.copy(FIXTURES / "number_owners.csv", owners)
    base = PipelineGraph(
        nodes=[
            PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model"),
            PipelineNode(id="visit_bookings", kind=PipelineNodeKind.SOURCE, label="Bookings"),
            PipelineNode(
                id="number_owners", kind=PipelineNodeKind.SOURCE, label="Owners",
                config={"source_location": str(owners)},
            ),  # fmt: skip
            PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
            PipelineNode(id="load", kind=PipelineNodeKind.LOAD, label="Load"),
        ],
        edges=[
            PipelineEdge(source="domain", target="visit_bookings"),
            PipelineEdge(source="domain", target="number_owners"),
            PipelineEdge(source="map", target="load"),
        ],
    )
    assert RECIPE.staging
    return pipeline_with_staging(base, RECIPE.staging)


@pytest.fixture
def staged(graph_client: TestClient, tmp_path: Path, store: Path) -> TestClient:
    bookings = tmp_path / "visit_bookings.csv"
    shutil.copy(FIXTURES / "visit_bookings.csv", bookings)
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        source_location=str(bookings),
        dataset_id="pid",
        row_template=RECIPE.row_template,
        pipeline=_pipeline(tmp_path),
    )
    # The route's principal is scoped to its case's datasets (`dataset_scope.scope_to_case`): a
    # case reading the recipe's dataset.
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR.model_copy(
        update={"datasets": ["pid"]}
    )
    app.dependency_overrides[get_target_models] = lambda: _Models([ESTABLISHMENTS.id])
    app.dependency_overrides[get_staging_storage] = lambda: STORAGE
    graph_client.store = store  # type: ignore[attr-defined]
    return graph_client


def _draft(client: TestClient) -> Any:
    return client.studio_recipes.draft  # type: ignore[attr-defined]


def _update(client: TestClient, **update: Any) -> None:
    client.studio_recipes.draft = _draft(client).model_copy(update=update)  # type: ignore[attr-defined]


def _files(client: TestClient) -> list[Path]:
    root: Path = client.store  # type: ignore[attr-defined]
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def _preview(client: TestClient, step: str, pipeline: PipelineGraph | None = None) -> Any:
    body = {
        "pipeline": (pipeline or _draft(client).pipeline).model_dump(mode="json"),
        "step": step,
    }
    return client.post(f"{RECIPE_URL}/staging-preview", json=body)


def _broken(client: TestClient) -> PipelineGraph:
    """The exit's pipeline with its Join normalising through something that is no text adapter."""
    graph = _draft(client).pipeline.model_copy(deep=True)
    join = next(n for n in graph.nodes if n.id == "with_owner")
    join.config["normalise"] = "no_such_adapter"
    return graph


def test_a_preview_shows_the_step_s_rows_and_counts(staged: TestClient) -> None:
    response = _preview(staged, "with_owner")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["problems"] == []
    assert "owner_family_name" in body["columns"] and "establishment" in body["columns"]
    assert [c["step"] for c in body["counts"]] == ["with_establishment", "with_owner"]
    assert body["rows_sampled"] == 10  # six bookings, four owner rows: each source's first ten
    assert len(body["rows"]) == body["counts"][-1]["rows_out"] == 5
    assert body["values_masked"] is False
    assert {c["name"] for c in body["profile"]["columns"]} == set(body["columns"])
    # A rejection is named by its rows, never by its value or key (rule 7).
    assert {r["refs"][0]["table"] for r in body["rejections"]} == {
        "number_owners", "visit_bookings",
    }  # fmt: skip
    assert "row_key" not in response.text


def test_a_preview_writes_nothing(staged: TestClient) -> None:
    before = _files(staged)
    assert _preview(staged, "titled").status_code == 200
    assert _files(staged) == before
    assert _draft(staged).verified_at is None


def test_a_drawer_refuses_what_the_save_gate_refuses_in_the_same_words(
    staged: TestClient,
) -> None:
    broken = _broken(staged)
    saved = staged.put(f"{RECIPE_URL}/pipeline", json=broken.model_dump(mode="json"))
    assert saved.status_code == 422
    previewed = _preview(staged, "with_owner", broken)
    assert previewed.status_code == 200
    assert previewed.json()["problems"] == saved.json()["problems"]
    assert any("no_such_adapter" in p for p in saved.json()["problems"])
    assert previewed.json()["rows"] == []


def test_the_save_refuses_a_step_the_gate_refuses(staged: TestClient) -> None:
    before = _draft(staged).pipeline
    response = staged.put(f"{RECIPE_URL}/pipeline", json=_broken(staged).model_dump(mode="json"))
    assert response.status_code == 422
    assert response.json()["error"] == "pipeline_invalid"
    assert _draft(staged).pipeline == before


def test_a_publish_refuses_steps_the_gate_refuses(staged: TestClient, git_repo: Path) -> None:
    from services.api.app import get_recipes_repo_root

    app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
    _update(staged, pipeline=_broken(staged), verified_at=datetime(2026, 11, 8, tzinfo=UTC))
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    response = staged.post(f"{RECIPE_URL}/publish", json={})
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "pipeline_invalid"
    assert not (git_repo / "recipes" / "recipe-1.yaml").exists()


def test_a_preview_needs_the_right_to_edit_pipelines(staged: TestClient) -> None:
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST
    assert _preview(staged, "with_owner").status_code == 403


def test_a_preview_of_another_units_recipe_is_not_found(staged: TestClient) -> None:
    _update(staged, owning_unit="unit-2")
    response = _preview(staged, "with_owner")
    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"


def test_a_reader_not_cleared_for_a_sampled_row_is_given_nothing_of_the_run(
    staged: TestClient,
) -> None:
    """Rule 3 (the review of L1.4): the reader writes the steps, so a Filter's counts, a Derive's
    shapes or a rejection's row could answer questions about a value a mask hides. A reader who
    may not view every sampled row is given no row, count, rejection or profile at all."""
    _update(staged, handling=_UNCLEARED_HANDLING)
    graph = _draft(staged).pipeline.model_copy(deep=True)
    graph.nodes.append(
        PipelineNode(
            id="guess", kind=PipelineNodeKind.FILTER, label="Guess",
            config={
                "input": "titled",
                "keep": [{"field": "owner_family_name", "equals": "WHITLOW"}],
            },
        )  # fmt: skip
    )
    graph.edges = [e for e in graph.edges if (e.source, e.target) != ("titled", "map")]
    graph.edges += [
        PipelineEdge(source="titled", target="guess"),
        PipelineEdge(source="guess", target="map"),
    ]
    response = _preview(staged, "guess", graph)
    assert response.status_code == 200
    body = response.json()
    assert body["values_masked"] is True
    assert body["rows"] == [] and body["counts"] == [] and body["rejections"] == []
    assert body["profile"] is None and body["columns"] == []
    assert any(p.startswith("The sample is withheld") for p in body["problems"])
    for name in ("WHITLOW", "VB-2605-001", "HMP Fenwick Moor"):
        assert name not in response.text


def test_a_preview_reads_only_the_saved_pipeline_s_sources(
    staged: TestClient, tmp_path: Path
) -> None:
    """Rules 3 and 4 (the review of L1.4): a source the request names that is not the saved
    draft's own (here, another file in the ingest folder) is refused in words and never read."""
    other = tmp_path / "elsewhere.csv"
    # Shaped as the owners' file, so the Join would bring its name across if it were read.
    other.write_text(
        "number,owner_family_name,since\n+447700900731,SHOULD-NOT-BE-READ,2020-01-01\n",
        encoding="utf-8",
    )
    graph = _draft(staged).pipeline.model_copy(deep=True)
    owners = next(n for n in graph.nodes if n.id == "number_owners")
    owners.config = {**owners.config, "source_location": str(other)}
    # The Join reads the swapped source, so a read of it would show in its sample.
    body = _preview(staged, "with_owner", graph).json()
    assert (
        "source 'Owners' is not the saved pipeline's: save its source before a step's sample "
        "reads it"
    ) in body["problems"]
    assert body["rows"] == [] and body["counts"] == []
    assert "SHOULD-NOT-BE-READ" not in json.dumps(body)


def test_a_step_s_sample_names_a_refusal_of_a_step_it_does_not_run(staged: TestClient) -> None:
    """The review of L1.4 (R1): the sample of an earlier step runs only the steps it needs, so a
    later step's catalogue refusal reaches the drawer only through the save gate's own call."""
    broken = _broken(staged)  # the Join's adapter is no text adapter
    saved = staged.put(f"{RECIPE_URL}/pipeline", json=broken.model_dump(mode="json"))
    body = _preview(staged, "with_establishment", broken).json()
    assert body["problems"] == saved.json()["problems"]
    assert any("no_such_adapter" in p for p in body["problems"])
    assert len(body["rows"]) == 6


def test_test_runs_the_steps_and_names_each_rejection_s_rows(staged: TestClient) -> None:
    response = staged.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_read"] == 10
    reasons = [r["reason"] for r in body["rejections"]]
    right = "staging step with_owner (right side, number_owners row 3)"
    assert any(r.startswith(right) for r in reasons)
    assert any(r.startswith("staged table titled row 4") for r in reasons)
    assert "row_key" not in response.text


def test_a_list_the_live_model_does_not_name_is_not_read(staged: TestClient) -> None:
    app.dependency_overrides[get_target_models] = lambda: _Models([])
    body = _preview(staged, "with_establishment").json()
    assert body["problems"] == [
        "step 'with_establishment' looks up 'establishments', which names no list this dataset "
        "holds or subscribes to"
    ]


def test_a_step_s_sample_runs_beside_refusals_of_steps_it_does_not_need(staged: TestClient) -> None:
    """A pipeline is built a step at a time: while a later step is half set, or a source not yet
    read, the save gate refuses the pipeline, and an earlier step's drawer still shows its sample,
    with every refusal beside it in the gate's own words."""
    graph = _draft(staged).pipeline.model_copy(deep=True)
    derive = next(n for n in graph.nodes if n.id == "titled")
    derive.config = {**derive.config, "columns": ["establishment"]}  # concat reads two
    saved = staged.put(f"{RECIPE_URL}/pipeline", json=graph.model_dump(mode="json"))
    assert saved.status_code == 422
    body = _preview(staged, "with_establishment", graph).json()
    assert body["problems"] == saved.json()["problems"]
    assert body["problems"] == ["step 'titled': concat reads at least 2 column(s), not 1"]
    assert body["rows"] == []  # a record the schema refuses runs nothing
    unread = _draft(staged).pipeline.model_copy(deep=True)
    unread.nodes = [n for n in unread.nodes if n.id not in ("with_owner", "titled")]
    gone = {"with_owner", "titled"}
    unread.edges = [e for e in unread.edges if not gone & {e.source, e.target}]
    unread.edges.append(PipelineEdge(source="with_establishment", target="map"))
    body = _preview(staged, "with_establishment", unread).json()
    assert body["problems"] == [
        "source 'Owners' reaches no load; its rows would go nowhere",
        "source 'Owners' is read by no step: a pipeline with staging steps maps only its last "
        "step's table, so its rows would go nowhere",
    ]
    assert len(body["rows"]) == 6


def test_a_lookup_s_list_rows_are_withheld_from_a_case_not_reading_the_dataset(
    staged: TestClient,
) -> None:
    """Rule 4 (the lane review's second round): a list's rows carry no marking; they are the
    dataset's, read by a case that reads it. A case on another dataset is given nothing of a
    sample a Lookup is in, and the sample of a step no Lookup feeds is unaffected."""
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR.model_copy(
        update={"datasets": ["ledger"]}
    )
    response = _preview(staged, "with_establishment")
    body = response.json()
    assert body["values_masked"] is True and body["rows"] == [] and body["counts"] == []
    withheld = "The sample is withheld: it reads this dataset's"
    assert any(p.startswith(withheld) for p in body["problems"])
    assert "HMP Fenwick Moor" not in response.text


# --- the orchestrator's review of L1.4: a dataset's files, and Test's guards (rules 3 and 4) ----

NOT_OFFERED = (
    "source 'Owners' reads a file that is not one of this dataset's files in the ingest folder: "
    "choose it from the dataset's files, or upload it"
)


def _another_dataset_s_file(tmp_path: Path) -> Path:
    """A file uploaded into another dataset's folder (`<root>/uploaded/ledger/`), shaped as the
    owners' file so the Join would bring its name across if it were read. The test's ingest root
    is `tmp_path` (`tests/conftest.py`'s autouse fixture), so this is where an upload puts it."""
    folder = tmp_path / "uploaded" / "ledger"
    folder.mkdir(parents=True)
    other = folder / "owners.csv"
    other.write_text(
        "number,owner_family_name,since\n07700 900731,LEDGER-ONLY-NAME,2020-01-01\n",
        encoding="utf-8",
    )
    return other


def _naming(client: TestClient, location: Path) -> PipelineGraph:
    graph = _draft(client).pipeline.model_copy(deep=True)
    owners = next(n for n in graph.nodes if n.id == "number_owners")
    owners.config = {**owners.config, "source_location": str(location)}
    return graph


def test_another_dataset_s_file_named_by_a_source_node_is_refused_at_save(
    staged: TestClient, tmp_path: Path
) -> None:
    before = _draft(staged).pipeline
    graph = _naming(staged, _another_dataset_s_file(tmp_path))
    saved = staged.put(f"{RECIPE_URL}/pipeline", json=graph.model_dump(mode="json"))
    assert saved.status_code == 422
    assert saved.json()["problems"] == [NOT_OFFERED]
    assert _draft(staged).pipeline == before
    # The drawer says it in the same words, and reads nothing.
    previewed = _preview(staged, "with_owner", graph)
    assert previewed.json()["problems"] == [NOT_OFFERED, *_unsaved(graph, staged)]
    assert "LEDGER-ONLY-NAME" not in previewed.text


def _unsaved(graph: PipelineGraph, client: TestClient) -> list[str]:
    from services.api.studio_staging import _unsaved_sources

    return _unsaved_sources(_draft(client), graph)


def test_another_dataset_s_file_held_by_a_saved_pipeline_is_never_read(
    staged: TestClient, tmp_path: Path
) -> None:
    """A pipeline saved before the gate refused it: the preview, Test, the Map and Load Preview
    and the run each read through `_confined`, for the recipe's own dataset."""
    from services.api.run_source import identify
    from services.api.studio_profile import SourceUnreadableError
    from services.api.studio_staging import source_tables

    other = _another_dataset_s_file(tmp_path)
    _update(staged, pipeline=_naming(staged, other))
    previewed = _preview(staged, "with_owner")
    assert "LEDGER-ONLY-NAME" not in previewed.text
    assert NOT_OFFERED in previewed.json()["problems"]
    for route in ("verify", "preview-graph"):
        response = staged.post(f"{RECIPE_URL}/{route}")
        assert response.status_code == 422, (route, response.text)
        assert "LEDGER-ONLY-NAME" not in response.text
    # The run's own reads: each source's table (`pipeline_run._run_staged_branch`) and the hash
    # *Run now* is held to.
    with pytest.raises(SourceUnreadableError):
        source_tables(_draft(staged), _draft(staged).pipeline, load_id="run-1")
    with pytest.raises(SourceUnreadableError):
        identify(str(other), "pid")


def test_the_dataset_s_own_uploaded_file_is_read(staged: TestClient, tmp_path: Path) -> None:
    """The control: the same file in this dataset's own folder is saved and read."""
    folder = tmp_path / "uploaded" / "pid"
    folder.mkdir(parents=True)
    own = folder / "owners.csv"
    shutil.copy(FIXTURES / "number_owners.csv", own)
    graph = _naming(staged, own)
    saved = staged.put(f"{RECIPE_URL}/pipeline", json=graph.model_dump(mode="json"))
    assert saved.status_code == 200, saved.text
    body = _preview(staged, "with_owner").json()
    assert body["problems"] == [] and len(body["rows"]) == 5


def test_connect_refuses_another_dataset_s_file(staged: TestClient, tmp_path: Path) -> None:
    other = str(_another_dataset_s_file(tmp_path))
    draft = _draft(staged)
    body = {
        "label": draft.label,
        "connector_profile": "generic-csv",
        "source_location": other,
        "handling": draft.handling,
        "legal_basis": draft.legal_basis,
    }
    for response in (
        staged.patch(RECIPE_URL, json=body),
        staged.post("/v1/investigations/inv-1/ingest/recipes", json=body),
    ):
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["error"] == "source_not_offered"
    assert _draft(staged).source_location == draft.source_location


def test_no_sample_of_any_step_reaches_a_case_not_reading_the_dataset(
    staged: TestClient,
) -> None:
    """Rule 4: a recipe's files are its dataset's, as its lists are. A case on another dataset is
    given nothing of any step's sample, nor of Test or the Map and Load Preview."""
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR.model_copy(
        update={"datasets": ["ledger"]}
    )
    graph = _draft(staged).pipeline.model_copy(deep=True)
    # A step no Lookup feeds: a Filter straight over the bookings.
    graph.nodes.append(
        PipelineNode(
            id="raw_filter", kind=PipelineNodeKind.FILTER, label="Raw",
            config={"input": "visit_bookings", "keep": [{"field": "estab_id", "equals": "FMR"}]},
        )  # fmt: skip
    )
    graph.edges.append(PipelineEdge(source="visit_bookings", target="raw_filter"))
    _update(staged, pipeline=graph)
    withheld = "The sample is withheld: it reads this dataset's files and lists"
    for step in ("raw_filter", "with_owner"):
        response = _preview(staged, step)
        body = response.json()
        assert body["values_masked"] is True and body["rows"] == [] and body["counts"] == []
        assert any(p.startswith(withheld) for p in body["problems"]), body["problems"]
        assert "WHITLOW" not in response.text and "VB-2605" not in response.text
    for route in ("verify", "preview-graph"):
        response = staged.post(f"{RECIPE_URL}/{route}")
        assert response.status_code == 422, (route, response.text)
        assert any(p.startswith(withheld) for p in response.json()["problems"])
        assert "WHITLOW" not in response.text and "VB-2605" not in response.text


def test_test_and_the_map_preview_give_nothing_to_a_reader_not_cleared_for_the_source(
    staged: TestClient,
) -> None:
    """Rule 3 (the review of L1.4, item (e)): the drawer's guard on Test and the Map and Load
    Preview, which run the same steps over the same rows."""
    _update(staged, handling=_UNCLEARED_HANDLING)
    for route in ("verify", "preview-graph"):
        response = staged.post(f"{RECIPE_URL}/{route}")
        assert response.status_code == 422, (route, response.text)
        assert any(p.startswith("The sample is withheld") for p in response.json()["problems"])
        for name in ("WHITLOW", "VB-2605-001", "HMP Fenwick Moor"):
            assert name not in response.text
    assert _draft(staged).verified_at is None


def _one_hidden_row(staged: TestClient, tmp_path: Path, hidden: str) -> None:
    """The bookings and owners with a per-row `classification` column, OFFICIAL but for the
    third booking's (`hidden`), and the booking's marking bound to it (ADR-127 decision 3)."""
    import csv

    for name in ("visit_bookings", "number_owners"):
        with (FIXTURES / f"{name}.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        for index, row in enumerate(rows):
            third_booking = name == "visit_bookings" and index == 2
            row["classification"] = hidden if third_booking else "OFFICIAL"
        with (tmp_path / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    template = RECIPE.row_template.model_copy(deep=True)
    booking = next(e for e in template.entities if e.ref == "booking")
    booking.handling = {"classification": {"field": "classification"}}
    _update(staged, row_template=template)


def test_one_hidden_row_among_ten_withholds_the_whole_sample_and_test(
    staged: TestClient, tmp_path: Path
) -> None:
    """The review's should-fix: one row of ten above the reader's clearance by its own per-row
    column, not the whole source masked, withholds the drawer's sample, Test and the Preview."""
    _one_hidden_row(staged, tmp_path, "SECRET")
    response = _preview(staged, "titled")
    assert response.json()["rows"] == [] and response.json()["counts"] == []
    assert any(p.startswith("The sample is withheld") for p in response.json()["problems"])
    for route in ("verify", "preview-graph"):
        response = staged.post(f"{RECIPE_URL}/{route}")
        assert response.status_code == 422, (route, response.text)
        assert "OKAFOR" not in response.text  # the hidden booking's visitor


def test_the_same_ten_rows_all_readable_are_shown(staged: TestClient, tmp_path: Path) -> None:
    """The control for the case above: the same column, every row OFFICIAL."""
    _one_hidden_row(staged, tmp_path, "OFFICIAL")
    assert len(_preview(staged, "titled").json()["rows"]) == 5
    for route in ("verify", "preview-graph"):
        assert staged.post(f"{RECIPE_URL}/{route}").status_code == 200, route


# --- ADR-140 Amendment 19 at a step's preview and at Test -----------------------------------------


def _marked(client: TestClient, tmp_path: Path, default: str | None) -> None:
    """The bookings get a `classification` column the source declares as its marking column, each
    element binding its classification from it; the owners have none, so their table is unmarked.
    The owners' source is registered on the dataset, declaring `default` (or nothing)."""
    import asyncio
    import csv

    from services.api.app import get_sources
    from services.api.sources import InMemorySourceStore

    from schemas.domain import Principal
    from schemas.sources import RegisterSourceInput

    draft = _draft(client)
    bookings = Path(draft.source_location)
    with bookings.open(newline="") as given:
        rows = list(csv.DictReader(given))
    with bookings.open("w", newline="") as out:
        writer = csv.DictWriter(out, [*rows[0], "classification"])
        writer.writeheader()
        writer.writerows(r | {"classification": "OFFICIAL"} for r in rows)
    bound = {"classification": {"field": "classification"}}
    given = draft.row_template
    template = given.model_copy(
        update={
            "entities": [e.model_copy(update={"handling": bound}) for e in given.entities],
            "edges": [e.model_copy(update={"handling": bound}) for e in given.edges],
        }
    )
    columns = {"classification": "classification"}
    _update(client, handling={**draft.handling, "handling_columns": columns}, row_template=template)
    sources = InMemorySourceStore()
    approver = Principal(id="approver-1", clearance="SECRET", org_unit="unit-1")

    async def register() -> None:
        owners = await sources.register(
            "pid",
            RegisterSourceInput(connection_id="files", name="Owners",
                                location=str(tmp_path / "number_owners.csv"),
                                handling={"classification": "OFFICIAL", "handling_code": "P",
                                          "originator": "unit-1", "owning_unit": "unit-1"},
                                legal_basis="Synthetic"),  # fmt: skip
            approver,
        )
        if default is not None:
            await sources.set_default_marking("pid", owners.id, default, approver)

    asyncio.run(register())
    app.dependency_overrides[get_sources] = lambda: sources


def test_a_preview_of_a_join_to_an_unmarked_source_without_a_default_is_refused(
    staged: TestClient, tmp_path: Path
) -> None:
    """Refused before the Join is reached: an unmarked row's empty marking cell reads as one the
    person may not view (fail closed), so the sample is withheld whole. The default, once
    declared, marks those rows, and the same preview runs (the next case)."""
    _marked(staged, tmp_path, None)
    body = _preview(staged, "with_owner").json()
    assert any("The sample is withheld" in p for p in body["problems"]), body["problems"]
    assert body["rows"] == [] and body["values_masked"] is True


def test_a_preview_joins_an_unmarked_source_carrying_its_declared_default(
    staged: TestClient, tmp_path: Path
) -> None:
    _marked(staged, tmp_path, "OFFICIAL")
    body = _preview(staged, "with_owner").json()
    assert body["problems"] == [], body["problems"]
    assert len(body["rows"]) == 5
    assert {r["classification"] for r in body["rows"]} == {"OFFICIAL"}


@pytest.mark.parametrize("default", [None, "OFFICIAL"], ids=["none-declared", "declared"])
def test_test_reads_the_sources_declared_default_as_the_run_does(
    staged: TestClient, tmp_path: Path, default: str | None
) -> None:
    _marked(staged, tmp_path, default)
    response = staged.post(f"{RECIPE_URL}/verify")
    if default is None:
        # Withheld before the Join, as the preview is (fail closed).
        assert response.status_code == 422, response.text
        assert "The sample is withheld" in response.text
    else:
        assert response.status_code == 200, response.text
        assert response.json()["rows_read"] == 10
