"""The source governance edit judges the marking it is asked to set (SE2, C187; ADR-140 Amendment 19).

The default-marking route refuses a marking above the editor's clearance, above the deployment's
highest marking, or below the source's own; the governance edit wrote `handling` as given. What a
mistake would do, and the case that catches it, through the real app and the request body the
route receives (`SourceGovernanceInput`):

- an editor marking a source above what they may read
  (`test_a_marking_the_governance_edit_may_not_set_is_refused_in_words_and_nothing_is_written`,
  "above-the-editor");
- a source marked above what the deployment may hold (the same case, "above-the-ceiling");
- a source's marking lowered by an edit ("below-the-source");
- the check refusing what it should accept: a raise within clearance and ceiling, an edit that
  changes no marking (even where the source's marking is now above the ceiling), no ceiling set,
  a marking outside the scheme (refused, failing closed) — each its own case below;
- the default-marking route changing with the shared check
  (`test_the_default_marking_route_refuses_and_accepts_as_before`).

Refused means 422 `governance_marking_refused` with the `problems` in words, and the store, the
flags, the following drafts and the audit trail untouched.
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

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}
PEOPLE = {
    "engineer": Principal(id="eng-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    # Below the SECRET a source may be marked: they may not mark one above their own clearance.
    "junior": Principal(id="jun-1", clearance="OFFICIAL", org_unit="unit-1", roles=["data_engineer"]),
}
CASES = {"eng-1": {"case-a": ["ds-a"]}, "jun-1": {"case-j": ["ds-a"]}}
CEILING_ENV = "OSPREY_HIGHEST_MARKING"


class _Resolver:
    async def resolve_principal(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c), "editor") for c in CASES[principal.id]]


class _Recipes:
    """Records what a governance edit does to the pipelines reading the source."""

    def __init__(self) -> None:
        self.flagged: list[tuple[str, str, str]] = []
        self.followed: list[tuple[str, str, str]] = []

    async def flag_for_source(self, dataset_id: str, location: str, reason: str) -> list[str]:
        self.flagged.append((dataset_id, location, reason))
        return ["PIN calls"]

    async def using_source(self, dataset_id: str, location: str) -> list[Any]:
        return []

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
    (root / "uploaded" / "ds-a").mkdir(parents=True)
    (root / "uploaded" / "ds-a" / "cells.csv").write_text("prisoner,cell\nSYN-1,A1\n")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    monkeypatch.delenv(CEILING_ENV, raising=False)
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(
            id="ds-a",
            name="ds-a",
            owning_unit="unit-1",
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


def _register(
    world: SimpleNamespace, marking: str = "OFFICIAL", file: str = "cells.csv"
) -> dict[str, Any]:
    (world.root / "uploaded" / "ds-a" / file).write_text("a\n1\n")
    response = world.client.post(
        "/v1/datasets/ds-a/sources",
        json={
            "connection_id": "files",
            "name": "Cell stays",
            "location": str(world.root / "uploaded" / "ds-a" / file),
            "handling": HANDLING | {"classification": marking},
            "legal_basis": "Synthetic demonstration",
        },
        headers=_as("engineer"),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _edit(world: SimpleNamespace, source_id: str, handling: dict[str, Any], who: str = "engineer") -> Any:
    """The request body the route receives: a `SourceGovernanceInput`, through the app."""
    return world.client.patch(
        f"/v1/datasets/ds-a/sources/{source_id}/governance",
        json={"handling": handling, "legal_basis": "Synthetic demonstration"},
        headers=_as(who),
    )


def _nothing_else_happened(world: SimpleNamespace) -> None:
    assert world.recipes.flagged == [] and world.recipes.followed == []
    assert [e for e in world.audit.entries if e["action"] == "edit_dataset_source_governance"] == []


@pytest.mark.parametrize(
    ("who", "source_marking", "new_marking", "ceiling", "words"),
    [
        (
            "junior", "OFFICIAL", "SECRET", None,
            "the marking is above your clearance: a source's rows are never marked higher than "
            "the person declaring it may read",
        ),
        (
            "engineer", "OFFICIAL", "SECRET", "OFFICIAL",
            "the marking is above this deployment's highest marking, OFFICIAL",
        ),
        (
            "engineer", "SECRET", "OFFICIAL", None,
            "the marking is below the source's current marking, SECRET: an edit never lowers a "
            "marking",
        ),
    ],
    ids=["above-the-editor", "above-the-ceiling", "below-the-source"],
)  # fmt: skip
def test_a_marking_the_governance_edit_may_not_set_is_refused_in_words_and_nothing_is_written(
    world: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    who: str,
    source_marking: str,
    new_marking: str,
    ceiling: str | None,
    words: str,
) -> None:
    if ceiling is not None:
        monkeypatch.setenv(CEILING_ENV, ceiling)
    made = _register(world, source_marking)
    before = world.sources._sources[made["id"]]
    response = _edit(world, made["id"], HANDLING | {"classification": new_marking}, who=who)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "governance_marking_refused"
    problems = response.json()["problems"]
    # The whole sentence, so the wording the brief names ("never lowers") is pinned, not a part of it.
    assert problems == [words], problems
    assert world.sources._sources[made["id"]] == before
    _nothing_else_happened(world)
    # The words name no data: not the source, its location or the marking asked for beyond the scheme.
    assert made["location"] not in response.text and "Cell stays" not in response.text


@pytest.mark.parametrize(
    "without", [None, "absent"], ids=["null", "left-out"]
)
def test_an_edit_that_carries_no_marking_does_not_erase_the_sources(
    world: SimpleNamespace, without: str | None
) -> None:
    """The handling an edit sends replaces the source's whole handling, so one with no
    classification would leave a SECRET source unmarked: a lowering, refused as one."""
    made = _register(world, "SECRET")
    before = world.sources._sources[made["id"]]
    handling = {k: v for k, v in HANDLING.items() if k != "classification"}
    if without is None:
        handling["classification"] = None  # type: ignore[assignment]
    response = _edit(world, made["id"], handling)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "governance_marking_refused"
    assert response.json()["problems"] == [
        "the marking is left out, which is below the source's current marking, SECRET: an edit "
        "never lowers a marking"
    ]
    assert world.sources._sources[made["id"]] == before
    assert world.sources._sources[made["id"]].handling["classification"] == "SECRET"
    _nothing_else_happened(world)


def test_every_problem_is_told_at_once(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Above both the editor's clearance and the ceiling: two sentences, not the first alone."""
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    made = _register(world)
    response = _edit(world, made["id"], HANDLING | {"classification": "SECRET"}, who="junior")
    assert response.status_code == 422, response.text
    problems = response.json()["problems"]
    assert any("above your clearance" in p for p in problems)
    assert any("highest marking, OFFICIAL" in p for p in problems)
    assert world.sources._sources[made["id"]].version == 1


