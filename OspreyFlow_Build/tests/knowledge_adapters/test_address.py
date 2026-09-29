"""Golden test — `address` (`01_DOMAIN_MODEL.md` §7)."""

from __future__ import annotations

import pytest

from knowledge_adapters.address import address
from knowledge_adapters.errors import NormalisationError


def test_uk_postcode_is_detected_and_normalised() -> None:
    result = address("221B Baker Street, London, nw16xe")
    assert result.postcode == "NW1 6XE"
    assert result.lines == ["221B Baker Street", "London", "nw16xe"]


def test_gazetteer_id_is_never_attached_in_phase_2() -> None:
    result = address("221B Baker Street, London, NW1 6XE")
    assert result.gazetteer_id is None


def test_address_with_no_postcode_still_structures_the_lines() -> None:
    result = address("100 Main Street\nSomewhere, ST 12345")
    assert result.postcode is None
    assert result.lines == ["100 Main Street", "Somewhere", "ST 12345"]


def test_empty_address_is_rejected() -> None:
    with pytest.raises(NormalisationError):
        address("   ")
