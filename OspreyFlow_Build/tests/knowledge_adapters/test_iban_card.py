"""Golden test — `iban` / `card` (`01_DOMAIN_MODEL.md` §7)."""

from __future__ import annotations

import hashlib

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.iban_card import card, iban

_VALID_IBAN = "GB29NWBK60161331926819"
_VALID_PAN = "4111111111111111"


def test_iban_spacing_is_stripped_and_checksum_validated() -> None:
    assert iban("GB29 NWBK 6016 1331 9268 19") == _VALID_IBAN
    assert iban(_VALID_IBAN.lower()) == _VALID_IBAN


def test_iban_with_bad_checksum_is_rejected() -> None:
    with pytest.raises(NormalisationError):
        iban("GB00NWBK60161331926819")


def test_card_spacing_is_stripped_and_luhn_validated() -> None:
    result = card("4111 1111 1111 1111")
    assert result.last_four == "1111"
    assert result.hash == hashlib.sha256(_VALID_PAN.encode("ascii")).hexdigest()


def test_masked_card_extracts_last_four_but_has_no_hash() -> None:
    result = card("4111********1111")
    assert result.last_four == "1111"
    assert result.hash is None


def test_card_failing_luhn_is_rejected() -> None:
    with pytest.raises(NormalisationError):
        card("4111111111111112")