def test_a_marking_outside_the_scheme_is_refused_and_nothing_is_written(
    world: SimpleNamespace,
) -> None:
    made = _register(world)
    response = _edit(world, made["id"], HANDLING | {"classification": "TOP-SECRET-ISH"})
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "governance_marking_refused"
    assert any("is not a classification of the" in p for p in response.json()["problems"])
    assert world.sources._sources[made["id"]].version == 1
    _nothing_else_happened(world)


# --- Controls (rule 15): what the check must still accept --------------------------------------


@pytest.mark.parametrize("new_marking", ["SECRET", "OFFICIAL-SENSITIVE"], ids=["secret", "between"])
def test_a_raise_within_the_clearance_and_the_ceiling_is_accepted(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, new_marking: str
) -> None:
    monkeypatch.setenv(CEILING_ENV, "SECRET")
    made = _register(world)
    response = _edit(world, made["id"], HANDLING | {"classification": new_marking})
    assert response.status_code == 200, response.text
    assert response.json()["source"]["handling"]["classification"] == new_marking
    assert world.sources._sources[made["id"]].version == 2
    assert world.recipes.followed == [("ds-a", made["location"], new_marking)]


def test_the_same_marking_is_accepted_and_other_declarations_change(world: SimpleNamespace) -> None:
    made = _register(world)
    response = _edit(world, made["id"], HANDLING | {"handling_code": "C"})
    assert response.status_code == 200, response.text
    assert world.sources._sources[made["id"]].handling["handling_code"] == "C"


