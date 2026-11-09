"""The grading scheme's change (`spec/06_DECISIONS.md` ADR-143 decision 11 and Amendment 6; the owner's
ruling C13; ADR-145 O1; L3.7): an old-to-new mapping; a dry run first, which writes nothing and
gives the token the change needs for that mapping on that state; every item keeping its original
grade and scheme beside the new one; the grade alone changed in place; audited before and after;
refused whole, before anything is written, naming the items, for a mapping that does not cover the
old scheme, an item in a third scheme, or a registered item that cannot be read back (rule 2).

The items are drawn through the board routes themselves (`test_boards`'s world: the Conduit's
stamping graph over `BoardGraph`, whose `regrade_drawn` refuses what the adapter's does), and
changed through `BoardGradedItems`, the port the operator command uses. The store's own
`regrade_drawn` is proved in the graph port's conformance suite, and the whole command against
ArcadeDB in `test_grading_change_live.py`. Each test was shown red by a plant at its call site
(`process/lanes/case-b/L3.7_RED_RECORD.md`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.app import app
from services.api.board_store import BoardItem
from services.api.config import GradingSettings
from services.api.grading import (
    BoardGradedItems,
    GradingIncomplete,
    GradingRefused,
    MappingRefused,
    built_in_schemes,
    change,
    operator_reader,
    parse_mapping,
)

from schemas.domain import Grading, GradingSchemeAnswer, Node, Principal

from .test_boards import (  # noqa: F401  (a fixture)
    SCHEME,
    K,
    _as,
    _board,
    _item,
    _link,
    world,
)

FIVE = GradingSchemeAnswer.of("5x5x5")
THREE = GradingSchemeAnswer.of("3x5x2")
#: A scheme file's scheme (Amendment 6).
FORCE = GradingSchemeAnswer(
    scheme="force-4x3", source=["W", "X", "Y", "Z"], intelligence=["1", "2", "3"], handling=["H"]
)
SCHEMES = {**built_in_schemes(), FORCE.scheme: FORCE}

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

FIVE_TO_FORCE = """
from: 5x5x5
to: force-4x3
source: {A: W, B: W, C: X, D: Y, E: Z}
intelligence: {"1": "1", "2": "1", "3": "2", "4": "3", "5": "3"}
handling: {"1": H, "2": H, "3": H, "4": H, "5": H}
"""

TARGETS = {"3x5x2": THREE, "5x5x5": FIVE, "force-4x3": FORCE}


def _registered(world: SimpleNamespace) -> Any:
    async def registered() -> list[BoardItem]:
        return list(world.items.items.values())

    return registered


def _port(world: SimpleNamespace, reader: Principal | None = None) -> BoardGradedItems:
    return BoardGradedItems(
        world.graph, _registered(world), reader or operator_reader(SCHEME, org_unit="unit-1")
    )


@contextmanager
def _deployment_grading_in(scheme: GradingSchemeAnswer) -> Iterator[None]:
    """Draw while the deployment grades in `scheme` (the board routes refuse any other)."""
    held = getattr(app.state, "grading", None)
    app.state.grading = GradingSettings(grades=scheme)
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


def _element(world: SimpleNamespace, element_id: str) -> Any:
    found: Node | Any = world.graph._graph_nodes.get(element_id)
    return found if found is not None else next(e for e in world.graph.edges() if e.id == element_id)


def _grade_of(world: SimpleNamespace, element_id: str) -> tuple[Grading, Grading | None]:
    drawn = _element(world, element_id).provenance.drawn
    assert drawn is not None
    return drawn.grading, drawn.original_grading


def _writes(world: SimpleNamespace) -> int:
    return len(world.graph.node_writes) + len(world.graph.edge_writes) + len(world.graph.regrades)


class _Audit:
    """Each audit record as it was written (the plan is one object, changed as the run goes)."""

    def __init__(self) -> None:
        self.plans: list[dict[str, Any]] = []

    async def __call__(self, plan: Any) -> None:
        self.plans.append(plan.record())

    def stages(self) -> list[tuple[str, int]]:
        return [(r["stage"], r["written"]) for r in self.plans]


async def _dry(
    world: SimpleNamespace, text: str, current: GradingSchemeAnswer = FIVE, port: Any = None
) -> Any:
    mapping = parse_mapping(text, SCHEMES)
    return await change(
        port or _port(world), mapping, current=current, target=TARGETS[mapping.to_scheme],
        dry_run=True, audit=_Audit(),
    )  # fmt: skip


async def _change(
    world: SimpleNamespace,
    text: str,
    current: GradingSchemeAnswer = FIVE,
    *,
    audit: _Audit | None = None,
    port: Any = None,
) -> Any:
    """The dry run, then the change with its token, as the operator runs them."""
    mapping = parse_mapping(text, SCHEMES)
    token = (await _dry(world, text, current, port)).token
    return await change(
        port or _port(world), mapping, current=current, target=TARGETS[mapping.to_scheme],
        dry_run=False, confirm=token, audit=audit or _Audit(),
    )  # fmt: skip


# --- a dry run first, which writes nothing ----------------------------------------------------


async def test_the_dry_run_writes_nothing_and_counts_each_mapping_line(
    world: SimpleNamespace,
) -> None:
    person, link = _drawn(world)  # graded B 2 1 (test_boards.GRADE)
    before = _writes(world)
    audit = _Audit()
    plan = await change(
        _port(world), parse_mapping(FIVE_TO_THREE, SCHEMES), current=FIVE, target=THREE,
        dry_run=True, audit=audit,
    )  # fmt: skip
    assert _writes(world) == before
    assert audit.plans == []
    assert _grade_of(world, person) == (Grading(source="B", intelligence="2", handling="1"), None)
    assert plan.to_change == 2 and plan.already_changed == 0 and not plan.written
    assert plan.moves[("source", "B", "A")] == 2
    assert plan.moves[("intelligence", "2", "2")] == 2
    assert plan.moves[("handling", "1", "P")] == 2
    assert "source B → A: 2 item(s)" in plan.lines()
    assert len(plan.token) == 20
    assert _grade_of(world, link)[1] is None


async def test_the_change_is_refused_without_its_dry_runs_token_for_this_state(
    world: SimpleNamespace,
) -> None:
    """C13's "a dry run first", enforced: no token, a token of another mapping, or a token of the
    items as they were before a drawing since, each refuses the change before any write."""
    person, _ = _drawn(world)
    mapping = parse_mapping(FIVE_TO_THREE, SCHEMES)
    before = _writes(world)

    async def real(confirm: str | None) -> Any:
        return await change(
            _port(world), mapping, current=FIVE, target=THREE, dry_run=False, confirm=confirm,
            audit=_Audit(),
        )  # fmt: skip

    for wrong in (None, "", (await _dry(world, FIVE_TO_FORCE)).token):
        with pytest.raises(GradingRefused, match="a dry run of this mapping"):
            await real(wrong)
    token = (await _dry(world, FIVE_TO_THREE)).token
    _item(_board(start="blank"))  # a drawing since the dry run: another state
    with pytest.raises(GradingRefused, match="as they were before a drawing or edit since"):
        await real(token)
    assert _writes(world) == before + 1  # the drawing's own node: the change wrote nothing
    plan = await real((await _dry(world, FIVE_TO_THREE)).token)
    assert plan.written == 3
    assert _grade_of(world, person)[1] == Grading(source="B", intelligence="2", handling="1")


async def test_an_edit_since_the_dry_run_is_another_state(world: SimpleNamespace) -> None:
    person, _ = _drawn(world)
    token = (await _dry(world, FIVE_TO_THREE)).token
    item = next(i.item_id for i in world.items.items.values() if i.element_id == person)
    edited = _as("alice").patch(f"/v1/investigations/{K}/board-items/{item}", json={"label": "y"})
    assert edited.status_code == 200, edited.text
    with pytest.raises(GradingRefused, match="a dry run of this mapping"):
        await change(
            _port(world), parse_mapping(FIVE_TO_THREE, SCHEMES), current=FIVE, target=THREE,
            dry_run=False, confirm=token, audit=_Audit(),
        )  # fmt: skip


# --- every item keeps its original grade and scheme -------------------------------------------


async def test_every_item_keeps_its_original_grade_and_scheme_through_two_changes(
    world: SimpleNamespace,
) -> None:
    person, link = _drawn(world)
    audit = _Audit()
    first = await _change(world, FIVE_TO_THREE, audit=audit)
    assert first.written == 2
    original = Grading(source="B", intelligence="2", handling="1")
    for element in (person, link):
        assert _grade_of(world, element) == (
            Grading(scheme="3x5x2", source="A", intelligence="2", handling="P"),
            original,
        )
    # Changed back: the original is still the one the item was drawn with, never the middle one.
    await _change(world, THREE_TO_FIVE, current=THREE, audit=audit)
    for element in (person, link):
        assert _grade_of(world, element) == (
            Grading(scheme="5x5x5", source="A", intelligence="2", handling="1"),
            original,
        )
    assert audit.stages() == [("started", 0), ("finished", 2), ("started", 0), ("finished", 2)]


async def test_the_change_is_the_grade_alone_in_place(world: SimpleNamespace) -> None:
    """No second write of the node or the link (which would merge into the link, counting it and
    weighing it again, ADR-120): the port's `regrade_drawn` alone, and every other field kept."""
    person, link = _drawn(world)
    before = {e: _element(world, e) for e in (person, link)}
    writes = len(world.graph.node_writes) + len(world.graph.edge_writes)
    await _change(world, FIVE_TO_THREE)
    assert len(world.graph.node_writes) + len(world.graph.edge_writes) == writes
    assert sorted(world.graph.regrades) == sorted([person, link])
    for element_id, was in before.items():
        now = _element(world, element_id)
        assert now.model_dump(exclude={"provenance"}) == was.model_dump(exclude={"provenance"})
        assert now.provenance.drawn.model_dump(
            exclude={"grading", "original_grading"}
        ) == was.provenance.drawn.model_dump(exclude={"grading", "original_grading"})


