"""A dataset's release bundle (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4 and its tests):
an export holds no credential, membership, owner or licensed row; export then read round-trips the
model, pipelines and lists; a bundle that is not what its manifest says is refused whole.

Each guard is shown red in `process/lanes/studio/L1.7_RED_RECORD.md` by taking it out at its call
site in `services/ingest/release.py` (rule 15): the value scan, the key scan, `_rows_travel`'s
screening-list test, and `read_bundle`'s checksum and extra-file checks.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml
from services.ingest.release import (
    MANIFEST,
    MAX_LIST_ROWS,
    ListToRelease,
    ReleaseRefused,
    build_bundle,
    pipeline_for,
    read_bundle,
)

from schemas.dataset_model import ReferenceList, TargetModel
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StudioRecipeDraft,
    StudioRecipeStatus,
)

OWNER = "acct-owner-7731"
PUBLISHER = "acct-publisher-5520"
CASE = "case-membership-9902"
SECRET = "s3cr3t-from-deployment-env-4417"
LICENSED = "LICENSED-ROW-ZX81"
_AT = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "synthetic",
    "owning_unit": "unit-a",
}


def _model() -> TargetModel:
    return TargetModel(
        dataset_id="ds-visits",
        version=3,
        state="live",
        packs={"niem": 2},
        extensions=[],
        reference_lists=["wings"],
        created_at=_AT,
        created_by=OWNER,
        made_live_at=_AT,
        made_live_by=OWNER,
    )


def _graph(extra_source_config: dict[str, object] | None = None) -> PipelineGraph:
    return PipelineGraph(
        nodes=[
            PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model"),
            PipelineNode(
                id="source",
                kind=PipelineNodeKind.SOURCE,
                label="Visits",
                config={
                    "source_location": "/srv/ingest/ds-visits/visits.csv",
                    **(extra_source_config or {}),
                },
            ),
            PipelineNode(id="profile", kind=PipelineNodeKind.PROFILE, label="Profile"),
            PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
            PipelineNode(
                id="load",
                kind=PipelineNodeKind.LOAD,
                label="Load",
                config={"dataset_id": "ds-visits"},
            ),
        ],
        edges=[
            PipelineEdge(source=a, target=b)
            for a, b in [
                ("domain", "source"),
                ("source", "profile"),
                ("profile", "map"),
                ("map", "load"),
            ]
        ],
    )


def _pipeline(**changes: object) -> StudioRecipeDraft:
    data: dict[str, object] = {
        "recipe_id": "rcp-visits-0001",
        "version": 4,
        "status": StudioRecipeStatus.PUBLISHED,
        "label": "Visits and contacts",
        "connector_profile": "csv",
        "source_location": "/srv/ingest/ds-visits/visits.csv",
        "handling": _HANDLING,
        "legal_basis": "Synthetic fixture: no real data",
        "owning_unit": "unit-a",
        "created_by": OWNER,
        "created_at": _AT,
        "ready_for_profile": True,
        "published_by": PUBLISHER,
        "published_at": _AT,
        "schedule_cron": "0 6 * * *",
        "schedule_owner": OWNER,
        "schedule_case": CASE,
        "dataset_id": "ds-visits",
        "pipeline": _graph(),
    }
    data.update(changes)
    return StudioRecipeDraft.model_validate(data)


def _lists(screening_rows: int = 1) -> list[ListToRelease]:
    return [
        ListToRelease(
            ReferenceList(
                id="lst-wings",
                dataset_id="ds-visits",
                name="wings",
                kind="reference",
                key_column="code",
                version=2,
            ),
            rows=[{"code": "A", "name": "A wing"}, {"code": "B", "name": "B wing"}],
        ),
        ListToRelease(
            ReferenceList(
                id="lst-sanctions",
                dataset_id="ds-visits",
                name="sanctions",
                kind="screening",
                key_column="entry",
                version=7,
            ),
            rows=[{"entry": LICENSED, "name": "a licensed entry"}] * screening_rows,
        ),
    ]


def _bundle(**changes: object) -> dict[str, bytes]:
    kwargs: dict[str, object] = {
        "name": "visits-and-contacts",
        "version": "1",
        "model": _model(),
        "pipelines": [_pipeline()],
        "lists": _lists(),
        "connections": ["prison-records"],
        "secrets": [SECRET],
    }
    kwargs.update(changes)
    return build_bundle(**kwargs)  # type: ignore[arg-type]


def _text(files: dict[str, bytes]) -> str:
    return "\n".join(d.decode() for d in files.values())


def test_an_export_holds_no_owner_membership_or_licensed_row() -> None:
    text = _text(_bundle())
    for planted in (OWNER, PUBLISHER, CASE, LICENSED, SECRET, "ds-visits", "/srv/ingest"):
        assert planted not in text, planted


def test_a_screening_lists_rows_never_travel_however_small() -> None:
    files = _bundle()
    assert yaml.safe_load(files["lists/sanctions.yaml"])["rows"] is None
    assert not any(LICENSED in d.decode() for d in files.values())


def test_a_deployment_secret_planted_in_a_pipeline_refuses_the_export() -> None:
    with pytest.raises(ReleaseRefused) as refused:
        _bundle(pipelines=[_pipeline(legal_basis=f"see {SECRET}")])
    assert "one of this deployment's secrets" in str(refused.value)
    assert SECRET not in str(refused.value)


def test_a_credential_field_planted_in_a_source_refuses_the_export() -> None:
    planted = _pipeline(pipeline=_graph({"connection": {"password": "a-password-typed-in"}}))
    with pytest.raises(ReleaseRefused) as refused:
        _bundle(pipelines=[planted])
    assert "a field a credential is kept in" in str(refused.value)
    assert "a-password-typed-in" not in str(refused.value)


def test_a_column_named_for_a_token_is_not_a_credential() -> None:
    _bundle(pipelines=[_pipeline(pipeline=_graph({"token_column": "ref"}))])


def test_export_then_read_round_trips_the_model_pipelines_and_lists() -> None:
    files = _bundle()
    bundle = read_bundle(files)
    assert bundle.model.packs == {"niem": 2}
    assert bundle.model.reference_lists == ["wings"]
    (pipeline,) = bundle.pipelines
    assert pipeline.label == "Visits and contacts"
    assert pipeline.handling == _HANDLING
    graph = pipeline_for(pipeline, "ds-elsewhere")
    assert graph is not None
    load = next(n for n in graph.nodes if n.kind is PipelineNodeKind.LOAD)
    assert load.config["dataset_id"] == "ds-elsewhere"
    assert [n.id for n in graph.nodes] == [n.id for n in _graph().nodes]
    assert bundle.list_rows == {
        "wings": [{"code": "A", "name": "A wing"}, {"code": "B", "name": "B wing"}]
    }
    assert {x.name for x in bundle.lists} == {"wings", "sanctions"}


def test_the_same_release_exported_twice_is_byte_identical() -> None:
    assert _bundle() == _bundle()


def test_a_large_lists_rows_stay_at_home_and_say_so() -> None:
    big = ListToRelease(
        ReferenceList(
            id="lst-big",
            dataset_id="ds-visits",
            name="big",
            kind="reference",
            key_column="k",
            version=1,
        ),
        rows=[{"k": str(i)} for i in range(MAX_LIST_ROWS + 1)],
    )
    files = _bundle(lists=[big])
    assert yaml.safe_load(files["lists/big.yaml"])["rows"] is None
    assert not any(p.startswith("lists/rows/") for p in files)


def test_the_manifest_names_every_file_with_its_checksum() -> None:
    files = _bundle()
    manifest = yaml.safe_load(files[MANIFEST])
    assert manifest["apiVersion"] == "ospreyflow.io/v1"
    assert manifest["kind"] == "DatasetRelease"
    assert manifest["spec"]["connections"] == ["prison-records"]
    assert {f["path"] for f in manifest["spec"]["files"]} == set(files) - {MANIFEST}


def test_a_changed_file_is_refused() -> None:
    files = _bundle()
    path = next(p for p in files if p.startswith("pipelines/"))
    files[path] = files[path].replace(b"Visits and contacts", b"Visits and contacts!")
    with pytest.raises(ReleaseRefused) as refused:
        read_bundle(files)
    assert "SHA-256 differs" in str(refused.value)


def test_a_file_the_manifest_does_not_name_is_refused() -> None:
    files = _bundle()
    files["deployment.env"] = f"POSTGRES_PASSWORD={SECRET}\n".encode()
    with pytest.raises(ReleaseRefused) as refused:
        read_bundle(files)
    assert "deployment.env is in the bundle but not in its manifest" in str(refused.value)


def test_a_screening_lists_rows_slipped_into_a_bundle_are_refused() -> None:
    files = _bundle()
    rows = f"entry,name\n{LICENSED},x\n".encode()
    import hashlib

    path = f"lists/rows/{hashlib.sha256(rows).hexdigest()}.csv"
    files[path] = rows
    listing = yaml.safe_load(files["lists/sanctions.yaml"])
    listing["rows"] = path
    files["lists/sanctions.yaml"] = yaml.safe_dump(listing, sort_keys=False).encode()
    manifest = yaml.safe_load(files[MANIFEST])
    for entry in manifest["spec"]["files"]:
        if entry["path"] == "lists/sanctions.yaml":
            entry["sha256"] = hashlib.sha256(files["lists/sanctions.yaml"]).hexdigest()
    manifest["spec"]["files"].append({"path": path, "role": "list_rows", "sha256": path[11:-4]})
    files[MANIFEST] = yaml.safe_dump(manifest, sort_keys=False).encode()
    with pytest.raises(ReleaseRefused) as refused:
        read_bundle(files)
    assert "a screening list; its rows never travel" in str(refused.value)


def test_a_manifest_that_is_not_a_release_is_refused() -> None:
    files = _bundle()
    files[MANIFEST] = b"apiVersion: v1\nkind: ConfigMap\nmetadata: {name: x}\n"
    with pytest.raises(ReleaseRefused):
        read_bundle(files)


def _rewrite(files: dict[str, bytes], path: str, data: bytes) -> None:
    """A file changed and the manifest's checksum kept true, as a hand-edited bundle would be."""
    import hashlib

    files[path] = data
    manifest = yaml.safe_load(files[MANIFEST])
    for entry in manifest["spec"]["files"]:
        if entry["path"] == path:
            entry["sha256"] = hashlib.sha256(data).hexdigest()
    files[MANIFEST] = yaml.safe_dump(manifest, sort_keys=False).encode()


def test_a_credential_field_in_a_received_pipeline_is_refused() -> None:
    """Planted in a source node's config, a free mapping no model forbids a key in, so only the
    key scan can refuse it (rule 15: not a key `extra="forbid"` would refuse anyway)."""
    files = _bundle()
    path = next(p for p in files if p.startswith("pipelines/"))
    pipeline = yaml.safe_load(files[path])
    pipeline["pipeline"]["nodes"][1]["config"]["client_secret"] = "typed-in"
    _rewrite(files, path, yaml.safe_dump(pipeline, sort_keys=False).encode())
    with pytest.raises(ReleaseRefused) as refused:
        read_bundle(files)
    assert "a field a credential is kept in (pipeline.nodes[1].config.client_secret)" in str(
        refused.value
    )
