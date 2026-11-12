"""Studio › Releases' routes (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4 and its tests;
rules 3 and 4): export then import round-trips the model, pipelines and lists as drafts;
`dry_run` writes nothing; an imported model is not live; an import any of whose pipelines the
canvas's gates refuse writes nothing; each route refuses a reader without its rights, and a dataset
the reader reaches through no case is 404 (rule 4: every read path).

The lists' rows are kept by the real Parquet keeper over a local store (not a fake); the recipe
store and the model store are this file's doubles, the model one refusing what the real one
refuses for these calls (a second draft is refused; `save_draft` needs an open draft). The live
round trip through a second store (`test_a_round_trip_lands_the_same_pipeline_model_and_list`) is
here; the real Postgres stores are run by the leased live set over the same routes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_list_rows,
    get_list_store,
    get_ontology,
    get_principal,
    get_sources,
    get_staging_storage,
    get_studio_recipes,
    get_target_models,
)
from services.api.list_connector import InMemoryListStore, ParquetListRows
from services.api.sources import InMemorySourceStore
from services.ingest.release import MANIFEST

from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.dataset_model import ReferenceList, TargetModel, TargetModelDraftInput
from schemas.domain import Principal
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StudioRecipeStatus,
)
from tests.services.api.test_app import _FakeAudit
from tests.services.api.test_studio_recipe_routes import _draft, _FakeStudioRecipes
from tests.services.api.test_studio_staging_routes import STORAGE, store  # noqa: F401

# ruff: noqa: F811  (the imported fixture is its tests' own same-named parameter)

_RIGHTS = ["right:edit_target_model", "right:publish_pipelines"]
ENGINEER = Principal(
    id="engineer-1",
    clearance="OFFICIAL",
    org_unit="unit-1",
    roles=["source_author", *_RIGHTS],
    datasets=["pid"],
)
_AT = datetime(2026, 11, 10, tzinfo=UTC)
_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "synthetic",
    "owning_unit": "unit-1",
}


class _Models:
    """The model store's calls an export and an import make, with the real store's refusals for
    them: one draft at a time, and a save needs an open draft."""

    def __init__(self) -> None:
        self.live_model: TargetModel | None = TargetModel(
            dataset_id="pid", version=2, state="live", packs={"niem": 1},
            reference_lists=["lst-wings"], created_at=_AT, created_by="owner-9",
        )  # fmt: skip
        self.draft_model: TargetModel | None = None
        self.saved: list[TargetModelDraftInput] = []

    async def live(self, dataset_id: str) -> TargetModel | None:
        return self.live_model if dataset_id == "pid" else None

    async def draft(self, dataset_id: str) -> TargetModel | None:
        return self.draft_model

    async def open_draft(self, dataset_id: str, principal: Principal) -> TargetModel:
        if self.draft_model is not None:
            raise AssertionError("a second draft: the real store refuses it")
        base = self.live_model
        self.draft_model = TargetModel(
            dataset_id=dataset_id, version=(base.version + 1 if base else 1), state="draft",
            created_at=_AT, created_by=principal.id,
        )  # fmt: skip
        return self.draft_model

    async def save_draft(
        self, dataset_id: str, given: TargetModelDraftInput, principal: Principal
    ) -> TargetModel:
        assert self.draft_model is not None, "the real store refuses a save with no draft open"
        self.saved.append(given)
        self.draft_model = self.draft_model.model_copy(update=given.model_dump())
        return self.draft_model


def _graph(location: str, *, sql: bool = False) -> PipelineGraph:
    nodes = [
        PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model"),
        PipelineNode(
            id="visits",
            kind=PipelineNodeKind.SOURCE,
            label="Visits",
            config={"source_location": location},
        ),  # fmt: skip
        PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
        PipelineNode(
            id="load", kind=PipelineNodeKind.LOAD, label="Load", config={"dataset_id": "pid"}
        ),
    ]
    edges = [("domain", "visits"), ("visits", "map"), ("map", "load")]
    if sql:
        nodes.insert(
            2,
            PipelineNode(
                id="tidy",
                kind=PipelineNodeKind.SQL,
                label="Tidy",
                config={
                    "select": "SELECT _ref, name FROM visits",
                    "summary": "Names only",
                    "inputs": ["visits"],
                },
            ),  # fmt: skip
        )
        edges = [("domain", "visits"), ("visits", "tidy"), ("tidy", "map"), ("map", "load")]
    return PipelineGraph(nodes=nodes, edges=[PipelineEdge(source=a, target=b) for a, b in edges])


@pytest.fixture
def ingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ingest"
    (root / "pid").mkdir(parents=True)
    (root / "pid" / "visits.csv").write_text("name\nA\n")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    return root


class _World:
    def __init__(self, ingest: Path, *, sql: bool = False, handling: dict[str, str] | None = None):
        location = str(ingest / "pid" / "visits.csv")
        self.recipes = _FakeStudioRecipes(
            _draft(
                recipe_id="rcp-1", version=3, status=StudioRecipeStatus.PUBLISHED,
                label="Visits", source_location=location, handling=handling or _HANDLING,
                legal_basis="Synthetic", dataset_id="pid", pipeline=_graph(location, sql=sql),
                created_by="owner-9", published_by="owner-9", schedule_owner="owner-9",
            )
        )  # fmt: skip
        self.models = _Models()
        self.rows = ParquetListRows(STORAGE)
        self.rows.write(
            ReferenceList(
                id="lst-wings", dataset_id="pid", name="wings", kind="reference",
                key_column="code", version=1,
            ),
            [{"code": "A", "name": "A wing"}],
        )  # fmt: skip
        self.audit = _FakeAudit()

    def install(self, principal: Principal) -> TestClient:
        app.dependency_overrides.update(
            {
                get_principal: lambda: principal,
                get_studio_recipes: lambda: self.recipes,
                get_target_models: lambda: self.models,
                get_list_rows: lambda: self.rows,
                get_list_store: lambda: InMemoryListStore(),
                get_sources: lambda: InMemorySourceStore(),
                get_staging_storage: lambda: STORAGE,
                get_audit: lambda: self.audit,
                get_handling_scheme: lambda: load_uk_le_scheme(),
                get_ontology: lambda: load_default_ontology(),
            }
        )
        return TestClient(app)


@pytest.fixture(autouse=True)
def _clear() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _export(client: TestClient) -> dict[str, str]:
    answer = client.get("/v1/datasets/pid/release", params={"name": "pid-release", "version": "1"})
    assert answer.status_code == 200, answer.text
    return answer.json()["files"]


def test_export_then_import_lands_drafts_and_nothing_live(store: Path, ingest: Path) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    assert set(files) >= {MANIFEST, "model.yaml", "lists/wings.yaml"}
    world.recipes.create_calls.clear()

    answer = client.post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 200, answer.text
    plan = answer.json()
    assert plan["refused"] == []
    assert {(i["role"], i["action"]) for i in plan["items"]} == {
        ("domain_model", "new_draft"),
        ("pipeline", "new_draft"),
    }
    assert world.models.saved and world.models.saved[-1].packs == {"niem": 1}
    assert world.models.draft_model is not None and world.models.draft_model.state == "draft"
    assert world.models.live_model is not None and world.models.live_model.version == 2
    (created,) = world.recipes.create_calls
    assert created["source_location"] == str(ingest / "pid" / "visits.csv")
    assert (
        world.recipes.draft is not None and world.recipes.draft.status is StudioRecipeStatus.DRAFT
    )
    assert "import_dataset_release" in [e["action"] for e in world.audit.records]


def test_a_dry_run_writes_nothing(store: Path, ingest: Path) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    world.recipes.create_calls.clear()
    answer = client.post(
        "/v1/datasets/pid/release/import", params={"dry_run": True}, json={"files": files}
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["dry_run"] is True and answer.json()["items"]
    assert world.recipes.create_calls == []
    assert world.models.saved == [] and world.models.draft_model is None


def test_an_import_whose_file_is_not_here_writes_nothing(store: Path, ingest: Path) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    (ingest / "pid" / "visits.csv").unlink()
    world.recipes.create_calls.clear()
    answer = client.post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 422
    assert any("visits.csv" in p and "add it here first" in p for p in answer.json()["refused"])
    assert world.recipes.create_calls == [] and world.models.saved == []


def test_an_expert_step_needs_write_sql_transforms_to_import(store: Path, ingest: Path) -> None:
    world = _World(ingest, sql=True)
    files = _export(world.install(ENGINEER))
    world.recipes.create_calls.clear()
    answer = world.install(ENGINEER).post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 422
    assert any("write_sql_transforms" in p for p in answer.json()["refused"])
    assert world.recipes.create_calls == [] and world.models.saved == []


def test_a_changed_bundle_is_refused_whole(store: Path, ingest: Path) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    files["model.yaml"] = files["model.yaml"].replace("niem: 1", "niem: 9")
    world.recipes.create_calls.clear()
    answer = client.post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 422
    assert any("SHA-256 differs" in p for p in answer.json()["refused"])
    assert world.recipes.create_calls == [] and world.models.saved == []


def test_a_pipeline_marked_above_the_exporter_is_left_out_and_counted(
    store: Path, ingest: Path
) -> None:
    world = _World(ingest, handling={**_HANDLING, "classification": "SECRET"})
    answer = world.install(ENGINEER).get(
        "/v1/datasets/pid/release", params={"name": "pid-release", "version": "1"}
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["left_out"] == 1
    manifest = yaml.safe_load(answer.json()["files"][MANIFEST])
    assert manifest["spec"]["pipelines"] == []


@pytest.mark.parametrize(
    ("missing", "route"),
    [
        ("right:edit_target_model", "export"),
        ("right:publish_pipelines", "export"),
        ("right:edit_target_model", "import"),
        # The studio role grants edit_pipelines itself, so the role goes, and the right with it.
        ("source_author", "import"),
    ],
)
def test_each_route_refuses_a_reader_without_its_rights(
    store: Path, ingest: Path, missing: str, route: str
) -> None:
    world = _World(ingest)
    files = _export(world.install(ENGINEER))
    without = ENGINEER.model_copy(update={"roles": [r for r in ENGINEER.roles if r != missing]})
    client = world.install(without)
    world.recipes.create_calls.clear()
    if route == "export":
        answer = client.get("/v1/datasets/pid/release", params={"name": "x", "version": "1"})
    else:
        answer = client.post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 403, answer.text
    assert world.recipes.create_calls == [] and world.models.saved == []


def test_a_dataset_reached_through_no_case_is_not_found(store: Path, ingest: Path) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER.model_copy(update={"datasets": ["another"]}))
    assert (
        client.get("/v1/datasets/pid/release", params={"name": "x", "version": "1"}).status_code
        == 404
    )
    assert client.post("/v1/datasets/pid/release/import", json={"files": {}}).status_code == 404


def _rewrite(files: dict[str, str], path: str, text: str) -> None:
    """A hand-edited bundle with its checksum kept true."""
    import hashlib

    files[path] = text
    manifest = yaml.safe_load(files[MANIFEST])
    for entry in manifest["spec"]["files"]:
        if entry["path"] == path:
            entry["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    files[MANIFEST] = yaml.safe_dump(manifest, sort_keys=False)


def _pipeline_path(files: dict[str, str]) -> str:
    return next(p for p in files if p.startswith("pipelines/"))


def test_an_imported_handling_is_judged_as_connect_judges_it(store: Path, ingest: Path) -> None:
    """The lane review of L1.7, item 3: Connect's declarations and ADR-068's default marking."""
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    path = _pipeline_path(files)
    bad = yaml.safe_load(files[path])
    bad["handling"]["units"] = ["", "unit-1"]
    edited = dict(files)
    _rewrite(edited, path, yaml.safe_dump(bad, sort_keys=False))
    world.recipes.create_calls.clear()
    answer = client.post("/v1/datasets/pid/release/import", json={"files": edited})
    assert answer.status_code == 422, answer.text
    assert any("its source's handling" in p for p in answer.json()["refused"])
    assert world.recipes.create_calls == []
    blank = yaml.safe_load(files[path])
    blank["handling"]["classification"] = ""
    _rewrite(files, path, yaml.safe_dump(blank, sort_keys=False))
    answer = client.post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 200, answer.text
    (created,) = world.recipes.create_calls
    assert created["handling"]["classification"] == "PUBLIC"  # type: ignore[index]


def test_a_round_trip_lands_the_same_pipeline_model_and_list(
    store: Path, ingest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Export from one store, import into another that keeps no list yet, then export what was
    imported: the pipeline's and the model's files are the same, but for the version numbers each
    environment gives its own (ADR-141's round trip; the lane review of L1.7, item 10)."""
    first = _World(ingest)
    files = _export(first.install(ENGINEER))
    app.dependency_overrides.clear()

    from services.ingest import staging

    from tests.services.api.test_studio_staging_routes import LocalStore

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(staging, "filesystem", lambda config: LocalStore(elsewhere))
    second = _World.__new__(_World)
    second.recipes = _FakeStudioRecipes(None)
    second.models = _Models()
    second.models.live_model = None
    second.rows = ParquetListRows(STORAGE)
    second.audit = _FakeAudit()
    client = second.install(ENGINEER)
    answer = client.post("/v1/datasets/pid/release/import", json={"files": files})
    assert answer.status_code == 200, answer.text
    assert ("reference_list", "new_draft") in {(i["role"], i["action"]) for i in answer.json()["items"]}
    wings = ReferenceList(id="lst-wings", dataset_id="pid", name="wings", kind="reference",
                          key_column="code", version=1)  # fmt: skip
    assert second.rows.read(wings) == [{"code": "A", "name": "A wing"}]
    # The imported draft deployed and the model made live there, as a person would, then exported.
    assert second.recipes.draft is not None and second.models.draft_model is not None
    second.recipes.draft = second.recipes.draft.model_copy(
        update={"status": StudioRecipeStatus.PUBLISHED, "dataset_id": "pid", "version": 3,
                "recipe_id": "rcp-1"}
    )  # fmt: skip
    second.models.live_model = second.models.draft_model.model_copy(update={"state": "live", "version": 2})
    again = _export(client)

    def comparable(text: str) -> dict[str, object]:
        data = yaml.safe_load(text)
        data.pop("exported_version", None)
        return data

    assert comparable(again["model.yaml"]) == comparable(files["model.yaml"])
    assert comparable(again[_pipeline_path(again)]) == comparable(files[_pipeline_path(files)])
    assert again["lists/wings.yaml"] == files["lists/wings.yaml"]


