"""Golden test — `account_ref` (`01_DOMAIN_MODEL.md` §7; ADR-127 decision 4).

A bank or private-cash account reference is canonicalised: trimmed, internal whitespace removed,
upper-cased. An empty value, or a character outside letters, digits, `-` and `/`, is refused with
the rule named and never the value. Nothing else is checked: no check digits, no country logic.

The accepted and refused tables are the golden file; every value is synthetic. The engine test that
three spellings of one account give one `Endpoint` is `tests/ingest/test_account_ref_engine.py`.
"""

from __future__ import annotations

import pytest

from knowledge_adapters import ARITY, REGISTRY
from knowledge_adapters.account_ref import account_ref
from knowledge_adapters.errors import NormalisationError

ACCEPTED: list[tuple[str, str]] = [
    ("SYN-70417", "SYN-70417"),
    (" syn-70417 ", "SYN-70417"),
    ("syn 70417", "SYN70417"),
    ("SYN-00988", "SYN-00988"),
    ("syn\t70417", "SYN70417"),
    ("  syn / 4 12 ", "SYN/412"),
    ("Syn- 70417", "SYN-70417"),
    ("70417", "70417"),
    # A no-break space is whitespace too, removed like any other (Unicode `\s`), not refused.
    ("SYN\u00a070417", "SYN70417"),
]

#: value, and the rule its refusal must name.
REFUSED: list[tuple[str, str]] = [
    ("", "empty"),
    ("   ", "empty"),
    ("\t\n", "empty"),
    ("SYN#70417", "outside"),
    ("SYN_70417", "outside"),
    ("SYN.70417", "outside"),
    ("SYN:70417", "outside"),
    ("SYNé70417", "outside"),  # a letter outside A-Z
    ("SYNß1", "outside"),  # would upper-case to ASCII "SS" if checked after upper-casing
    ("SYN-７０４１７", "outside"),  # full-width digits are not digits here
    ("SYN​70417", "outside"),  # a zero-width space is not whitespace to strip
]


@pytest.mark.parametrize(("raw", "canonical"), ACCEPTED)
def test_golden_accepted(raw: str, canonical: str) -> None:
    assert account_ref(raw) == canonical


@pytest.mark.parametrize(("raw", "rule"), REFUSED)
def test_golden_refused(raw: str, rule: str) -> None:
    with pytest.raises(NormalisationError) as refusal:
        account_ref(raw)
    assert refusal.value.adapter == "account_ref"
    assert rule in refusal.value.reason


@pytest.mark.parametrize(("raw", "_rule"), REFUSED)
def test_a_reason_names_the_rule_and_quotes_no_value(raw: str, _rule: str) -> None:
    with pytest.raises(NormalisationError) as refusal:
        account_ref(raw)
    reason = refusal.value.reason
    assert reason
    for fragment in {raw, raw.strip(), *raw.split()}:
        if fragment:
            assert fragment not in reason


def test_canonicalising_twice_changes_nothing() -> None:
    for raw, _ in ACCEPTED:
        once = account_ref(raw)
        assert account_ref(once) == once


def test_it_checks_nothing_but_the_character_set() -> None:
    # No check digit and no country logic: a well-formed IBAN-shaped value is just characters.
    assert account_ref("gb00 xxxx 0000") == "GB00XXXX0000"


def test_a_recipe_can_name_it_and_it_takes_one_column() -> None:
    assert REGISTRY["account_ref"] is account_ref
    assert "account_ref" not in ARITY
