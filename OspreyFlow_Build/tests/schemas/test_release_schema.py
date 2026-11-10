"""The release manifest's published schema (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4):
`packages/schemas/release.schema.json` is what a script or CI checks a bundle against, so it must
be the model's own and must refuse what the model refuses.

Rule 15: the drift check is shown red by a changed model, and the schema's refusal by a manifest
carrying a field a credential would ride in, in the shape a real bundle's manifest takes.
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from schemas.generate_ts import RELEASE_SCHEMA, release_schema_text

_MANIFEST = {
    "apiVersion": "ospreyflow.io/v1",
    "kind": "DatasetRelease",
    "metadata": {"name": "visits-and-contacts", "version": "1"},
    "spec": {
        "domain_model": "model.yaml",
        "packs": {"niem": 2},
        "pipelines": ["pipelines/visits.yaml"],
        "reference_lists": ["lists/wings.yaml"],
        "connections": ["prison-records"],
        "files": [{"path": "model.yaml", "role": "domain_model", "sha256": "a" * 64}],
    },
}


def _published() -> dict[str, object]:
    return json.loads(RELEASE_SCHEMA.read_text())


def test_the_published_schema_is_the_models_own() -> None:
    assert RELEASE_SCHEMA.read_text() == release_schema_text()


def test_the_drift_check_sees_a_changed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import schemas.generate_ts as generate

    real = generate.DatasetRelease.model_json_schema
    monkeypatch.setattr(
        generate.DatasetRelease,
        "model_json_schema",
        classmethod(lambda cls, **kw: {**real(**kw), "title": "Changed"}),
    )
    assert RELEASE_SCHEMA.read_text() != release_schema_text()


def test_a_bundles_manifest_validates() -> None:
    jsonschema.validate(_MANIFEST, _published())


@pytest.mark.parametrize(
    ("where", "planted"),
    [
        ("spec", {"connection_secrets": {"prison-records": "hunter2"}}),
        ("metadata", {"owner": "an-account-id"}),
        ("top", {"members": ["an-account-id"]}),
    ],
)
def test_a_manifest_with_a_field_beyond_the_schema_is_refused(
    where: str, planted: dict[str, object]
) -> None:
    manifest = json.loads(json.dumps(_MANIFEST))
    target = manifest if where == "top" else manifest[where]
    target.update(planted)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, _published())


def test_a_file_path_climbing_out_of_the_bundle_is_refused() -> None:
    manifest = json.loads(json.dumps(_MANIFEST))
    manifest["spec"]["files"][0]["path"] = "../deployment.env"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, _published())


def test_the_api_version_and_kind_are_fixed() -> None:
    manifest = json.loads(json.dumps(_MANIFEST))
    manifest["kind"] = "ConfigMap"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, _published())
