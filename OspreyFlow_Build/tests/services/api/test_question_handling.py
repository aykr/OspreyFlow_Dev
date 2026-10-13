"""ADR-114 Amendment 6: a question reads several Documents at once, so it goes under their handling
only when every one carries the same code; otherwise under none — and material whose handling is
not given never reaches a client's provider (`model_routing.py`)."""

from __future__ import annotations

from services.api.questions import shared_handling

from schemas.domain import Handling


def _h(code: str) -> Handling:
    return Handling(classification="OFFICIAL", handling_code=code, owning_unit="u", originator="u")


def test_documents_of_one_code_are_asked_about_under_it() -> None:
    assert shared_handling([_h("P"), _h("P")]) == _h("P")


def test_documents_of_mixed_codes_are_asked_about_under_none() -> None:
    assert shared_handling([_h("P"), _h("C")]) is None
