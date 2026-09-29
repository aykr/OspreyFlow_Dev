"""Golden test — `imei` (`01_DOMAIN_MODEL.md` §7)."""

from __future__ import annotations

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.imei import imei

# A real-format, Luhn-valid 15-digit IMEI (TAC 490154, serial 203237, check digit 8).
_VALID_15 = "490154203237518"
_BODY = "49015420323751"


def test_14_digit_body_with_no_check_digit_passes_through() -> None:
    assert imei(_BODY) == _BODY


def test_valid_15_digit_imei_drops_the_check_digit() -> None:
    assert imei(_VALID_15) == _BODY


def test_16_digit_imeisv_drops_the_software_version_suffix() -> None:
    # IMEISV is TAC(8)+serial(6)+SV(2) — 16 digits, no check digit at all.
    assert imei(_BODY + "01") == _BODY


def test_slash_and_space_separators_are_stripped() -> None:
    assert imei("49-015420/3237518") == _BODY
    assert imei("49 0154 20 323751 8") == _BODY


def test_wrong_check_digit_is_rejected_not_coerced() -> None:
    with pytest.raises(NormalisationError):
        imei(_BODY + "9")  # 9 is not the valid Luhn check digit for this body


@pytest.mark.parametrize("raw", ["not-digits-at-all", "123456789012", "1" * 20])
def test_wrong_length_or_non_digit_is_rejected(raw: str) -> None:
    with pytest.raises(NormalisationError):
        imei(raw)
