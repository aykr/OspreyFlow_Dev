"""A board's ceiling is never told to a reader below it (GG4j; the owner's ruling of 26 November
2026; rule 3). Pure: the boards service over `board_fakes.BoardGraph` and the in-memory stores
(rows 1 to 5), and the other routes that send a case's ceiling through the real app over the same
fakes (row 6).

The rule: a reader cleared for the case's ceiling is told it; anyone else is told the highest
marking both under it and within their own clearance, in the field and in every refusal's words.
The write check itself stays against the case's real ceiling.

Case K reads `src`, whose highest allowed marking is each test's to set. Bram (B) is cleared to
OFFICIAL, below it; Cass (C) to exactly OFFICIAL-SENSITIVE, at it; Cora to SECRET, above it.

Each row is shown red by its plant at the real call site (rule 15): rows 1, 3, 5b and 6 by the
code before this slice (and row 6 by the rule put in `open()` alone), and by
`..._with_the_real_ceiling_sent`; rows 2, 4 and 5 by `..._with_the_readers_highest_sent_to_all`,
`..._with_the_write_check_given_the_readers_ceiling` and
`..._with_the_write_check_given_the_clearance`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.board_store import InMemoryBoardItemStore, new_item
from services.api.boards import Boards, DrawingRefused
from services.api.case_views import InMemoryCaseViewStore, StoredCaseView
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel
from services.ingest.ceiling import AboveTheDeploymentCeiling, DeploymentCeiling

from adapters.media_objectstore import reference_for
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.boards import BoardOpened, DrawnItemEdit, DrawnItemInput, DrawnLinkInput, PictureChoice
from schemas.domain import DrawnAssertion, Grading, Node, Principal

from .board_fakes import BoardGraph
from .test_boards import K, _as, _board, _item
from .test_drawn_merge import _step, _three, mw  # noqa: F401  (the fixture)
from .test_promotions import _removed_with_items, _sheet, pw, world  # noqa: F401  (the fixtures)
from .working_set.test_visible_link import node

SCHEME = load_uk_le_scheme()
ONTOLOGY = load_deployment_ontology()
UNIT = "unit-1"
MADE = datetime(2026, 11, 1, tzinfo=UTC)
GRADE = Grading(source="B", intelligence="2", handling="1")
OS = "OFFICIAL-SENSITIVE"
#: Every case ceiling above B's clearance: set, higher, and none set (the scheme's highest).
ABOVE_B: tuple[str | None, ...] = (OS, "SECRET", None)


def _who(name: str, clearance: str) -> Principal:
    return Principal(
        id=name, clearance=clearance, org_unit=UNIT, roles=["analyst"],
        datasets=["src", "layer-k"],
    )  # fmt: skip


BRAM = _who("bram", "OFFICIAL")
CASS = _who("cass", OS)
CORA = _who("cora", "SECRET")


async def _service(highest: str | None = OS) -> SimpleNamespace:
    """The boards service: two loaded people and a picture in `src`, and Bram's own drawn person
    on the board, in the case's layer."""
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(id="src", name="Prison intel", owning_unit=UNIT, created_by="eng",
                created_at=MADE, highest_marking=highest)
    )  # fmt: skip
    datasets.cases[K] = ["src"]

    def loaded(node_id: str, **update: Any) -> Node:
        return node(node_id).model_copy(update={"datasets": ["src"], **update})

    base = loaded("d-bram", datasets=["layer-k"])
    drawn = base.model_copy(
        update={
            "properties": {"family_name": "Tall"},
            "provenance": base.provenance.model_copy(
                update={"drawn": DrawnAssertion(
                    item_id="item-bram", asserted_by="bram", board_id="board", case_id=K,
                    label="Tall", grading=GRADE, source_note="Wing officer report",
                )}
            ),
        }
    )  # fmt: skip
    image = loaded(
        "img-1",
        type="Document",
        properties={"title": "photo.png", "media_kind": "image",
                    "object_ref": reference_for(b"png", "image/png")},
    )  # fmt: skip
    graph = BoardGraph(ONTOLOGY, nodes=[loaded("p-1"), loaded("p-2"), drawn, image])
    views, items = InMemoryCaseViewStore(), InMemoryBoardItemStore()
    board = await views.save_board(K, "Wing B", "bram", node_ids=["p-1", "p-2"])
    await items.add(
        new_item(board_id=board.id, case_id=K, kind="node", element_id="d-bram",
                 author="bram", dataset_id="layer-k", item_id="item-bram"),
        None,
    )  # fmt: skip
    boards = Boards(
        graph=graph, views=views, items=items, datasets=datasets, ontology=ONTOLOGY,
        scheme=SCHEME, media=InMemoryMediaStore(),
    )  # fmt: skip
    return SimpleNamespace(boards=boards, board=board, datasets=datasets, graph=graph)


