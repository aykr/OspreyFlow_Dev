"""A monitoring rule on connection strength and on shared-attribute rarity (`spec/06_DECISIONS.md`
ADR-139 decision 8): "… and the connection strength (or shared-attribute rarity) between … reaches
X", checked against the ontology, said in words, previewed and judged as the rule's author.

The graph is the **real** ArcadeDB adapter (a throwaway one, through the conformance registry):
what is being proven is that the rule reads strength and rarity under its author's access, so no
stand-in may decide what the author sees (rule 15).

What a mistake would do, and the case that catches it:
- an alert raised on evidence its author could not read (a SECRET passport thickening a link they
  see) — `test_a_strength_rule_raises_on_the_authors_visible_strength_and_not_on_hidden_evidence`;
- a rarity rule moved by an entity its author may not see —
  `test_a_rarity_rule_is_judged_on_what_its_author_may_see`;
- a strength condition that names an undeclared link type, or runs before commit —
  `test_a_strength_condition_is_checked_against_the_ontology_and_runs_after_commit`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from services.api.rule_sentences import (
    SentenceContext,
    SentenceRefused,
    check_sentence,
    preview_sentence,
    sentence_words,
)

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.sentences import RarityReaches, RuleSentence, StrengthReaches
from schemas.strength import ActiveInfluencer, InfluencerTrigger, StrengthInfluencer
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

ONTOLOGY = load_default_ontology()
UNIT = "unit-1"
OFFICIAL = Principal(id="author-official", clearance="OFFICIAL", org_unit=UNIT)
CLEARED = Principal(id="author-secret", clearance="SECRET", org_unit=UNIT)
PASSPORT = ActiveInfluencer(
    layer="installation", version=1,
    influencer=StrengthInfluencer(
        id="passport", label="Evidenced by a passport", link_types=["ASSOCIATE_OF"], size=0.5,
        trigger=InfluencerTrigger(entity_type="Document", property="document_kind",
                                  values=["passport"]),
    ),
)  # fmt: skip


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime.now(UTC),
    )


def _handling(classification: str) -> dict[str, str | None]:
    return {"classification": classification, "handling_code": "P", "originator": UNIT,
            "owning_unit": UNIT, "action_code": None, "sanitisation_code": None}  # fmt: skip


def _node(kind: str, classification: str, **properties: object) -> NodeWrite:
    base: dict[str, object] = {"Person": {"family_name": "Okafor"},
                               "Endpoint": {"value_normalised": "+447700900001"}}.get(kind, {})  # type: ignore[assignment]
    return NodeWrite(
        id=new_node_id(), type=kind, properties={**base, **properties}, provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1", created_at=now_utc(),
    )  # fmt: skip


def _edge(kind: str, source: str, target: str, classification: str = "OFFICIAL") -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(), type=kind, source=source, target=target, provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1", created_at=now_utc(),
    )  # fmt: skip


async def _write(graph: object, nodes: list[NodeWrite], edges: list[EdgeWrite]) -> None:
    tx = await graph.begin_transaction()  # type: ignore[attr-defined]
    await graph.upsert_nodes(nodes, tx)  # type: ignore[attr-defined]
    await graph.upsert_edges(edges, tx)  # type: ignore[attr-defined]
    await graph.commit_transaction(tx)  # type: ignore[attr-defined]


def _ctx(graph: object) -> SentenceContext:
    return SentenceContext(
        graph=graph, analytics=None, investigation_scope="case-1", ontology=ONTOLOGY,  # type: ignore[arg-type]
        influencers=[PASSPORT],
    )  # fmt: skip


def test_a_strength_condition_is_checked_against_the_ontology_and_runs_after_commit() -> None:
    with pytest.raises(SentenceRefused) as refused:
        check_sentence(RuleSentence(subject="Person", strength=StrengthReaches(
            link_type="KNOWS_OF", reaches=0.8)), ONTOLOGY)  # fmt: skip
    assert refused.value.refusal.blank == "strength"
    with pytest.raises(SentenceRefused):
        check_sentence(RuleSentence(subject="Person", strength=StrengthReaches(
            link_type="COMMUNICATED_WITH", reaches=0.8)), ONTOLOGY)  # fmt: skip
    with pytest.raises(ValidationError, match="after commit"):
        RuleSentence(subject="Person", runs="pre_commit",
                     strength=StrengthReaches(reaches=0.8))  # fmt: skip
    words = sentence_words(RuleSentence(subject="Person", strength=StrengthReaches(
        link_type="ASSOCIATE_OF", other_type="Person", reaches=0.8)), ONTOLOGY)  # fmt: skip
    assert "and the connection strength between it and a Person by “" in words
    assert "reaches 0.8" in words
    rarity = sentence_words(RuleSentence(subject="Person", strength=RarityReaches(reaches=2)),
                            ONTOLOGY)  # fmt: skip
    assert "shared-attribute rarity between it and another Person reaches 2 (per dataset)" in rarity


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_a_strength_rule_raises_on_the_authors_visible_strength_and_not_on_hidden_evidence(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        a, b = _node("Person", "OFFICIAL"), _node("Person", "OFFICIAL", family_name="Adeyemi")
        passport = _node("Document", "SECRET", document_kind="passport")
        await _write(graph, [a, b, passport], [
            _edge("ASSOCIATE_OF", a.id, b.id),
            _edge("VERIFIED_BY", a.id, passport.id), _edge("VERIFIED_BY", b.id, passport.id),
        ])  # fmt: skip
        (link,) = await graph.connection_strengths(
            [e.id for e in (await graph.edges_among([a.id, b.id], CLEARED))], CLEARED,
            influencers=[PASSPORT],
        )  # fmt: skip
        # Between the stored weight and the strength the hidden passport would give it.
        threshold = (link.base_weight + link.strength) / 2
        assert link.base_weight < threshold < link.strength
        sentence = RuleSentence(subject="Person", strength=StrengthReaches(
            link_type="ASSOCIATE_OF", other_type="Person", reaches=round(threshold, 4)))  # fmt: skip
        seen = await preview_sentence(sentence, OFFICIAL, _ctx(graph))
        assert seen.would_raise == 0 and seen.examples == []
        cleared = await preview_sentence(sentence, CLEARED, _ctx(graph))
        assert cleared.would_raise == 2
        assert "connection strength" in cleared.examples[0].words


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_a_rarity_rule_is_judged_on_what_its_author_may_see(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        p1, p2, p3 = (_node("Person", "OFFICIAL") for _ in range(3))
        hidden = _node("Person", "SECRET")
        rare = _node("Endpoint", "OFFICIAL")
        await _write(graph, [p1, p2, p3, hidden, rare],
                     [_edge("USES", p.id, rare.id) for p in (p1, p2, hidden)])  # fmt: skip
        # As the author sees it, ln(3/2); with the hidden person, ln(4/3), below the figure.
        sentence = RuleSentence(subject="Person", strength=RarityReaches(
            reaches=round(math.log(3 / 2) - 0.01, 4), scope="case"))  # fmt: skip
        seen = await preview_sentence(sentence, OFFICIAL, _ctx(graph))
        assert seen.would_raise == 2
        assert {e.node_id for e in seen.examples} == {p1.id, p2.id}
        assert all(hidden.id not in e.words for e in seen.examples)
        cleared = await preview_sentence(sentence, CLEARED, _ctx(graph))
        assert cleared.would_raise == 0
