"""Registered sources on dataset routes (`06_DECISIONS.md` ADR-140 Amendment 4; redesign phase 3).

The real app and the real `get_principal` run, so the dataset scoping is what is tested, with only
the token resolver and the stores standing in. What a mistake would do, and the case that catches
it:

- a person reaching a dataset none of their cases loads into: one that a case only reads
  (`test_a_dataset_a_case_only_reads_is_not_reached`), another unit's, or none at all — each told
  404 in the same words (`test_another_units_dataset_and_a_missing_one_answer_alike`);
- a source of one dataset read through another's route
  (`test_a_source_is_not_found_through_another_datasets_route`);
- a source registered on a file outside the dataset's files, which would read past the ingest root
  (`test_a_file_outside_the_datasets_files_is_refused_whether_or_not_it_exists`);
- one location registered twice (`test_a_location_is_registered_once_per_dataset`);
- a governance edit that leaves deployed pipelines loading under the old marking, or goes
  unaudited (`test_editing_governance_is_a_new_version_flags_the_pipelines_and_is_audited`);
- a profile stored and shown to another reader (`test_the_profile_is_computed_for_the_reader`), or
  one computed for a cleared reader shown unmasked to a reader below the source's marking
  (`test_the_profile_is_masked_for_a_reader_below_the_sources_marking`);
- the register wizard's file listing reached for another unit's dataset, or listing another
  dataset's files (`test_the_dataset_files_are_listed_only_for_a_reached_dataset_and_only_its_own`);
- a connection named, or the Admin list of connections read, by someone who is not an
  administrator (`test_only_an_administrator_names_a_connection`,
  `test_only_an_administrator_reads_the_admin_list_of_connections`).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.sources import InMemorySourceStore
from services.api.studio_recipes import SOURCE_GOVERNANCE_CHANGED

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}
PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit=unit, roles=[role])
    for name, pid, unit, role in (
        ("engineer", "eng-1", "unit-1", "data_engineer"),
        ("reader", "read-1", "unit-1", "data_engineer"),
        ("stranger", "str-1", "unit-2", "data_engineer"),
        ("admin", "adm-1", "unit-1", "osprey-admin"),
    )
} | {
    # Below the SECRET a source may be marked: the profile is masked for this reader alone.
    "junior": Principal(
        id="jun-1", clearance="OFFICIAL", org_unit="unit-1", roles=["data_engineer"]
    )
}
#: The cases each person holds a level in, by the datasets each reads (its first loads into it).
CASES = {
    "eng-1": {"case-a": ["ds-a"], "case-c": ["ds-c"]},
    "read-1": {"case-r": ["ds-x", "ds-a"]},
    "str-1": {"case-s": ["ds-s"]},
    "adm-1": {},
    "jun-1": {"case-j": ["ds-a"]},
}


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c), "editor") for c in CASES[principal.id]]


class _Recipes:
    def __init__(self) -> None:
        self.flagged: list[tuple[str, str, str]] = []
        self.followed: list[tuple[str, str, str]] = []
        #: What `using_source` answers: as the real store, every status but a previous version.
        self.readers: list[Any] = []

    async def flag_for_source(self, dataset_id: str, location: str, reason: str) -> list[str]:
        self.flagged.append((dataset_id, location, reason))
        return ["PIN calls"]

    async def using_source(self, dataset_id: str, location: str) -> list[Any]:
        return list(self.readers)

    async def follow_source(
        self, dataset_id: str, location: str, handling: dict[str, Any], legal_basis: str | None
    ) -> list[str]:
        self.followed.append((dataset_id, location, handling["classification"]))
        return ["Draft reading it"]


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
    root = tmp_path / "ingest"
    for dataset in ("ds-a", "ds-c"):
        (root / "uploaded" / dataset).mkdir(parents=True)
    (root / "uploaded" / "ds-a" / "cells.csv").write_text("prisoner,cell\nSYN-1,A1\nSYN-2,A2\n")
    (root / "uploaded" / "ds-c" / "other.csv").write_text("a\n1\n")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    datasets = InMemoryDatasetStore()
    for d, unit in (("ds-a", "unit-1"), ("ds-c", "unit-1"), ("ds-x", "unit-1"), ("ds-s", "unit-2")):
        datasets.add(
            Dataset(
                id=d,
                name=d,
                owning_unit=unit,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                created_by="s",
            )
        )
    for person in CASES.values():
        for case, reads in person.items():
            datasets.cases[case] = reads
    recipes, audit, sources = _Recipes(), _Audit(), InMemorySourceStore()
    state = {
        "principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
        "sources": sources, "studio_recipes": recipes, "audit": audit,
        "handling_scheme": load_uk_le_scheme(),
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(
        client=TestClient(app), root=root, recipes=recipes, audit=audit, sources=sources
    )


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _register(world: SimpleNamespace, dataset: str = "ds-a", **extra: Any) -> Any:
    body = {
        "connection_id": "files",
        "name": "Cell stays",
        "location": str(world.root / "uploaded" / dataset / "cells.csv"),
        "handling": HANDLING,
        "legal_basis": "Synthetic demonstration",
    } | extra
    return world.client.post(f"/v1/datasets/{dataset}/sources", json=body, headers=_as("engineer"))


def test_a_person_reaches_a_dataset_one_of_their_cases_loads_into(world: SimpleNamespace) -> None:
    response = world.client.get("/v1/datasets/ds-a/sources", headers=_as("engineer"))
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_a_dataset_a_case_only_reads_is_not_reached(world: SimpleNamespace) -> None:
    """The reader's one case reads ds-a second: through it a load would go into ds-x."""
    response = world.client.get("/v1/datasets/ds-a/sources", headers=_as("reader"))
    assert response.status_code == 404


