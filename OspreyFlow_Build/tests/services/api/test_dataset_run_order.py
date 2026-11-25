"""A dataset's run order, stored (slice IS6a; ADR-140 Amendment 22 items 7 and 8; ADR-141 Amendment 2 point 6; the
owner's rulings of 24 November 2026, items 1 to 6 under "IS6").

**What the order is stored as: "runs after" links.** For each pipeline of the dataset, the pipelines it runs after. A cycle
is therefore possible (a pipeline that must run after itself, directly or through others), and a cycle among the pipelines
the saver can see is refused on save, in words naming the pipelines in it. **A cycle that closes only through a pipeline
hidden from the saver is stored, and the saver is told nothing of it** (the owner's ruling of 25 November 2026, option a,
which amends his ruling 3 of 24 November for that case only; refused at the run by a later part). A pipeline with no link runs after nothing. The stored order is **versioned**: every save
is a new number (the first is 1, none stored is 0), with who saved it and when, and **a save names the number its person
read** (`expected_version`, required): a stale number is refused 409 `run_order_refused` in words, never overwritten, as a
domain-model draft's save is (`test_model_draft_expected_version.py`). Nothing is run.

The routes (both behind the dataset's own gate, and `edit_pipelines`: the right the dataset map has always needed, since it
reads the case's pipelines through it; there is no lesser right to read the map):

- `GET /v1/datasets/{id}/run-order` -> `{dataset_id, version, saved_by, saved_at, entries: [{pipeline_id, runs_after}]}`;
- `PUT /v1/datasets/{id}/run-order` with `{expected_version, entries}` -> the same, as saved.

What a mistake would do, and the case that catches it (each ID is in the test's name; each planted fault is the request
the code really receives, through the real app and the real `get_principal`, with one thing changed: rule 15):

- RO1/RO2 no order read as "none" and a save that forgets who and when, or keeps no history:
  `test_ro1_*`, `test_ro2_*`;
- RO3 to RO5 a stale number overwriting, a missing one accepted, or the route handing the store a number it read for
  itself: `test_ro3_*`, `test_ro4_*`, `test_ro5_*`;
- RO6 a cycle saved, a cycle found where there is none (a diamond), or a pipeline named that is not in the cycle:
  `test_ro6_*`;
- RO7 an undeployed pipeline refused: `test_ro7_*`;
- RO8 a pipeline that is another unit's, another dataset's, superseded, placed nowhere or unknown, saved: or refused in
  words that tell one reason from another: `test_ro8_*`;
- RO9 to RO12 the access rules: a person without the right, or whose cases do not read the dataset, told anything; the
  gate after the version; a pipeline the reader may not see named, counted or implied; a save over another unit's links
  losing them; a cycle through a hidden pipeline refused, or told differently (it is stored, the answer is the same as
  with no such path), or a cycle among visible pipelines not refused, or naming a hidden one: `test_ro9_*` to
  `test_ro12_*`;
- RO13 a route with no right declared, or another right: `test_ro13_*`; RO14 two saves of one number both winning:
  `test_ro14_*`.

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It imports the app and the stores and reads no folder.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.dataset_run_order import (
    InMemoryRunOrderStore,
    PostgresRunOrderStore,
    RunOrderRefused,
    pipelines_in_a_cycle,
)
from services.api.datasets import Dataset, InMemoryDatasetStore

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.rights import Right

DATASET = "ds-a"
URL = f"/v1/datasets/{DATASET}/run-order"
#: The Conduit's own principal, which writes what a person of another unit would (their pipelines are not the saver's).
SYSTEM = Principal(id="conduit", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"])
PEOPLE = {
    "alice": Principal(
        id="alice-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]
    ),
    "bob": Principal(id="bob-2", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    # Reaches the dataset through a case, lacks edit_pipelines.
    "analyst": Principal(id="ana-3", clearance="SECRET", org_unit="unit-1", roles=["analyst"]),
    # Holds the right, and no case of theirs reads the dataset.
    "stranger": Principal(
        id="str-4", clearance="SECRET", org_unit="unit-2", roles=["data_engineer"]
    ),
    # Holds the right and reads the dataset, but of another unit: sees none of unit-1's pipelines.
    "carol": Principal(id="car-5", clearance="SECRET", org_unit="unit-2", roles=["data_engineer"]),
}
CASES = {
    "alice-1": {"case-a": [DATASET]},
    "bob-2": {"case-b": [DATASET]},
    "ana-3": {"case-n": [DATASET]},
    "str-4": {"case-s": ["ds-s"]},
    "car-5": {"case-c": [DATASET]},
}
AT = datetime(2026, 11, 1, tzinfo=UTC)


def _recipe(
    recipe_id: str, label: str, status: StudioRecipeStatus, *, unit: str = "unit-1",
    dataset: str | None = DATASET, version: int = 1,
) -> StudioRecipeDraft:  # fmt: skip
    return StudioRecipeDraft(
        recipe_id=recipe_id, version=version, status=status, label=label, owning_unit=unit,
        created_by="x", created_at=AT, ready_for_profile=False, dataset_id=dataset,
    )  # fmt: skip


P = StudioRecipeStatus.PUBLISHED
RECIPES = [
    _recipe("p-ingest", "Ingest", P, version=2),
    _recipe("p-enrich", "Enrich", P),
    _recipe("p-report", "Report", P),
    _recipe("p-clean", "Clean", P),
    # Undeployed: a draft. It may be in the order.
    _recipe("p-load", "Load", StudioRecipeStatus.DRAFT),
    # A previous version of a pipeline is not a pipeline of the map, and the older row is never listed.
    _recipe("p-old", "Old", StudioRecipeStatus.SUPERSEDED, version=2),
    _recipe("p-ingest", "Ingest (before)", StudioRecipeStatus.SUPERSEDED, version=1),
    # Another dataset's, one placed in none, and another unit's own (unit-2 can see it, unit-1 cannot).
    _recipe("p-elsewhere", "Elsewhere", P, dataset="ds-x"),
    _recipe("p-nowhere", "Nowhere", P, dataset=None),
    _recipe("p-theirs", "Theirs", P, unit="unit-2"),
]


class _Recipes:
    """The recipe store's listing, as the real one answers it (`StudioRecipeStore.list_all`): the principal's own unit's
    recipes at whatever status, one row per recipe (its latest version), kept to the datasets the principal reaches."""

    async def list_all(self, principal: Principal) -> list[StudioRecipeDraft]:
        mine = [
            r for r in RECIPES
            if r.owning_unit == principal.org_unit
            and (principal.datasets is None or r.dataset_id in principal.datasets or r.dataset_id is None)
        ]  # fmt: skip
        latest: dict[str, StudioRecipeDraft] = {}
        for r in sorted(mine, key=lambda x: x.version):
            latest[r.recipe_id] = r
        return list(latest.values())


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


class _Resolver:
    async def resolve_principal(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c, name=f"Case {c}"), "editor") for c in CASES[principal.id]]


def _dataset(dataset_id: str, unit: str) -> Dataset:
    return Dataset(
        id=dataset_id, name=f"Dataset {dataset_id}", owning_unit=unit,
        created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="s",
    )  # fmt: skip


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    datasets = InMemoryDatasetStore()
    datasets.add(_dataset(DATASET, "unit-1"))
    datasets.add(_dataset("ds-s", "unit-2"))
    for reads in CASES.values():
        for case, ids in reads.items():
            datasets.cases[case] = list(ids)
    audit, store = _Audit(), InMemoryRunOrderStore()
    state = {
        "principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
        "studio_recipes": _Recipes(), "audit": audit, "run_orders": store,
        "handling_scheme": load_uk_le_scheme(), "ontology": load_deployment_ontology(),
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app), audit=audit, store=store)


def _headers(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _entries(**runs_after: list[str]) -> list[dict[str, Any]]:
    """`_entries(p_enrich=["p-ingest"])` is the order "Enrich runs after Ingest": keyword names use `_` for `-`."""
    return [{"pipeline_id": k.replace("_", "-"), "runs_after": v} for k, v in runs_after.items()]


def _get(world: SimpleNamespace, person: str = "alice", dataset: str = DATASET) -> Any:
    return world.client.get(f"/v1/datasets/{dataset}/run-order", headers=_headers(person))


def _put(
    world: SimpleNamespace, entries: list[dict[str, Any]], expected: Any = 0, person: str = "alice",
    dataset: str = DATASET,
) -> Any:  # fmt: skip
    body: dict[str, Any] = {"entries": entries}
    if expected is not None:
        body["expected_version"] = expected
    return world.client.put(
        f"/v1/datasets/{dataset}/run-order", json=body, headers=_headers(person)
    )


def _saves(world: SimpleNamespace) -> list[dict[str, Any]]:
    return [e for e in world.audit.entries if e["action"] == "save_run_order"]


def _links(answer: Any) -> dict[str, list[str]]:
    return {e["pipeline_id"]: e["runs_after"] for e in answer.json()["entries"]}


ORDER = _entries(p_enrich=["p-ingest"], p_report=["p-enrich"], p_load=["p-report"])


# --- RO1 and RO2: the stored order, versioned, with who and when ---------------------------------------------


def test_ro1_a_dataset_with_no_stored_order_reads_as_none_not_as_an_empty_order(
    world: SimpleNamespace,
) -> None:
    answer = _get(world)
    assert answer.status_code == 200, answer.text
    assert answer.json() == {
        "dataset_id": DATASET, "version": 0, "saved_by": None, "saved_at": None, "entries": [],
    }  # fmt: skip


def test_ro2_every_save_is_a_new_number_with_who_and_when_and_the_old_ones_are_kept(
    world: SimpleNamespace,
) -> None:
    before = datetime.now(UTC)
    first = _put(world, ORDER, 0, "alice")
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1 and first.json()["saved_by"] == "alice-1"
    saved_at = datetime.fromisoformat(first.json()["saved_at"])
    assert before <= saved_at <= datetime.now(UTC)
    assert _links(first) == {
        "p-enrich": ["p-ingest"],
        "p-report": ["p-enrich"],
        "p-load": ["p-report"],
    }
    # What a read answers is what was saved, whole.
    assert _get(world, "bob").json() == first.json()
    second = _put(world, _entries(p_enrich=["p-ingest"]), 1, "bob")
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2 and second.json()["saved_by"] == "bob-2"
    assert _links(_get(world)) == {"p-enrich": ["p-ingest"]}
    # The first number is not lost to the second: each save keeps its own person, time and links.
    held = asyncio.run(world.store.versions(DATASET))
    assert [(v.version, v.saved_by) for v in held] == [(1, "alice-1"), (2, "bob-2")]
    assert held[0].runs_after == {
        "p-enrich": ["p-ingest"],
        "p-report": ["p-enrich"],
        "p-load": ["p-report"],
    }
    # Each save is audited with the dataset and the number, and nothing of the pipelines.
    assert [e["resolved_query"] for e in _saves(world)] == [
        {"dataset_id": DATASET, "version": 1}, {"dataset_id": DATASET, "version": 2},
    ]  # fmt: skip
    # An empty order is a save too (it clears the links), and is not "none stored": the number moves.
    cleared = _put(world, [], 2)
    assert (
        cleared.status_code == 200
        and cleared.json()["version"] == 3
        and cleared.json()["entries"] == []
    )


def test_ro2_the_links_are_kept_as_a_set_in_the_order_given_and_a_repeat_is_not_stored_twice(
    world: SimpleNamespace,
) -> None:
    answer = _put(
        world, [{"pipeline_id": "p-report", "runs_after": ["p-enrich", "p-ingest", "p-enrich"]}], 0
    )
    assert answer.status_code == 200, answer.text
    assert _links(answer) == {"p-report": ["p-enrich", "p-ingest"]}
    # Two entries for one pipeline would say two things about it: refused, as is a blank one.
    twice = _put(world, _entries(p_report=["p-enrich"]) + _entries(p_report=["p-ingest"]), 1)
    assert twice.status_code == 422, twice.text
    assert _links(_get(world)) == {"p-report": ["p-enrich", "p-ingest"]}


# --- RO3 to RO5: the expected number -----------------------------------------------------------------------------


def test_ro3_a_stale_number_is_refused_in_words_and_nothing_is_changed(
    world: SimpleNamespace,
) -> None:
    assert _put(world, ORDER, 0, "alice").status_code == 200
    before = _get(world).json()
    # Bob read the order before alice's save: he read "none", number 0.
    stale = _put(world, _entries(p_report=["p-ingest"]), 0, "bob")
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"] == "run_order_refused"
    words = stale.json()["detail"]
    # In the store's words: the number he meant, the number it is now, and to read it again.
    assert "you meant version 0" in words and "now version 1" in words and "read it again" in words
    assert _get(world).json() == before
    assert len(_saves(world)) == 1
    # A number from the future is as stale as one from the past.
    ahead = _put(world, _entries(p_report=["p-ingest"]), 7, "bob")
    assert ahead.status_code == 409, ahead.text
    assert _get(world).json() == before
    # Control: the number it is now saves.
    assert _put(world, _entries(p_report=["p-ingest"]), 1, "bob").status_code == 200


@pytest.mark.parametrize("unusable", [None, -1, "one", 1.5, True, ""])
def test_ro4_a_save_with_no_number_or_an_unusable_one_is_refused_and_nothing_changes(
    world: SimpleNamespace, unusable: Any
) -> None:
    answer = _put(world, ORDER, unusable)
    assert answer.status_code == 422, answer.text
    assert "expected_version" in answer.text
    assert _get(world).json()["version"] == 0
    assert _saves(world) == []
    # "No order stored" is number 0 and is a number: the first save names it, and 0 is not "any".
    assert _put(world, ORDER, 0).status_code == 200


def test_ro5_the_route_hands_the_store_the_number_the_client_sent(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's check is what refuses, so the route must hand it the client's number and not one it read itself (the
    fault the draft's route once had). The spy sees the arguments the store really receives at the route's call site."""
    seen: list[int | None] = []
    real = world.store.save

    async def save(*args: Any, expected_version: int | None = None, **kw: Any) -> Any:
        seen.append(expected_version)
        return await real(*args, expected_version=expected_version, **kw)

    monkeypatch.setattr(world.store, "save", save)
    assert _put(world, ORDER, 5).status_code == 409
    assert _put(world, ORDER, 0).status_code == 200
    assert _put(world, ORDER, 3).status_code == 409
    assert seen == [5, 0, 3]


