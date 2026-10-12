"""Where a case's events are (`06_DECISIONS.md` ADR-099 Amendment 9, the owner's ruling of 12 October
2026): events stay with the case they were loaded into (decision 7, unchanged); a case with none of
its own is told which other cases the reader can open read one of its datasets and hold events the
reader may count — never a case they cannot open, never on the strength of an event they may not
see. Counted through the real DuckDB adapter, so a hidden event is hidden by the store itself (rule 3).

What a mistake would do, and the case that catches it:
- a case the reader holds no level on named in the notice — `test_a_case_the_reader_cannot_open_is_never_named`;
- an event the reader may not see making a case look as if it holds events —
  `test_an_event_the_reader_may_not_see_makes_no_holder`;
- a case that shares no dataset named — `test_a_case_reading_another_dataset_is_not_named`;
- a branch's inherited events missed, so a branch is told it has none —
  `test_a_branch_counts_the_events_it_inherits_from_its_parent`;
- the route read without Viewer or without the investigate right —
  `test_reading_needs_viewer_on_the_case_and_the_investigate_right`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_datasets,
    get_investigations,
    get_principal,
    get_working_set,
)
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventRecord
from schemas.domain import Handling, Principal

UNIT = "unit-1"
ANALYST = Principal(id="ana", clearance="OFFICIAL", org_unit=UNIT, roles=["analyst"])
READER = Principal(id="rv", clearance="OFFICIAL", org_unit=UNIT, roles=["reports_viewer"])
WHEN = datetime(2026, 9, 7, 12, tzinfo=UTC)


def _case(case_id: str, name: str) -> Investigation:
    return Investigation(id=case_id, name=name, created_at=WHEN, created_by="seed", owning_unit=UNIT)


REVIEW, LEDGER, HIDDEN, OTHER = (_case("review", "Ledger review"), _case("ledger", "Ledger (demo)"),
                                 _case("hidden", "Unshared ledger"), _case("other", "Other dataset"))  # fmt: skip
BRANCH = _case("branch", "Branch of Ledger (demo)").model_copy(update={"branched_from": "ledger"})


class _Cases:
    """The case store's own refusals: no level is not found; a case without one is never listed."""

    def __init__(self) -> None:
        self.cases = {c.id: c for c in (REVIEW, LEDGER, HIDDEN, OTHER, BRANCH)}
        self.levels: dict[tuple[str, str], AccessLevel] = {}

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Investigation:
        level = self.levels.get((investigation_id, principal.id))
        if investigation_id not in self.cases or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return self.cases[investigation_id]

    async def get(self, investigation_id: str) -> Investigation:
        if investigation_id not in self.cases:
            raise InvestigationNotFoundError(investigation_id)
        return self.cases[investigation_id]

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [(self.cases[c], lvl) for (c, who), lvl in self.levels.items() if who == principal.id]


class _Audit:
    async def record(self, **_: Any) -> None:
        return None


class _WorkingSet:
    """A branch holds its parent's one link; no other case is a branch."""

    async def current_membership(self, investigation_id: str) -> Any:
        assert investigation_id == BRANCH.id, "only a branch's membership is read"
        return [], [SimpleNamespace(id=f"e-{LEDGER.id}")]


class World:
    def __init__(self) -> None:
        self.cases = _Cases()
        self.datasets = InMemoryDatasetStore()
        con = duckdb.connect(":memory:")
        create_events_table(con)
        self.analytics = AnalyticsDuckDBAdapter(con, load_uk_le_scheme())
        self.principal = ANALYST

    def grant(self, case: Investigation, who: Principal = ANALYST, level: AccessLevel = AccessLevel.VIEWER) -> None:
        self.cases.levels[(case.id, who.id)] = level

    def reads(self, case: Investigation, *dataset_ids: str) -> None:
        for d in dataset_ids:
            self.datasets.add(Dataset(id=d, name=d, owning_unit=UNIT, created_at=WHEN, created_by="seed"))
        self.datasets.cases[case.id] = list(dataset_ids)

    async def event(self, case: Investigation, classification: str = "OFFICIAL") -> None:
        handling = Handling(classification=classification, handling_code="P", owning_unit=UNIT, originator=UNIT)
        await self.analytics.load_events([EventRecord(
            event_id=f"{case.id}-{classification}", edge_id=f"e-{case.id}", edge_type="TRANSACTED",
            source_id="a", target_id="b", occurred_at=WHEN, investigation_scope=case.id, handling=handling)])  # fmt: skip

    def holders(self, case: Investigation, who: Principal | None = None) -> Any:
        self.principal = who or ANALYST
        return TestClient(app).get(f"/v1/investigations/{case.id}/events/holders")


