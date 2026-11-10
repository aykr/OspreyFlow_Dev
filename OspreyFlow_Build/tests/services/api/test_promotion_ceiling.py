"""The deployment's marking ceiling on the write side of a promotion and a drawn merge (ADR-148
decision 10 and Amendment 2 decision 6; L3.H2 part 2): what would write data marked above
`deployment.highest_marking` is refused before anything is written, in words naming the limit and
never the item's content. The read-side fallback that reads an unmarked dataset at the scheme's
highest (`Promotions.highest`) stays: capping it would loosen access.

The worlds are `test_promotions.py`'s and `test_drawn_merge.py`'s, through the real app. The
ceiling is the rendered setting (`OSPREY_HIGHEST_MARKING`), set here after the items are drawn: a
deployment whose ceiling was lowered over what it already holds (ADR-148 Amendment 2), which is
how an item above it can exist at all once the drawing's own check (case-b) and the stamping
graph's backstop refuse new ones.

What a mistake would do, and the case that catches it (each red by its plant, in
`process/lanes/case/gates/L3.H2-plants.txt`):

- an item above the ceiling promoted, the sheet saying nothing:
  `test_an_item_above_the_deployments_ceiling_is_refused_at_the_sheet_and_at_the_route`;
- a picture above it going with its node: `test_a_picture_above_the_ceiling_is_named_and_left_behind`;
- a write above it reaching the store when the per-item check misses it (a match, a picture's
  document, a path to come): `test_the_promotions_own_record_is_refused_above_the_ceiling`;
- a promotion sent for review committed after the ceiling was lowered:
  `test_an_approval_after_the_ceiling_was_lowered_promotes_nothing`, and the load's own last
  check, `test_the_load_itself_is_refused_above_the_ceiling_and_the_promotion_rejected`;
- a drawn merge's chosen match marked above the ceiling written:
  `test_a_drawn_merges_match_above_the_ceiling_refuses_the_merge_and_writes_nothing`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from services.api.promotions import Promotions
from services.ingest.ceiling import CEILING_ENV

from .test_boards import K, _as, _board, _item
from .test_drawn_merge import _ids, _nothing_written, _said, _step, _three, mw  # noqa: F401
from .test_promotions import _policy, _promote, _sheet, _studio, pw, world  # noqa: F401

LIMIT = "OFFICIAL"


def _above(pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict[str, Any]]:  # noqa: F811
    """An item drawn at OFFICIAL-SENSITIVE, within `src`'s own highest; then the deployment's
    ceiling lowered to OFFICIAL, so it is above the deployment's and no other limit."""
    board = _board()
    made = _item(board, label="Tall", marking="OFFICIAL-SENSITIVE")
    monkeypatch.setenv(CEILING_ENV, LIMIT)
    return board, made


def _nothing_promoted(pw: SimpleNamespace) -> None:  # noqa: F811
    assert pw.graph.promotions == 0


def _no_items_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-item checks planted out, as `test_promotions.py`'s own route check is shown red, so
    that what refuses is the check under test and nothing before it (rule 15)."""

    async def no_problems(self: Promotions, reads: Any, *_: Any, **__: Any) -> dict[str, list[Any]]:
        return {r.item.item_id: [] for r in reads}

    monkeypatch.setattr(Promotions, "_problems", no_problems)


def test_an_item_above_the_deployments_ceiling_is_refused_at_the_sheet_and_at_the_route(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    board, made = _above(pw, monkeypatch)
    (item,) = _sheet(board)["items"]
    assert item["problems"] == [
        "Marked OFFICIAL-SENSITIVE, above this deployment's highest marking, OFFICIAL."
    ]
    answer = _promote(board, made["item_id"])
    assert (answer.status_code, answer.json()["error"]) == (422, "check_failed")
    assert "above this deployment's highest marking, OFFICIAL" in answer.json()["detail"]
    assert not pw.store.records
    _nothing_promoted(pw)


def test_within_the_ceiling_an_item_is_promoted_as_ever(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    board = _board()
    made = _item(board, marking="OFFICIAL")
    monkeypatch.setenv(CEILING_ENV, LIMIT)
    assert _sheet(board)["items"][0]["problems"] == []
    answer = _promote(board, made["item_id"])
    assert answer.status_code == 201 and answer.json()["status"] == "committed", answer.text


def test_a_picture_above_the_ceiling_is_named_and_left_behind(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A node within the ceiling whose picture is marked above it: the picture is named at the
    sheet in the limit's words, and left behind when its node is promoted."""
    board = _board()
    made = _item(board)
    uploaded = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{made['element_id']}/picture",
        params={"name": "tall.png", "marking": "OFFICIAL-SENSITIVE", "source_note": "Gate camera"},
        content=b"\x89PNG drawn",
    )
    assert uploaded.status_code == 201, uploaded.text
    monkeypatch.setenv(CEILING_ENV, LIMIT)
    items = {i["kind"]: i for i in _sheet(board)["items"]}
    assert items["node"]["problems"] == []
    assert (
        "The picture is marked OFFICIAL-SENSITIVE, above this deployment's highest marking, "
        "OFFICIAL." in items["picture"]["problems"]
    )
    # Promoted, the node goes and its picture stays behind, said why: nothing above the ceiling
    # is written (a picture follows its node, so it is left out rather than refusing the node).
    answer = _promote(board, made["item_id"])
    assert answer.status_code == 201, answer.text
    (left,) = answer.json()["left_out"]
    assert "above this deployment's highest marking, OFFICIAL" in left["why"]
    record = pw.store.records[answer.json()["id"]]
    assert record.node_ids == (made["element_id"],) and record.edge_ids == ()
    assert record.marking == "OFFICIAL"