# --- RO6: a cycle -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entries, named, not_named",
    [
        # Two pipelines each after the other.
        (_entries(p_ingest=["p-enrich"], p_enrich=["p-ingest"]), {"Ingest", "Enrich"}, {"Report", "Clean"}),
        # Three, round the ring, with a pipeline hanging off it that is not in it.
        (
            _entries(p_ingest=["p-report"], p_enrich=["p-ingest"], p_report=["p-enrich"], p_clean=["p-ingest"]),
            {"Ingest", "Enrich", "Report"}, {"Clean", "Load"},
        ),
        # A pipeline after itself.
        (_entries(p_clean=["p-clean"]), {"Clean"}, {"Ingest", "Enrich", "Report"}),
        # A cycle beside an honest chain: only the cycle is named.
        (
            _entries(p_enrich=["p-ingest"], p_report=["p-load"], p_load=["p-report"]),
            {"Report", "Load"}, {"Ingest", "Enrich", "Clean"},
        ),
    ],
)  # fmt: skip
def test_ro6_a_cycle_is_refused_on_save_in_words_naming_the_pipelines_in_it_and_no_others(
    world: SimpleNamespace, entries: list[dict[str, Any]], named: set[str], not_named: set[str]
) -> None:
    assert _put(world, _entries(p_clean=["p-ingest"]), 0).status_code == 200
    before = _get(world).json()
    answer = _put(world, entries, 1)
    assert answer.status_code == 422, answer.text
    assert answer.json()["error"] == "run_order_cycle"
    words = answer.json()["detail"]
    # Named as the Studio names them (the label), never by identifier.
    for label in named:
        assert f"“{label}”" in words, (label, words)
    for label in not_named:
        assert f"“{label}”" not in words, (label, words)
    assert "p-" not in words
    # Nothing was saved: the number, the links and the audit are as they were.
    assert _get(world).json() == before
    assert len(_saves(world)) == 1