def _set_highest(held: SimpleNamespace, highest: str | None) -> None:
    src = held.datasets.datasets["src"]
    held.datasets.datasets["src"] = src.model_copy(update={"highest_marking": highest})


async def _open(held: SimpleNamespace, who: Principal) -> BoardOpened:
    return await held.boards.open(held.board, who)


# --- rows 1 to 3: the field -------------------------------------------------------------------


async def test_row_1_a_reader_below_the_ceiling_is_told_their_own_highest() -> None:
    opened = await _open(await _service(OS), BRAM)
    assert opened.ceiling == "OFFICIAL"
    assert opened.markings == ["PUBLIC", "OFFICIAL"]  # as before


@pytest.mark.parametrize(
    ("who", "highest", "told"),
    [(CASS, OS, OS), (CORA, OS, OS), (CORA, "SECRET", "SECRET"), (CORA, None, "SECRET"),
     (BRAM, "OFFICIAL", "OFFICIAL"), (BRAM, "PUBLIC", "PUBLIC")],
)  # fmt: skip
async def test_row_2_a_reader_cleared_for_the_ceiling_is_told_the_cases_own(
    who: Principal, highest: str | None, told: str
) -> None:
    opened = await _open(await _service(highest), who)
    assert opened.ceiling == told
    assert opened.markings == SCHEME.classification[: SCHEME.classification.index(told) + 1]


async def test_row_2_fails_with_the_readers_highest_sent_to_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plant: the reader's own highest in place of the case's, to everyone."""
    held = await _service(OS)
    monkeypatch.setattr(
        Boards, "ceiling_told", lambda self, ceiling, principal: principal.clearance
    )
    with pytest.raises(AssertionError):
        assert (await _open(held, CORA)).ceiling == OS


async def test_row_3_bs_answer_is_the_same_whatever_the_ceiling_above_b_is() -> None:
    held = await _service(OS)
    answers = []
    for highest in ABOVE_B:
        _set_highest(held, highest)
        answers.append((await _open(held, BRAM)).model_dump_json())
    assert len(set(answers)) == 1, "B's answer changes with a ceiling above B"
    assert OS not in answers[0] and "SECRET" not in answers[0]


async def test_row_3_in_a_composite_b_is_told_nothing_of_a_members_ceiling() -> None:
    held = await _service(None)
    for member, highest in (("m-1", OS), ("m-2", "SECRET")):
        held.datasets.add(
            Dataset(id=member, name=member, owning_unit=UNIT, created_by="eng", created_at=MADE,
                    highest_marking=highest)
        )  # fmt: skip
    held.datasets.add(
        Dataset(id="mix", name="Both", owning_unit=UNIT, created_by="eng", created_at=MADE,
                kind=COMPOSITE, members=["m-1", "m-2"])
    )  # fmt: skip
    held.datasets.cases[K] = ["mix"]
    assert (await _open(held, BRAM)).ceiling == "OFFICIAL"
    assert (await _open(held, CORA)).ceiling == OS


async def test_a_clearance_the_scheme_does_not_know_is_told_no_ceiling() -> None:
    """Fails closed: no marking is both under the ceiling and within such a clearance."""
    held = await _service(OS)
    nobody = _who("nobody", "UNKNOWN")
    opened = await _open(held, nobody)
    assert (opened.ceiling, opened.markings) == (None, [])
    with pytest.raises(DrawingRefused) as refused:
        held.boards.check_marking("SECRET", OS, nobody)
    assert refused.value.code == "above_the_ceiling"
    assert refused.value.message == "SECRET is above this case's ceiling"


# --- rows 4, 5 and 5b: the write check, at each of its real call sites ------------------------


def _item_input(marking: str) -> DrawnItemInput:
    return DrawnItemInput(
        type="Person", label="x", marking=marking, grading=GRADE, source_note="n",
        properties={"family_name": "x"},
    )  # fmt: skip


Site = Callable[[Boards, StoredCaseView, Principal, str], Awaitable[Any]]


async def _declare(boards: Boards, board: StoredCaseView, who: Principal, marking: str) -> Any:
    return await boards.declare(board, _item_input(marking), who)


async def _link(boards: Boards, board: StoredCaseView, who: Principal, marking: str) -> Any:
    given = DrawnLinkInput(
        type="ASSOCIATE_OF", label="x", marking=marking, grading=GRADE, source_note="n",
        source="p-1", target="p-2",
    )  # fmt: skip
    return await boards.link(board, given, who)


async def _edit(boards: Boards, board: StoredCaseView, who: Principal, marking: str) -> Any:
    return await boards.edit(K, "item-bram", DrawnItemEdit(marking=marking), who)


async def _upload(boards: Boards, board: StoredCaseView, who: Principal, marking: str) -> Any:
    return await boards.upload_picture(
        board, "d-bram", who, name="x.png", data=b"png", marking=marking, source_note="n"
    )


async def _choose(boards: Boards, board: StoredCaseView, who: Principal, marking: str) -> Any:
    given = PictureChoice(document_id="img-1", marking=marking)
    return await boards.choose_picture(board, "d-bram", given, who)


#: Every caller of `check_marking` a reader below the ceiling can reach with a marking of their
#: own choosing. (A match decision's marking is that of two items the reader sees, so it is never
#: above a ceiling at or above their clearance.)
SITES: dict[str, Site] = {
    "declare": _declare, "link": _link, "edit": _edit, "upload": _upload, "choose": _choose,
}  # fmt: skip


async def _refusal(
    held: SimpleNamespace, site: str, who: Principal, marking: str
) -> DrawingRefused:
    with pytest.raises(DrawingRefused) as refused:
        await SITES[site](held.boards, held.board, who, marking)
    assert not held.graph.node_writes and not held.graph.edge_writes
    return refused.value


@pytest.mark.parametrize("site", SITES)
async def test_row_4_b_may_not_draw_above_their_own_clearance(site: str) -> None:
    refused = await _refusal(await _service(OS), site, BRAM, OS)
    assert (refused.code, refused.status) == ("above_your_clearance", 409)
    assert refused.message == f"{OS} is above your own clearance, OFFICIAL"


@pytest.mark.parametrize("site", ["declare", "link", "upload", "choose"])
async def test_row_4_fails_with_the_write_check_given_the_readers_ceiling(
    site: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant, at `check_marking` as every writer calls it: B's told ceiling given in place of
    the case's, so what is only above B is refused as above the case's ceiling."""
    real = Boards.check_marking

    def told(self: Boards, marking: str, ceiling: str, principal: Principal) -> None:
        real(self, marking, str(self.ceiling_told(ceiling, principal)), principal)

    monkeypatch.setattr(Boards, "check_marking", told)
    refused = await _refusal(await _service(OS), site, BRAM, OS)
    assert refused.code == "above_the_ceiling"


