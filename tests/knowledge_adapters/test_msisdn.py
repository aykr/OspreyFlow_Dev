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