def test_ro6_a_diamond_and_a_long_chain_are_not_cycles(world: SimpleNamespace) -> None:
    """Control: the check refuses a cycle, not every order with a shared pipeline or a long run."""
    diamond = _entries(
        p_report=["p-enrich", "p-clean"], p_enrich=["p-ingest"], p_clean=["p-ingest"]
    )
    assert _put(world, diamond, 0).status_code == 200
    chain = _entries(
        p_enrich=["p-ingest"], p_report=["p-enrich"], p_clean=["p-report"], p_load=["p-clean"]
    )
    assert _put(world, chain, 1).status_code == 200


# --- RO7 and RO8: which pipelines may be named ----------------------------------------------------------------


def test_ro7_an_undeployed_pipeline_may_be_in_the_order(world: SimpleNamespace) -> None:
    answer = _put(world, _entries(p_load=["p-ingest"], p_report=["p-load"]), 0)
    assert answer.status_code == 200, answer.text
    assert _links(answer) == {"p-load": ["p-ingest"], "p-report": ["p-load"]}


@pytest.mark.parametrize(
    "named",
    [
        "p-theirs",  # another unit's: the saver may not see it
        "p-elsewhere",  # another dataset's
        "p-nowhere",  # placed in no dataset
        "p-old",  # a previous version
        "p-no-such-pipeline",
    ],
)
def test_ro8_a_pipeline_the_saver_cannot_see_in_this_dataset_is_refused_in_one_set_of_words_for_every_reason(
    world: SimpleNamespace, named: str
) -> None:
    for entries in (
        _entries(p_enrich=[named]),
        [{"pipeline_id": named, "runs_after": ["p-ingest"]}],
    ):
        answer = _put(world, entries, 0)
        assert answer.status_code == 422, (named, answer.text)
        assert answer.json()["error"] == "run_order_refused"
        # No reason is given and no identifier echoed: an unknown id and a hidden one read alike.
        assert (
            named not in answer.text and "unit-2" not in answer.text and "ds-x" not in answer.text
        )
    unknown = _put(world, _entries(p_enrich=["p-no-such-pipeline-at-all"]), 0)
    refused = _put(world, _entries(p_enrich=[named]), 0)
    assert unknown.json()["detail"] == refused.json()["detail"]
    assert unknown.json()["error"] == refused.json()["error"]
    assert _get(world).json()["version"] == 0 and _saves(world) == []