def test_an_edit_that_changes_no_marking_is_not_newly_refused(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source marked SECRET, the deployment's ceiling later set to OFFICIAL, an editor below
    SECRET changing the handling code alone: the marking is not the edit's, so it is not judged."""
    made = _register(world, "SECRET")
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    response = _edit(
        world, made["id"], HANDLING | {"classification": "SECRET", "handling_code": "C"}, who="junior"
    )
    assert response.status_code == 200, response.text
    assert world.sources._sources[made["id"]].handling["handling_code"] == "C"
    assert world.sources._sources[made["id"]].handling["classification"] == "SECRET"


def test_with_no_ceiling_only_the_clearance_and_the_source_are_judged(
    world: SimpleNamespace,
) -> None:
    made = _register(world)
    assert _edit(world, made["id"], HANDLING | {"classification": "SECRET"}).status_code == 200
    # Still refused without a ceiling: below the source, and above the editor.
    low = _edit(world, made["id"], HANDLING | {"classification": "OFFICIAL"})
    assert low.status_code == 422 and "below the source's current marking" in low.text
    other = _register(world, file="more.csv")
    high = _edit(world, other["id"], HANDLING | {"classification": "SECRET"}, who="junior")
    assert high.status_code == 422 and "above your clearance" in high.text
    assert "highest marking" not in high.text


def test_the_default_marking_route_refuses_and_accepts_as_before(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared check keeps the default-marking route's words and its error code."""
    monkeypatch.setitem(
        PEOPLE, "approver",
        Principal(id="apr-1", clearance="SECRET", org_unit="unit-1",
                  roles=["data_engineer", "source_approver"]),
    )  # fmt: skip
    monkeypatch.setitem(CASES, "apr-1", {"case-a": ["ds-a"]})
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    made = _register(world)

    def put(marking: str) -> Any:
        return world.client.put(
            f"/v1/datasets/ds-a/sources/{made['id']}/default-marking",
            json={"default_marking": marking},
            headers=_as("approver"),
        )

    refused = put("SECRET")
    assert refused.status_code == 422, refused.text
    assert refused.json() == {
        "error": "default_marking_refused",
        "problems": ["the default marking is above this deployment's highest marking, OFFICIAL"],
    }
    assert put("OFFICIAL").status_code == 200
    assert world.sources._sources[made["id"]].default_marking == "OFFICIAL"


def test_the_default_marking_routes_other_sentences_are_word_for_word_as_before(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared check builds the default route's clearance and "never lowers" sentences from
    parameters; they are pinned whole, as the ceiling's is above, so a change to either shows."""
    monkeypatch.setitem(
        PEOPLE, "junior-approver",
        Principal(id="jap-1", clearance="OFFICIAL", org_unit="unit-1",
                  roles=["data_engineer", "source_approver"]),
    )  # fmt: skip
    monkeypatch.setitem(
        PEOPLE, "approver",
        Principal(id="apr-1", clearance="SECRET", org_unit="unit-1",
                  roles=["data_engineer", "source_approver"]),
    )  # fmt: skip
    monkeypatch.setitem(CASES, "jap-1", {"case-a": ["ds-a"]})
    monkeypatch.setitem(CASES, "apr-1", {"case-a": ["ds-a"]})
    official = _register(world)
    secret = _register(world, "SECRET", file="more.csv")

    def put(source: dict[str, Any], marking: str, who: str) -> Any:
        return world.client.put(
            f"/v1/datasets/ds-a/sources/{source['id']}/default-marking",
            json={"default_marking": marking},
            headers=_as(who),
        )

    above = put(official, "SECRET", "junior-approver")
    assert above.status_code == 422, above.text
    assert above.json() == {
        "error": "default_marking_refused",
        "problems": [
            "the default marking is above your clearance: a source's rows are never marked "
            "higher than the person declaring it may read"
        ],
    }
    below = put(secret, "OFFICIAL", "approver")
    assert below.status_code == 422, below.text
    assert below.json() == {
        "error": "default_marking_refused",
        "problems": [
            "the default marking is below the source's own marking, SECRET: a default never "
            "lowers a marking"
        ],
    }
