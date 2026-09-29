"""Golden test — `person_name` (`01_DOMAIN_MODEL.md` §7)."""

from __future__ import annotations

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.person_name import person_name


def test_surname_comma_given_ordering() -> None:
    result = person_name("WILSON, Owen")
    assert result.family == "WILSON"
    assert result.given == "Owen"


def test_given_all_caps_surname_ordering() -> None:
    # 09_INGEST_STUDIO.md §7's own example.
    result = person_name("Owen WILSON")
    assert result.given == "Owen"
    assert result.family == "WILSON"


def test_ordinary_given_family_ordering_with_no_case_signal() -> None:
    result = person_name("Owen Wilson")
    assert result.given == "Owen"
    assert result.family == "Wilson"


def test_honorific_is_stripped() -> None:
    result = person_name("Dr Owen Wilson")
    assert result.given == "Owen"
    assert result.family == "Wilson"


def test_diacritics_are_preserved_not_transliterated() -> None:
    result = person_name("François Müller")
    assert result.given == "François"
    assert result.family == "Müller"


def test_single_token_is_a_mononym_family_only() -> None:
    result = person_name("Prince")
    assert result.given == ""
    assert result.family == "Prince"


def test_empty_name_is_rejected() -> None:
    with pytest.raises(NormalisationError):
        person_name("   ")
