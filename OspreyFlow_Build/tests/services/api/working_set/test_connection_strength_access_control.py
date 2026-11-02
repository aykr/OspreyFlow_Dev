"""Rule 4 for ADR-139's two reads (`services/api/connection_strength.py`): connection strength and
shared-attribute rarity over a case's working set, the routes behind the Metrics panel's two
filters, the Matrix view's sorts and the Inspector's explanation.

The working set's membership is deliberately unfiltered (`compute_routes.py` says why), so each
read narrows it to what the reader may see and asks the graph adapter as the reader. These cases
seed a hidden record and a hidden entity into that membership and prove the reader's answer is the
answer in a world without them — and that nothing in it names them or counts beyond the filter
(rule 7). The **real** ArcadeDB adapter (a throwaway one), as every access-control case here; the
working-set store is the in-memory fake, and the influencer store a stand-in returning one
influencer, since neither's own logic is what is tested.

ADR-139 Amendment 2 adds three reads to prove under access: client parity's strength (a hidden link
of the same type is in no `n`), the client's rarity measure (a hidden holder is in no `k` and no
sum), and a dataset trigger the reader cannot read (neither applied nor told in the legend).
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.connection_strength import case_connection_strengths, case_rarity
from services.api.working_set.service import WorkingSetService

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.influencers import StrengthDefaults, StrengthSettings
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.strength import (
    SHARED_VALUE,
    ActiveInfluencer,
    DatasetTrigger,
    CaseInfluencers,
    ConnectionStrengthRequest,
    ConnectionStrengths,
    InfluencerSetHistory,
    InfluencerTrigger,
    RarityRequest,
    RarityResult,
    StrengthInfluencer,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory
from tests.services.api.corpus_counts import field_names_reachable

from .fakes import FakeWorkingSetStore

CASE = "inv-strength"
UNIT = "unit-1"
OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit=UNIT)
CLEARED = Principal(id="analyst-secret", clearance="SECRET", org_unit=UNIT)
DEFAULTS = StrengthDefaults(influencers=(), rarity_exclude_types=("Alert",))
#: The first decision's measure, which the cases written before Amendment 2 read.
DEFAULTS_IDF = StrengthDefaults(influencers=(), rarity_exclude_types=("Alert",), rarity_measure="idf")
PASSPORT = ActiveInfluencer(
    layer="case",
    version=1,
    influencer=StrengthInfluencer(
        id="passport", label="Evidenced by a passport", link_types=["ASSOCIATE_OF"], size=0.3,
        trigger=InfluencerTrigger(entity_type="Document", property="document_kind",
                                  values=["passport"]),
    ),
)  # fmt: skip


class _Influencers:
    def __init__(
        self, active: list[ActiveInfluencer] | None = None, settings: StrengthSettings | None = None
    ) -> None:
        self.active = [PASSPORT] if active is None else active
        self.settings = settings or StrengthSettings()

    async def active_for_case(self, investigation_id: str | None, shipped: Any) -> Any:
        return self.active, [], None

    async def settings_for_case(self, investigation_id: str | None, defaults: Any) -> Any:
        return self.settings


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
    defaults: dict[str, object] = {"Person": {"family_name": "Test"},
                                   "Endpoint": {"value_normalised": "+441234567890"}}.get(kind, {})  # type: ignore[assignment]
    return NodeWrite(
        id=new_node_id(), type=kind, properties={**defaults, **properties},
        provenance=_provenance(), handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1", created_at=now_utc(),
    )  # fmt: skip


def _edge(
    kind: str, source: str, target: str, classification: str = "OFFICIAL",
    datasets: list[str] | None = None,
) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(), type=kind, source=source, target=target, provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1", created_at=now_utc(), datasets=datasets or [],
    )  # fmt: skip


def _stub_node(write: NodeWrite) -> Node:
    return Node(id=write.id, type=write.type, properties={}, provenance=_provenance(),
                handling=write.handling, audit=AuditStub(created_at=now_utc(),
                                                         created_by="loader-1"))  # fmt: skip


def _stub_edge(write: EdgeWrite) -> Edge:
    return Edge(id=write.id, type=write.type, source=write.source, target=write.target,
                properties={}, provenance=_provenance(), handling=write.handling,
                audit=AuditStub(created_at=now_utc(), created_by="loader-1"))  # fmt: skip


async def _seed(graph: Any, nodes: list[NodeWrite], edges: list[EdgeWrite]) -> WorkingSetService:
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(nodes, tx)
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)
    store = FakeWorkingSetStore()
    # The membership holds everything, hidden or not: `current_membership` is unfiltered.
    await store.add_nodes(CASE, [_stub_node(n) for n in nodes])
    await store.add_edges(CASE, [_stub_edge(e) for e in edges])
    return WorkingSetService(graph, store, load_uk_le_scheme())


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_a_hidden_record_never_thickens_a_visible_link_through_the_case_read(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        a, b = _node("Person", "OFFICIAL"), _node("Person", "OFFICIAL")
        hidden_person = _node("Person", "SECRET")
        passport = _node("Document", "SECRET", document_kind="passport")
        ab = _edge("ASSOCIATE_OF", a.id, b.id)
        to_hidden = _edge("ASSOCIATE_OF", a.id, hidden_person.id)
        nodes = [a, b, hidden_person, passport]
        edges = [ab, to_hidden, _edge("VERIFIED_BY", a.id, passport.id),
                 _edge("VERIFIED_BY", b.id, passport.id)]  # fmt: skip
        working_set = await _seed(graph, nodes, edges)

        async def read(who: Principal) -> ConnectionStrengths:
            return await case_connection_strengths(
                CASE, ConnectionStrengthRequest(), working_set=working_set, graph=graph,
                principal=who, store=_Influencers(), defaults=DEFAULTS,  # type: ignore[arg-type]
            )  # fmt: skip

        seen = await read(OFFICIAL)
        by_id = {s.edge_id: s for s in seen.links}
        assert set(by_id) == {ab.id}  # the link to the hidden person is not there at all
        assert by_id[ab.id].applied == [] and by_id[ab.id].strength == by_id[ab.id].base_weight
        wire = seen.model_dump_json()
        for hidden in (hidden_person.id, passport.id, to_hidden.id):
            assert hidden not in wire
        # The filter is real: cleared, the passport evidences the link.
        cleared = {s.edge_id: s for s in (await read(CLEARED)).links}
        assert [x.id for x in cleared[ab.id].applied] == ["passport"]
        assert cleared[ab.id].strength > by_id[ab.id].strength


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_the_case_rarity_read_never_counts_or_names_a_hidden_entity(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        p1, p2, p3 = (_node("Person", "OFFICIAL") for _ in range(3))
        hidden = _node("Person", "SECRET")
        rare = _node("Endpoint", "OFFICIAL")
        nodes = [p1, p2, p3, hidden, rare]
        edges = [_edge("USES", p.id, rare.id) for p in (p1, p2, hidden)]
        working_set = await _seed(graph, nodes, edges)

        async def read(who: Principal, pairs: list[tuple[str, str]]) -> RarityResult:
            return await case_rarity(
                CASE, RarityRequest(scope="case", pairs=pairs), working_set=working_set,
                graph=graph, principal=who, defaults=DEFAULTS_IDF,
            )  # fmt: skip

        seen = await read(OFFICIAL, [(p1.id, p2.id), (p1.id, hidden.id)])
        # The world without the hidden person: N = 3 visible persons, df(rare) = 2.
        assert seen.node_values == {p1.id: pytest.approx(math.log(3 / 2)),
                                    p2.id: pytest.approx(math.log(3 / 2))}  # fmt: skip
        assert seen.pairs[0].score == pytest.approx(math.log(3 / 2))
        # The pair naming the hidden person is answered as one naming nobody: the reader's own ids
        # echoed, no score, nothing shared. Beyond that echo, the answer never names them.
        assert seen.pairs[1].model_dump() == {"a": p1.id, "b": hidden.id, "score": None,
                                              "dataset": None, "shared": [], "parity_raw": None,
                                              "parity_strength": None, "parity_applied": []}  # fmt: skip
        assert hidden.id not in seen.model_copy(update={"pairs": seen.pairs[:1]}).model_dump_json()
        cleared = await read(CLEARED, [(p1.id, p2.id)])
        assert cleared.pairs[0].score == pytest.approx(math.log(4 / 3))


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_client_parity_through_the_case_read_never_counts_a_hidden_link(
    factory: GraphAdapterFactory,
) -> None:
    """Amendment 2 (rule 3): under client parity a link's rarity term is `1 − 1/n` over the links
    of its type the reader may see. A SECRET call, and a call to a SECRET endpoint, are in no `n`:
    the OFFICIAL reader's sum is the sum in a world without them, and nothing names them."""
    async with factory.context() as graph:
        x1, x2, x3, x4 = (_node("Endpoint", "OFFICIAL") for _ in range(4))
        hidden_end = _node("Endpoint", "SECRET")
        c12, c34 = _edge("COMMUNICATED_WITH", x1.id, x2.id), _edge("COMMUNICATED_WITH", x3.id, x4.id)
        secret_call = _edge("COMMUNICATED_WITH", x2.id, x3.id, "SECRET")
        to_hidden = _edge("COMMUNICATED_WITH", x1.id, hidden_end.id)
        working_set = await _seed(graph, [x1, x2, x3, x4, hidden_end], [c12, c34, secret_call, to_hidden])
        direct = ActiveInfluencer(layer="file", influencer=StrengthInfluencer(
            id="direct", label="Direct link", link_types=["COMMUNICATED_WITH"], size=0.2))  # fmt: skip
        parity = _Influencers([direct], StrengthSettings(composition="client_parity"))

        async def read(who: Principal) -> ConnectionStrengths:
            return await case_connection_strengths(
                CASE, ConnectionStrengthRequest(), working_set=working_set, graph=graph,
                principal=who, store=parity, defaults=DEFAULTS,  # type: ignore[arg-type]
            )  # fmt: skip

        seen = await read(OFFICIAL)
        by_id = {s.edge_id: s for s in seen.links}
        assert set(by_id) == {c12.id, c34.id}
        # The world without the two: two calls, 1 − 1/2, and the direct add.
        assert by_id[c12.id].rarity_term == pytest.approx(0.5)
        assert by_id[c12.id].raw_sum == pytest.approx(0.7)
        assert seen.legend.composition == "client_parity"
        wire = seen.model_dump_json()
        for hidden in (hidden_end.id, secret_call.id, to_hidden.id):
            assert hidden not in wire
        cleared = {s.edge_id: s for s in (await read(CLEARED)).links}
        assert cleared[c12.id].rarity_term == pytest.approx(1 - 1 / 4)


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_the_case_rarity_read_in_the_clients_measure_never_counts_a_hidden_holder(
    factory: GraphAdapterFactory,
) -> None:
    """Amendment 2's hidden-holder test, through the case read: the client's `1 − C(k,2)/ΣC` with
    a SECRET person holding the common phone counts only what the reader may see."""
    async with factory.context() as graph:
        p1, p2, p3, p4 = (_node("Person", "OFFICIAL") for _ in range(4))
        hidden = _node("Person", "SECRET")
        rare, common = _node("Endpoint", "OFFICIAL"), _node("Endpoint", "OFFICIAL")
        edges = [_edge("USES", p.id, rare.id) for p in (p1, p2)]
        edges += [_edge("USES", p.id, common.id) for p in (p3, p4, hidden)]
        working_set = await _seed(graph, [p1, p2, p3, p4, hidden, rare, common], edges)

        async def read(who: Principal) -> RarityResult:
            return await case_rarity(
                CASE, RarityRequest(scope="case", pairs=[(p1.id, p2.id), (p3.id, p4.id)]),
                working_set=working_set, graph=graph, principal=who, defaults=DEFAULTS,
            )  # fmt: skip

        seen = await read(OFFICIAL)
        assert seen.measure == "share"
        # Without the hidden holder: rare 1 pair link, common 1; ΣL = 2.
        assert [p.score for p in seen.pairs] == pytest.approx([0.5, 0.5])
        assert hidden.id not in seen.model_dump_json()
        cleared = await read(CLEARED)
        # Cleared: common has three holders, 3 pair links; ΣL = 4.
        assert [p.score for p in cleared.pairs] == pytest.approx([0.75, 0.25])


@pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)
async def test_a_dataset_trigger_the_reader_cannot_read_is_neither_applied_nor_told(
    factory: GraphAdapterFactory,
) -> None:
    """Amendment 2, ruling 3 (rule 3): a link in `calls` and `assaults`, read by an analyst whose
    case reads `calls` alone, is not thickened by the `assaults` influencer, and the legend they
    are sent does not name it; a reader of both sees it applied and named."""
    async with factory.context() as graph:
        a = _node("Endpoint", "OFFICIAL")
        b = _node("Endpoint", "OFFICIAL")
        both = ["calls", "assaults"]
        a.datasets, b.datasets = both, both
        call = _edge("COMMUNICATED_WITH", a.id, b.id, datasets=both)
        working_set = await _seed(graph, [a, b], [call])
        by_assaults = ActiveInfluencer(layer="installation", version=1, influencer=StrengthInfluencer(
            id="source-assaults", label="From the assaults table", size=0.3,
            trigger=DatasetTrigger(datasets=["assaults"]),
            link_types=["COMMUNICATED_WITH", SHARED_VALUE],
        ))  # fmt: skip
        for settings in (StrengthSettings(), StrengthSettings(composition="client_parity")):
            store = _Influencers([by_assaults], settings)

            async def read(who: Principal, store: _Influencers = store) -> ConnectionStrengths:
                return await case_connection_strengths(
                    CASE, ConnectionStrengthRequest(), working_set=working_set, graph=graph,
                    principal=who, store=store, defaults=DEFAULTS,  # type: ignore[arg-type]
                )  # fmt: skip

            calls_only = await read(OFFICIAL.model_copy(update={"datasets": ["calls"]}))
            (link,) = calls_only.links
            assert link.applied == [], settings
            assert calls_only.legend.influencers == []
            assert "assaults" not in calls_only.model_dump_json()
            reader_of_both = await read(OFFICIAL.model_copy(update={"datasets": both}))
            (link,) = reader_of_both.links
            assert [x.id for x in link.applied] == ["source-assaults"], settings
            assert [x.influencer.id for x in reader_of_both.legend.influencers] == ["source-assaults"]


#: A name that would carry a count: what rarity is worked out from, a corpus figure, or a figure for
#: what the reader may not see (rule 7; ADR-122; ADR-124).
_COUNTISH = re.compile(r"count|total|corpus|degree|population|^n$|^n_|_n$|^df|df_|visible_")


def test_the_glass_payload_carries_no_count_from_beyond_the_filter() -> None:
    """ADR-139's payload test: every field ADR-139's responses can carry, at any depth, is a score,
    a definition or the reader's own records — none is named as a count. The walk is over the
    declared shape, so a field added later is seen whatever its value."""
    names = set()
    for model in (ConnectionStrengths, RarityResult, CaseInfluencers, InfluencerSetHistory):
        names |= field_names_reachable(model)
    assert {"score", "strength", "base_weight", "shared", "node_values"} <= names
    assert sorted(n for n in names if _COUNTISH.search(n)) == []
