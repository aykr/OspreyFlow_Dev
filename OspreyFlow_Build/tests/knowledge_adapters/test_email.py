"""Golden test — `email` (`01_DOMAIN_MODEL.md` §7)."""

from __future__ import annotations

import pytest

from knowledge_adapters.email import email
from knowledge_adapters.errors import NormalisationError


def test_case_folds_on_both_local_and_domain() -> None:
    assert email("Analyst.One@Example.COM") == "analyst.one@example.com"


def test_plus_addressing_is_preserved_not_folded_away() -> None:
    assert email("user+tag@example.com") == "user+tag@example.com"


def test_unicode_domain_becomes_punycode() -> None:
    assert email("contact@café.fr") == "contact@xn--caf-dma.fr"


@pytest.mark.parametrize("raw", ["not-an-email", "@example.com", "user@", "user@@example.com"])
def test_malformed_addresses_are_rejected(raw: str) -> None:
    with pytest.raises(NormalisationError):
        email(raw)
