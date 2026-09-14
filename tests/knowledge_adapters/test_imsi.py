"""Golden test — `imsi` (`01_DOMAIN_MODEL.md` §7)."""

from __future__ import annotations

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.imsi import imsi

_CANONICAL = "234150123456789"


def test_bare_15_digits_passes_through() -> None:
    assert imsi(_CANONICAL) == _CANONICAL


def test_mcc_mnc_separators_are_stripped() -> None:
    assert imsi("234-15-0123456789") == _CANONICAL
    assert imsi("234 15 0123456789") == _CANONICAL


@pytest.mark.parametrize("raw", ["23415012345678", "2341501234567890", "not-an-imsi-at-all"])
def test_wrong_length_or_non_digit_is_rejected(raw: str) -> None:
    with pytest.raises(NormalisationError):
        imsi(raw)
