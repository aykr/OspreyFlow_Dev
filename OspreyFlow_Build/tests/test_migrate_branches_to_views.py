"""`scripts.migrate_branches_to_views` (ADR-144 decision 6, Amendment 1 decision 3; L3.2 part D; the
owner's rulings of 8 November 2026 on Q1-Q4), its plan run against an in-memory deployment.

What a mistake would do, and the case that catches it:

- the dry run writing anything: `test_the_dry_run_writes_nothing_and_says_what_the_real_run_does`,
  red with the real writer handed to the dry run
  (`test_the_dry_run_check_fails_with_the_real_writer_handed_in`);
- a case made from another left behind, or a view missing its nodes, window, threshold or origin:
  `test_the_real_run_leaves_every_seeded_case_with_its_views_and_none_made_from_another`;
- something in a retired case's own layer lost or left there:
  `test_everything_in_a_retired_cases_own_layer_moves_into_the_originals_tagged`, red with the
  move planted out (`test_the_move_check_fails_with_the_move_planted_out`);
- a case opened from an alert since L3.1 moved into the alert's case (Q3):
  `test_a_case_opened_from_an_alert_since_l3_1_stays_a_case`, red with it classed as a copy
  (`test_the_q3_check_fails_with_every_case_converted`);
- a view shared with people its maker never chose, or its other members not named (Q4):
  `test_a_view_is_private_to_its_maker_and_the_others_are_named`;
- a case it cannot place guessed at: `test_what_cannot_be_placed_is_reported_and_left_as_it_was`;
- a second run changing anything: `test_a_second_run_changes_nothing`.

The same on real Postgres, at `_main`, is in `test_migrate_branches_to_views_store.py`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from scripts import migrate_branches_to_views as script
from scripts.migrate_branches_to_views import (
    LEGACY_LAYER_MAKER,
    CaseRecord,
    DryRun,
    Report,
    migrate,
)

from schemas.case_views import CaseViewInput
from schemas.domain import Interval

WINDOW = Interval(
    valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 2, 1, tzinfo=UTC)
)


@dataclass
class World:
    """A deployment as the migration sees it."""

    cases: dict[str, CaseRecord] = field(default_factory=dict)
    #: layer id -> (its case, who made it)
    layers: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: case id -> the original's layer it reads (made since L3.1)
    links: dict[str, str] = field(default_factory=dict)
    #: element id -> its datasets, and its tag if moved
    elements: dict[str, list[str]] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    working: dict[str, list[str]] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    #: case id -> the accounts holding a level on it
    members: dict[str, set[str]] = field(default_factory=dict)
    views: list[dict[str, Any]] = field(default_factory=list)


class Reads:
    def __init__(self, world: World) -> None:
        self.w = world

    async def cases(self) -> list[CaseRecord]:
        return list(self.w.cases.values())

    async def own_layer(self, case_id: str) -> tuple[str, str] | None:
        for layer, (case, maker) in self.w.layers.items():
            if case == case_id:
                return layer, maker
        return None

    async def reads_layer(self, case_id: str) -> str | None:
        return self.w.links.get(case_id)

    async def case_of_layer(self, layer_id: str) -> str | None:
        held = self.w.layers.get(layer_id)
        return held[0] if held else None

    async def holds_a_level(self, person: str, unit: str, case_id: str) -> bool:
        return person in self.w.members.get(case_id, set())

    async def other_members(self, case_id: str, maker: str) -> list[str]:
        return sorted(self.w.members.get(case_id, set()) - {maker})

    async def node_ids(self, case_id: str) -> list[str]:
        return sorted(self.w.working.get(case_id, []))

    async def threshold(self, case_id: str) -> float | None:
        return self.w.thresholds.get(case_id)

    async def elements_in(self, layer_id: str) -> int:
        return sum(1 for d in self.w.elements.values() if layer_id in d)


class Writes:
    def __init__(self, world: World, writes: list[str]) -> None:
        self.w = world
        self.writes = writes

    async def save_view(self, case: CaseRecord, original: str, given: CaseViewInput) -> str:
        view_id = f"view-{len(self.w.views) + 1}"
        self.w.views.append(
            {"id": view_id, "case_id": original, "created_by": case.created_by, "shared": False,
             "node_ids": given.node_ids, "window": given.window, "threshold": given.threshold,
             "converted_from_case": case.id, "name": given.name}
        )  # fmt: skip
        self.writes.append(view_id)
        return view_id

    async def move_layer(self, from_layer: str, to_layer: str, tag: str) -> int:
        moved = 0
        for element, datasets in self.w.elements.items():
            if from_layer in datasets:
                held = [d for d in datasets if d != from_layer]
                self.w.elements[element] = held + ([to_layer] if to_layer not in held else [])
                self.w.tags[element] = tag
                moved += 1
        self.writes.append(f"move {from_layer}")
        return moved

    async def retire(self, case: CaseRecord) -> None:
        self.w.cases[case.id] = CaseRecord(
            id=case.id, name=case.name, created_by=case.created_by,
            owning_unit=case.owning_unit, made_from=None, removed=True,
        )  # fmt: skip
        self.w.links.pop(case.id, None)
        self.writes.append(f"retire {case.id}")

    async def drop_origin(self, case: CaseRecord) -> None:
        self.w.cases[case.id] = CaseRecord(
            id=case.id, name=case.name, created_by=case.created_by,
            owning_unit=case.owning_unit, made_from=None, removed=case.removed,
        )  # fmt: skip
        self.writes.append(f"drop {case.id}")


def _case(case_id: str, name: str, maker: str = "alice", made_from: str | None = None,
          **kw: Any) -> CaseRecord:  # fmt: skip
    return CaseRecord(id=case_id, name=name, created_by=maker, owning_unit="unit-1",
                      made_from=made_from, **kw)  # fmt: skip


def seeded() -> World:
    """Kestrel, Alice's, with its layer; and every kind of case made from another."""
    w = World()
    w.cases = {
        c.id: c
        for c in (
            _case("kestrel", "Kestrel"),
            # Made since L3.1 by copying: reads Kestrel's layer through the link.
            _case("copy-new", "Branch of Kestrel", made_from="kestrel", window=WINDOW),
            # Made before L3.1: the old migration gave it a layer of its own, holding two items.
            _case("copy-old", "Old branch", made_from="kestrel"),
            # Opened from an alert since L3.1 by Bob, who holds no level on Kestrel: stays a case.
            _case("jump-new", "From alert A14", maker="bob", made_from="kestrel"),
            # Made from the alert's case above before L3.1, by Bob: goes under that case.
            _case("copy-of-jump", "Bob's copy", maker="bob", made_from="jump-new"),
            # Cannot be placed: its maker, Carol, holds no level on Kestrel.
            _case("carols", "Carol's", maker="carol", made_from="kestrel"),
            # Cannot be placed: its original is removed.
            _case("gone", "Removed one", removed=True),
            _case("of-gone", "Of the removed one", made_from="gone"),
            # Cannot be placed: it reads no layer at all.
            _case("bare", "No layer", made_from="kestrel"),
        )
    }
    w.layers = {
        "layer-kestrel": ("kestrel", LEGACY_LAYER_MAKER),
        "layer-old": ("copy-old", LEGACY_LAYER_MAKER),
        "layer-jump": ("jump-new", "bob"),
        "layer-copy-of-jump": ("copy-of-jump", LEGACY_LAYER_MAKER),
        "layer-carols": ("carols", LEGACY_LAYER_MAKER),
        "layer-gone": ("gone", LEGACY_LAYER_MAKER),
        "layer-of-gone": ("of-gone", LEGACY_LAYER_MAKER),
    }
    w.links = {"copy-new": "layer-kestrel"}
    w.elements = {
        "mark-1": ["layer-old"], "link-1": ["layer-old"], "kestrels-own": ["layer-kestrel"],
        "bobs-mark": ["layer-copy-of-jump"], "loaded": ["src"], "carols-mark": ["layer-carols"],
    }  # fmt: skip
    w.working = {"copy-new": ["p1", "p2"], "copy-old": ["p3", "mark-1"], "copy-of-jump": ["p9"]}
    w.thresholds = {"copy-new": 0.8}
    w.members = {
        "kestrel": {"alice", "dave"},
        "copy-new": {"alice", "erin"},
        "copy-old": {"alice"},
        "jump-new": {"bob"},
        "copy-of-jump": {"bob"},
        "carols": {"carol"},
    }
    return w


