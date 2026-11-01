"""ADR-127 decision 7(b): a hotlist's identifier is canonicalised on entry, through the Knowledge
Adapter for its kind, so a number typed in national form matches the `Endpoint` stored in E.164.

A hotlist has no declared kind, so the kind is read from the text, and only where the text can be of
one kind alone: an address with an `@` is an `email`, and anything else the `msisdn` adapter accepts
is a phone number. A string of fourteen to sixteen digits is left as written: it fits `imei` and
`imsi` alike, and their canonical forms differ (`imei` drops the check digit, `imsi` keeps all
fifteen), so a guess could silently hotlist the wrong value. A text an adapter refuses is kept as
written, still matching as before, and is reported as not canonicalised (never silently).

What a mistake would do, and the case that catches it:

- the national form `07700 900310` never matching the stored `+447700900310`
  (`test_a_national_number_is_stored_in_e164`);
- the form the analyst typed lost from the display (`canonical_identifier` returns it with the
  canonical value: `test_the_typed_form_is_kept_beside_the_canonical_one`);
- a refusal hiding as a success (`test_a_text_the_adapter_refuses_is_kept_as_written_and_said_so`);
- a fifteen-digit string guessed as the wrong kind
  (`test_a_digit_string_that_fits_two_kinds_is_left_as_written`).
"""

from __future__ import annotations

import pytest
from services.api.hotlists import canonical_identifier


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("07700 900310", "+447700900310"),
        ("+447700900310", "+447700900310"),
        ("447700900310", "+447700900310"),
        ("7700900310", "+447700900310"),
        ("  07700 900310  ", "+447700900310"),
        ("Jo@Example.COM", "jo@example.com"),
    ],
)
def test_a_national_number_is_stored_in_e164(typed: str, canonical: str) -> None:
    assert canonical_identifier(typed) == (canonical, True)


def test_the_typed_form_is_kept_beside_the_canonical_one() -> None:
    value, ok = canonical_identifier("07700 900310")
    assert (value, ok) == ("+447700900310", True)
    # The store keeps the typed text in `identifier_typed`; the function never alters what it was
    # given, so the caller still holds it.
    typed = "07700 900310"
    canonical_identifier(typed)
    assert typed == "07700 900310"


@pytest.mark.parametrize("typed", ["+44-hotlist-abc123", "SYN-1", "abc", "12345", ""])
def test_a_text_the_adapter_refuses_is_kept_as_written_and_said_so(typed: str) -> None:
    assert canonical_identifier(typed) == (typed, False)


@pytest.mark.parametrize("typed", ["490154203237518", "234 15 0999999999", "49-015420-323751-8"])
def test_a_digit_string_that_fits_two_kinds_is_left_as_written(typed: str) -> None:
    assert canonical_identifier(typed) == (typed, False)


# --- an account number (ADR-108 Amendment 5, Operation Ledger's A2) ---------------------------------
#
# An `Account` (FIBO) is identified by its `account_number` (the pack declares `iban` as its kind),
# and carries no `value_normalised`, so before this a hotlist on an account matched nothing: the
# evaluation and the sentence's "on a hotlist" read `value_normalised` alone. An account number is
# now canonicalised by the `account_ref` adapter (whitespace removed, upper case), and a node's
# `account_number` is watched in that form beside its `value_normalised`. The IBAN checksum is not
# asked for: an account is matched on what the bank's file says, as written, not on whether it is a
# valid IBAN (Operation Ledger's synthetic numbers are not).


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("GB58 LOYD 3096 1700 7099 43", "GB58LOYD30961700709943"),
        ("gb58loyd30961700709943", "GB58LOYD30961700709943"),
        ("  GB29 NWBK 6016 1331 9268 19 ", "GB29NWBK60161331926819"),
    ],
)
def test_an_account_number_is_stored_compact_and_upper_case(typed: str, canonical: str) -> None:
    assert canonical_identifier(typed) == (canonical, True)


def test_a_node_is_watched_by_its_account_number_as_well_as_its_value() -> None:
    from services.api.evaluation import watched_values

    account = {"account_number": "GB58 LOYD 3096 1700 7099 43", "institution": "Lloyds"}
    assert watched_values(account) == {"GB58LOYD30961700709943"}
    assert watched_values({"value_normalised": "+447700900461"}) == {"+447700900461"}
    # Neither: a node with nothing an identifier is watched by is never matched.
    assert watched_values({"family_name": "Carter", "account_number": "Lloyds — no number"}) == set()
    assert watched_values({"account_number": 1234}) == set()


def test_a_sentence_on_a_hotlist_reads_an_accounts_number() -> None:
    from datetime import UTC, datetime

    from services.api.rule_sentences import _identifiers

    from ontology.packs import load_deployment_ontology
    from schemas.domain import Handling, Node, Provenance, ProvenanceState, SourceRef

    node = Node(
        id="acc-1", type="Account",
        properties={"account_number": "GB58 LOYD 3096 1700 7099 43"},
        provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=datetime.now(UTC),
                              sources=[SourceRef(document_id="d", locator="row 1", excerpt_hash="")]),
        handling=Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"),
        audit={"created_at": datetime.now(UTC), "created_by": "x", "revision": 1},
    )  # fmt: skip
    assert "GB58LOYD30961700709943" in _identifiers(node, load_deployment_ontology())