@pytest.mark.parametrize(
    "name",
    ["POSTGRES_PASSWORD", "OSPREY_MODEL_PROVIDER_KEY", "OSPREY_MODEL_KEY_ANTHROPIC", "MINIO_ACCESS_KEY",
     "AZURE_STORAGE_KEY", "OIDC_TOKEN_EXCHANGE_CLIENT_SECRET"],
)  # fmt: skip
def test_a_secret_planted_in_the_deployments_environment_is_never_exported(
    store: Path, ingest: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """ADR-140 Amendment 9's test at the route's own call site: the value `deployment.env` puts in
    the Conduit's environment, planted in a pipeline's words, refuses the export, which names the
    file and never the value (`deployment_secrets()`, read by the route)."""
    planted = f"planted-{name.lower()}-0x51"
    monkeypatch.setenv(name, planted)
    world = _World(ingest)
    world.recipes.draft = world.recipes.draft.model_copy(update={"legal_basis": f"see {planted}"})  # type: ignore[union-attr]
    answer = world.install(ENGINEER).get(
        "/v1/datasets/pid/release", params={"name": "pid-release", "version": "1"}
    )
    assert answer.status_code == 422, answer.text
    assert "one of this deployment's secrets" in answer.text
    assert planted not in answer.text


# --- CARRIES row 90 (L1.7's review): an import never silently replaces an in-progress draft ------


def _held_by(world: _World, who: str) -> TargetModel:
    """An in-progress draft of the dataset's model, opened by `who`, as the real store holds one."""
    world.models.draft_model = TargetModel(
        dataset_id="pid", version=3, state="draft", packs={"niem": 1},
        reference_lists=["lst-wings"], created_at=_AT, created_by=who,
    )  # fmt: skip
    return world.models.draft_model


def _import(client: TestClient, files: dict[str, str], **params: object):  # type: ignore[no-untyped-def]
    return client.post("/v1/datasets/pid/release/import", params=params, json={"files": files})


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("dry_run", [False, True])
def test_another_persons_draft_is_refused_in_words_naming_them(
    store: Path, ingest: Path, confirmed: bool, dry_run: bool
) -> None:
    """Their draft is theirs: no confirmation of the importer's replaces it, and a dry run says so
    before the import is tried."""
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    held = _held_by(world, "analyst-7")
    world.recipes.create_calls.clear()
    answer = _import(client, files, dry_run=dry_run, replace_own_draft=confirmed)
    assert answer.status_code == 422, answer.text
    plan = answer.json()
    (words,) = [p for p in plan["refused"] if "in-progress draft" in p]
    assert "analyst-7" in words and "Studio › Model" in words and "discard" in words
    assert plan["replaces_own_draft"] is False, "another's draft is never offered to confirm"
    assert world.models.draft_model == held and world.models.saved == []
    assert world.recipes.create_calls == []


@pytest.mark.parametrize("dry_run", [False, True])
def test_the_importers_own_draft_is_refused_until_confirmed(
    store: Path, ingest: Path, dry_run: bool
) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    held = _held_by(world, ENGINEER.id)
    world.recipes.create_calls.clear()
    answer = _import(client, files, dry_run=dry_run)
    assert answer.status_code == 422, answer.text
    plan = answer.json()
    (words,) = [p for p in plan["refused"] if "in-progress draft" in p]
    assert "your own" in words and "--replace-own-draft" in words
    assert plan["replaces_own_draft"] is True
    assert world.models.draft_model == held and world.models.saved == []
    assert world.recipes.create_calls == []


def test_the_importers_own_draft_is_replaced_when_confirmed(store: Path, ingest: Path) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    _held_by(world, ENGINEER.id)
    world.recipes.create_calls.clear()
    answer = _import(client, files, replace_own_draft=True)
    assert answer.status_code == 200, answer.text
    plan = answer.json()
    assert plan["refused"] == [] and plan["replaces_own_draft"] is True
    assert ("domain_model", "replaces_draft") in {(i["role"], i["action"]) for i in plan["items"]}
    assert world.models.saved and world.models.saved[-1].packs == {"niem": 1}
    assert len(world.recipes.create_calls) == 1
    (entry,) = [e for e in world.audit.records if e["action"] == "import_dataset_release"]
    assert entry["resolved_query"]["replaced_own_draft"] is True


def test_with_no_draft_the_import_opens_one_without_a_confirmation(
    store: Path, ingest: Path
) -> None:
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    world.recipes.create_calls.clear()
    answer = _import(client, files)
    assert answer.status_code == 200, answer.text
    assert answer.json()["replaces_own_draft"] is False
    assert world.models.draft_model is not None
    assert world.models.draft_model.created_by == ENGINEER.id
    (entry,) = [e for e in world.audit.records if e["action"] == "import_dataset_release"]
    assert entry["resolved_query"]["replaced_own_draft"] is False


def test_a_draft_opened_by_another_between_plan_and_write_is_refused_before_any_write(
    store: Path, ingest: Path
) -> None:
    """The plan and the write each read the draft: someone opening one in between is refused at
    the write, before the model, a pipeline or a list is written (the strict option)."""
    world = _World(ingest)
    client = world.install(ENGINEER)
    files = _export(client)
    world.recipes.create_calls.clear()
    reads = 0
    real_draft = world.models.draft

    async def opened_meanwhile(dataset_id: str) -> TargetModel | None:
        nonlocal reads
        reads += 1
        if reads == 2:
            _held_by(world, "analyst-7")
        return await real_draft(dataset_id)

    world.models.draft = opened_meanwhile  # type: ignore[method-assign]
    answer = _import(client, files)
    assert answer.status_code == 422, answer.text
    assert any("analyst-7" in p for p in answer.json()["refused"])
    assert world.models.saved == [] and world.recipes.create_calls == []
    assert world.models.draft_model is not None
    assert world.models.draft_model.created_by == "analyst-7"
