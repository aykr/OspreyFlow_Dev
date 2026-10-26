"""ADR-121: the adapter refuses a condition the applied ontology does not allow before it sends
anything to the store, and sends the conditioned traversal for one it does.

The store itself is a recording stand-in (this file proves the adapter's own decision, not what
ArcadeDB makes of the Gremlin; that is the conformance suite's, live). It records every command
sent, so "refused before anything is sent" is a count of zero rather than an absence of a result.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ontology.pattern_where import PatternConditionRefused
from schemas.domain import PatternNode, PatternQuery, Principal

READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class _RecordingClient:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def gremlin(self, command: str, **_: Any) -> list[dict[str, Any]]:
        self.sent.append(command)
        return [{"result": 0}] if command.endswith(".count()") else []


def _adapter(*, applied: bool = True) -> tuple[GraphArcadeDBAdapter, _RecordingClient]:
    client = _RecordingClient()
    adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())  # type: ignore[arg-type]
    if applied:
        adapter._schema = load_default_ontology()
    return adapter, client


def _one(where: dict[str, str]) -> PatternQuery:
    return PatternQuery(
        nodes=[PatternNode(var="p", entity_type="Person", where=where)], edges=[]
    )


@pytest.mark.parametrize(
    ("where", "reason"),
    [
        ({"date_of_birth": "1990-01-01"}, "sensitive"),
        ({"list_name": "x"}, "not_indexed"),
        ({"no_such_property": "x"}, "unknown_property"),
    ],
)
async def test_a_refused_condition_sends_nothing_to_the_store(
    where: dict[str, str], reason: str
) -> None:
    adapter, client = _adapter()
    with pytest.raises(PatternConditionRefused) as in_match:
        await adapter.match(_one(where), READER)
    with pytest.raises(PatternConditionRefused) as in_count:
        await adapter.match_count(_one(where), READER, ceiling=10)
    assert in_match.value.reason == in_count.value.reason == reason
    assert client.sent == []


async def test_an_allowed_condition_is_sent_in_the_traversal_by_match_and_by_match_count() -> None:
    adapter, client = _adapter()
    await adapter.match(_one({"family_name": "Smith"}), READER)
    assert await adapter.match_count(_one({"family_name": "Smith"}), READER, ceiling=10) == 0
    assert len(client.sent) == 2
    assert all(".has('family_name','Smith')" in command for command in client.sent)


async def test_a_pattern_with_no_condition_needs_no_applied_schema_as_before() -> None:
    adapter, client = _adapter(applied=False)
    await adapter.match(_one({}), READER)
    assert len(client.sent) == 1


async def test_a_condition_with_no_schema_applied_is_refused_in_words_not_run_unchecked() -> None:
    from ontology.errors import OntologyError

    adapter, client = _adapter(applied=False)
    with pytest.raises(OntologyError, match="apply_schema"):
        await adapter.match(_one({"family_name": "Smith"}), READER)
    assert client.sent == []