async def _real(world: World) -> Report:
    report = Report()
    return await migrate(Reads(world), Writes(world, report.writes), report)


async def test_the_dry_run_writes_nothing_and_says_what_the_real_run_does() -> None:
    world = seeded()
    before = copy.deepcopy(world)
    dry = Report()
    await migrate(Reads(world), DryRun(Reads(world), dry.writes), dry)
    assert world == before
    real = await _real(seeded())
    assert len(dry.writes) == len(real.writes)
    assert [c.moved for c in dry.converted] == [c.moved for c in real.converted]
    assert dry.unplaced == real.unplaced and dry.kept_as_cases == real.kept_as_cases


async def test_the_dry_run_check_fails_with_the_real_writer_handed_in() -> None:
    world = seeded()
    before = copy.deepcopy(world)
    report = Report()
    await migrate(Reads(world), Writes(world, report.writes), report)  # the plant
    assert world != before


async def test_the_real_run_leaves_every_seeded_case_with_its_views_and_none_made_from_another(
) -> None:  # fmt: skip
    world = seeded()
    report = await _real(world)
    unplaced = {"carols", "of-gone", "bare"}
    left = {c.id for c in world.cases.values() if c.made_from is not None}
    assert left == unplaced
    by_origin = {v["converted_from_case"]: v for v in world.views}
    assert set(by_origin) == {"copy-new", "copy-old", "copy-of-jump"}
    assert by_origin["copy-new"]["case_id"] == "kestrel"
    assert by_origin["copy-new"]["node_ids"] == ["p1", "p2"]
    assert by_origin["copy-new"]["window"] == WINDOW
    assert by_origin["copy-new"]["threshold"] == 0.8
    assert by_origin["copy-new"]["name"] == "Branch of Kestrel"  # its name, the view's default
    assert by_origin["copy-old"]["case_id"] == "kestrel"
    assert by_origin["copy-of-jump"]["case_id"] == "jump-new"  # under the case that stays one
    for converted in ("copy-new", "copy-old", "copy-of-jump"):
        assert world.cases[converted].removed
    assert "copy-new" not in world.links
    assert len(report.converted) == 3


