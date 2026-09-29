"""Golden tests for `grid_ref` — `01_DOMAIN_MODEL.md` §7. Test vectors are
computed forward from real WGS84 coordinates via `pyproj` (see
`tests/knowledge_adapters/test_coordinates.py`'s British National Grid
fixture for the same pattern), not typed in from a half-remembered
example, so a wrong digit shows up as a failing assertion rather than a
plausible-looking test that happens to pass either way.

Norwich Cathedral, EPSG:27700 (623324, 308791) truncated to whole metres —
`TG 23324 08791` — is the full-precision (1 m) reference used throughout;
`TG 233 087` is the same point at 100 m precision.
"""

from __future__ import annotations

import pytest

from knowledge_adapters.coordinates import geometry_reference
from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.grid_ref import grid_ref

_EXPECTED_REF = geometry_reference("EPSG:27700", 623324.0, 308791.0)


def test_a_bare_reference_string_with_spaces_parses_to_the_right_point() -> None:
    assert grid_ref("TG 23324 08791") == _EXPECTED_REF


def test_a_bare_reference_string_with_no_spaces_parses_to_the_same_point() -> None:
    assert grid_ref("TG2332408791") == _EXPECTED_REF


def test_lowercase_letters_are_accepted() -> None:
    assert grid_ref("tg 23324 08791") == _EXPECTED_REF


def test_the_three_column_split_form_parses_to_the_same_point() -> None:
    assert grid_ref(("TG", "23324", "08791")) == _EXPECTED_REF


def test_lower_precision_is_a_genuinely_different_point_not_the_same_ref() -> None:
    """100 m precision (`TG 233 087`) is a coarser reference to the same
    neighbourhood, not the same point as the 1 m one — the two must not
    collide onto one `geometry_ref`."""
    coarse = grid_ref("TG 233 087")
    assert coarse != _EXPECTED_REF
    assert coarse == geometry_reference("EPSG:27700", 623300.0, 308700.0)


def test_the_grids_true_origin_square_sv_is_recognised() -> None:
    """`SV` is `e100k=0, n100k=0` — the Isles of Scilly, the grid's own
    origin square. If the letter-pair algorithm is wrong, this is usually
    the first case to fail."""
    assert grid_ref("SV 00000 00000") == geometry_reference("EPSG:27700", 0.0, 0.0)


def test_londons_square_tq_is_recognised() -> None:
    assert grid_ref("TQ 00000 00000") == geometry_reference("EPSG:27700", 500000.0, 100000.0)


def test_an_unrecognised_letter_pair_is_rejected_not_guessed() -> None:
    with pytest.raises(NormalisationError, match="decodes outside Great Britain"):
        grid_ref("ZZ 123 456")


def test_a_non_letter_prefix_is_rejected() -> None:
    with pytest.raises(NormalisationError, match="not a recognisable British National Grid"):
        grid_ref("T1 123 456")


def test_an_odd_number_of_digits_cannot_split_evenly_and_is_rejected() -> None:
    with pytest.raises(NormalisationError, match="odd number of digits"):
        grid_ref("TG 12 345")


def test_the_three_column_form_requires_exactly_three_fields() -> None:
    with pytest.raises(NormalisationError):
        grid_ref(("TG", "23324"))
