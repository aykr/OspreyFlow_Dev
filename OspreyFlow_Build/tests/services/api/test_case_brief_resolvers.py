"""The four title resolvers of the case brief — ADR-128 decision 3, rule 3. Each answers a reader with
the title of an attachment only when that kind's own store and own rule let that reader read it, and
with None otherwise: not-found and not-allowed are one answer.

The stand-ins refuse what the real stores refuse (`CLAUDE.md` rule 15): a pattern of another owner is
`PatternNotFoundError`, a judgement of another unit is `JudgementNotFoundError`, a case with no level
is `InvestigationNotFoundError`, a node the principal cannot see is None from the graph. The one real
rule exercised un-faked is `judgement_visible_to`, ADR-046's hide-in-full, which the assessment
resolver must apply and which a resolver that only checked ownership would miss.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.assessments import JudgementNotFoundError
from services.api.case_brief_resolvers import title_resolvers
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    InvestigationNotFoundError,
)
from services.api.pattern_store import PatternNotFoundError

from schemas.domain import Judgement, Principal

CASE = "case-1"
ME = Principal(id="me", clearance="OFFICIAL", org_unit="unit-1")
OTHER = Principal(id="other", clearance="OFFICIAL", org_unit="unit-1")
OTHER_UNIT = Principal(id="third", clearance="OFFICIAL", org_unit="unit-2")
WHEN = datetime(2026, 10, 26, tzinfo=UTC)


class _Trends:
    def __init__(self) -> None:
        self.rows = {(CASE, "t1"): SimpleNamespace(title="Throw-overs by week")}

    async def get(self, case_id: str, trend_id: str) -> Any:
        return self.rows.get((case_id, trend_id))


class _Patterns:
    def __init__(self) -> None:
        self.owner = {"p1": ("me", "Organised-crime links on the wing")}

    async def get_authorized(self, pattern_id: str, principal: Principal) -> Any:
        found = self.owner.get(pattern_id)
        if found is None or found[0] != principal.id:
            raise PatternNotFoundError(pattern_id)
        return SimpleNamespace(name=found[1])


def _judgement(judgement_id: str, case: str, statement: str, supporting: list[str]) -> Judgement:
    return Judgement(
        id=judgement_id,
        investigation_id=case,
        statement=statement,
        probability_band="likely",
        supporting=supporting,
        author="me",
        created_at=WHEN,
    )


class _Judgements:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, Judgement]] = {}

    def add(self, unit: str, judgement: Judgement) -> None:
        self.rows[judgement.id] = (unit, judgement)

    async def get_authorized(self, judgement_id: str, principal: Principal) -> Judgement:
        found = self.rows.get(judgement_id)
        if found is None or found[0] != principal.org_unit:
            raise JudgementNotFoundError(judgement_id)
        return found[1]


class _Graph:
    """`get_node` answers a node only to a principal who may see it (a stand-in for the filtered
    adapter): `visible[principal.id]` is the set of node ids that principal sees."""

    def __init__(self, visible: dict[str, set[str]]) -> None:
        self.visible = visible

    async def get_node(
        self, node_id: str, principal: Principal, *, include_superseded: bool = False
    ) -> Any:
        return object() if node_id in self.visible.get(principal.id, set()) else None


class _Investigations:
    def __init__(self) -> None:
        self.levels: dict[tuple[str, str], AccessLevel] = {}
        self.names: dict[str, str] = {}

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Any:
        held = self.levels.get((investigation_id, principal.id))
        if held is None:
            raise InvestigationNotFoundError(investigation_id)
        if held.rank < need.rank:
            raise InsufficientAccessError(need.value)
        return SimpleNamespace(name=self.names[investigation_id])


@pytest.fixture
def world() -> SimpleNamespace:
    judgements = _Judgements()
    judgements.add("unit-1", _judgement("j-open", CASE, "The wing's organiser is X.", ["n1"]))
    judgements.add(
        "unit-1", _judgement("j-hidden", CASE, "Rests on a node you cannot see.", ["n1", "secret"])
    )
    judgements.add("unit-1", _judgement("j-elsewhere", "case-2", "Another case's.", ["n1"]))
    investigations = _Investigations()
    investigations.levels = {
        ("tab-1", "me"): AccessLevel.VIEWER,
        ("tab-2", "me"): AccessLevel.AUTHOR,
        ("tab-3", "other"): AccessLevel.AUTHOR,
    }
    investigations.names = {"tab-1": "Yards", "tab-2": "", "tab-3": "Not mine"}
    graph = _Graph({"me": {"n1"}, "other": {"n1", "secret"}})
    return SimpleNamespace(
        resolvers=title_resolvers(
            trends=_Trends(),  # type: ignore[arg-type]
            patterns=_Patterns(),  # type: ignore[arg-type]
            judgements=judgements,  # type: ignore[arg-type]
            graph=graph,  # type: ignore[arg-type]
            investigations=investigations,  # type: ignore[arg-type]
        ),
        judgements=judgements,
    )


def test_there_is_one_resolver_for_each_kind_the_brief_can_hold(world: SimpleNamespace) -> None:
    assert set(world.resolvers) == {"trend", "pattern", "assessment", "view"}


# --- trend ----------------------------------------------------------------------------------


async def test_a_trend_of_this_case_is_titled(world: SimpleNamespace) -> None:
    assert await world.resolvers["trend"](CASE, "t1", ME) == "Throw-overs by week"


async def test_a_trend_of_another_case_or_a_missing_one_is_none(world: SimpleNamespace) -> None:
    assert await world.resolvers["trend"]("case-2", "t1", ME) is None
    assert await world.resolvers["trend"](CASE, "nope", ME) is None


# --- pattern --------------------------------------------------------------------------------


async def test_a_pattern_is_titled_only_to_its_owner(world: SimpleNamespace) -> None:
    assert await world.resolvers["pattern"](CASE, "p1", ME) == "Organised-crime links on the wing"
    assert await world.resolvers["pattern"](CASE, "p1", OTHER) is None
    assert await world.resolvers["pattern"](CASE, "nope", ME) is None


# --- assessment -----------------------------------------------------------------------------


async def test_an_assessment_of_this_case_resting_on_what_the_reader_sees_is_titled(
    world: SimpleNamespace,
) -> None:
    assert await world.resolvers["assessment"](CASE, "j-open", ME) == "The wing's organiser is X."


async def test_an_assessment_resting_on_a_node_the_reader_cannot_see_is_none_but_not_for_one_who_can(
    world: SimpleNamespace,
) -> None:
    """ADR-046: hidden in full from a reader whose access does not cover a supporting reference. A
    resolver that checked only that the judgement exists and is the unit's would show this title."""
    assert await world.resolvers["assessment"](CASE, "j-hidden", ME) is None
    assert (
        await world.resolvers["assessment"](CASE, "j-hidden", OTHER)
        == "Rests on a node you cannot see."
    )


