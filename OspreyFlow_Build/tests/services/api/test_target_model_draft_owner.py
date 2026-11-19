"""Only a model draft's creator can save into, replace or discard it (C186; rules 3, 4, 12, 15).

A dataset's model draft belongs to whoever opened it. Before this change a second data engineer's
`PUT /v1/datasets/{id}/model/draft` answered 200 and rewrote the first one's work (audited as the
first one's), and a second one's `DELETE` discarded it. The refusal is the neighbours' own: 409
`model_refused`, in words copied from the import path's `held_draft_problem`, naming who holds the
draft and never what is in it, before anything is changed.

What a mistake would do, and the case that catches it:

- a second writer's PUT rewriting the draft:
  `test_a_second_principals_put_is_refused_and_the_draft_is_unchanged`;
- a second writer's discard removing it:
  `test_a_second_principals_discard_is_refused_and_the_draft_is_still_there`;
- the check living only in the route, not the store (the import path and the link-type acceptance
  call the store directly): `test_the_creator_check_holds_at_the_store`;
- a stale save over one's own draft: `test_the_creators_own_save_is_confirmed_against_the_version`;
- the two tests ADR-152 decision 11 (X5) names: `test_a_second_person_cannot_save_into_replace_or_delete_
  another_persons_draft` and `test_a_stale_version_is_refused_in_words` (the latter plants a stale
  discard, at the store and through the DELETE route; red with the version argument deleted from
  either the store's discard or the route's call);
- the refusal leaking the draft's content: `test_the_refusal_names_who_holds_it_and_none_of_its_content`.

The second writer is planted as the code meets one: a different `principal.id` arriving through the
route's own token resolver (the real `get_principal` runs). The Postgres store's own cases are in
`test_target_models_store.py` (they need the dev stack and are owed).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.datasets import InMemoryDatasetStore
from services.api.studio_release import DraftHeld, held_draft_problem
from services.api.target_models import (
    CORE_TYPES_FOR_TESTS,
    InMemoryTargetModelStore,
    TargetModelRefused,
)

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.dataset_model import HomeCase, ModelExtension, TargetModel, TargetModelDraftInput
from schemas.domain import Principal
from tests.services.api.test_dataset_model_routes import _Audit, _dataset, _Recipes

DATASET = "ds-a"
PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit="unit-1", roles=["data_engineer"])
    for name, pid in (("alice", "alice-1"), ("bob", "bob-2"))
}
#: Both reach ds-a through their own case, and both hold the right: the only thing between bob and
#: alice's draft is that it is alice's.
CASES = {"alice-1": ["case-a"], "bob-2": ["case-b"]}
#: Content nobody else's words may carry.
SECRET_EXTENSION = "Zebra"


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
    for pid, reads in CASES.items():
        for case in reads:
            datasets.cases[case] = [DATASET]
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


def _call(world: SimpleNamespace, method: str, person: str, body: Any = None) -> Any:
    return world.client.request(
        method,
        f"/v1/datasets/{DATASET}/model/draft",
        json=body,
        headers={"Authorization": f"Bearer {person}"},
    )


def _content(packs: dict[str, int], *, extension: bool = False) -> dict[str, Any]:
    extensions = (
        [{"name": SECRET_EXTENSION, "kind": "entity_type", "added_in": 1}] if extension else []
    )
    return {"packs": packs, "extensions": extensions, "reference_lists": []}


def _alice_holds_a_draft(world: SimpleNamespace) -> TargetModel:
    """Alice opens the draft and saves content into it, all through the routes."""
    assert _call(world, "POST", "alice").status_code == 201
    saved = _call(world, "PUT", "alice", _content({"fibo": 1}, extension=True))
    assert saved.status_code == 200, saved.text
    return TargetModel.model_validate(saved.json())


async def _held(world: SimpleNamespace) -> TargetModel | None:
    return await world.models.draft(DATASET)


def _actions(world: SimpleNamespace) -> list[str]:
    return [e["action"] for e in world.audit.entries]


# --- through the routes -------------------------------------------------------------------------


async def test_a_second_principals_put_is_refused_and_the_draft_is_unchanged(
    world: SimpleNamespace,
) -> None:
    held = _alice_holds_a_draft(world)
    before = await _held(world)
    assert before is not None and before.created_by == "alice-1" and before == held

    answer = _call(world, "PUT", "bob", _content({"niem": 1}))

    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "model_refused"
    after = await _held(world)
    assert after == before  # content, version and created_by, all as alice left them
    assert after is not None and after.packs == {"fibo": 1} and after.created_by == "alice-1"
    assert _actions(world) == ["open_model_draft", "save_model_draft"]  # bob's is no entry


async def test_a_second_principals_discard_is_refused_and_the_draft_is_still_there(
    world: SimpleNamespace,
) -> None:
    _alice_holds_a_draft(world)
    before = await _held(world)

    answer = _call(world, "DELETE", "bob")

    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "model_refused"
    assert await _held(world) == before and before is not None
    assert _actions(world) == ["open_model_draft", "save_model_draft"]


async def test_a_second_person_cannot_save_into_replace_or_delete_another_persons_draft(
    world: SimpleNamespace,
) -> None:
    """The first of the two tests ADR-152 decision 11 (X5) names, by its name. Through the route
    (save into, delete) and at the store (save into, replace as the import confirms it, delete):
    another person's attempt is refused 409 `model_refused`, and the draft is as it was."""
    _alice_holds_a_draft(world)
    before = await _held(world)
    assert before is not None
    # Through the route, a different principal.id arriving by the route's own token resolver.
    for method, body in (("PUT", _content({"niem": 1})), ("DELETE", None)):
        answer = _call(world, method, "bob", body)
        assert answer.status_code == 409, (method, answer.text)
        assert answer.json()["error"] == "model_refused"
        assert await _held(world) == before
    # At the store, as the import path and the link-type acceptance reach it: a save into the
    # draft, a replace confirmed against the exact version, and a discard, all refused.
    bob = PEOPLE["bob"]
    attempts = (
        world.models.save_draft(DATASET, TargetModelDraftInput(packs={"niem": 1}), bob),
        world.models.save_draft(
            DATASET, TargetModelDraftInput(packs={"niem": 1}), bob,
            expected_version=before.version,
        ),
        world.models.discard_draft(DATASET, bob),
        world.models.discard_draft(DATASET, bob, expected_version=before.version),
    )  # fmt: skip
    for attempt in attempts:
        with pytest.raises(TargetModelRefused, match="alice-1"):
            await attempt
    assert await _held(world) == before


