"""`services/api/assessments.py` — `01_DOMAIN_MODEL.md` §5, `06_DECISIONS.md` ADR-046 (accepted),
Phase 8 Stage 4b. Real Postgres (the judgement store) and real ArcadeDB (the citation visibility
recheck, the review-flag loop's own `supersede_node` trigger) — access control and "a cited node
was retracted" are exactly the class of claim `07_BUILD_PLAN.md`'s "Fake-based tests" gaps entry
says a fake cannot stand in for.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.assessments import (
    JudgementNotFoundError,
    JudgementStore,
    NoSupportingReferenceError,
    flag_judgements_citing_superseded_node,
    judgement_visible_to,
    list_visible_judgements,
    new_judgement,
)
from services.api.config import PostgresConfig
from services.extract.writer import retract_node

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

AUTHOR = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
VIEWER_SAME_UNIT = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")
VIEWER_OTHER_UNIT = Principal(id="analyst-3", clearance="OFFICIAL", org_unit="unit-2")


@pytest.fixture
async def judgement_store():
    s = await JudgementStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


def _node_write(
    *,
    owning_unit: str,
    classification: str = "OFFICIAL",
    state: ProvenanceState = ProvenanceState.ASSERTED,
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": "Assessmentfixture",
            "given_names": "A",
            "date_of_birth": "1990-01-01",
        },
        provenance=Provenance(
            state=state,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


# --- Evidence-link validation — A13's own literal assertion --------------------------------------


async def test_a_judgement_cannot_be_saved_with_zero_supporting_references(judgement_store) -> None:
    empty = new_judgement(
        investigation_id="inv-1",
        statement="The subject is the principal organiser.",
        probability_band="likely",
        supporting=[],
        author=AUTHOR.id,
    )
    with pytest.raises(NoSupportingReferenceError):
        await judgement_store.save(empty, AUTHOR)

    # And it genuinely never reached the table — not merely that the call raised.
    with pytest.raises(JudgementNotFoundError):
        await judgement_store.get(empty.id)


async def test_a_judgement_with_a_supporting_reference_saves_and_reads_back(
    judgement_store,
) -> None:
    j = new_judgement(
        investigation_id="inv-1",
        statement="The subject is the principal organiser.",
        probability_band="likely",
        supporting=["node-1"],
        author=AUTHOR.id,
    )
    saved = await judgement_store.save(j, AUTHOR)
    assert saved.id == j.id
    reread = await judgement_store.get_authorized(j.id, AUTHOR)
    assert reread.statement == j.statement
    assert reread.supporting == ["node-1"]
    assert reread.flagged_for_review is False


# --- owning_unit scoping — the existence-leak discipline CLAUDE.md rule 4 requires ----------------


async def test_a_judgement_owned_by_a_different_unit_is_not_found_not_forbidden(
    judgement_store,
) -> None:
    j = new_judgement(
        investigation_id="inv-1",
        statement="Statement.",
        probability_band="likely",
        supporting=["node-1"],
        author=AUTHOR.id,
    )
    await judgement_store.save(j, AUTHOR)
    with pytest.raises(JudgementNotFoundError):
        await judgement_store.get_authorized(j.id, VIEWER_OTHER_UNIT)


async def test_list_never_returns_another_units_judgement(judgement_store) -> None:
    investigation_id = new_id()
    j = new_judgement(
        investigation_id=investigation_id,
        statement="Statement.",
        probability_band="likely",
        supporting=["node-1"],
        author=AUTHOR.id,
    )
    await judgement_store.save(j, AUTHOR)
    listed = await judgement_store.list_for_investigation(investigation_id, VIEWER_OTHER_UNIT)
    assert listed == []
    same_unit = await judgement_store.list_for_investigation(investigation_id, VIEWER_SAME_UNIT)
    assert any(row.id == j.id for row in same_unit)


# --- ADR-046's access rule — real ArcadeDB -------------------------------------------------------


async def test_a_judgement_is_hidden_from_a_viewer_who_cannot_read_at_least_one_of_its_supporting_references(  # noqa: E501
    judgement_store,
) -> None:
    """`06_DECISIONS.md` ADR-046's own named test: write a judgement citing two supporting nodes,
    one visible and one not to principal B; list judgements as B; assert the judgement is absent
    from B's own list entirely, not present with a placeholder or an "unavailable" marker."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (visible_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=VIEWER_SAME_UNIT.org_unit)], tx
        )
        (hidden_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-9", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        investigation_id = new_id()
        j = new_judgement(
            investigation_id=investigation_id,
            statement="The subject is the principal organiser.",
            probability_band="likely",
            supporting=[visible_id, hidden_id],
            author=AUTHOR.id,
        )
        await judgement_store.save(j, AUTHOR)

        # Sanity: the author's own principal (OFFICIAL, unit-1) cannot see the SECRET/unit-9 node
        # either — this is the same viewer class as `VIEWER_SAME_UNIT` for clearance purposes.
        assert await judgement_visible_to(j, VIEWER_SAME_UNIT, graph) is False

        visible_list = await list_visible_judgements(
            judgement_store, investigation_id, VIEWER_SAME_UNIT, graph
        )
        assert visible_list == []


async def test_a_judgement_with_all_supporting_references_visible_is_not_hidden(
    judgement_store,
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=VIEWER_SAME_UNIT.org_unit)], tx
        )
        await graph.commit_transaction(tx)

        investigation_id = new_id()
        j = new_judgement(
            investigation_id=investigation_id,
            statement="The subject is the principal organiser.",
            probability_band="likely",
            supporting=[node_id],
            author=AUTHOR.id,
        )
        await judgement_store.save(j, AUTHOR)

        visible_list = await list_visible_judgements(
            judgement_store, investigation_id, VIEWER_SAME_UNIT, graph
        )
        assert any(row.id == j.id for row in visible_list)