@pytest.mark.parametrize("site", SITES)
async def test_row_5_a_drawing_above_the_cases_real_ceiling_is_refused_as_before(
    site: str,
) -> None:
    """To Cora, cleared above it, in the words as they were: the real ceiling's name."""
    held = await _service(OS)
    if site == "edit":  # only an item's author edits it
        author = _who("bram", "SECRET")
    else:
        author = CORA.model_copy(update={"id": "bram"})  # the board's and the item's maker
    refused = await _refusal(held, site, author, "SECRET")
    assert (refused.code, refused.status) == ("above_the_ceiling", 409)
    assert refused.message == (
        f"SECRET is above this case's ceiling, {OS}: nothing drawn in this case may be marked "
        f"above {OS}"
    )


class _PastTheCheck(Exception):
    pass


async def test_row_5_fails_with_the_write_check_given_the_clearance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plant: the reader's clearance given in place of the case's ceiling, so a reader cleared
    above it draws above it. `into`, the step after the checks, says the drawing got through."""
    real = Boards.check_marking

    def cleared(self: Boards, marking: str, ceiling: str, principal: Principal) -> None:
        real(self, marking, principal.clearance, principal)

    async def past(self: Boards, case_id: str) -> Any:
        raise _PastTheCheck

    monkeypatch.setattr(Boards, "check_marking", cleared)
    monkeypatch.setattr(Boards, "into", past)
    held = await _service(OS)
    with pytest.raises(_PastTheCheck):
        await _declare(held.boards, held.board, CORA, "SECRET")


@pytest.mark.parametrize("site", SITES)
async def test_row_5b_bs_refusal_names_only_the_ceiling_the_board_sent_b(site: str) -> None:
    held = await _service(OS)
    sent = (await _open(held, BRAM)).ceiling
    refused = await _refusal(held, site, BRAM, "SECRET")
    assert (refused.code, refused.status) == ("above_the_ceiling", 409)
    assert OS not in refused.message and OS not in str(refused)
    assert refused.message == (
        f"SECRET is above this case's ceiling, {sent}: nothing drawn in this case may be marked "
        f"above {sent}"
    )


@pytest.mark.parametrize(("who", "told"), [(BRAM, "OFFICIAL"), (CASS, OS), (CORA, OS)])
async def test_the_boards_deployment_refusal_names_no_marking_above_the_reader(
    who: Principal, told: str
) -> None:
    """The other refusal of `check_marking` that names a ceiling: the deployment's highest
    marking (ADR-148 decision 10), named as it is only to a reader cleared for it."""
    held = await _service(OS)
    held.boards.deployment_ceiling = DeploymentCeiling.of(OS, SCHEME)
    with pytest.raises(AboveTheDeploymentCeiling) as refused:
        await _declare(held.boards, held.board, who, "SECRET")
    assert refused.value.problems == [
        f"This would write something marked above this deployment's highest marking, {told}, so "
        "nothing was written."
    ]
    assert refused.value.ceiling == told
    assert not held.graph.node_writes


@pytest.mark.parametrize("site", SITES)
async def test_row_5b_fails_with_the_real_ceiling_sent(
    site: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant: the case's real ceiling told to everyone, in the field and the words."""
    monkeypatch.setattr(Boards, "ceiling_told", lambda self, ceiling, principal: ceiling)
    held = await _service(OS)
    assert (await _open(held, BRAM)).ceiling == OS
    assert OS in (await _refusal(held, site, BRAM, "SECRET")).message