async def test_a_stale_version_is_refused_in_words(world: SimpleNamespace) -> None:
    """The second of the two X5 names. The creator's own save and discard, confirmed against a
    version the draft no longer has, are refused in words (the version it is now, and to read it
    again) and change nothing — at the store, and through the DELETE route, whose read of the
    version can be stale by the time it discards."""
    store = world.models
    alice = PEOPLE["alice"]
    first = _alice_holds_a_draft(world)
    await store.make_live(DATASET, first.version, alice)
    second = await store.open_draft(DATASET, alice)
    assert second.version == first.version + 1
    before = await _held(world)

    with pytest.raises(TargetModelRefused, match=f"version {second.version}") as stale_save:
        await store.save_draft(
            DATASET, TargetModelDraftInput(packs={"niem": 1}), alice,
            expected_version=first.version,
        )  # fmt: skip
    with pytest.raises(TargetModelRefused, match=f"version {second.version}") as stale_discard:
        await store.discard_draft(DATASET, alice, expected_version=first.version)
    for refused in (stale_save, stale_discard):
        words = str(refused.value)
        assert f"you meant your draft's version {first.version}" in words
        assert "read it again" in words
    assert await _held(world) == before  # neither changed anything

    # Through the route: it reads the draft, then discards confirming what it read. Plant a read
    # gone stale (the draft replaced between the route's read and its discard), as a race would.
    real_draft = store.draft
    calls = {"n": 0}

    async def stale_read(dataset_id: str) -> TargetModel | None:
        calls["n"] += 1
        held = await real_draft(dataset_id)
        if calls["n"] == 1 and held is not None:
            return held.model_copy(update={"version": first.version})
        return held

    store.draft = stale_read  # type: ignore[method-assign]
    answer = _call(world, "DELETE", "alice")
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "model_refused"
    assert f"you meant your draft's version {first.version}" in answer.json()["detail"]
    assert await real_draft(DATASET) == before  # still there
    assert "discard_model_draft" not in _actions(world)


async def test_the_refusal_names_who_holds_it_and_none_of_its_content(
    world: SimpleNamespace,
) -> None:
    _alice_holds_a_draft(world)
    for method, body in (("PUT", _content({"niem": 1})), ("DELETE", None)):
        answer = _call(world, method, "bob", body)
        assert answer.status_code == 409, answer.text
        words = answer.json()["detail"]
        assert "alice-1" in words and "version 1" in words
        assert "Studio › Model" in words  # how to go on, as the import path says it
        # None of the draft's content, in the words or anywhere in the body.
        assert SECRET_EXTENSION not in answer.text and "fibo" not in answer.text
        assert "extensions" not in answer.text and "packs" not in answer.text


async def test_the_creators_own_save_and_discard_work(world: SimpleNamespace) -> None:
    """Control (rule 15): the check refuses another person, not the creator."""
    _alice_holds_a_draft(world)
    again = _call(world, "PUT", "alice", _content({"fibo": 2}))
    assert again.status_code == 200, again.text
    assert again.json()["packs"] == {"fibo": 2} and again.json()["created_by"] == "alice-1"
    gone = _call(world, "DELETE", "alice")
    assert gone.status_code == 204, gone.text
    assert await _held(world) is None
    assert _actions(world) == [
        "open_model_draft", "save_model_draft", "save_model_draft", "discard_model_draft",
    ]  # fmt: skip
    # With it gone, bob may open his own, and it is bob's to save into.
    assert _call(world, "POST", "bob").status_code == 201
    assert _call(world, "PUT", "bob", _content({"niem": 1})).status_code == 200