# --- RO9: every path has a test with the right and without it ------------------------------------------------------


def test_ro9_each_path_answers_a_person_with_the_right_and_refuses_one_without_it(
    world: SimpleNamespace,
) -> None:
    assert _put(world, ORDER, 0, "alice").status_code == 200
    for person in ("alice", "bob"):
        assert _get(world, person).status_code == 200
    assert _put(world, _entries(p_report=["p-ingest"]), 1, "bob").status_code == 200
    # A reader who reaches the dataset and lacks edit_pipelines: refused in words, for the read and for the save.
    stored = _get(world).json()
    for answer in (
        _get(world, "analyst"),
        _put(world, ORDER, 2, "analyst"),
        _put(world, [], 2, "analyst"),
    ):
        assert answer.status_code == 403, answer.text
        assert answer.json()["detail"] == {
            "error": "right_required",
            "right": Right.EDIT_PIPELINES.value,
        }
        assert (
            "p-" not in answer.text and "Ingest" not in answer.text and "alice" not in answer.text
        )
    assert _get(world).json() == stored
    assert len(_saves(world)) == 2


# --- RO10: no oracle: the dataset's gate -----------------------------------------------------------------------------


def test_ro10_a_dataset_the_persons_cases_do_not_read_is_answered_as_one_that_does_not_exist(
    world: SimpleNamespace,
) -> None:
    assert _put(world, ORDER, 0).status_code == 200
    # A stranger with the right: the read and the save, with a number and without, a stored order or none.
    for sent in (0, 1, None):
        got = _get(world, "stranger")
        put = _put(world, ORDER, sent, "stranger")
        missing_get = _get(world, "alice", "ds-that-does-not-exist")
        missing_put = _put(world, ORDER, sent, "alice", "ds-that-does-not-exist")
        for answer in (got, put, missing_get, missing_put):
            assert answer.status_code == 404, answer.text
        # Byte for byte, bar the dataset's own name in nothing (the body names no dataset).
        assert got.content == missing_get.content
        assert put.content == missing_put.content
        assert (
            "expected_version" not in put.text and "p-" not in put.text and "Ingest" not in put.text
        )
    assert _get(world).json()["version"] == 1
    assert len(_saves(world)) == 1


