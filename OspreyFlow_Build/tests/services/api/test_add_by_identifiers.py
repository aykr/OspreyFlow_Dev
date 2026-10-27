"""Resolving a list of typed identifiers to what the analyst may see (ADR-128 decision 1, B2).

The access filter itself is the adapter's (`find_node` reads under the principal's handling and
datasets), so this file proves what the resolution does with the answers, with a graph that holds
what the principal may see and answers `None` for everything else, as the adapter does for a hidden
node and an absent one alike. The live case that the real adapter's filter makes a hidden node
answer so is `test_add_by_identifiers_live.py`.

What a mistake would do, and the case that catches it:

- an identifier the analyst may not see counted differently from one that does not exist, or looked
  up differently (`test_a_hidden_identifier_and_a_made_up_one_give_the_same_counts_and_work`);
- three spellings of one number counted as three nodes
  (`test_three_spellings_of_one_number_count_once`);
- a number of one kind matching an endpoint of another
  (`test_an_endpoint_of_another_kind_is_not_a_match`);
- 5,001 identifiers truncated rather than refused (`test_more_than_5000_is_refused_by_name`);
- the add given the typed strings' own order lost, or a repeat added twice
  (`test_a_repeated_identifier_adds_one_node`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.add_by_identifiers import (
    MAX_IDENTIFIERS,
    IdentifierCounts,
    TooManyIdentifiersError,
    resolve_identifiers,
)

from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


def _node(node_id: str, kind: str, props: dict[str, Any]) -> Node:
    return Node(
        id=node_id,
        type=kind,
        properties=props,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


def _person(node_id: str, **ids: str) -> Node:
    return _node(node_id, "Person", {"family_name": "Test", **ids})


def _endpoint(node_id: str, value: str, kind: str) -> Node:
    return _node(
        node_id, "Endpoint", {"value_normalised": value, "endpoint_kind": kind, "value_raw": value}
    )


class _Graph:
    """What the principal may see, keyed by `(type, field, value)`. Everything else, a node that
    exists above the principal's clearance included, is `None`, as the adapter answers."""

    def __init__(self, *visible: tuple[str, str, str, Node]) -> None:
        self.visible = {(t, f, v): n for t, f, v, n in visible}
        self.calls: list[tuple[str, str, str]] = []

    async def find_node(
        self,
        entity_type: str,
        identifier_field: str,
        value: str,
        principal: Principal,
        *,
        also: dict[str, str] | None = None,
    ) -> Node | None:
        self.calls.append((entity_type, identifier_field, value))
        return self.visible.get((entity_type, identifier_field, value))


def _graph() -> _Graph:
    return _Graph(
        ("Person", "prison_number", "Z1234ZZ", _person("p1", prison_number="Z1234ZZ")),
        ("Person", "nino", "QQ123456A", _person("p2", nino="QQ123456A")),
        ("Endpoint", "value_normalised", "+447700900123",
         _endpoint("e1", "+447700900123", "msisdn")),
        ("Endpoint", "value_normalised", "SYN-70417", _endpoint("e2", "SYN-70417", "account")),
        # An endpoint of another kind holding a value an account reference reads as.
        ("Endpoint", "value_normalised", "PIN-Z2345ZZ", _endpoint("e3", "PIN-Z2345ZZ", "handle")),
    )


async def test_mixed_kinds_resolve_through_the_access_filtered_lookup() -> None:
    graph = _graph()
    typed = ["Z1234ZZ, QQ123456A\n07700900123 SYN-70417", "Z9999ZZ", "hello"]
    result = await resolve_identifiers(graph, typed, ANALYST)
    assert result.counts == IdentifierCounts(read=6, found=4, matched_nothing=2, repeated=0)
    assert [n.id for n in result.nodes] == ["p1", "p2", "e1", "e2"]
    assert ("Person", "prison_number", "Z1234ZZ") in graph.calls
    assert ("Person", "nino", "QQ123456A") in graph.calls
    assert ("Endpoint", "value_normalised", "+447700900123") in graph.calls
    assert ("Endpoint", "value_normalised", "SYN-70417") in graph.calls


async def test_three_spellings_of_one_number_count_once() -> None:
    graph = _graph()
    result = await resolve_identifiers(
        graph, ["+447700900123\n07700 900123\n0044 7700 900123"], ANALYST
    )
    assert [n.id for n in result.nodes] == ["e1"]
    assert result.counts == IdentifierCounts(read=3, found=3, matched_nothing=0, repeated=2)
    assert graph.calls == [("Endpoint", "value_normalised", "+447700900123")]


async def test_a_repeated_identifier_adds_one_node() -> None:
    result = await resolve_identifiers(_graph(), ["Z1234ZZ", "QQ123456A", "z1234zz"], ANALYST)
    assert [n.id for n in result.nodes] == ["p1", "p2"]
    assert result.counts.repeated == 1


async def test_a_repeat_of_an_identifier_that_matched_nothing_is_still_repeated() -> None:
    result = await resolve_identifiers(_graph(), ["Z9999ZZ", "Z9999ZZ"], ANALYST)
    assert result.counts == IdentifierCounts(read=2, found=0, matched_nothing=2, repeated=1)


