"""The single search box reads a phone number or an account reference the same way a list does
(ADR-128 decision 1, B2; script VERIFY item 1): `07700 900640` finds `+447700900640`.

The scout of 26 October 2026 found `search.py` passed the typed text to the graph unchanged, so a
number written the way a person writes it found nothing. What a mistake would do, and the case that
catches it:

- the box still searching the typed text alone, as before this change
  (`test_a_phone_number_written_nationally_finds_the_canonical_endpoint`);
- the normalised ask replacing the typed one, so a text that is itself a stored value stopped
  matching (`test_the_typed_text_is_still_asked_first`);
- another text's behaviour moving: one ask, as typed
  (`test_other_text_is_asked_once_exactly_as_typed`);
- the suggestions (what the Glass's box actually asks while typing) not normalising
  (`test_the_suggestions_normalise_the_same_way`);
- a hit named twice when both asks find it (`test_a_node_both_asks_find_is_named_once`).
"""

from __future__ import annotations

from services.api.search import SearchRequest, SuggestRequest, search, suggest

from ports.graph import NodeSuggestions, SuggestOptions
from schemas.domain import Node, Principal
from tests.services.api.test_search_route import _node

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
CANONICAL = "+447700900640"


class _Graph:
    def __init__(self) -> None:
        self.searched: list[tuple[str, int]] = []
        self.suggested: list[tuple[str, int]] = []
        self.also: dict[str, list[Node]] = {}
        self.suggest_also: dict[str, NodeSuggestions] = {}

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        self.searched.append((query, limit))
        if query in self.also:
            return self.also[query]
        return [_node("endpoint-1")] if query == CANONICAL else []

    async def suggest_nodes(
        self, prefix: str, principal: Principal, *, limit: int = 10,
        options: SuggestOptions | None = None,
    ) -> NodeSuggestions:
        self.suggested.append((prefix, limit))
        if prefix in self.suggest_also:
            return self.suggest_also[prefix]
        nodes = [_node("endpoint-1")] if CANONICAL.startswith(prefix) else []
        return NodeSuggestions(nodes=nodes, more=False)


async def test_a_phone_number_written_nationally_finds_the_canonical_endpoint() -> None:
    graph = _Graph()
    result = await search(graph, SearchRequest(query="07700 900640"), ANALYST)  # type: ignore[arg-type]
    assert [n.id for n in result.nodes] == ["endpoint-1"]


async def test_the_typed_text_is_still_asked_first() -> None:
    graph = _Graph()
    await search(graph, SearchRequest(query="07700 900640"), ANALYST)  # type: ignore[arg-type]
    assert [q for q, _ in graph.searched] == ["07700 900640", CANONICAL]


async def test_other_text_is_asked_once_exactly_as_typed() -> None:
    graph = _Graph()
    for text in ("AB123456C", "Smith", "alpha", CANONICAL, "12"):
        graph.searched.clear()
        await search(graph, SearchRequest(query=text), ANALYST)  # type: ignore[arg-type]
        assert graph.searched == [(text, 20)]


async def test_an_account_reference_in_another_case_is_asked_in_its_canonical_form() -> None:
    graph = _Graph()
    await search(graph, SearchRequest(query="syn-70417"), ANALYST)  # type: ignore[arg-type]
    assert [q for q, _ in graph.searched] == ["syn-70417", "SYN-70417"]


async def test_a_node_both_asks_find_is_named_once() -> None:
    graph = _Graph()
    graph.also["07700 900640"] = [_node("endpoint-1")]
    result = await search(graph, SearchRequest(query="07700 900640"), ANALYST)  # type: ignore[arg-type]
    assert [n.id for n in result.nodes] == ["endpoint-1"]


async def test_the_suggestions_normalise_the_same_way() -> None:
    graph = _Graph()
    result = await suggest(graph, SuggestRequest(query="07700 900640"), ANALYST)  # type: ignore[arg-type]
    assert [n.id for n in result.nodes] == ["endpoint-1"]
    assert [q for q, _ in graph.suggested] == ["07700 900640", CANONICAL]


async def test_suggestions_for_other_text_are_asked_once_as_typed() -> None:
    graph = _Graph()
    result = await suggest(graph, SuggestRequest(query="Smi"), ANALYST)  # type: ignore[arg-type]
    assert graph.suggested == [("Smi", 10)]
    assert result.more is False


async def test_a_merged_list_is_cut_to_the_limit() -> None:
    graph = _Graph()
    graph.also["07700 900640"] = [_node("a"), _node("b")]
    result = await search(graph, SearchRequest(query="07700 900640", limit=2), ANALYST)  # type: ignore[arg-type]
    assert [n.id for n in result.nodes] == ["a", "b"]


async def test_suggestions_cut_to_the_limit_say_more_match() -> None:
    graph = _Graph()
    graph.suggest_also["07700 900640"] = NodeSuggestions(nodes=[_node("a")], more=False)
    result = await suggest(
        graph, SuggestRequest(query="07700 900640", limit=1), ANALYST  # type: ignore[arg-type]
    )
    assert [n.id for n in result.nodes] == ["a"]
    assert result.more is True