def test_ro10_the_gate_comes_before_the_body_and_the_number(world: SimpleNamespace) -> None:
    """With no body at all a person without the right is refused as for a body that was sent, never told by a 422 that the
    route exists for them or what it wants."""
    for person, dataset, status in (
        ("analyst", DATASET, 403), ("stranger", DATASET, 404), ("alice", "ds-that-does-not-exist", 404),
    ):  # fmt: skip
        blind = world.client.put(f"/v1/datasets/{dataset}/run-order", headers=_headers(person))
        sent = _put(world, ORDER, 1, person, dataset)
        assert blind.status_code == sent.status_code == status, (person, blind.text)
        assert "expected_version" not in blind.text and "entries" not in blind.text


# --- RO11: a pipeline the reader may not see ---------------------------------------------------------------------------


def _write_other_units_links(world: SimpleNamespace) -> None:
    """Links as unit-2's own person would have saved them: among pipelines (the dataset's `p-theirs`) unit-1 cannot see
    and visible ones, written through the store, since unit-1's saver is refused the name."""
    asyncio.run(
        world.store.save(
            DATASET,
            {"p-enrich": ["p-ingest"], "p-load": ["p-theirs"], "p-theirs": ["p-ingest", "p-enrich"],
             "p-report": ["p-enrich", "p-theirs"]},
            SYSTEM, expected_version=0,
        )
    )  # fmt: skip