async def test_a_scheme_files_scheme_is_a_target_like_any(world: SimpleNamespace) -> None:
    person, link = _drawn(world)
    plan = await _change(world, FIVE_TO_FORCE)
    assert plan.written == 2
    assert _grade_of(world, person) == (
        Grading(scheme="force-4x3", source="W", intelligence="1", handling="H"),
        Grading(source="B", intelligence="2", handling="1"),
    )


# --- refused whole, before anything is written ------------------------------------------------


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (FIVE_TO_THREE.replace(", E: C}", "}"), "source E"),  # a grade of the old scheme unmapped
        (FIVE_TO_THREE.replace("E: C}", "E: C, F: C}"), "source F"),  # not a grade of the old
        (FIVE_TO_THREE.replace('"5": C}', '"5": X}'), "handling X"),  # not a grade of the new
        (FIVE_TO_THREE.replace("to: 3x5x2", "to: 4x4"), "4x4"),
        (FIVE_TO_THREE.replace("to: 3x5x2", "to: 5x5x5"), "the same scheme"),
        (FIVE_TO_FORCE.replace("E: Z}", "E: Q}"), "source Q is not a grade of force-4x3"),
        ("from: 5x5x5\nto: 3x5x2\n", "source"),
        ("[]", "mapping"),
    ],
)
def test_a_mapping_that_does_not_cover_the_old_scheme_is_refused_in_words(
    text: str, said: str
) -> None:
    with pytest.raises(MappingRefused) as refused:
        parse_mapping(text, SCHEMES)
    assert said in str(refused.value)


