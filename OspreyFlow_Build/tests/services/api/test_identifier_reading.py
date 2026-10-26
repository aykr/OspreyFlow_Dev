"""Reading a typed identifier (ADR-128 decision 1, B2): split from a line, a comma or a space,
its kind told from its shape, normalised by the Knowledge Adapter its recipe uses.

What a mistake would do, and the case that catches it:

- three spellings of one number counted as three
  (`test_three_spellings_of_one_number_read_as_one_identifier`);
- a number written with spaces shattered by the split into pieces that match nothing
  (`test_a_number_written_with_spaces_is_one_identifier`);
- a word typed in the search box rewritten, so another text's behaviour moved
  (`test_the_search_box_leaves_other_text_as_typed`);
- a phone number the search box does not normalise
  (`test_the_search_box_normalises_a_phone_number`).
"""

from __future__ import annotations

import pytest
from services.api.identifier_reading import (
    Reading,
    read_identifier,
    search_alternative,
    split_identifiers,
)


def test_a_list_is_split_from_a_line_a_comma_or_a_space() -> None:
    assert split_identifiers(["Z1234ZZ\nZ2345ZZ, Z3456ZZ Z4567ZZ,,\n\n  "]) == [
        "Z1234ZZ",
        "Z2345ZZ",
        "Z3456ZZ",
        "Z4567ZZ",
    ]


def test_each_string_of_the_list_is_split_the_same_way() -> None:
    assert split_identifiers(["Z1234ZZ", "Z2345ZZ,Z3456ZZ"]) == ["Z1234ZZ", "Z2345ZZ", "Z3456ZZ"]


def test_a_number_written_with_spaces_is_one_identifier() -> None:
    assert split_identifiers(["+44 7700 900123\n07700 900641, QQ 12 34 56 A"]) == [
        "+44 7700 900123",
        "07700 900641",
        "QQ 12 34 56 A",
    ]


def test_numbers_separated_only_by_a_space_are_split() -> None:
    assert split_identifiers(["07700900123 07700900641"]) == ["07700900123", "07700900641"]


def test_quotes_a_csv_cell_may_carry_are_dropped() -> None:
    assert split_identifiers(['"Z1234ZZ",\'Z2345ZZ\'']) == ["Z1234ZZ", "Z2345ZZ"]


@pytest.mark.parametrize(
    ("typed", "kind", "canonical"),
    [
        ("Z1234ZZ", "prison_number", "Z1234ZZ"),
        ("z1234zz", "prison_number", "Z1234ZZ"),
        ("QQ123456A", "nino", "QQ123456A"),
        ("qq 12 34 56 a", "nino", "QQ123456A"),
        ("SYN-70417", "account", "SYN-70417"),
        ("syn-70417", "account", "SYN-70417"),
        ("PC-Z1234ZZ", "account", "PC-Z1234ZZ"),
        ("07700 900123", "msisdn", "+447700900123"),
        ("+44 7700 900123", "msisdn", "+447700900123"),
        ("447700900123", "msisdn", "+447700900123"),
    ],
)
def test_the_kind_is_told_from_the_shape_and_normalised_by_its_adapter(
    typed: str, kind: str, canonical: str
) -> None:
    assert read_identifier(typed) == Reading(kind=kind, canonical=canonical)


@pytest.mark.parametrize("typed", ["", "hello", "12345", "07700 9006", "a b", "!!", "12-34"])
def test_anything_else_matches_nothing(typed: str) -> None:
    assert read_identifier(typed).kind == "unknown"


def test_three_spellings_of_one_number_read_as_one_identifier() -> None:
    keys = {read_identifier(t).key for t in ("+447700900123", "07700 900123", "0044 7700 900123")}
    assert len(keys) == 1


def test_a_prison_number_and_an_account_of_the_same_letters_stay_apart() -> None:
    assert read_identifier("Z1234ZZ").key != read_identifier("PC-Z1234ZZ").key


def test_the_search_box_normalises_a_phone_number() -> None:
    assert search_alternative("07700 900123") == "+447700900123"
    assert search_alternative("0044 7700 900123") == "+447700900123"


def test_the_search_box_normalises_an_account_reference() -> None:
    assert search_alternative("syn-70417") == "SYN-70417"


@pytest.mark.parametrize(
    "typed", ["+447700900123", "SYN-70417", "AB123456C", "Z1234ZZ", "alpha", "Smith", "12", ""]
)
def test_the_search_box_leaves_other_text_as_typed(typed: str) -> None:
    assert search_alternative(typed) is None