def test_another_units_dataset_and_a_missing_one_answer_alike(world: SimpleNamespace) -> None:
    other = world.client.get("/v1/datasets/ds-s/sources", headers=_as("engineer"))
    missing = world.client.get("/v1/datasets/no-such/sources", headers=_as("engineer"))
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


def test_a_file_outside_the_datasets_files_is_refused_whether_or_not_it_exists(
    world: SimpleNamespace,
) -> None:
    there = _register(world, location=str(world.root / "uploaded" / "ds-c" / "other.csv"))
    nowhere = _register(world, location="/etc/no-such-file.csv")
    outside = _register(world, location="/etc/passwd")
    assert there.status_code == nowhere.status_code == outside.status_code == 422
    assert there.json() == nowhere.json() == outside.json()
    assert world.sources._sources == {}


def test_a_location_is_registered_once_per_dataset(world: SimpleNamespace) -> None:
    first = _register(world)
    assert first.status_code == 201, first.text
    again = _register(world, name="Cell stays again")
    assert again.status_code == 409
    listed = world.client.get("/v1/datasets/ds-a/sources", headers=_as("engineer")).json()
    assert [s["name"] for s in listed] == ["Cell stays"]
    assert any(e["action"] == "register_dataset_source" for e in world.audit.entries)


def test_a_source_is_not_found_through_another_datasets_route(world: SimpleNamespace) -> None:
    made = _register(world).json()
    own = world.client.get(f"/v1/datasets/ds-a/sources/{made['id']}", headers=_as("engineer"))
    other = world.client.get(f"/v1/datasets/ds-c/sources/{made['id']}", headers=_as("engineer"))
    assert own.status_code == 200
    assert other.status_code == 404
    for path in ("profile", "lineage"):
        assert (
            world.client.get(
                f"/v1/datasets/ds-c/sources/{made['id']}/{path}", headers=_as("engineer")
            ).status_code
            == 404
        )