async def test_a_mapping_from_another_scheme_than_the_deployments_is_refused(
    world: SimpleNamespace,
) -> None:
    # Every item in the mapping's own old scheme, so nothing but the deployment's setting can
    # refuse it: an item in another scheme would be refused by its own check, for its own reason.
    board = _board(start="blank")
    with _deployment_grading_in(THREE):
        _item(board, grading={"scheme": "3x5x2", "source": "A", "intelligence": "1",
                              "handling": "P"})  # fmt: skip
    before = _writes(world)
    for dry_run in (True, False):
        with pytest.raises(GradingRefused) as refused:
            await change(
                _port(world), parse_mapping(THREE_TO_FIVE, SCHEMES), current=FIVE, target=FIVE,
                dry_run=dry_run, confirm="x", audit=_Audit(),
            )  # fmt: skip
        assert "this deployment grades in 5x5x5" in str(refused.value)
    assert _writes(world) == before


async def test_an_item_in_a_third_scheme_refuses_the_whole_change_naming_it(
    world: SimpleNamespace,
) -> None:
    first, _ = _drawn(world)  # in 5x5x5, drawn first, so a loop writing as it goes reaches it
    board = _board(start="blank")
    with _deployment_grading_in(FORCE):  # drawn under a scheme file, then the setting put back
        made = _item(board, grading={"scheme": "force-4x3", "source": "W", "intelligence": "1",
                                     "handling": "H"})  # fmt: skip
    before = _writes(world)
    audit = _Audit()
    with pytest.raises(GradingRefused) as refused:
        await _dry(world, FIVE_TO_THREE)
    said = str(refused.value)
    assert "1 item(s) graded in force-4x3" in said and made["element_id"] in said
    assert _writes(world) == before and audit.plans == []
    assert _grade_of(world, first)[1] is None