async def test_everything_in_a_retired_cases_own_layer_moves_into_the_originals_tagged() -> None:
    world = seeded()
    await _real(world)
    assert world.elements["mark-1"] == ["layer-kestrel"]
    assert world.elements["link-1"] == ["layer-kestrel"]
    assert world.tags["mark-1"] == world.tags["link-1"] == "Old branch"
    assert world.elements["bobs-mark"] == ["layer-jump"]
    assert world.tags["bobs-mark"] == "Bob's copy"
    assert world.elements["kestrels-own"] == ["layer-kestrel"] and "kestrels-own" not in world.tags
    assert world.elements["loaded"] == ["src"]
    # Nothing of an unplaced case moves.
    assert world.elements["carols-mark"] == ["layer-carols"] and "carols-mark" not in world.tags


async def test_the_move_check_fails_with_the_move_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def kept(self: Writes, from_layer: str, to_layer: str, tag: str) -> int:
        return 0

    monkeypatch.setattr(Writes, "move_layer", kept)
    world = seeded()
    await _real(world)
    assert world.elements["mark-1"] == ["layer-old"]


async def test_a_case_opened_from_an_alert_since_l3_1_stays_a_case() -> None:
    world = seeded()
    report = await _real(world)
    jump = world.cases["jump-new"]
    assert jump.made_from is None and not jump.removed
    assert not [v for v in world.views if v["converted_from_case"] == "jump-new"]
    assert report.kept_as_cases == ["From alert A14 (jump-new)"]


async def test_the_q3_check_fails_with_every_case_converted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planted: the maker of a layer is never read, so a case opened from an alert since L3.1 is
    taken for one made before L3.1. Bob holds a level on Kestrel here, so it is converted."""
    monkeypatch.setattr(script, "LEGACY_LAYER_MAKER", "bob")
    world = seeded()
    world.members["kestrel"].add("bob")
    await _real(world)
    assert world.cases["jump-new"].removed


async def test_a_view_is_private_to_its_maker_and_the_others_are_named() -> None:
    world = seeded()
    report = await _real(world)
    assert all(not v["shared"] for v in world.views)
    by_case = {c.case: c for c in report.converted}
    assert by_case["Branch of Kestrel (copy-new)"].other_members == ["erin"]
    assert by_case["Old branch (copy-old)"].other_members == []
    assert {v["created_by"] for v in world.views if v["case_id"] == "kestrel"} == {"alice"}


async def test_what_cannot_be_placed_is_reported_and_left_as_it_was() -> None:
    world = seeded()
    report = await _real(world)
    reasons = dict(report.unplaced)
    assert "holds no level" in reasons["Carol's (carols)"]
    assert "missing or removed" in reasons["Of the removed one (of-gone)"]
    assert "reads no layer" in reasons["No layer (bare)"]
    assert world.cases["carols"].made_from == "kestrel" and not world.cases["carols"].removed


async def test_a_second_run_changes_nothing() -> None:
    world = seeded()
    await _real(world)
    after_first = copy.deepcopy(world)
    second = await _real(world)
    assert world == after_first
    assert second.converted == [] and second.kept_as_cases == []
    assert {u for u, _ in second.unplaced} == {u for u, _ in (await _real(seeded())).unplaced}