async def test_an_unreadable_contradicting_reference_does_not_hide_the_judgement(
    judgement_store,
) -> None:
    """`06_DECISIONS.md` ADR-046's own named companion test: the same judgement, with its
    `contradicting` list (not `supporting`) carrying the inaccessible node instead, still renders
    in full to the same viewer — and is lazily flagged for review as a side effect of that read."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (visible_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=VIEWER_SAME_UNIT.org_unit)], tx
        )
        (hidden_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-9", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        investigation_id = new_id()
        j = new_judgement(
            investigation_id=investigation_id,
            statement="The subject is the principal organiser.",
            probability_band="likely",
            supporting=[visible_id],
            contradicting=[hidden_id],
            author=AUTHOR.id,
        )
        await judgement_store.save(j, AUTHOR)
        assert j.flagged_for_review is False

        visible_list = await list_visible_judgements(
            judgement_store, investigation_id, VIEWER_SAME_UNIT, graph
        )
        assert any(row.id == j.id for row in visible_list)

        reread = await judgement_store.get_authorized(j.id, VIEWER_SAME_UNIT)
        assert reread.flagged_for_review is True
        assert reread.flag_reason is not None and "contradicting" in reread.flag_reason


# --- The review-flag loop — real ArcadeDB retraction, real Postgres flag write --------------------


async def test_retracting_a_cited_node_flags_the_judgement_within_the_same_session(
    judgement_store,
) -> None:
    """The un-numbered assertion after A15 (`08_ACCEPTANCE_SCENARIOS.md`): "retract one node that
    supports a judgement. The judgement is flagged for review within the same session." Proves the
    loop end to end — a real `retract_node` call (the actual route's own business function,
    `services/extract/writer.py`), then the real review-flag hook, against real ArcadeDB and real
    Postgres, not a mocked `GraphPort`."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=AUTHOR.org_unit, state=ProvenanceState.ASSERTED)], tx
        )
        await graph.commit_transaction(tx)

        investigation_id = new_id()
        cites_it = new_judgement(
            investigation_id=investigation_id,
            statement="The subject is the principal organiser.",
            probability_band="likely",
            supporting=[node_id],
            author=AUTHOR.id,
        )
        unrelated = new_judgement(
            investigation_id=investigation_id,
            statement="An unrelated judgement citing a different node.",
            probability_band="unlikely",
            supporting=["some-other-node"],
            author=AUTHOR.id,
        )
        await judgement_store.save(cites_it, AUTHOR)
        await judgement_store.save(unrelated, AUTHOR)

        # The actual retraction — the same call `retract_node_route` makes.
        tx = await graph.begin_transaction()
        try:
            await retract_node(graph, node_id, AUTHOR, tx=tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)

        flagged_ids = await flag_judgements_citing_superseded_node(judgement_store, node_id)
        assert flagged_ids == [cites_it.id]

        reread_flagged = await judgement_store.get_authorized(cites_it.id, AUTHOR)
        assert reread_flagged.flagged_for_review is True
        assert reread_flagged.flag_reason is not None and node_id in reread_flagged.flag_reason

        # The unrelated judgement, citing a different node entirely, is untouched — proves this is
        # a real, targeted match, not a blanket flag-everything side effect.
        reread_unrelated = await judgement_store.get_authorized(unrelated.id, AUTHOR)
        assert reread_unrelated.flagged_for_review is False


async def test_retracting_a_node_no_judgement_cites_flags_nothing(judgement_store) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=AUTHOR.org_unit, state=ProvenanceState.ASSERTED)], tx
        )
        await graph.commit_transaction(tx)

        tx = await graph.begin_transaction()
        try:
            await retract_node(graph, node_id, AUTHOR, tx=tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)

        flagged_ids = await flag_judgements_citing_superseded_node(judgement_store, node_id)
        assert flagged_ids == []