def test_the_promotions_own_record_is_refused_above_the_ceiling(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the per-item checks planted out, the promotion's record, which holds every marking it
    would write (its items, a picture's document, a drawn merge's matches), is judged before it
    is stored: refused as a load is, 422 in the ceiling's own words."""
    board, made = _above(pw, monkeypatch)
    _no_items_checked(monkeypatch)
    answer = _promote(board, made["item_id"])
    assert _said(answer) == (422, "above_the_deployments_highest_marking"), answer.text
    detail = answer.json()["detail"]
    assert "highest marking, OFFICIAL" in detail and "Tall" not in detail
    assert not pw.store.records
    _nothing_promoted(pw)


def _waiting_then_lowered(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Sent for review at OFFICIAL-SENSITIVE with no ceiling set; then the ceiling lowered."""
    _policy(pw, "second_person_reviews")
    board = _board()
    made = _item(board, marking="OFFICIAL-SENSITIVE")
    sent = _promote(board, made["item_id"])
    assert sent.status_code == 201 and sent.json()["status"] == "awaiting_review", sent.text
    monkeypatch.setenv(CEILING_ENV, LIMIT)
    return str(sent.json()["id"])


def test_an_approval_after_the_ceiling_was_lowered_promotes_nothing(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    promotion = _waiting_then_lowered(pw, monkeypatch)
    answer = _studio("dana", f"/{promotion}/decision", "post", approve=True)
    assert _said(answer) == (409, "items_changed"), answer.text
    assert "above this deployment's highest marking, OFFICIAL" in answer.json()["detail"]
    assert pw.store.records[promotion].status == "rejected"
    _nothing_promoted(pw)


def test_the_load_itself_is_refused_above_the_ceiling_and_the_promotion_rejected(
    pw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approval's re-check planted out: the load's own last check, before its transaction
    begins, refuses it in the ceiling's words and leaves the promotion rejected, never waiting."""
    promotion = _waiting_then_lowered(pw, monkeypatch)
    _no_items_checked(monkeypatch)
    answer = _studio("dana", f"/{promotion}/decision", "post", approve=True)
    assert _said(answer) == (422, "above_the_deployments_highest_marking"), answer.text
    assert pw.store.records[promotion].status == "rejected"
    _nothing_promoted(pw)


def test_a_drawn_merges_match_above_the_ceiling_refuses_the_merge_and_writes_nothing(
    mw: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every drawn item within the ceiling, but the loaded Mercer held at OFFICIAL-SENSITIVE (held
    before the ceiling was lowered): the chosen match, marked as the stricter of its ends, would
    be written above the ceiling, so the merge is refused, naming the limit."""
    drawn = _three(mw)
    loaded = mw.graph._graph_nodes["p-loaded"]
    mw.graph._graph_nodes["p-loaded"] = loaded.model_copy(
        update={"handling": loaded.handling.model_copy(
            update={"classification": "OFFICIAL-SENSITIVE"})}
    )  # fmt: skip
    monkeypatch.setenv(CEILING_ENV, LIMIT)
    match = [{"drawn": drawn.mercer["element_id"], "loaded": "p-loaded"}]
    answer = _step(mw, "merge", "dana", item_ids=_ids(drawn), matches=match)
    assert _said(answer) == (422, "check_failed"), answer.text
    assert answer.json()["detail"] == (
        "A match would be marked OFFICIAL-SENSITIVE, above this deployment's highest marking, "
        "OFFICIAL."
    )
    _nothing_written(mw, drawn.mercer["element_id"])