async def test_an_item_drawn_in_the_new_scheme_is_left_and_counted(world: SimpleNamespace) -> None:
    """The way out of a drawing made in the new scheme (the setting changed by hand, say): it
    needs no mapping, so it is left as drawn and said, never refused, never changed."""
    _drawn(world)
    board = _board(start="blank")
    with _deployment_grading_in(THREE):
        made = _item(board, grading={"scheme": "3x5x2", "source": "B", "intelligence": "3",
                                     "handling": "C"})["element_id"]  # fmt: skip
    plan = await _change(world, FIVE_TO_THREE)
    assert plan.written == 2 and plan.already_in_new == 1 and plan.already_changed == 0
    assert "1 drawn in 3x5x2 and left as they are" in plan.lines()[0]
    assert _grade_of(world, made) == (
        Grading(scheme="3x5x2", source="B", intelligence="3", handling="C"),
        None,
    )


async def test_an_item_whose_grade_is_not_of_the_deployments_scheme_refuses_naming_it(
    world: SimpleNamespace,
) -> None:
    """A scheme file edited under items already drawn in it (a grade taken out): the mapping
    cannot say what such an item becomes, so the change is refused whole, naming it."""
    board = _board(start="blank")
    with _deployment_grading_in(FORCE):
        made = _item(board, grading={"scheme": "force-4x3", "source": "W", "intelligence": "1",
                                     "handling": "H"})["element_id"]  # fmt: skip
    narrowed = FORCE.model_copy(update={"source": ["X", "Y", "Z"]})
    text = "from: force-4x3\nto: 3x5x2\nsource: {X: A, Y: B, Z: C}\n" \
        "intelligence: {'1': '1', '2': '2', '3': '3'}\nhandling: {H: P}\n"
    mapping = parse_mapping(text, {**SCHEMES, FORCE.scheme: narrowed})
    before = _writes(world)
    with pytest.raises(GradingRefused) as refused:
        await change(
            _port(world), mapping, current=narrowed, target=THREE, dry_run=True, audit=_Audit()
        )
    assert "1 item(s) carry a grade that is not one of force-4x3's" in str(refused.value)
    assert made in str(refused.value) and _writes(world) == before


