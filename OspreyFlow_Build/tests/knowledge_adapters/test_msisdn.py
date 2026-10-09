"""Golden test — `msisdn` (`01_DOMAIN_MODEL.md` §7).

The four renderings here are `01_DOMAIN_MODEL.md` §7's own example and
`08_ACCEPTANCE_SCENARIOS.md` B1's "all four renderings ... resolve to one
`Endpoint`" — every one of them must produce the identical canonical value.
"""

from __future__ import annotations

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.msisdn import msisdn

_CANONICAL = "+441621926368"

_GOLDEN_VARIANTS = [
    "01621926368",
    "+44(0)1621926368",
    "441621926368",
    "#31#01621926368",
    "+441621926368",
    "  01621926368  ",
]


@pytest.mark.parametrize("raw", _GOLDEN_VARIANTS)
def test_every_rendering_resolves_to_the_same_e164_value(raw: str) -> None:
    assert msisdn(raw) == _CANONICAL


def test_extension_is_dropped_from_the_canonical_e164_value() -> None:
    assert msisdn("01621926368x123") == _CANONICAL


@pytest.mark.parametrize(
    "raw",
    [
        "not a phone number",
        "123",
        "",
    ],
)
def test_unparseable_or_invalid_numbers_are_rejected_not_guessed(raw: str) -> None:
    with pytest.raises(NormalisationError):
        msisdn(raw)


# --- ADR-103: Ofcom's reserved drama numbers are numbers -------------------------------------
#
# 9 October 2026, the data engineer's journey: every number in a synthetic CDR was rejected as
# "not a valid phone number", because `phonenumbers` treats the ranges Ofcom reserves for drama as
# unallocated — and those ranges are the only numbers `CLAUDE.md` rule 9's synthetic data may use
# (`scripts/seed_scenarios.py`, `tests/test_seed_scenarios.py`). The planted values are the ones a
# synthetic source actually holds, in the renderings a carrier export actually uses.


@pytest.mark.parametrize(
    "raw",
    ["07700900461", "+44 7700 900461", "447700900461", "+44(0)7700 900461", "#31#07700900461"],
)
def test_a_drama_mobile_number_resolves_in_every_rendering(raw: str) -> None:
    assert msisdn(raw) == "+447700900461"


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("020 7946 0123", "+442079460123"),
        ("0113 496 0999", "+441134960999"),
        ("0161 496 0000", "+441614960000"),
        ("028 9649 6123", "+442896496123"),
        ("029 2018 0123", "+442920180123"),
        ("01632 960123", "+441632960123"),
        ("0808 157 0123", "+448081570123"),
    ],
)
def test_the_geographic_and_non_geographic_drama_ranges_resolve(raw: str, canonical: str) -> None:
    assert msisdn(raw) == canonical


@pytest.mark.parametrize("raw", ["0770090046", "077009004611", "+44 7700 90046"])
def test_a_drama_number_of_the_wrong_length_is_still_refused(raw: str) -> None:
    with pytest.raises(NormalisationError):
        msisdn(raw)


# 9 October 2026: `phonenumbers` reads letters as keypad digits, so "0800 FLOWERS" became a real
# freephone number and "07700 900 ABC" became +447700900222. In a carrier's or a seizure's number
# field a letter is corruption, not a rendering `01_DOMAIN_MODEL.md` §7 names, and turning it into
# a different, plausible number is a guess. Letters are allowed only as an extension marker.
@pytest.mark.parametrize("raw", ["0800 FLOWERS", "07700 900 ABC", "+44 7700 9OO461", "0162192636B"])
def test_a_number_with_letters_in_it_is_refused_not_read_as_a_keypad(raw: str) -> None:
    with pytest.raises(NormalisationError):
        msisdn(raw)


@pytest.mark.parametrize("raw", ["01621926368 ext 123", "01621926368 ext. 123", "01621926368X123"])
def test_an_extension_marker_is_still_read_as_one(raw: str) -> None:
    assert msisdn(raw) == _CANONICAL