@pytest.fixture
def world() -> Iterator[World]:
    w = World()
    app.dependency_overrides.update({
        get_principal: lambda: w.principal, get_investigations: lambda: w.cases, get_audit: lambda: _Audit(),
        get_datasets: lambda: w.datasets, get_analytics: lambda: w.analytics, get_working_set: lambda: _WorkingSet(),
    })  # fmt: skip
    yield w
    app.dependency_overrides.clear()


async def test_a_case_with_its_own_events_says_so_and_names_no_other(world: World) -> None:
    world.grant(LEDGER), world.grant(REVIEW)
    world.reads(LEDGER, "ledger-ds"), world.reads(REVIEW, "ledger-ds")
    await world.event(LEDGER)
    body = world.holders(LEDGER).json()
    assert body == {"has_events": True, "held_by": []}


async def test_a_reading_case_is_told_which_case_holds_its_datasets_events(world: World) -> None:
    world.grant(LEDGER), world.grant(REVIEW)
    world.reads(LEDGER, "ledger-ds"), world.reads(REVIEW, "ledger-ds")
    await world.event(LEDGER)
    response = world.holders(REVIEW)
    assert response.status_code == 200, response.text
    assert response.json() == {"has_events": False,
                               "held_by": [{"investigation_id": "ledger", "name": "Ledger (demo)"}]}  # fmt: skip


async def test_a_case_the_reader_cannot_open_is_never_named(world: World) -> None:
    world.grant(REVIEW)
    world.reads(HIDDEN, "ledger-ds"), world.reads(REVIEW, "ledger-ds")
    await world.event(HIDDEN)
    response = world.holders(REVIEW)
    assert response.json() == {"has_events": False, "held_by": []}
    assert "Unshared" not in response.text and "hidden" not in response.text


async def test_an_event_the_reader_may_not_see_makes_no_holder(world: World) -> None:
    world.grant(LEDGER), world.grant(REVIEW)
    world.reads(LEDGER, "ledger-ds"), world.reads(REVIEW, "ledger-ds")
    await world.event(LEDGER, "SECRET")
    await world.event(REVIEW, "SECRET")
    assert world.holders(REVIEW).json() == {"has_events": False, "held_by": []}


async def test_a_case_reading_another_dataset_is_not_named(world: World) -> None:
    world.grant(OTHER), world.grant(REVIEW)
    world.reads(OTHER, "other-ds"), world.reads(REVIEW, "ledger-ds")
    await world.event(OTHER)
    assert world.holders(REVIEW).json() == {"has_events": False, "held_by": []}


async def test_reading_needs_viewer_on_the_case_and_the_investigate_right(world: World) -> None:
    world.grant(LEDGER), world.reads(LEDGER, "ledger-ds")
    await world.event(LEDGER)
    assert world.holders(REVIEW).status_code == 404, "no level on the case asked about"
    world.grant(LEDGER, READER)
    assert world.holders(LEDGER, READER).status_code == 403, "a Reports Viewer has no investigate right"


async def test_a_branch_counts_the_events_it_inherits_from_its_parent(world: World) -> None:
    world.grant(LEDGER), world.grant(BRANCH)
    world.reads(LEDGER, "ledger-ds"), world.reads(BRANCH, "ledger-ds")
    await world.event(LEDGER)
    assert world.holders(BRANCH).json() == {"has_events": True, "held_by": []}