# --- row 6: every other path that sends a case's ceiling, through the real app ----------------


def _bobs_board(pw: SimpleNamespace) -> str:  # noqa: F811
    """Bob (OFFICIAL) made an Author of K, so he may promote from a board of his own."""
    pw.cases.grants[K]["bob"] = AccessLevel.AUTHOR
    board = _board("bob")
    _item(board, "bob")
    return board


def _marking_check(sheet: dict[str, Any]) -> str:
    (words,) = [c["words"] for c in sheet["checks"] if c["name"] == "marking"]
    return str(words)


def test_row_6_the_promotion_sheet_tells_a_reader_below_the_ceiling_only_their_own(
    pw: SimpleNamespace,  # noqa: F811
) -> None:
    board = _bobs_board(pw)
    answers = []
    for highest in ABOVE_B:
        _set_highest(pw, highest)
        sheet = _sheet(board, "bob")
        assert sheet["highest_marking"] == "OFFICIAL"
        assert _marking_check(sheet) == (
            "Every marking within Prison intel's highest allowed, OFFICIAL"
        )
        assert OS not in str(sheet) and "SECRET" not in str(sheet)
        answers.append(sheet)
    assert answers[0] == answers[1] == answers[2]


def test_row_6_the_promotion_sheet_tells_a_reader_cleared_for_it_the_cases_own(
    pw: SimpleNamespace,  # noqa: F811
) -> None:
    board = _board()
    _item(board)
    sheet = _sheet(board)
    assert sheet["highest_marking"] == OS
    assert _marking_check(sheet) == f"Every marking within Prison intel's highest allowed, {OS}"


def test_row_6_a_sheet_that_promotes_nothing_names_no_marking_above_its_reader(
    pw: SimpleNamespace,  # noqa: F811
) -> None:
    """Such a sheet (here, a case reading a composite) holds the scheme's highest in the field."""
    board = _bobs_board(pw)
    pw.datasets.add(
        Dataset(id="mix", name="Both", owning_unit="unit-1", created_by="eng", created_at=MADE,
                kind=COMPOSITE, members=["src"])
    )  # fmt: skip
    pw.datasets.cases[K] = ["mix"]
    sheet = _sheet(board, "bob")
    assert sheet["refused"] and sheet["highest_marking"] == "OFFICIAL"


@pytest.mark.parametrize(("who", "told"), [("erin", "OFFICIAL"), ("dana", OS)])
def test_row_6_the_layer_merge_sheet_opened_and_read_again(
    pw: SimpleNamespace, who: str, told: str  # noqa: F811
) -> None:
    _removed_with_items(pw)
    opened = _as(who).post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet")
    assert opened.status_code == 200, opened.text
    again = _as(who).get(f"/v1/datasets/src/layer-merges/{opened.json()['grant_id']}")
    assert again.status_code == 200, again.text
    for sheet in (opened.json(), again.json()):
        assert sheet["highest_marking"] == told
        assert _marking_check(sheet) == (
            f"Every marking within Prison intel's highest allowed, {told}"
        )
        if who == "erin":
            assert OS not in str(sheet)


@pytest.mark.parametrize(("who", "told"), [("erin", "OFFICIAL"), ("dana", OS)])
def test_row_6_the_merge_targets_and_the_drawn_merge_sheet(
    mw: SimpleNamespace, who: str, told: str  # noqa: F811
) -> None:
    """The target's highest allowed marking is the ceiling of every case reading it."""
    _three(mw)
    targets = _step(mw, "targets", who)
    assert targets.status_code == 200, targets.text
    assert [(t["dataset_id"], t["highest_marking"]) for t in targets.json()["targets"]] == [
        ("src", told)
    ]
    answer = _step(mw, "sheet", who)
    assert answer.status_code == 200, answer.text
    sheet = answer.json()
    assert sheet["highest_marking"] == told
    assert _marking_check(sheet) == f"Every marking within Prison intel's highest allowed, {told}"
    if who == "erin":
        assert OS not in targets.text and OS not in answer.text