async def test_an_assessment_of_another_case_unit_or_none_at_all_is_none(
    world: SimpleNamespace,
) -> None:
    assert await world.resolvers["assessment"](CASE, "j-elsewhere", ME) is None
    assert await world.resolvers["assessment"](CASE, "j-open", OTHER_UNIT) is None
    assert await world.resolvers["assessment"](CASE, "nope", ME) is None


async def test_a_long_statement_is_a_shortened_one_line_title_and_the_statement_is_not_changed(
    world: SimpleNamespace,
) -> None:
    long = "First line of a long assessment.\nSecond line. " + "word " * 100
    world.judgements.add("unit-1", _judgement("j-long", CASE, long, ["n1"]))
    title = await world.resolvers["assessment"](CASE, "j-long", ME)
    assert title is not None
    assert "\n" not in title and len(title) <= 120 and title.endswith("…")
    assert title.startswith("First line of a long assessment.")
    assert world.judgements.rows["j-long"][1].statement == long


# --- view -----------------------------------------------------------------------------------


async def test_a_view_is_titled_by_its_case_name_to_anyone_who_may_open_it(
    world: SimpleNamespace,
) -> None:
    assert await world.resolvers["view"](CASE, "tab-1", ME) == "Yards"
    assert await world.resolvers["view"](CASE, "tab-2", ME) == "Untitled view"


async def test_a_view_the_reader_holds_no_level_on_or_that_does_not_exist_is_none(
    world: SimpleNamespace,
) -> None:
    assert await world.resolvers["view"](CASE, "tab-3", ME) is None
    assert await world.resolvers["view"](CASE, "nope", ME) is None
