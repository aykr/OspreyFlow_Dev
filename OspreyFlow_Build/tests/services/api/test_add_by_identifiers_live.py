"""Add many from a list, against the real ArcadeDB adapter (ADR-128 decision 1, B2; rule 3 and 4).

**Live.** Needs the throwaway ArcadeDB, so the coordinator runs it (rule 14); nothing else here
opens a connection. `test_add_by_identifiers.py` proves what the resolution does with the answers
`find_node` gives; this is the other half, that the adapter's own access filter makes a person the
reader may not see answer as one nobody holds, through the real `resolve_identifiers`.

- **The access test.** A person above the reader's clearance, a person in a dataset the case does
  not read, and a made-up identifier give one answer to the reader (same counts, same nodes), and
  the filter is real because a reader cleared for the first finds that person (the red half).
- **Kinds.** A prison number, a National Insurance number, a number written two ways and an account
  reference each resolve to their node; a PIN (`handle`) holding an account's text is no match.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.add_by_identifiers import IdentifierCounts, resolve_identifiers

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

ONTOLOGY = load_default_ontology()
READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["fixture"])
CLEARED = READER.model_copy(update={"clearance": "SECRET"})
OTHER_CASE = READER.model_copy(update={"datasets": ["elsewhere"]})


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture", locator="row:1", excerpt_hash="")],
        first_seen=datetime.now(UTC),
    )


def _write(kind: str, props: dict[str, str], classification: str = "OFFICIAL",
           dataset: str = "fixture") -> NodeWrite:
    handling = Handling(classification=classification, handling_code="P", originator="unit-1",
                        owning_unit="unit-1")
    return NodeWrite(id=new_id(), type=kind, properties=props, provenance=_provenance(),
                     handling=handling, created_by="loader", created_at=datetime.now(UTC),
                     datasets=[dataset])


def _person(**ids: str) -> NodeWrite:
    return _write("Person", {"family_name": "Test", **ids})


def _endpoint(value: str, kind: str) -> NodeWrite:
    props = {"value_raw": value, "value_normalised": value, "endpoint_kind": kind}
    return _write("Endpoint", props)


async def test_a_person_the_reader_may_not_see_answers_as_a_made_up_one() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        seen = _person(prison_number="Z1111ZZ")
        above = _write("Person", {"family_name": "Test", "prison_number": "Z2222ZZ"}, "SECRET")
        elsewhere = _write("Person", {"family_name": "Test", "prison_number": "Z3333ZZ"},
                           dataset="elsewhere")
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([seen, above, elsewhere], tx)
        await graph.commit_transaction(tx)

        around = ["Z1111ZZ"]
        made_up = await resolve_identifiers(graph, [*around, "Z9999ZZ"], READER)
        for hidden in ("Z2222ZZ", "Z3333ZZ"):
            answer = await resolve_identifiers(graph, [*around, hidden], READER)
            assert answer.counts == made_up.counts == IdentifierCounts(
                read=2, found=1, matched_nothing=1, repeated=0
            )
            assert [n.id for n in answer.nodes] == [n.id for n in made_up.nodes] == [seen.id]
        # The filter is what hid them: cleared for it, the reader finds the SECRET one, and a case
        # reading the other dataset finds the other.
        cleared = await resolve_identifiers(graph, ["Z2222ZZ"], CLEARED)
        assert [n.id for n in cleared.nodes] == [above.id]
        elsewhere_found = await resolve_identifiers(graph, ["Z3333ZZ"], OTHER_CASE)
        assert [n.id for n in elsewhere_found.nodes] == [elsewhere.id]


async def test_each_kind_resolves_to_its_node_and_a_pin_is_not_an_account() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        person = _person(prison_number="Z1111ZZ", nino="QQ111111A")
        number = _endpoint("+447700900640", "msisdn")
        account = _endpoint("SYN-70417", "account")
        pin = _endpoint("PIN-Z1111ZZ", "handle")
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([person, number, account, pin], tx)
        await graph.commit_transaction(tx)

        typed = ["Z1111ZZ\nQQ 11 11 11 A\n07700 900640\n+44 7700 900640\nsyn-70417\nPIN-Z1111ZZ"]
        result = await resolve_identifiers(graph, typed, READER)
        assert result.counts == IdentifierCounts(read=6, found=5, matched_nothing=1, repeated=1)
        assert {n.id for n in result.nodes} == {person.id, number.id, account.id}