async def test_a_second_writers_open_is_still_refused(world: SimpleNamespace) -> None:
    """Control: the neighbour this slice copies from, unchanged."""
    _alice_holds_a_draft(world)
    answer = _call(world, "POST", "bob")
    assert answer.status_code == 409 and answer.json()["error"] == "model_refused"
    assert "already has a draft" in answer.json()["detail"]
    held = await _held(world)
    assert held is not None and held.created_by == "alice-1"


# --- at the store, called directly --------------------------------------------------------------


async def test_the_creator_check_holds_at_the_store() -> None:
    """The import path and the link-type acceptance reach the store without the route: the check
    is the store's, so it holds there, and holds whatever version is confirmed."""
    store = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    alice, bob = PEOPLE["alice"], PEOPLE["bob"]
    draft = await store.open_draft(DATASET, alice)
    mine = await store.save_draft(
        DATASET,
        TargetModelDraftInput(
            packs={"fibo": 1},
            extensions=[ModelExtension(name=SECRET_EXTENSION, kind="entity_type", added_in=1)],
        ),
        alice,
    )
    for confirmed in (None, draft.version):  # the strongest a second writer could send
        with pytest.raises(TargetModelRefused, match="alice-1"):
            await store.save_draft(
                DATASET, TargetModelDraftInput(packs={"niem": 1}), bob, expected_version=confirmed
            )
        with pytest.raises(TargetModelRefused, match="alice-1"):
            await store.discard_draft(DATASET, bob)
    assert await store.draft(DATASET) == mine
    assert mine.created_by == "alice-1" and mine.packs == {"fibo": 1}
    await store.discard_draft(DATASET, alice)
    assert await store.draft(DATASET) is None


async def test_the_creators_own_save_is_confirmed_against_the_version() -> None:
    store = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    alice = PEOPLE["alice"]
    draft = await store.open_draft(DATASET, alice)
    saved = await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 1}), alice, expected_version=draft.version
    )
    assert saved.packs == {"fibo": 1} and saved.created_by == "alice-1"
    before = await store.draft(DATASET)

    # A draft discarded and opened again since is version 1 again, so plant a later version: the
    # live version 1 made, then alice's next draft is version 2, and a save confirmed for 1 is stale.
    await store.make_live(DATASET, draft.version, alice)
    second = await store.open_draft(DATASET, alice)
    assert second.version == 2
    before = await store.draft(DATASET)
    with pytest.raises(TargetModelRefused, match="version 2") as refused:
        await store.save_draft(
            DATASET, TargetModelDraftInput(packs={"niem": 1}), alice, expected_version=1
        )
    assert "version 1" in str(refused.value)
    assert await store.draft(DATASET) == before  # nothing changed
    ok = await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"niem": 1}), alice, expected_version=2
    )
    assert ok.packs == {"niem": 1}


async def test_a_second_writers_link_type_acceptance_still_appends_to_the_draft() -> None:
    """Control: `add_extension` is the shared, append-only write ADR-143 decision 9 designed (two
    data engineers' acceptances both land), not a save over the creator's work. Unchanged here."""
    store = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    alice, bob = PEOPLE["alice"], PEOPLE["bob"]
    await store.open_draft(DATASET, alice)
    got = await store.add_extension(DATASET, "BRIBED", "link_type", bob)
    assert [e.name for e in got.extensions] == ["BRIBED"] and got.created_by == "alice-1"


# --- the import path, unchanged -----------------------------------------------------------------


def _draft_of(who: str, version: int = 3) -> TargetModel:
    return TargetModel(
        dataset_id=DATASET, version=version, state="draft", packs={"niem": 1},
        created_at=datetime(2026, 11, 10, tzinfo=UTC), created_by=who,
    )  # fmt: skip


def test_the_import_paths_verdicts_on_a_held_draft_are_unchanged() -> None:
    """Control: another person's draft is refused whatever is confirmed, naming them; the
    importer's own is replaced only on a confirmation of that exact version."""
    others = _draft_of("alice-1")
    for confirmed in (None, 3, 4):
        held = held_draft_problem(others, PEOPLE["bob"], replace_own_draft=confirmed)
        assert isinstance(held, DraftHeld) and held.own is False
        assert "alice-1" in str(held) and "never replaces another person's draft" in str(held)
    assert held_draft_problem(None, PEOPLE["bob"], replace_own_draft=None) is None
    own = _draft_of("bob-2")
    assert held_draft_problem(own, PEOPLE["bob"], replace_own_draft=3) is None
    for confirmed in (None, 2):
        held = held_draft_problem(own, PEOPLE["bob"], replace_own_draft=confirmed)
        assert isinstance(held, DraftHeld) and held.own is True