async def test_a_registered_item_that_cannot_be_read_back_refuses_the_whole_change(
    world: SimpleNamespace,
) -> None:
    """The board registry names an item the graph no longer gives back to the operator's reader
    (its element gone from the store under it): never skipped silently (rule 2), named by its
    registry id so the operator can act, and nothing is written though the others could be."""
    person, link = _drawn(world)
    del world.graph._graph_nodes[person]
    item = next(i.item_id for i in world.items.items.values() if i.element_id == person)
    before = _writes(world)
    with pytest.raises(GradingRefused) as refused:
        await _dry(world, FIVE_TO_THREE)
    # The link rests on the gone node, so it is not read back either (as in the store).
    assert "2 drawn item(s) could not be read back" in str(refused.value)
    assert item in str(refused.value)
    assert _writes(world) == before
    assert _grade_of(world, link)[1] is None


def test_a_refusal_names_ten_ids_and_counts_the_rest() -> None:
    from services.api.grading import named

    ids = [f"id-{n:02}" for n in range(13)]
    assert named(ids) == ", ".join(ids[:10]) + " and 3 more"
    assert named(ids[:2]) == "id-00, id-01"


async def test_a_withdrawn_item_keeps_the_grade_it_was_drawn_with(world: SimpleNamespace) -> None:
    board = _board(start="blank")
    made = _item(board)
    withdrawn = _as("alice").post(f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    element = made["element_id"]
    plan = await _change(world, FIVE_TO_THREE)
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
        await _change(world, FIVE_TO_THREE, audit=audit, port=port)
    assert stopped.value.done == 1 and stopped.value.total == 2
    assert audit.stages() == [("started", 0), ("stopped", 1)]
    again = await _change(world, FIVE_TO_THREE, audit=audit)
    assert again.already_changed == 1 and again.written == 1
    assert audit.stages()[2:] == [("started", 0), ("finished", 1)]
    original = Grading(source="B", intelligence="2", handling="1")
    assert _grade_of(world, person)[1] == original and _grade_of(world, link)[1] == original


async def test_an_element_gone_from_under_the_change_stops_it_saying_so(
    world: SimpleNamespace,
) -> None:
    """The store's `regrade_drawn` says False (the element reverted between the read and the
    write): the run stops, never counting it as changed."""
    _drawn(world)
    port = _port(world)

    async def gone(*_: Any) -> bool:
        return False

    port.graph = SimpleNamespace(  # type: ignore[assignment]
        get_nodes=world.graph.get_nodes, get_edges=world.graph.get_edges, regrade_drawn=gone
    )
    with pytest.raises(GradingIncomplete) as stopped:
        await _change(world, FIVE_TO_THREE, port=port)
    assert stopped.value.done == 0 and "no longer a live drawn item" in str(stopped.value)


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
    token = (await _dry(world, FIVE_TO_THREE)).token
    code = await run(
        target=THREE, mapping_text=FIVE_TO_THREE, current=FIVE, dry_run=False, confirm=token,
        items=port, audit=audit, say=said.append,
    )  # fmt: skip
    assert code == 0
    lines, stages = seen_at_first_write[0]
    assert "source B → A: 2 item(s)" in lines and "5x5x5 to 3x5x2: 2 item(s) to change." in lines
    assert stages == [("started", 0)]
    assert audit.stages() == [("started", 0), ("finished", 2)]
    assert audit.plans[0]["dry_run_token"] == token


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
        target=THREE, mapping_text=FIVE_TO_THREE, current=FIVE, dry_run=True,
        items=_port(world), audit=audit, say=said.append,
    )  # fmt: skip
    assert code == 0 and _writes(world) == before and audit.plans == []
    assert "5x5x5 to 3x5x2: 2 item(s) to change." in said
    assert "source B → A: 2 item(s)" in said
    token = said[-1].rsplit(" ", 1)[-1]
    assert said[-1] == f"A dry run: nothing was written. To make this change, add --confirm {token}"
    code = await run(
        target=THREE, mapping_text=FIVE_TO_THREE, current=FIVE, dry_run=False, confirm=token,
        items=_port(world), audit=audit, say=said.append,
    )  # fmt: skip
    assert code == 0 and audit.stages() == [("started", 0), ("finished", 2)]


