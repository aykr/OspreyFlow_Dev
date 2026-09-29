"""Golden tests for `postcode` — `01_DOMAIN_MODEL.md` §7."""

from __future__ import annotations

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.postcode import postcode


def test_lowercase_and_no_space_is_normalised() -> None:
    assert postcode("sw1a1aa") == "SW1A 1AA"


def test_already_correct_is_unchanged() -> None:
    assert postcode("SW1A 1AA") == "SW1A 1AA"


def test_extra_internal_whitespace_is_collapsed() -> None:
    assert postcode("M1   1AE") == "M1 1AE"


def test_short_outward_code() -> None:
    assert postcode("m11ae") == "M1 1AE"


def test_a_non_postcode_is_rejected_not_guessed() -> None:
    with pytest.raises(NormalisationError, match="not a recognisable UK postcode"):
        postcode("not a postcode")


def test_a_free_text_value_containing_a_postcode_is_still_rejected() -> None:
    """`postcode` validates a whole column; `address` is the adapter that
    finds one embedded in free text — the two are not interchangeable."""
    with pytest.raises(NormalisationError):
        postcode("10 Downing Street, London SW1A 2AA")