def test_ro11_a_stored_order_that_names_a_pipeline_the_reader_may_not_see_reads_back_without_it_and_without_a_count(
    world: SimpleNamespace,
) -> None:
    _write_other_units_links(world)
    answer = _get(world, "alice")
    assert answer.status_code == 200, answer.text
    # Only what alice may see: no entry for the hidden pipeline, none for one whose only link is to it, and a link to a
    # hidden one is gone from the entry that held it.
    assert _links(answer) == {"p-enrich": ["p-ingest"], "p-report": ["p-enrich"]}
    assert "p-theirs" not in answer.text and "Theirs" not in answer.text
    # The answer's shape is fixed: nothing in it is a count of what was left out, and no entry is kept empty (an empty one
    # would say that its pipeline runs after something it may not name).
    assert set(answer.json()) == {"dataset_id", "version", "saved_by", "saved_at", "entries"}
    assert all(
        set(e) == {"pipeline_id", "runs_after"} and e["runs_after"]
        for e in answer.json()["entries"]
    )
    # The other unit's person, who reaches the dataset through their own case, sees none of unit-1's pipelines and so no
    # link at all: the order's number says only that one was saved.
    carol = _get(world, "carol")
    assert carol.status_code == 200, carol.text
    assert carol.json()["entries"] == []
    assert (
        "p-ingest" not in carol.text and "Ingest" not in carol.text and "p-enrich" not in carol.text
    )


def test_ro11_what_a_hidden_link_would_change_is_not_to_be_told_by_the_answer(
    world: SimpleNamespace,
) -> None:
    """Two datasets' orders that differ only in a link to a hidden pipeline read back alike, apart from the number's own
    history: the reader cannot tell a hidden link from none."""
    asyncio.run(world.store.save(DATASET, {"p-enrich": ["p-ingest"]}, SYSTEM, expected_version=0))
    plain = _get(world, "alice").json()
    asyncio.run(
        world.store.save(
            DATASET, {"p-enrich": ["p-ingest"], "p-load": ["p-theirs"], "p-theirs": ["p-clean"]},
            SYSTEM, expected_version=1,
        )
    )  # fmt: skip
    hidden = _get(world, "alice").json()
    assert hidden["entries"] == plain["entries"]
    assert set(hidden) == set(plain)


# --- RO12: a save never loses another unit's links, and a cycle is no oracle ---------------------------------------------


