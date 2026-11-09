"""The deployment's grading scheme on the boards (`spec/06_DECISIONS.md` ADR-143 decision 11; L3.7):
an opened board offers the scheme `grading.scheme` names, and a drawn node, link or edit graded in
any other scheme is refused in words before anything is written, so every drawn item stays in the
one scheme the change command maps from (an item in another scheme would refuse the whole change).

Each test was shown red by a plant at its call site in `services/api/app.py`
(`process/lanes/case-b/L3.7_RED_RECORD.md`)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from services.api.app import app
from services.api.config import GradingSettings

from schemas.domain import GradingSchemeAnswer

from .test_boards import GRADE, K, _as, _board, _item, _link, world  # noqa: F401  (a fixture)

THREE = {"scheme": "3x5x2", "source": "A", "intelligence": "1", "handling": "P"}


def _writes(world: SimpleNamespace) -> int:
    return len(world.graph.node_writes) + len(world.graph.edge_writes)


@pytest.fixture
def three_by_five(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setattr(app.state, "grading", GradingSettings.of("3x5x2"), raising=False)
    return world


def test_an_opened_board_offers_the_deployments_scheme(three_by_five: SimpleNamespace) -> None:
    board = _board(start="blank")
    opened = _as("alice").get(f"/v1/investigations/{K}/boards/{board}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["grading_scheme"] == "3x5x2"


def test_an_opened_board_offers_5x5x5_by_default(world: SimpleNamespace) -> None:
    board = _board(start="blank")
    assert _as("alice").get(f"/v1/investigations/{K}/boards/{board}").json()[
        "grading_scheme"
    ] == "5x5x5"


def test_a_drawn_item_in_another_scheme_is_refused_before_anything_is_written(
    three_by_five: SimpleNamespace,
) -> None:
    board = _board(start="blank")
    before = _writes(three_by_five)
    answer = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "OFFICIAL", "grading": GRADE,
              "source_note": "n"},
    )  # fmt: skip
    assert answer.status_code == 422, answer.text
    assert answer.json()["error"] == "grading_scheme"
    assert "3x5x2" in answer.json()["detail"] and "5x5x5" in answer.json()["detail"]
    assert _writes(three_by_five) == before
    # In the deployment's own scheme, it is drawn.
    _item(board, grading=THREE)


def test_a_drawn_link_in_another_scheme_is_refused_before_anything_is_written(
    three_by_five: SimpleNamespace,
) -> None:
    board = _board(start="selection", node_ids=["p-loaded"])
    person = _item(board, grading=THREE)["element_id"]
    before = _writes(three_by_five)
    refused = _link(board, person, "p-loaded")  # graded GRADE, in 5x5x5
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "grading_scheme"
    assert _writes(three_by_five) == before
    assert _link(board, person, "p-loaded", grading=THREE).status_code == 201


def test_an_edit_to_a_grade_in_another_scheme_is_refused_before_anything_is_written(
    three_by_five: SimpleNamespace,
) -> None:
    board = _board(start="blank")
    item = _item(board, grading=THREE)["item_id"]
    before = _writes(three_by_five)
    refused = _as("alice").patch(
        f"/v1/investigations/{K}/board-items/{item}", json={"grading": GRADE}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "grading_scheme"
    assert _writes(three_by_five) == before
    # An edit that leaves the grade alone is not refused for it.
    assert _as("alice").patch(
        f"/v1/investigations/{K}/board-items/{item}", json={"label": "y"}
    ).status_code == 200


FORCE = GradingSchemeAnswer(
    scheme="force-4x3", source=["W", "X", "Y", "Z"], intelligence=["1", "2", "3"], handling=["H"]
)


def test_a_scheme_files_grades_are_offered_and_checked(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 6: a scheme file's scheme is known only from the setting, so the board says its
    grades, and a grade that is not one of them is refused though `Grading` alone accepts it."""
    monkeypatch.setattr(app.state, "grading", GradingSettings(grades=FORCE), raising=False)
    board = _board(start="blank")
    opened = _as("alice").get(f"/v1/investigations/{K}/boards/{board}").json()
    assert opened["grading_scheme"] == "force-4x3"
    assert opened["grading_grades"] == FORCE.model_dump(mode="json")
    before = _writes(world)
    refused = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "OFFICIAL", "source_note": "n",
              "grading": {"scheme": "force-4x3", "source": "Q", "intelligence": "1",
                          "handling": "H"}},
    )  # fmt: skip
    assert refused.status_code == 422, refused.text
    assert "source 'Q' is not a grade of force-4x3" in refused.json()["detail"]
    assert _writes(world) == before
    _item(board, grading={"scheme": "force-4x3", "source": "W", "intelligence": "3",
                          "handling": "H"})  # fmt: skip
