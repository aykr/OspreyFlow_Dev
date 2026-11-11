"""On the `cloud-platform` profile an S3 or Athena connection reaches only a source the render made a
way out to (ADR-140 Amendment 21; L1.9 part 2): `cloud_platform.connector_sources`, as the render
tells the Conduit (`OSPREY_CONNECTOR_SOURCES`). Admin › Connections refuses one not declared, in
words naming the setting, the re-render and `helm upgrade`, as Admin › Models refuses an engine the
render did not make (ADR-135 Amendment 8).

Every path a connection is used on, each refused (the build plan's "every sibling path"):
- **saving it** — `test_an_undeclared_connection_is_refused_when_it_is_saved`;
- **Test connection** and **every read** (registering a source, Refresh now), for a connection
  saved before the declaration was taken out of a re-render —
  `test_a_connection_no_longer_declared_is_refused_at_test_and_at_every_read`;
- **each way a connection can differ from the declaration** — another bucket, region, wider or
  sibling folder; another workgroup, region, database, catalog or results location —
  `test_a_connection_wider_than_its_declaration_is_refused`.

And what it must not refuse: a declared one, a narrower folder, a connection's own results location
left to its workgroup (`test_a_declared_connection_is_saved_and_tested`), and every other profile,
which has no egress render (`test_another_profile_is_not_held_to_a_declaration`).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.app import READ_REFUSED_FOR_AUTHORS

from .test_cloud_connector_access import (  # noqa: F401 (the fixture, by name)
    READS,
    SETTINGS,
    _as,
    _reads,
    _register,
    world,
)

DECLARED = {
    "s3": [{"bucket": "synthetic-exports", "region": "eu-west-2", "prefix": "client-a/"}],
    "athena": [{"workgroup": "primary", "region": "eu-west-2", "databases": ["visits", "finance"],
                "results_location": "s3://synthetic-athena-results/out/",
                "table_locations": []}],
}  # fmt: skip
KINDS = pytest.mark.parametrize("kind", ["s3", "athena"])


def _render_made(monkeypatch: pytest.MonkeyPatch, declared: dict[str, Any] | None) -> None:
    """What a cloud-platform render tells the Conduit: its profile, and the declaration when any."""
    monkeypatch.setenv("OSPREY_PROFILE", "cloud-platform")
    if declared is None:
        monkeypatch.delenv("OSPREY_CONNECTOR_SOURCES", raising=False)
    else:
        monkeypatch.setenv("OSPREY_CONNECTOR_SOURCES", json.dumps(declared))


def _save(world: SimpleNamespace, kind: str, settings: dict[str, Any] | None = None) -> Any:
    body = {"kind": kind, "name": f"Synthetic {kind}", "datasets": ["ds-a"],
            "settings": settings or SETTINGS[kind]}  # fmt: skip
    return world.client.post("/v1/admin/connections", json=body, headers=_as("admin"))


def _refused_in_words(reply: Any) -> str:
    assert reply.status_code == 422, reply.text
    words = str(reply.json()["detail"]["detail"])
    assert "cloud_platform.connector_sources" in words
    assert "re-render" in words and "helm upgrade" in words
    return words


@KINDS
def test_an_undeclared_connection_is_refused_when_it_is_saved(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    _render_made(monkeypatch, None)
    _refused_in_words(_save(world, kind))
    kept = world.client.get("/v1/admin/connections", headers=_as("admin")).json()
    assert [c["kind"] for c in kept] == ["files"]  # the built-in one alone: nothing was saved
    assert _reads(world) == 0


@KINDS
def test_a_declared_connection_is_saved_and_tested(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    _render_made(monkeypatch, DECLARED)
    narrower = {**SETTINGS[kind], **({"prefix": "client-a/visits/"} if kind == "s3" else {})}
    made = _save(world, kind, narrower)
    assert made.status_code == 201, made.text
    tested = world.client.post(f"/v1/admin/connections/{made.json()['id']}/test",
                               headers=_as("admin"))  # fmt: skip
    assert tested.json()["ok"] is True, tested.text


@KINDS
def test_a_connection_no_longer_declared_is_refused_at_test_and_at_every_read(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    _render_made(monkeypatch, DECLARED)
    connection_id = _save(world, kind).json()["id"]
    source = _register(world, "ds-a", connection_id, "author_a", kind)
    assert source.status_code == 201, source.text
    asked = _reads(world)
    _render_made(monkeypatch, {"s3": [], "athena": []})  # re-rendered without it
    tested = world.client.post(f"/v1/admin/connections/{connection_id}/test", headers=_as("admin"))
    assert tested.json()["ok"] is False
    assert "cloud_platform.connector_sources" in tested.json()["words"]
    again = world.client.post(f"/v1/datasets/ds-a/sources/{source.json()['id']}/read",
                              headers=_as("author_a"))  # fmt: skip
    assert again.status_code == 422
    assert again.json()["detail"]["detail"] == READ_REFUSED_FOR_AUTHORS  # an author's fixed words
    fresh = world.client.post(
        "/v1/datasets/ds-a/sources",
        json={"connection_id": connection_id, "name": "Visits again", "location": "visits-again",
              "handling": source.json()["handling"], "legal_basis": "Synthetic demonstration",
              "read": READS[kind]},
        headers=_as("author_a"),
    )  # fmt: skip
    assert fresh.status_code == 422, fresh.text
    assert _reads(world) == asked  # nothing asked of the bucket or Athena


WIDER = [
    ("s3", {"bucket": "synthetic-other"}),
    ("s3", {"region": "eu-west-1"}),
    ("s3", {"prefix": ""}),
    ("s3", {"prefix": "client-b/"}),
    ("s3", {"prefix": "client-ab/"}),
    ("athena", {"workgroup": "analysts"}),
    ("athena", {"region": "eu-west-1"}),
    ("athena", {"databases": ["visits", "payroll"]}),
    ("athena", {"catalog": "other_catalog"}),
    ("athena", {"results_location": "s3://synthetic-athena-results/elsewhere/"}),
]


@pytest.mark.parametrize(("kind", "change"), WIDER)
def test_a_connection_wider_than_its_declaration_is_refused(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str, change: dict[str, Any]
) -> None:
    _render_made(monkeypatch, DECLARED)
    _refused_in_words(_save(world, kind, {**SETTINGS[kind], **change}))
    assert _reads(world) == 0


@KINDS
def test_another_profile_is_not_held_to_a_declaration(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Small and the cluster render no namespace egress; their allow-list (part 1's) stands."""
    monkeypatch.setenv("OSPREY_PROFILE", "small")
    monkeypatch.delenv("OSPREY_CONNECTOR_SOURCES", raising=False)
    assert _save(world, kind).status_code == 201
