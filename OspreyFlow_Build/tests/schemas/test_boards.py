"""Drawing boards' shapes (ADR-143 decision 4, `schemas/boards.py`; L3.3).

What a mistake here would do, and the case that catches it:

- a grade outside its scheme stored as if it were one (3x5x2 has no source D, 5x5x5 no handling P):
  `test_a_grade_outside_its_scheme_is_refused`;
- a drawn item with no source at all, which decision 4 forbids: `test_a_drawn_item_needs_a_source`;
- every element that is not drawn stored differently from before (a `drawn: null` key added to every
  provenance, so every stored fingerprint and golden file moves):
  `test_an_undrawn_provenance_is_stored_exactly_as_before`, red with the serializer removed
  (`test_the_undrawn_check_fails_without_the_serializer`);
- the drawn assertion lost on its way through the store's JSON: `test_a_drawn_assertion_round_trips`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError, model_serializer
from schemas.boards import BoardInput, DrawnItemInput
from schemas.domain import (
    DrawnAssertion,
    Grading,
    Provenance,
    ProvenanceState,
    SourceRef,
)

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def _provenance(drawn: DrawnAssertion | None = None) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="drawn:i1", locator="alice", excerpt_hash="")],
        first_seen=NOW,
        drawn=drawn,
    )


def _drawn(**over: Any) -> DrawnAssertion:
    given: dict[str, Any] = {
        "item_id": "i1",
        "asserted_by": "alice",
        "board_id": "b1",
        "case_id": "case-k",
        "label": "Unknown male “Tall”",
        "grading": Grading(source="B", intelligence="2", handling="1"),
        "source_note": "Wing officer report, 4 Nov",
    }
    given.update(over)
    return DrawnAssertion(**given)


@pytest.mark.parametrize(
    ("scheme", "source", "intelligence", "handling"),
    [("3x5x2", "D", "1", "P"), ("5x5x5", "A", "1", "P"), ("5x5x5", "A", "6", "1")],
)
def test_a_grade_outside_its_scheme_is_refused(
    scheme: str, source: str, intelligence: str, handling: str
) -> None:
    with pytest.raises(ValidationError):
        Grading(scheme=scheme, source=source, intelligence=intelligence, handling=handling)  # type: ignore[arg-type]


def test_a_grade_in_each_scheme_is_kept_with_its_scheme() -> None:
    assert Grading(scheme="3x5x2", source="C", intelligence="5", handling="C").scheme == "3x5x2"
    assert Grading(source="E", intelligence="5", handling="5").scheme == "5x5x5"


def test_a_drawn_item_needs_a_source() -> None:
    with pytest.raises(ValidationError):
        _drawn(source_note="  ", source_document=None)
    with pytest.raises(ValidationError):
        DrawnItemInput(
            type="Person",
            label="Tall",
            marking="OFFICIAL",
            grading=Grading(source="B", intelligence="2", handling="1"),
        )
    assert _drawn(source_note=None, source_document="doc-1").source_document == "doc-1"


def test_an_undrawn_provenance_is_stored_exactly_as_before() -> None:
    assert "drawn" not in _provenance().model_dump(mode="json")


def test_the_undrawn_check_fails_without_the_serializer() -> None:
    """Rule 15: the plant is the serializer with its one line, the pop, taken out. Pydantic binds a
    serializer when the class is made, so the plant is a subclass declaring the same serializer by
    the same name without the pop; the check above, run against it, must fail."""

    class KeepsEveryKey(Provenance):
        @model_serializer(mode="wrap")
        def _leave_out_undrawn(self, handler: Any) -> dict[str, Any]:
            data: dict[str, Any] = handler(self)
            return data

    plain = KeepsEveryKey.model_validate(_provenance().model_dump())
    assert "drawn" in plain.model_dump(mode="json")


def test_a_drawn_assertion_round_trips() -> None:
    stored = _provenance(_drawn()).model_dump(mode="json")
    back = Provenance.model_validate(stored)
    assert back.drawn is not None
    assert back.drawn.provenance_class == "analyst_drawn"
    assert back.drawn.grading.source == "B"
    assert back.drawn.board_id == "b1"


def test_a_board_starts_whole() -> None:
    with pytest.raises(ValidationError):
        BoardInput(name="b", start="view")
    with pytest.raises(ValidationError):
        BoardInput(name="b", start="selection", node_ids=[])
    with pytest.raises(ValidationError):
        BoardInput(name="b", start="blank", node_ids=["n1"])
    assert BoardInput(name="b", start="selection", node_ids=["n1"]).node_ids == ["n1"]