def test_editing_governance_is_a_new_version_flags_the_pipelines_and_is_audited(
    world: SimpleNamespace,
) -> None:
    made = _register(world).json()
    raised = HANDLING | {"classification": "SECRET"}
    response = world.client.patch(
        f"/v1/datasets/ds-a/sources/{made['id']}/governance",
        json={"handling": raised, "legal_basis": "Synthetic demonstration"},
        headers=_as("engineer"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"]["version"] == 2
    assert body["source"]["handling"]["classification"] == "SECRET"
    assert body["needs_attention"] == ["PIN calls"]
    assert world.recipes.flagged == [("ds-a", made["location"], SOURCE_GOVERNANCE_CHANGED)]
    assert world.recipes.followed == [("ds-a", made["location"], "SECRET")]
    (entry,) = [e for e in world.audit.entries if e["action"] == "edit_dataset_source_governance"]
    query = entry["resolved_query"]
    assert query["handling_before"]["classification"] == "OFFICIAL"
    assert query["handling_after"]["classification"] == "SECRET"


def test_governance_is_not_edited_through_another_datasets_route(world: SimpleNamespace) -> None:
    made = _register(world).json()
    response = world.client.patch(
        f"/v1/datasets/ds-c/sources/{made['id']}/governance",
        json={"handling": HANDLING},
        headers=_as("engineer"),
    )
    assert response.status_code == 404
    assert world.recipes.flagged == []


def test_the_profile_is_computed_for_the_reader(world: SimpleNamespace) -> None:
    made = _register(world).json()
    response = world.client.get(
        f"/v1/datasets/ds-a/sources/{made['id']}/profile", headers=_as("engineer")
    )
    assert response.status_code == 200, response.text
    assert [c["name"] for c in response.json()["columns"]] == ["prisoner", "cell"]
    assert (
        "profile"
        not in world.client.get(
            f"/v1/datasets/ds-a/sources/{made['id']}", headers=_as("engineer")
        ).json()
    )


def test_only_an_administrator_names_a_connection(world: SimpleNamespace) -> None:
    refused = world.client.post(
        "/v1/admin/connections", json={"name": "Second folder"}, headers=_as("engineer")
    )
    assert refused.status_code == 403
    made = world.client.post(
        "/v1/admin/connections", json={"name": "Second folder"}, headers=_as("admin")
    )
    assert made.status_code == 201, made.text
    listed = world.client.get("/v1/ingest/connections", headers=_as("engineer")).json()
    assert [c["id"] for c in listed][0] == "files"
    assert "Second folder" in [c["name"] for c in listed]
    assert any(e["action"] == "add_ingest_connection" for e in world.audit.entries)


def test_the_profile_is_masked_for_a_reader_below_the_sources_marking(
    world: SimpleNamespace,
) -> None:
    """The cleared engineer reads first, so a profile kept from that read would reach the junior
    reader unmasked. Both reach ds-a through a case of their own that loads into it."""
    made = _register(world, handling=HANDLING | {"classification": "SECRET"}).json()
    path = f"/v1/datasets/ds-a/sources/{made['id']}/profile"
    cleared = world.client.get(path, headers=_as("engineer"))
    junior = world.client.get(path, headers=_as("junior"))
    assert cleared.status_code == junior.status_code == 200, (cleared.text, junior.text)
    assert cleared.json()["values_masked"] is False
    assert junior.json()["values_masked"] is True
    samples = [v for c in junior.json()["columns"] for v in c.get("sample_values") or []]
    assert "SYN-1" not in samples


def test_the_dataset_files_are_listed_only_for_a_reached_dataset_and_only_its_own(
    world: SimpleNamespace,
) -> None:
    own = world.client.get("/v1/datasets/ds-a/source-files", headers=_as("engineer"))
    assert own.status_code == 200, own.text
    names = [f["source_location"].rsplit("/", 1)[-1] for f in own.json()["files"]]
    assert names == ["cells.csv"]
    other = world.client.get("/v1/datasets/ds-s/source-files", headers=_as("engineer"))
    missing = world.client.get("/v1/datasets/no-such/source-files", headers=_as("engineer"))
    only_read = world.client.get("/v1/datasets/ds-a/source-files", headers=_as("reader"))
    assert other.status_code == missing.status_code == only_read.status_code == 404
    assert other.json() == missing.json()


def test_only_an_administrator_reads_the_admin_list_of_connections(world: SimpleNamespace) -> None:
    assert world.client.get("/v1/admin/connections", headers=_as("engineer")).status_code == 403
    listed = world.client.get("/v1/admin/connections", headers=_as("admin"))
    assert listed.status_code == 200, listed.text
    assert [c["id"] for c in listed.json()][0] == "files"


# --- ADR-110 Amendment 6: the refresh policy ----------------------------------------------------

WATCH = {
    "trigger": "watch",
    "pattern": "cells-*.csv",
    "mode": "snapshot",
    "dropped_rows": "withdraw",
}


def _reader(label: str, status: str, keyed: bool) -> Any:
    from schemas.ingest import StudioRecipeStatus

    return SimpleNamespace(
        recipe_id=label,
        label=label,
        version=1,
        status=StudioRecipeStatus(status),
        deduplicate=SimpleNamespace(key=["prisoner"]) if keyed else None,
    )


def test_the_policys_owner_is_whoever_set_it_never_what_the_body_says(
    world: SimpleNamespace,
) -> None:
    claimed = WATCH | {"owner": "someone-else", "paused": True, "paused_reason": "planted"}
    made = _register(world, refresh=claimed)
    assert made.status_code == 201, made.text
    refresh = made.json()["refresh"]
    assert refresh["owner"] == "eng-1"
    assert refresh["paused"] is False
    assert refresh["paused_reason"] is None


def test_an_edit_that_changes_the_policy_takes_its_owner_and_keeps_its_pause(
    world: SimpleNamespace,
) -> None:
    made = _register(world, refresh=WATCH).json()
    stored = world.sources._sources[made["id"]]
    world.sources._sources[made["id"]] = stored.model_copy(
        update={"refresh": stored.refresh.model_copy(update={"paused": True, "paused_reason": "r"})}
    )
    path = f"/v1/datasets/ds-a/sources/{made['id']}/governance"
    edited = world.client.patch(
        path,
        json={"handling": HANDLING, "refresh": WATCH | {"pattern": "stays-*.csv"}},
        headers=_as("engineer"),
    )
    assert edited.status_code == 200, edited.text
    refresh = edited.json()["source"]["refresh"]
    assert refresh["owner"] == "eng-1"
    assert (refresh["paused"], refresh["paused_reason"]) == (True, "r")


def test_an_unchanged_policy_keeps_its_owner(world: SimpleNamespace) -> None:
    made = _register(world, refresh=WATCH).json()
    world.sources._sources[made["id"]] = world.sources._sources[made["id"]].model_copy(
        update={
            "refresh": world.sources._sources[made["id"]].refresh.model_copy(
                update={"owner": "first-owner"}
            )
        }
    )
    edited = world.client.patch(
        f"/v1/datasets/ds-a/sources/{made['id']}/governance",
        json={"handling": HANDLING | {"classification": "SECRET"}, "refresh": WATCH},
        headers=_as("engineer"),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["source"]["refresh"]["owner"] == "first-owner"


@pytest.mark.parametrize(
    ("policy", "words"),
    [
        ({"trigger": "watch"}, "pattern"),
        ({"trigger": "watch", "pattern": "a-*.csv", "mode": "incremental"}, "watermark"),
    ],
)
def test_a_policy_missing_what_its_mode_needs_is_refused_in_words(
    world: SimpleNamespace, policy: dict[str, str], words: str
) -> None:
    response = _register(world, refresh=policy)
    assert response.status_code == 422
    assert words in response.text
    assert world.sources._sources == {}


def test_a_refreshing_policy_is_refused_where_a_deployed_keyless_pipeline_reads_the_source(
    world: SimpleNamespace,
) -> None:
    world.recipes.readers = [
        _reader("Keyless deployed", "published", keyed=False),
        _reader("Keyless draft", "draft", keyed=False),
        _reader("Keyed deployed", "published", keyed=True),
    ]
    refused = _register(world, refresh=WATCH)
    assert refused.status_code == 422, refused.text
    body = refused.json()["detail"]
    assert body["error"] == "refresh_needs_a_key"
    assert "Keyless deployed" in body["detail"]
    assert "Keyless draft" not in body["detail"] and "Keyed deployed" not in body["detail"]
    assert world.sources._sources == {}
    # By hand is not a refresh policy: it is registered.
    assert _register(world, refresh={"trigger": "manual"}).status_code == 201


def test_a_keyed_or_draft_reader_does_not_refuse_the_policy_nor_an_edit_to_one(
    world: SimpleNamespace,
) -> None:
    world.recipes.readers = [
        _reader("Keyless draft", "draft", keyed=False),
        _reader("Keyed needing attention", "flagged", keyed=True),
    ]
    made = _register(world, refresh={"trigger": "manual"})
    assert made.status_code == 201, made.text
    world.recipes.readers.append(_reader("Keyless needing attention", "flagged", keyed=False))
    edited = world.client.patch(
        f"/v1/datasets/ds-a/sources/{made.json()['id']}/governance",
        json={"handling": HANDLING, "refresh": WATCH},
        headers=_as("engineer"),
    )
    assert edited.status_code == 422
    assert "Keyless needing attention" in edited.json()["detail"]["detail"]
