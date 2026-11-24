"""The expected version on a model draft's save and discard, and the type record (slice IS2a; ADR-140 Amendment 22
items 3 and 4; ADR-152 X5 and decision 12; owner's rulings of 21 and 23 November 2026).

`PUT` and `DELETE /v1/datasets/{id}/model/draft` carry the version the person's copy was read at, so a save or a discard
made over a draft opened again since is refused in the store's own words, and a request that carries no version is
refused too (an old client cannot skip the check). The type record carries its class, identifiers, matching rule and
properties with an indexed flag; a matching rule the matching code does not know is refused. The scenario's rows are
`spec/08_ACCEPTANCE_SCENARIOS.md` "Scenario MS" (MS2 to MS8 are this file's; each test's name says its id).

What a mistake would do, and the case that catches it:

- a save that ignores the version it is sent (the route passing none, or its own read of the draft):
  `test_ms5_a_stale_save_is_refused_and_nothing_changes` and `test_ms7_the_route_hands_the_store_the_version_the_client_sent`;
- a discard that confirms the version it read itself, as the route did before: `test_ms6_a_stale_discard_is_refused_and_the_draft_is_still_there`
  and the same spy case;
- a request with no version, or an unusable one, still carried out: `test_ms5_a_save_with_no_version_is_refused` and
  `test_ms6_a_discard_with_no_version_is_refused`;
- the version check running before the right or the dataset's gate, telling a person something they may not know:
  `test_ms8_the_gate_comes_before_the_version`;
- the creator check lost beside the version: `test_ms4_the_creator_check_holds_beside_the_version`;
- a type record that loses its class, identifiers, matching rule or an indexed flag on the way in or out:
  `test_ms2_a_type_record_carries_its_class_identifiers_matching_rule_and_indexed_properties`;
- a matching rule the matching code does not know, or one that names a field a reference cannot find, saved:
  `test_ms3_a_matching_rule_the_matching_code_does_not_know_is_refused`.

Every planted fault is the request the code really receives (a JSON body or a query through the real app and the real
`get_principal`), with one thing changed (rule 15). The stale version is made the way it happens: the draft is made live
and the person's next draft is a later version, so a copy read before is stale.

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It imports the app and the stores and reads no folder.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.dataset_model import HomeCase, TargetModel
from schemas.domain import Principal

from services.api.app import app
from services.api.datasets import InMemoryDatasetStore
from services.api.target_models import CORE_TYPES_FOR_TESTS, InMemoryTargetModelStore
from tests.services.api.test_dataset_model_routes import _Audit, _dataset, _Recipes

DATASET = "ds-a"
#: The bearer a person sends is their name here; the resolver turns it into the principal the real
#: `get_principal` is given.
PEOPLE = {
    "alice": Principal(id="alice-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "bob": Principal(id="bob-2", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "analyst": Principal(id="ana-3", clearance="SECRET", org_unit="unit-1", roles=["analyst"]),
    "stranger": Principal(id="str-4", clearance="SECRET", org_unit="unit-2", roles=["data_engineer"]),
}
#: Each person's cases, by the datasets each reads. The stranger's case reads another dataset altogether.
CASES = {
    "alice-1": {"case-a": [DATASET]},
    "bob-2": {"case-b": [DATASET]},
    "ana-3": {"case-n": [DATASET]},
    "str-4": {"case-s": ["ds-s"]},
}
URL = f"/v1/datasets/{DATASET}/model/draft"


class _Resolver:
    async def resolve_principal(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c, name=f"Case {c}"), "editor") for c in CASES[principal.id]]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    datasets = InMemoryDatasetStore()
    datasets.add(_dataset(DATASET))
    datasets.add(_dataset("ds-s", "unit-2"))
    for reads in CASES.values():
        for case, ids in reads.items():
            datasets.cases[case] = list(ids)
    datasets.homes[DATASET] = HomeCase(
        dataset_id=DATASET, investigation_id="case-a", made_at=datetime(2026, 1, 1, tzinfo=UTC),
        made_by="alice-1",
    )  # fmt: skip
    audit = _Audit()
    models = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    state = {
        "principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
        "studio_recipes": _Recipes(), "audit": audit, "target_models": models,
        "handling_scheme": load_uk_le_scheme(), "ontology": load_deployment_ontology(),
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app), audit=audit, models=models)


def _headers(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _open(world: SimpleNamespace, person: str = "alice") -> TargetModel:
    answer = world.client.post(URL, headers=_headers(person))
    assert answer.status_code == 201, answer.text
    return TargetModel.model_validate(answer.json())


def _save(
    world: SimpleNamespace, person: str, body: dict[str, Any], version: int | None
) -> Any:
    """A save as a client sends it: the content and the version it was read at (none when `version` is None)."""
    sent = dict(body) if version is None else {**body, "expected_version": version}
    return world.client.put(URL, json=sent, headers=_headers(person))


def _discard(world: SimpleNamespace, person: str, version: int | None) -> Any:
    params = {} if version is None else {"expected_version": version}
    return world.client.delete(URL, params=params, headers=_headers(person))


def _content(packs: dict[str, int] | None = None) -> dict[str, Any]:
    return {"packs": packs or {}, "extensions": [], "reference_lists": []}


async def _draft(world: SimpleNamespace) -> TargetModel | None:
    return await world.models.draft(DATASET)


def _actions(world: SimpleNamespace) -> list[str]:
    return [e["action"] for e in world.audit.entries]


async def _a_later_draft(world: SimpleNamespace) -> tuple[TargetModel, TargetModel]:
    """Alice's draft made live and her next one opened: a copy read before is now stale, as it is in life.
    Returns the first draft (the stale copy's version) and the second (the draft as it is now)."""
    first = _open(world)
    made = await world.models.make_live(DATASET, first.version, PEOPLE["alice"])
    assert made[0].version == first.version
    second = _open(world)
    assert second.version == first.version + 1
    return first, second


# --- MS2 and MS3: the type record ----------------------------------------------------------------

VESSEL = {
    "name": "Vessel", "kind": "entity_type", "added_in": 1, "pole_class": "object",
    "identifiers": ["imo_number"],
    "matching": {"match_on": "imo_number", "on_match": "reference"},
}  # fmt: skip
FLAG_STATE = {
    "name": "flag_state", "kind": "property", "on_type": "Vessel", "added_in": 1,
    "value_type": "string", "indexed": True,
}  # fmt: skip
CALL_SIGN = {
    "name": "call_sign", "kind": "property", "on_type": "Vessel", "added_in": 1,
    "value_type": "string", "indexed": False,
}  # fmt: skip


def _types(*extensions: dict[str, Any]) -> dict[str, Any]:
    return {"packs": {}, "extensions": list(extensions), "reference_lists": []}


def test_ms2_a_type_record_carries_its_class_identifiers_matching_rule_and_indexed_properties(
    world: SimpleNamespace,
) -> None:
    opened = _open(world)
    saved = _save(world, "alice", _types(VESSEL, FLAG_STATE, CALL_SIGN), opened.version)
    assert saved.status_code == 200, saved.text
    read = world.client.get(f"/v1/datasets/{DATASET}/model", headers=_headers("alice")).json()
    by_name = {e["name"]: e for e in read["draft"]["extensions"]}
    vessel = by_name["Vessel"]
    # Its class, its identifiers and its matching rule: the rule as the matching code takes it.
    assert vessel["pole_class"] == "object"
    assert vessel["identifiers"] == ["imo_number"]
    assert vessel["matching"] == {"match_on": "imo_number", "on_match": "reference"}
    # Its properties, each with its indexed flag, true and false both kept as given.
    assert by_name["flag_state"]["on_type"] == "Vessel" and by_name["flag_state"]["indexed"] is True
    assert by_name["call_sign"]["on_type"] == "Vessel" and by_name["call_sign"]["indexed"] is False
    assert by_name["flag_state"]["value_type"] == "string"
    # What was saved is what comes back, whole, and an extension saved before these fields existed still reads.
    assert saved.json()["extensions"] == read["draft"]["extensions"]
    plain = {"name": "Wing", "kind": "entity_type", "added_in": opened.version}
    again = _save(world, "alice", _types(VESSEL, FLAG_STATE, CALL_SIGN, plain), opened.version)
    assert again.status_code == 200, again.text
    wing = next(e for e in again.json()["extensions"] if e["name"] == "Wing")
    assert wing["pole_class"] is None and wing["identifiers"] == [] and wing["matching"] is None


@pytest.mark.parametrize(
    "change, status, said",
    [
        # A rule the matching code has no mode for: the engine knows `reference` and `create` alone.
        ({"matching": {"match_on": "imo_number", "on_match": "merge"}}, 422, "on_match"),
        # A sixth class: the upper ontology is closed to the five.
        ({"pole_class": "vehicle"}, 422, "pole_class"),
        # A rule on a field a reference cannot find: not an identifier, not an indexed property.
        ({"matching": {"match_on": "call_sign", "on_match": "reference"}}, 409, "call_sign"),
        ({"matching": {"match_on": "no_such_field", "on_match": "reference"}}, 409, "no_such_field"),
    ],
)
def test_ms3_a_matching_rule_the_matching_code_does_not_know_is_refused(
    world: SimpleNamespace, change: dict[str, Any], status: int, said: str
) -> None:
    opened = _open(world)
    before = _save(world, "alice", _types(VESSEL, FLAG_STATE, CALL_SIGN), opened.version).json()
    planted = {**VESSEL, **change}
    answer = _save(world, "alice", _types(planted, FLAG_STATE, CALL_SIGN), opened.version)
    assert answer.status_code == status, answer.text
    assert said in answer.text
    if status == 409:
        assert answer.json()["error"] == "model_refused"
        assert "cannot be found by" in answer.json()["detail"]
    # Nothing was saved: the draft is as the last good save left it.
    now = world.client.get(f"/v1/datasets/{DATASET}/model", headers=_headers("alice")).json()
    assert now["draft"]["extensions"] == before["extensions"]
    assert _actions(world) == ["open_model_draft", "save_model_draft"]


def test_ms3_the_rule_may_name_an_identifier_or_an_indexed_property_and_a_type_shape_is_kept_to_its_kind(
    world: SimpleNamespace,
) -> None:
    """Control: the check refuses what a reference cannot find, not every rule. And the type fields belong to the
    kinds they describe: a class on a property, an indexed flag on a type, are the schema's refusal."""
    opened = _open(world)
    by_property = {**VESSEL, "matching": {"match_on": "flag_state", "on_match": "reference"}}
    assert _save(world, "alice", _types(by_property, FLAG_STATE), opened.version).status_code == 200
    by_create = {**VESSEL, "matching": {"match_on": "imo_number", "on_match": "create"}}
    assert _save(world, "alice", _types(by_create), opened.version).status_code == 200
    for wrong in (
        {**FLAG_STATE, "pole_class": "object"},
        {**VESSEL, "indexed": True},
        {**VESSEL, "value_type": "string"},
        {"name": "BRIBED", "kind": "link_type", "added_in": 1, "matching": VESSEL["matching"]},
    ):
        answer = _save(world, "alice", _types(VESSEL, wrong), opened.version)
        assert answer.status_code == 422, (wrong, answer.text)


# --- MS4: the creator check holds beside the version -----------------------------------------------


async def test_ms4_the_creator_check_holds_beside_the_version(world: SimpleNamespace) -> None:
    """Bob confirms the exact version of alice's draft, the strongest thing a second writer can send, and is
    refused for save and discard alike, in words that name who holds it and none of what is in it."""
    opened = _open(world)
    assert _save(world, "alice", _types(VESSEL), opened.version).status_code == 200
    before = await _draft(world)
    assert before is not None
    for answer in (
        _save(world, "bob", _content({"niem": 1}), opened.version),
        _discard(world, "bob", opened.version),
    ):
        assert answer.status_code == 409, answer.text
        assert answer.json()["error"] == "model_refused"
        words = answer.json()["detail"]
        assert "alice-1" in words
        assert "Vessel" not in answer.text and "imo_number" not in answer.text and "niem" not in answer.text
    assert await _draft(world) == before
    assert _actions(world) == ["open_model_draft", "save_model_draft"]
    # Bob with no version at all is refused too, and the answer carries nothing of alice's draft.
    for blind in (_save(world, "bob", _content(), None), _discard(world, "bob", None)):
        assert blind.status_code == 422, blind.text
        assert "alice" not in blind.text and "Vessel" not in blind.text
    assert await _draft(world) == before


# --- MS5 and MS6: the expected version ---------------------------------------------------------------


async def test_ms5_a_current_version_saves(world: SimpleNamespace) -> None:
    """Control: the check refuses a stale version, not every one."""
    opened = _open(world)
    answer = _save(world, "alice", _content({"fibo": 1}), opened.version)
    assert answer.status_code == 200, answer.text
    assert answer.json()["packs"] == {"fibo": 1} and answer.json()["version"] == opened.version
    held = await _draft(world)
    assert held is not None and held.packs == {"fibo": 1}
    assert _actions(world) == ["open_model_draft", "save_model_draft"]


async def test_ms5_a_stale_save_is_refused_and_nothing_changes(world: SimpleNamespace) -> None:
    first, second = await _a_later_draft(world)
    before = await _draft(world)
    assert before == second
    answer = _save(world, "alice", _content({"niem": 1}), first.version)
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "model_refused"
    words = answer.json()["detail"]
    # In the store's words: the version meant, the version it is now, and to read it again.
    assert f"you meant your draft's version {first.version}" in words
    assert f"version {second.version}" in words
    assert "read it again" in words
    assert await _draft(world) == before  # content, version and creator, all as they were
    assert "save_model_draft" not in _actions(world)


def test_ms5_a_save_with_no_version_is_refused(world: SimpleNamespace) -> None:
    opened = _open(world)
    absent = _save(world, "alice", _content({"fibo": 1}), None)
    assert absent.status_code == 422, absent.text
    assert "expected_version" in absent.text
    for unusable in (0, -1, "one", None):
        sent = {**_content({"fibo": 1}), "expected_version": unusable}
        answer = world.client.put(URL, json=sent, headers=_headers("alice"))
        assert answer.status_code == 422, (unusable, answer.text)
    held = world.client.get(f"/v1/datasets/{DATASET}/model", headers=_headers("alice")).json()
    assert held["draft"]["packs"] == {} and held["draft"]["version"] == opened.version
    assert "save_model_draft" not in _actions(world)


async def test_ms6_a_current_version_discards(world: SimpleNamespace) -> None:
    opened = _open(world)
    answer = _discard(world, "alice", opened.version)
    assert answer.status_code == 204, answer.text
    assert await _draft(world) is None
    assert _actions(world) == ["open_model_draft", "discard_model_draft"]


async def test_ms6_a_stale_discard_is_refused_and_the_draft_is_still_there(
    world: SimpleNamespace,
) -> None:
    first, second = await _a_later_draft(world)
    before = await _draft(world)
    answer = _discard(world, "alice", first.version)
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "model_refused"
    words = answer.json()["detail"]
    assert f"you meant your draft's version {first.version}" in words
    assert f"version {second.version}" in words and "read it again" in words
    assert await _draft(world) == before and before == second
    assert "discard_model_draft" not in _actions(world)


def test_ms6_a_discard_with_no_version_is_refused(world: SimpleNamespace) -> None:
    opened = _open(world)
    absent = _discard(world, "alice", None)
    assert absent.status_code == 422, absent.text
    assert "expected_version" in absent.text
    for unusable in ("0", "-1", "one", ""):
        answer = world.client.delete(
            URL, params={"expected_version": unusable}, headers=_headers("alice")
        )
        assert answer.status_code == 422, (unusable, answer.text)
    held = world.client.get(f"/v1/datasets/{DATASET}/model", headers=_headers("alice")).json()
    assert held["draft"]["version"] == opened.version  # still there
    assert "discard_model_draft" not in _actions(world)


# --- MS7: the route hands the store the client's own version ------------------------------------------


async def test_ms7_the_route_hands_the_store_the_version_the_client_sent(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's check is what refuses, so the route must hand it the client's version and not one it read
    itself (the route's old DELETE read the draft and passed that, which confirms nothing the client held). The
    spy sees the arguments the store really receives at the route's call site."""
    opened = _open(world)
    seen: list[tuple[str, int | None]] = []
    real_save, real_discard = world.models.save_draft, world.models.discard_draft

    async def save(*args: Any, expected_version: int | None = None, **kw: Any) -> TargetModel:
        seen.append(("save", expected_version))
        return await real_save(*args, expected_version=expected_version, **kw)

    async def discard(*args: Any, expected_version: int | None = None, **kw: Any) -> None:
        seen.append(("discard", expected_version))
        await real_discard(*args, expected_version=expected_version, **kw)

    monkeypatch.setattr(world.models, "save_draft", save)
    monkeypatch.setattr(world.models, "discard_draft", discard)
    # A version that is not the draft's: whatever the route does, the store must see this very number.
    stale = opened.version + 6
    assert _save(world, "alice", _content(), stale).status_code == 409
    assert _discard(world, "alice", stale).status_code == 409
    assert _save(world, "alice", _content(), opened.version).status_code == 200
    assert _discard(world, "alice", opened.version).status_code == 204
    assert seen == [
        ("save", stale), ("discard", stale), ("save", opened.version), ("discard", opened.version),
    ]  # fmt: skip


# --- MS8: the gate comes before the version -----------------------------------------------------------


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_ms8_the_gate_comes_before_the_version(world: SimpleNamespace, method: str) -> None:
    """A person without the right, and a dataset not reached, are refused with no version and with one: the same
    answer both ways (403 for the right, 404 for a dataset the person's cases do not read), never a 422 that
    would tell them the route exists for them, and never anything of the draft."""
    _open(world)

    def call(person: str, dataset: str, version: int | None) -> Any:
        url = f"/v1/datasets/{dataset}/model/draft"
        if method == "PUT":
            sent = _content() if version is None else {**_content(), "expected_version": version}
            return world.client.put(url, json=sent, headers=_headers(person))
        params = {} if version is None else {"expected_version": version}
        return world.client.delete(url, params=params, headers=_headers(person))

    for person, dataset, expected in (
        ("analyst", DATASET, 403),  # reaches the dataset, lacks edit_target_model
        ("stranger", DATASET, 404),  # holds the right, but no case of theirs reads the dataset
        ("alice", "ds-that-does-not-exist", 404),
    ):
        for version in (None, 1):
            answer = call(person, dataset, version)
            assert answer.status_code == expected, (person, dataset, version, answer.text)
            assert "expected_version" not in answer.text
            assert "alice" not in answer.text and "Vessel" not in answer.text
            assert "ds-that-does-not-exist" not in answer.text
    # The unknown dataset and the one the stranger cannot reach are one answer, byte for byte.
    assert call("stranger", DATASET, 1).content == call("alice", "ds-that-does-not-exist", 1).content