@pytest.mark.parametrize(
    ("target", "text", "current", "said"),
    [
        (FIVE, FIVE_TO_THREE, FIVE, "--to is 5x5x5, but the mapping is to 3x5x2"),
        (THREE, FIVE_TO_THREE.replace(", E: C}", "}"), FIVE, "source E of 5x5x5"),
        (THREE, FIVE_TO_THREE, THREE, "this deployment grades in 3x5x2"),
        (THREE, FIVE_TO_THREE, FIVE, "a dry run of this mapping"),
    ],
)
async def test_the_command_refuses_with_exit_1_and_writes_nothing(
    world: SimpleNamespace,
    target: GradingSchemeAnswer,
    text: str,
    current: GradingSchemeAnswer,
    said: str,
) -> None:
    from scripts.grading_change import run

    _drawn(world)
    before = _writes(world)
    lines: list[str] = []
    code = await run(
        target=target, mapping_text=text, current=current, dry_run=False, confirm="not-the-token",
        items=_port(world), audit=_Audit(), say=lines.append,
    )  # fmt: skip
    assert code == 1 and _writes(world) == before
    assert any(said in line for line in lines), lines


def _argv(tmp_path: Any, *more: str) -> list[str]:
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(FIVE_TO_THREE, encoding="utf-8")
    return ["--to", "3x5x2", "--mapping", str(mapping), "--changed-by", "ops-1", *more]


def _no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    def opened(*_: Any, **__: Any) -> Any:
        raise AssertionError("a store was opened")

    monkeypatch.setattr("asyncpg.create_pool", opened)


def test_the_command_without_store_settings_refuses_before_opening_any(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from scripts import grading_change

    for name in ("ARCADEDB_HOST", "ARCADEDB_HTTP_PORT", "OSPREY_GRADING_SCHEME"):
        monkeypatch.delenv(name, raising=False)
    _no_store(monkeypatch)
    argv = _argv(tmp_path, "--dry-run")
    assert grading_change.main(argv) == 64
    monkeypatch.setenv("ARCADEDB_HOST", "nowhere")
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "4x4")  # an unknown setting stops it too
    assert grading_change.main(argv) == 64


async def test_the_change_is_refused_while_the_conduit_answers_before_any_store_is_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """A drawing or an edit during the change, or before the restart in the new scheme, would be
    in the old scheme: the change itself (not its dry run) needs the Conduit stopped."""
    from scripts import grading_change

    monkeypatch.setenv("ARCADEDB_HOST", "nowhere")
    monkeypatch.delenv("OSPREY_GRADING_SCHEME", raising=False)
    _no_store(monkeypatch)
    asked: list[str] = []

    async def answers(url: str) -> bool:
        asked.append(url)
        return True

    args = grading_change.build_parser().parse_args(
        _argv(tmp_path, "--confirm", "t", "--conduit-url", "http://api:8000")
    )
    assert await grading_change._main(args, answers=answers) == 1
    assert asked == ["http://api:8000"]
    assert "the Conduit is running at http://api:8000" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("given", "said"),
    [
        ("4x4", "neither a grading scheme"),
        ("missing.yaml", "cannot be read"),
        ("bad.yaml", "is not a grading scheme"),
        ("built-in.yaml", "a built-in scheme"),
    ],
)
def test_a_target_that_is_no_scheme_is_refused_in_words(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, given: str, said: str
) -> None:
    from scripts.grading_change import TargetRefused, target_scheme

    (tmp_path / "bad.yaml").write_text("scheme: x\nsource: []\n", encoding="utf-8")
    (tmp_path / "built-in.yaml").write_text(
        "scheme: 5x5x5\nsource: [A]\nintelligence: ['1']\nhandling: ['1']\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(TargetRefused, match=said):
        target_scheme(given)
    good = tmp_path / "force.yaml"
    good.write_text(FORCE.model_dump_json(), encoding="utf-8")
    assert target_scheme(str(good)) == FORCE