def test_ro12_a_save_by_a_person_who_cannot_see_all_the_links_keeps_the_ones_they_cannot_see(
    world: SimpleNamespace,
) -> None:
    _write_other_units_links(world)
    answer = _put(world, _entries(p_clean=["p-ingest"]), 1, "alice")
    assert answer.status_code == 200, answer.text
    assert _links(answer) == {"p-clean": ["p-ingest"]}
    assert "p-theirs" not in answer.text
    kept = asyncio.run(world.store.current(DATASET))
    assert kept is not None and kept.version == 2
    # What alice replaced is hers to replace (the links among pipelines she sees); what names a pipeline she cannot see
    # stays, so unit-2's own order is not undone by a save that never showed it to her.
    assert kept.runs_after["p-theirs"] == ["p-ingest", "p-enrich"]
    assert kept.runs_after["p-load"] == ["p-theirs"]
    assert kept.runs_after["p-report"] == ["p-theirs"]
    assert "p-enrich" not in kept.runs_after and kept.runs_after["p-clean"] == ["p-ingest"]


def test_ro12_a_cycle_that_runs_through_a_pipeline_the_saver_cannot_see_is_not_told_to_them(
    world: SimpleNamespace,
) -> None:
    """Rule 3: refusing "Ingest after Enrich" only when a path Enrich -> hidden -> Ingest exists would tell the saver that
    such a path exists (a path through nodes they may not see). The check is made over what the saver sees, and the answer
    is the same as with no hidden link: saved."""
    asyncio.run(
        world.store.save(
            DATASET, {"p-theirs": ["p-enrich"], "p-ingest": ["p-theirs"]}, SYSTEM, expected_version=0
        )
    )  # fmt: skip
    answer = _put(world, _entries(p_enrich=["p-ingest"]), 1)
    assert answer.status_code == 200, answer.text
    assert _links(answer) == {"p-enrich": ["p-ingest"]}
    # And a cycle among what the saver does see is refused whatever else is stored.
    again = _put(world, _entries(p_enrich=["p-ingest"], p_ingest=["p-enrich"]), 2)
    assert again.status_code == 422 and again.json()["error"] == "run_order_cycle"


#: Another unit's links: a path Enrich -> Theirs -> Ingest, which with "Ingest after Enrich" closes a cycle through a
#: pipeline alice cannot see. And the same stored order with the path cut: the only thing the second world lacks.
CLOSES_THROUGH_HIDDEN = {"p-theirs": ["p-enrich"], "p-ingest": ["p-theirs"]}
NO_PATH_THROUGH_HIDDEN = {"p-theirs": ["p-enrich"]}


def _alice_saves_in_a_world_holding(
    world: SimpleNamespace, stored: dict[str, list[str]], entries: list[dict[str, Any]]
) -> Any:
    """A fresh store holding `stored` as the Conduit wrote it (version 1), then alice's save from number 1."""
    fresh = InMemoryRunOrderStore()
    asyncio.run(fresh.save(DATASET, stored, SYSTEM, expected_version=0))
    app.state.run_orders = fresh
    world.store = fresh
    return _put(world, entries, 1, "alice")


def test_ro12_a_cycle_that_closes_only_through_a_pipeline_the_saver_cannot_see_is_stored_and_the_answer_is_the_same_as_with_no_such_path(
    world: SimpleNamespace,
) -> None:
    """The owner's ruling of 25 November 2026 (option a): such a cycle is stored (refused at the run, a later part's), and
    the saver is told nothing of it: not a refusal, not other words, not another count, not another key. Both worlds give
    alice the same save, so she cannot tell a hidden path from none. A planted change that checks the merged links for a
    cycle and refuses turns the first world's save into a 422, which is what tells her a path exists."""
    through = _alice_saves_in_a_world_holding(
        world, CLOSES_THROUGH_HIDDEN, _entries(p_enrich=["p-ingest"])
    )
    # The cycle really is what was stored (so this is the case, not a nearby one), and it is whole: the hidden links stayed.
    kept = asyncio.run(world.store.current(DATASET))
    assert kept is not None and kept.version == 2
    assert kept.runs_after == {
        "p-enrich": ["p-ingest"], "p-theirs": ["p-enrich"], "p-ingest": ["p-theirs"],
    }  # fmt: skip
    assert pipelines_in_a_cycle(kept.runs_after) == {"p-enrich", "p-ingest", "p-theirs"}
    without = _alice_saves_in_a_world_holding(
        world, NO_PATH_THROUGH_HIDDEN, _entries(p_enrich=["p-ingest"])
    )
    assert through.status_code == without.status_code == 200, (through.text, without.text)
    one, other = through.json(), without.json()
    for answer in (one, other):
        answer.pop("saved_at")
    assert one == other
    assert "p-theirs" not in through.text and "Theirs" not in through.text


