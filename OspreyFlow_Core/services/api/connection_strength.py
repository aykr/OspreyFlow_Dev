"""Connection strength and shared-attribute rarity over a case's working set (`06_DECISIONS.md`
ADR-139 decisions 5, 6, 7 and 9): what the Metrics panel's two filters, the Matrix view's two sorts,
the legend box and the Inspector's explanation read.

Each read starts from the working set's membership narrowed to what the reader may see
(`narrow_to_visible`, as `compute_routes.py` does: the membership itself is unfiltered), and asks
the graph adapter, as the reader, for strengths and rarity (rule 3: worked out there, under the
access predicate, never here after retrieval). The influencers are the case's in force, resolved
case → installation → file (`InfluencerStore.active_for_case`). The answer carries scores, the
reader's visible shared attributes, and the influencers' own definitions: never `N`, `df`, a
corpus count or the stored weight components (rule 7; ADR-122).

**Amendment 2:** the case's composition and rarity measure (`InfluencerStore.settings_for_case`)
travel with each read: under client parity, strengths are the client's sums drawn on 0–1 and a
pair's parity score rides with its rarity. A dataset-triggered influencer is told to the reader
only by the datasets they may read (`as_the_reader_sees`).
"""

from __future__ import annotations

from collections.abc import Sequence

from ontology.influencers import (
    StrengthDefaults,
    legend_of,
    resolve_influencers,
    resolve_settings,
)
from ports.graph import GraphPort, RarityTooLarge
from schemas.domain import Principal
from schemas.strength import (
    ConnectionStrengthRequest,
    ConnectionStrengths,
    PairRarity,
    RarityRequest,
    RarityResult,
    StrengthLegend,
)

from .access import narrow_to_visible
from .principal_names import PrincipalNameDirectory
from .strength_influencers import InfluencerStore
from .working_set.models import LimitExceeded, LimitExceededError
from .working_set.service import WorkingSetService


async def case_legend(
    investigation_id: str,
    *,
    store: InfluencerStore,
    defaults: StrengthDefaults,
    names: PrincipalNameDirectory | None = None,
    readable: Sequence[str] | None = None,
) -> StrengthLegend:
    """The legend box's account of strength for a case: exactly the influencers in force, as the
    reader may be told of them, and the composition and rarity measure."""
    active, switched_off, case = await store.active_for_case(investigation_id, defaults.influencers)
    settings = await store.settings_for_case(investigation_id, defaults)
    set_by_name = None
    if case is not None and names is not None:
        set_by_name = (await names.display_names([case.set_by])).get(case.set_by)
    return legend_of(
        active,
        switched_off,
        case_version=case.version if case else None,
        case_set_by_name=set_by_name,
        settings=settings,
        readable=readable,
    )


async def case_connection_strengths(
    investigation_id: str,
    body: ConnectionStrengthRequest,
    *,
    working_set: WorkingSetService,
    graph: GraphPort,
    principal: Principal,
    store: InfluencerStore,
    defaults: StrengthDefaults,
) -> ConnectionStrengths:
    """The connection strength of each link of the working set the reader may see, or of the ones
    named (a link named that is not in the working set, or not visible, is left out: the reader
    learns nothing of it that the working set would not have shown)."""
    nodes, _ = await working_set.current_membership(investigation_id)
    visible = await narrow_to_visible(graph, [n.id for n in nodes], principal)
    in_view = [e.id for e in visible.edges]
    if body.edge_ids is not None:
        named = set(body.edge_ids)
        in_view = [e for e in in_view if e in named]
    active, switched_off, case = await store.active_for_case(investigation_id, defaults.influencers)
    settings = await store.settings_for_case(investigation_id, defaults)
    links = await graph.connection_strengths(
        in_view, principal, influencers=active, composition=settings.composition
    )
    return ConnectionStrengths(
        links=links,
        legend=legend_of(
            active, switched_off, case_version=case.version if case else None,
            settings=settings, readable=principal.datasets,
        ),
    )  # fmt: skip


async def case_rarity(
    investigation_id: str,
    body: RarityRequest,
    *,
    working_set: WorkingSetService,
    graph: GraphPort,
    principal: Principal,
    defaults: StrengthDefaults,
    store: InfluencerStore | None = None,
) -> RarityResult:
    """Each visible working-set entity's highest rarity with another of its kind in the working
    set, and the pairs asked for. A pair naming an entity not in the reader's view has no score
    (None), so whether it exists is not told. More pairs than the cap is `limit_exceeded`."""
    nodes, _ = await working_set.current_membership(investigation_id)
    visible = await narrow_to_visible(graph, [n.id for n in nodes], principal)
    ids = sorted(visible.nodes)
    in_view = set(ids)
    pairs = [(a, b) for a, b in body.pairs if a in in_view and b in in_view]
    if store is not None:
        active, _, _ = await store.active_for_case(investigation_id, defaults.influencers)
        settings = await store.settings_for_case(investigation_id, defaults)
    else:
        active, _ = resolve_influencers(defaults.influencers)
        settings = resolve_settings(defaults)
    try:
        result = await graph.shared_attribute_rarity(
            ids,
            principal,
            scope=body.scope,
            pairs=pairs,
            exclude_types=defaults.rarity_exclude_types,
            measure=settings.rarity_measure,
            influencers=active,
            composition=settings.composition,
        )
    except RarityTooLarge as refused:
        raise LimitExceededError(
            LimitExceeded(cap_kind="pairs", cap=refused.cap, would_be=refused.pairs)
        ) from refused
    explained = {(p.a, p.b): p for p in result.pairs}
    return RarityResult(
        scope=result.scope,
        node_values=result.node_values,
        pairs=[explained.get((a, b)) or PairRarity(a=a, b=b, score=None) for a, b in body.pairs],
        measure=result.measure,
        composition=result.composition,
    )


__all__ = ["case_connection_strengths", "case_legend", "case_rarity"]