async def test_a_person_found_by_two_identifiers_is_added_once() -> None:
    both = _person("p9", prison_number="Z7777ZZ", nino="QQ777777A")
    graph = _Graph(
        ("Person", "prison_number", "Z7777ZZ", both), ("Person", "nino", "QQ777777A", both)
    )
    result = await resolve_identifiers(graph, ["Z7777ZZ QQ777777A"], ANALYST)
    assert [n.id for n in result.nodes] == ["p9"]
    assert result.counts.found == 2


async def test_an_endpoint_of_another_kind_is_not_a_match() -> None:
    result = await resolve_identifiers(_graph(), ["PIN-Z2345ZZ"], ANALYST)
    assert result.counts == IdentifierCounts(read=1, found=0, matched_nothing=1, repeated=0)
    assert result.nodes == []


async def test_a_hidden_identifier_and_a_made_up_one_give_the_same_counts_and_work() -> None:
    """The graph holds a person at `Z5555ZZ` the principal may not see, so it answers `None` for it,
    as for `Z6666ZZ`, which nobody holds: same shape, same figure, same single lookup each."""
    around = ["Z1234ZZ", "07700 900123"]
    hidden_graph, made_up_graph = _graph(), _graph()
    hidden = await resolve_identifiers(hidden_graph, [*around, "Z5555ZZ"], ANALYST)
    made_up = await resolve_identifiers(made_up_graph, [*around, "Z6666ZZ"], ANALYST)
    assert hidden.counts == made_up.counts == IdentifierCounts(
        read=3, found=2, matched_nothing=1, repeated=0
    )
    assert [n.id for n in hidden.nodes] == [n.id for n in made_up.nodes]
    assert [c[:2] for c in hidden_graph.calls] == [c[:2] for c in made_up_graph.calls]
    assert len(hidden_graph.calls) == len(made_up_graph.calls) == 3


async def test_an_unreadable_identifier_matches_nothing_and_is_never_looked_up() -> None:
    graph = _graph()
    result = await resolve_identifiers(graph, ["hello, 12345"], ANALYST)
    assert result.counts == IdentifierCounts(read=2, found=0, matched_nothing=2, repeated=0)
    assert graph.calls == []


async def test_5000_identifiers_are_read() -> None:
    typed = [f"Z{n:04d}ZZ" for n in range(MAX_IDENTIFIERS)]
    result = await resolve_identifiers(_Graph(), typed, ANALYST)
    assert result.counts.read == MAX_IDENTIFIERS


async def test_more_than_5000_is_refused_by_name() -> None:
    typed = [f"Z{n:04d}ZZ" for n in range(MAX_IDENTIFIERS + 1)]
    graph = _Graph()
    with pytest.raises(TooManyIdentifiersError) as raised:
        await resolve_identifiers(graph, typed, ANALYST)
    assert raised.value.received == 5001
    assert MAX_IDENTIFIERS == 5000
    assert graph.calls == []


async def test_the_count_is_over_what_the_strings_hold_not_over_the_strings() -> None:
    one_string = ["\n".join(f"Z{n:04d}ZZ" for n in range(MAX_IDENTIFIERS + 1))]
    with pytest.raises(TooManyIdentifiersError):
        await resolve_identifiers(_Graph(), one_string, ANALYST)


class _SharedTextGraph:
    """Two visible Endpoints holding the same `value_normalised` with different kinds, the handle
    first. A lookup that cannot say which kind it wants gets the first, as the store's `limit(1)`
    does; one that names the kind (`also`) gets the one of that kind."""

    def __init__(self, *nodes: Node) -> None:
        self.nodes = nodes

    async def find_node(
        self,
        entity_type: str,
        identifier_field: str,
        value: str,
        principal: Principal,
        *,
        also: dict[str, str] | None = None,
    ) -> Node | None:
        for node in self.nodes:
            if node.type == entity_type and node.properties.get(identifier_field) == value:
                if all(node.properties.get(k) == v for k, v in (also or {}).items()):
                    return node
        return None


async def test_an_account_is_found_when_a_pin_handle_holds_the_same_text() -> None:
    """The kind is part of the lookup, not a check on whichever node came back first: a handle
    and an account with the same text were a coin toss, and the account could read as unmatched."""
    handle = _endpoint("e-handle", "SYN-70417", "handle")
    account = _endpoint("e-account", "SYN-70417", "account")
    graph = _SharedTextGraph(handle, account)
    result = await resolve_identifiers(graph, ["SYN-70417"], ANALYST)
    assert [n.id for n in result.nodes] == ["e-account"]
    assert result.counts == IdentifierCounts(read=1, found=1, matched_nothing=0, repeated=0)
    reversed_order = _SharedTextGraph(account, handle)
    again = await resolve_identifiers(reversed_order, ["SYN-70417"], ANALYST)
    assert [n.id for n in again.nodes] == ["e-account"]