def test_ro12_a_cycle_among_pipelines_the_saver_sees_is_refused_naming_them_whatever_hidden_links_are_stored(
    world: SimpleNamespace,
) -> None:
    """Item 1 of the ruling: every cycle among what the saver sees is refused, naming them. Their pipelines are named and a
    hidden one is not (a check over the merged links would name "Theirs" too, and in the stored world only), and the refusal
    is word for word the one a world with no hidden path gives, so it says nothing of one."""
    cycle = _entries(p_enrich=["p-ingest"], p_ingest=["p-enrich"])
    through = _alice_saves_in_a_world_holding(world, CLOSES_THROUGH_HIDDEN, cycle)
    without = _alice_saves_in_a_world_holding(world, NO_PATH_THROUGH_HIDDEN, cycle)
    assert through.status_code == without.status_code == 422, (through.text, without.text)
    assert through.json()["error"] == "run_order_cycle"
    assert through.json() == without.json()
    assert "“Enrich”" in through.text and "“Ingest”" in through.text
    assert "Theirs" not in through.text and "p-theirs" not in through.text
    # Nothing was written by either refusal.
    kept = asyncio.run(world.store.current(DATASET))
    assert kept is not None and kept.version == 1


# --- RO13: every route names its right ----------------------------------------------------------------------------------


def test_ro13_both_routes_name_edit_pipelines_behind_the_datasets_own_gate() -> None:
    found: dict[str, set[str]] = {}
    for route in app.routes:
        if getattr(route, "path", "") != "/v1/datasets/{dataset_id}/run-order":
            continue
        rights = {
            getattr(d.call, "required_right").value  # noqa: B009
            for d in route.dependant.dependencies  # type: ignore[attr-defined]
            if hasattr(d.call, "required_right")
        }
        for method in route.methods:  # type: ignore[attr-defined]
            found[method] = rights
    assert found == {"GET": {"edit_pipelines"}, "PUT": {"edit_pipelines"}}


# --- RO14: the store's own refusals ---------------------------------------------------------------------------------------


def test_ro14_two_saves_of_one_number_are_not_both_saved() -> None:
    """Two people saving from the number they both read: one wins, the other is refused, never both written (the Postgres
    store holds a primary key on the dataset and number behind its lock, as the in-memory one holds the number)."""

    async def run() -> list[object]:
        store = InMemoryRunOrderStore()
        mine = {"p-enrich": ["p-ingest"]}
        yours = {"p-report": ["p-ingest"]}
        return list(
            await asyncio.gather(
                store.save(DATASET, mine, PEOPLE["alice"], expected_version=0),
                store.save(DATASET, yours, PEOPLE["bob"], expected_version=0),
                return_exceptions=True,
            )
        )

    outcomes = asyncio.run(run())
    assert sum(isinstance(o, RunOrderRefused) for o in outcomes) == 1
    assert sum(not isinstance(o, BaseException) for o in outcomes) == 1


def test_ro14_the_postgres_store_cannot_hold_two_rows_for_one_dataset_and_number() -> None:
    sql = " ".join(PostgresRunOrderStore.BOOTSTRAP_SQL.split())
    assert "CREATE TABLE IF NOT EXISTS dataset_run_orders" in sql
    assert "PRIMARY KEY (dataset_id, version)" in sql
    for column in (
        "saved_by TEXT NOT NULL",
        "saved_at TIMESTAMPTZ NOT NULL",
        "content JSONB NOT NULL",
    ):
        assert column in sql
