"""The grading scheme's change command (`spec/06_DECISIONS.md` ADR-143 decision 11 and C13; ADR-145
O1; L3.7): an old-to-new mapping, a dry run first that writes nothing, every item keeping its
original grade and scheme beside the new one, audited, and refused whole, before anything is
written, for a mapping that does not cover the old scheme, an item in another scheme, or a
registered item that cannot be read back (rule 2).

The items are drawn through the board routes themselves (`test_boards`'s world: the Conduit's
stamping graph over `BoardGraph`, which models the adapter's refusals), and changed through
`BoardGradedItems`, the port the operator command uses over the board registry and the graph. Each
test was shown red by a plant at its call site (`process/lanes/case-b/L3.7_RED_RECORD.md`).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from services.api.board_store import BoardItem
from services.api.grading import (
    BoardGradedItems,
    GradedItem,
    GradingIncomplete,
    GradingRefused,
    MappingRefused,
    change,
    operator_reader,
    parse_mapping,
)

from collections.abc import Iterator
from contextlib import contextmanager

from services.api.app import app
from services.api.config import GradingSettings

from schemas.domain import Grading, Node, Principal

from .test_boards import (  # noqa: F401  (a fixture)
    ONTOLOGY,
    SCHEME,
    K,
    _as,
    _board,
    _item,
    _link,
    world,
)

FIVE_TO_THREE = """
from: 5x5x5
to: 3x5x2
source: {A: A, B: A, C: B, D: C, E: C}
intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
handling: {"1": P, "2": P, "3": P, "4": C, "5": C}
"""

THREE_TO_FIVE = """
from: 3x5x2
to: 5x5x5
source: {A: A, B: C, C: E}
intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
handling: {P: "1", C: "4"}
"""


def _registered(world: SimpleNamespace) -> Any:
    async def registered() -> list[BoardItem]:
        return list(world.items.items.values())

    return registered


def _port(
    world: SimpleNamespace, reader: Principal | None = None, ontology: Any = None
) -> BoardGradedItems:
    return BoardGradedItems(
        world.graph,
        _registered(world),
        reader or operator_reader(SCHEME, org_unit="unit-1"),
        written_by="ops-1",
        ontology=ontology or ONTOLOGY,
    )


@contextmanager
def _deployment_grading_in(scheme: str) -> Iterator[None]:
    """Draw while the deployment grades in `scheme` (the board routes refuse any other)."""
    held = getattr(app.state, "grading", None)
    app.state.grading = GradingSettings(scheme=scheme)  # type: ignore[arg-type]
    try:
        yield
    finally:
        if held is None:
            del app.state.grading
        else:
            app.state.grading = held


def _drawn(world: SimpleNamespace, **grade: str) -> tuple[str, str]:
    """A board of case K holding a drawn person, linked to the loaded Mercer: their element ids."""
    board = _board(start="selection", node_ids=["p-loaded"])
    over = {"grading": grade} if grade else {}
    person = _item(board, **over)["element_id"]
    linked = _link(board, person, "p-loaded", **over)
    assert linked.status_code == 201, linked.text
    return person, linked.json()["element_id"]


def _grade_of(world: SimpleNamespace, element_id: str) -> tuple[Grading, Grading | None]:
    found: Node | Any = world.graph._graph_nodes.get(element_id)
    if found is None:
        found = next(e for e in world.graph.edges() if e.id == element_id)
    drawn = found.provenance.drawn
    assert drawn is not None
    return drawn.grading, drawn.original_grading


def _writes(world: SimpleNamespace) -> int:
    return len(world.graph.node_writes) + len(world.graph.edge_writes)


class _Audit:
    """Each audit record as it was written (the plan is one object, changed as the run goes)."""

    def __init__(self) -> None:
        self.plans: list[dict[str, Any]] = []

    async def __call__(self, plan: Any) -> None:
        self.plans.append(plan.record())

    def stages(self) -> list[tuple[str, int]]:
        return [(r["stage"], r["written"]) for r in self.plans]


# --- the dry run writes nothing ---------------------------------------------------------------


async def test_the_dry_run_writes_nothing_and_counts_each_mapping_line(
    world: SimpleNamespace,
) -> None:
    person, link = _drawn(world)  # graded B 2 1 (test_boards.GRADE)
    before = _writes(world)
    audit = _Audit()
    plan = await change(
        _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=True, audit=audit
    )
    assert _writes(world) == before
    assert audit.plans == []
    assert _grade_of(world, person) == (Grading(source="B", intelligence="2", handling="1"), None)
    assert plan.to_change == 2 and plan.already_changed == 0 and not plan.written
    assert plan.moves[("source", "B", "A")] == 2
    assert plan.moves[("intelligence", "2", "2")] == 2
    assert plan.moves[("handling", "1", "P")] == 2
    assert "source B → A: 2 item(s)" in plan.lines()
    assert _grade_of(world, link)[1] is None


# --- every item keeps its original grade and scheme -------------------------------------------


async def test_every_item_keeps_its_original_grade_and_scheme_through_two_changes(
    world: SimpleNamespace,
) -> None:
    person, link = _drawn(world)
    audit = _Audit()
    first = await change(
        _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False, audit=audit
    )
    assert first.written == 2
    original = Grading(source="B", intelligence="2", handling="1")
    for element in (person, link):
        assert _grade_of(world, element) == (
            Grading(scheme="3x5x2", source="A", intelligence="2", handling="P"),
            original,
        )
    # Changed back: the original is still the one the item was drawn with, never the middle one.
    await change(
        _port(world), parse_mapping(THREE_TO_FIVE), current="3x5x2", dry_run=False, audit=audit
    )
    for element in (person, link):
        assert _grade_of(world, element) == (
            Grading(scheme="5x5x5", source="A", intelligence="2", handling="1"),
            original,
        )
    assert audit.stages() == [("started", 0), ("finished", 2), ("started", 0), ("finished", 2)]


async def test_the_change_keeps_the_items_other_drawn_fields_and_its_marking(
    world: SimpleNamespace,
) -> None:
    person, _ = _drawn(world)
    before = world.graph.node(person)
    await change(
        _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False, audit=_Audit()
    )
    after = world.graph.node(person)
    assert after.handling == before.handling
    assert after.datasets == before.datasets
    assert after.properties == before.properties
    assert before.provenance.drawn is not None and after.provenance.drawn is not None
    kept = {"item_id", "asserted_by", "board_id", "case_id", "label", "source_note"}
    assert {k: getattr(after.provenance.drawn, k) for k in kept} == {
        k: getattr(before.provenance.drawn, k) for k in kept
    }


# --- refused whole, before anything is written ------------------------------------------------


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (FIVE_TO_THREE.replace(", E: C}", "}"), "source E"),  # a grade of the old scheme unmapped
        (FIVE_TO_THREE.replace("E: C}", "E: C, F: C}"), "source F"),  # not a grade of the old
        (FIVE_TO_THREE.replace('"5": C}', '"5": X}'), "handling X"),  # not a grade of the new
        (FIVE_TO_THREE.replace("to: 3x5x2", "to: 4x4"), "4x4"),
        (FIVE_TO_THREE.replace("to: 3x5x2", "to: 5x5x5"), "the same scheme"),
        ("from: 5x5x5\nto: 3x5x2\n", "source"),
        ("[]", "mapping"),
    ],
)
def test_a_mapping_that_does_not_cover_the_old_scheme_is_refused_in_words(
    text: str, said: str
) -> None:
    with pytest.raises(MappingRefused) as refused:
        parse_mapping(text)
    assert said in str(refused.value)


async def test_a_mapping_from_another_scheme_than_the_deployments_is_refused(
    world: SimpleNamespace,
) -> None:
    # Every item in the mapping's own old scheme, so nothing but the deployment's setting can
    # refuse it: an item in another scheme would be refused by its own check, for its own reason.
    board = _board(start="blank")
    with _deployment_grading_in("3x5x2"):
        _item(board, grading={"scheme": "3x5x2", "source": "A", "intelligence": "1",
                              "handling": "P"})  # fmt: skip
    before = _writes(world)
    with pytest.raises(GradingRefused) as refused:
        await change(
            _port(world), parse_mapping(THREE_TO_FIVE), current="5x5x5", dry_run=False,
            audit=_Audit(),
        )  # fmt: skip
    assert "this deployment grades in 5x5x5" in str(refused.value)
    assert _writes(world) == before


async def test_an_item_in_another_scheme_refuses_the_whole_change_before_any_write(
    world: SimpleNamespace,
) -> None:
    first, _ = _drawn(world)  # in 5x5x5, drawn first, so a loop writing as it goes reaches it
    board = _board(start="blank")
    with _deployment_grading_in("3x5x2"):  # drawn before a change, say, then the setting put back
        _item(board, grading={"scheme": "3x5x2", "source": "A", "intelligence": "1",
                              "handling": "P"})  # fmt: skip
    before = _writes(world)
    audit = _Audit()
    with pytest.raises(GradingRefused) as refused:
        await change(
            _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False,
            audit=audit,
        )  # fmt: skip
    assert "1 item(s) graded in 3x5x2" in str(refused.value)
    assert _writes(world) == before and audit.plans == []
    assert _grade_of(world, first)[1] is None


async def test_a_registered_item_that_cannot_be_read_back_refuses_the_whole_change(
    world: SimpleNamespace,
) -> None:
    """The board registry names an item the graph no longer gives back to the operator's reader
    (its element gone from the store under it): never skipped silently (rule 2), and nothing is
    written, though the other items could be."""
    person, link = _drawn(world)
    del world.graph._graph_nodes[person]
    before = _writes(world)
    with pytest.raises(GradingRefused) as refused:
        await change(
            _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False,
            audit=_Audit(),
        )  # fmt: skip
    assert "drawn item(s) could not be read back" in str(refused.value)
    assert _writes(world) == before
    assert _grade_of(world, link)[1] is None


async def test_an_item_whose_rewrite_would_be_refused_refuses_the_whole_change_first(
    world: SimpleNamespace,
) -> None:
    """Every check the rewrite's own write would make is made for every item first: here the
    link's type is no longer in the ontology in force (a proposal withdrawn after the link was
    drawn). The node, drawn first, is not written, and a dry run says so too."""
    person, _ = _drawn(world)
    without = ONTOLOGY.model_copy(
        update={"edge_types": [t for t in ONTOLOGY.edge_types if t.name != "ASSOCIATE_OF"]}
    )
    before = _writes(world)
    for dry_run in (True, False):
        audit = _Audit()
        with pytest.raises(GradingRefused) as refused:
            await change(
                _port(world, ontology=without), parse_mapping(FIVE_TO_THREE), current="5x5x5",
                dry_run=dry_run, audit=audit,
            )  # fmt: skip
        assert "1 drawn item(s) could not be written back" in str(refused.value)
        assert "ASSOCIATE_OF is not a type in the ontology in force" in str(refused.value)
        assert _writes(world) == before and audit.plans == []
    assert _grade_of(world, person)[1] is None


async def test_the_plan_is_said_and_audited_before_the_first_write(
    world: SimpleNamespace,
) -> None:
    """Decision 11: it reports how many items each mapping line moves, then rewrites; C13: never
    a changed grade with no record of the change."""
    from scripts.grading_change import run

    _drawn(world)
    port = _port(world)
    real = port.rewrite
    said: list[str] = []
    audit = _Audit()
    seen_at_first_write: list[tuple[list[str], list[tuple[str, int]]]] = []

    async def rewrite(*args: Any, **kwargs: Any) -> None:
        if not seen_at_first_write:
            seen_at_first_write.append((list(said), audit.stages()))
        await real(*args, **kwargs)

    port.rewrite = rewrite  # type: ignore[method-assign]
    code = await run(
        to="3x5x2", mapping_text=FIVE_TO_THREE, current="5x5x5", dry_run=False, items=port,
        audit=audit, say=said.append,
    )  # fmt: skip
    assert code == 0
    lines, stages = seen_at_first_write[0]
    assert "source B → A: 2 item(s)" in lines and "5x5x5 to 3x5x2: 2 item(s) to change." in lines
    assert stages == [("started", 0)]
    assert audit.stages() == [("started", 0), ("finished", 2)]


async def test_a_withdrawn_item_keeps_the_grade_it_was_drawn_with(world: SimpleNamespace) -> None:
    board = _board(start="blank")
    made = _item(board)
    withdrawn = _as("alice").post(f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    element = made["element_id"]
    plan = await change(
        _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False, audit=_Audit()
    )
    assert plan.to_change == 0
    assert _grade_of(world, element) == (Grading(source="B", intelligence="2", handling="1"), None)


# --- a stop part way, and the run again that finishes it ---------------------------------------


async def test_a_change_stopped_part_way_finishes_when_run_again(world: SimpleNamespace) -> None:
    person, link = _drawn(world)
    port = _port(world)
    real = port.rewrite
    calls = 0

    async def fails_second(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("the store went away")
        await real(*args, **kwargs)

    port.rewrite = fails_second  # type: ignore[method-assign]
    audit = _Audit()
    with pytest.raises(GradingIncomplete) as stopped:
        await change(
            port, parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False, audit=audit
        )
    assert stopped.value.done == 1 and stopped.value.total == 2
    assert audit.stages() == [("started", 0), ("stopped", 1)]
    again = await change(
        _port(world), parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False, audit=audit
    )
    assert again.already_changed == 1 and again.written == 1
    assert audit.stages()[2:] == [("started", 0), ("finished", 1)]
    original = Grading(source="B", intelligence="2", handling="1")
    assert _grade_of(world, person)[1] == original and _grade_of(world, link)[1] == original


# --- the operator command ---------------------------------------------------------------------


async def test_the_command_says_each_mapping_lines_count_and_a_dry_run_writes_nothing(
    world: SimpleNamespace,
) -> None:
    from scripts.grading_change import run

    _drawn(world)
    before = _writes(world)
    said: list[str] = []
    audit = _Audit()
    code = await run(
        to="3x5x2", mapping_text=FIVE_TO_THREE, current="5x5x5", dry_run=True,
        items=_port(world), audit=audit, say=said.append,
    )  # fmt: skip
    assert code == 0 and _writes(world) == before and audit.plans == []
    assert "5x5x5 to 3x5x2: 2 item(s) to change." in said
    assert "source B → A: 2 item(s)" in said and "A dry run: nothing was written." in said
    code = await run(
        to="3x5x2", mapping_text=FIVE_TO_THREE, current="5x5x5", dry_run=False,
        items=_port(world), audit=audit, say=said.append,
    )  # fmt: skip
    assert code == 0 and audit.stages() == [("started", 0), ("finished", 2)]
    assert any("set grading.scheme: 3x5x2 in osprey.yaml" in line for line in said)


@pytest.mark.parametrize(
    ("to", "text", "current", "said"),
    [
        ("5x5x5", FIVE_TO_THREE, "5x5x5", "--to is 5x5x5, but the mapping is to 3x5x2"),
        ("3x5x2", FIVE_TO_THREE.replace(", E: C}", "}"), "5x5x5", "source E of 5x5x5"),
        ("3x5x2", FIVE_TO_THREE, "3x5x2", "this deployment grades in 3x5x2"),
    ],
)
async def test_the_command_refuses_with_exit_1_and_writes_nothing(
    world: SimpleNamespace, to: str, text: str, current: str, said: str
) -> None:
    from scripts.grading_change import run

    _drawn(world)
    before = _writes(world)
    lines: list[str] = []
    code = await run(
        to=to, mapping_text=text, current=current, dry_run=False, items=_port(world),
        audit=_Audit(), say=lines.append,
    )  # fmt: skip
    assert code == 1 and _writes(world) == before
    assert any(said in line for line in lines), lines


def test_the_command_without_store_settings_refuses_before_opening_any(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from scripts import grading_change

    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(FIVE_TO_THREE, encoding="utf-8")
    for name in ("ARCADEDB_HOST", "ARCADEDB_HTTP_PORT", "OSPREY_GRADING_SCHEME"):
        monkeypatch.delenv(name, raising=False)

    def no_store(*_: Any, **__: Any) -> Any:
        raise AssertionError("a store was opened")

    monkeypatch.setattr("asyncpg.create_pool", no_store)
    argv = ["--to", "3x5x2", "--mapping", str(mapping), "--changed-by", "ops-1", "--dry-run"]
    assert grading_change.main(argv) == 64
    monkeypatch.setenv("ARCADEDB_HOST", "nowhere")
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "4x4")  # an unknown setting stops it too
    assert grading_change.main(argv) == 64


async def test_a_body_read_with_its_board_withheld_is_never_written_back(
    world: SimpleNamespace,
) -> None:
    """Defence beside `sources_in_full`: an item read as a reader is shown it (its board emptied
    for anyone but its author) is refused at the write, not stored without its board."""
    person, _ = _drawn(world)
    shown = (await world.graph.get_nodes([person], Principal(id="carol", clearance="SECRET",
                                                             org_unit="unit-1")))[0]  # fmt: skip
    assert shown.provenance.drawn is not None and shown.provenance.drawn.board_id == ""
    before = _writes(world)
    with pytest.raises(GradingRefused, match="withheld"):
        await _port(world).rewrite(
            GradedItem(shown, shown.provenance.drawn.grading, None),
            Grading(scheme="3x5x2", source="A", intelligence="2", handling="P"),
            shown.provenance.drawn.grading,
        )
    assert _writes(world) == before
