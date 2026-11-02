"""Connection strength and shared-attribute rarity in the ArcadeDB adapter (`06_DECISIONS.md`
ADR-139 decisions 2 and 4; `GraphPort.connection_strengths` and `shared_attribute_rarity`).

Every query here carries the access step on every vertex and every link it steps over (rule 3), so
a record, entity or link the principal may not see is in no count and evidences nothing: the result
is the result in a world without it. Nothing is stored. The arithmetic is pure and lives elsewhere:
`ontology/influencers.py` for strength, and `rarity_scores` below for rarity.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from schemas.domain import Principal
from schemas.strength import InfluencerTrigger

from .access_filter import AccessFilter
from .gremlin_literals import groovy_args_literal, groovy_string_list_literal, groovy_string_literal
from .naming import physical_type_name


def _rids(record_ids: Sequence[str]) -> str:
    """A `g.V(...)` start: the empty form reads nothing (as `render_get_nodes_gremlin`'s)."""
    if not record_ids:
        return "g.V().limit(0)"
    return f"g.V({groovy_string_list_literal(list(record_ids))})"


def _record_step(trigger: InfluencerTrigger) -> str:
    """A node of the trigger's type whose property (read from the stored map, where every property
    is kept, indexed or not) holds one of the trigger's values."""
    label = groovy_string_literal(physical_type_name(trigger.entity_type))
    values = groovy_args_literal(sorted(trigger.values))
    prop = groovy_string_literal(trigger.property)
    return f'hasLabel({label}).filter(values("properties").select({prop}).is(within({values})))'


def render_records_at_ends(
    record_ids: Sequence[str], trigger: InfluencerTrigger, access: AccessFilter, who: Principal
) -> str:
    """Which of the vertices at `record_ids` (a link's ends) are themselves visible records."""
    acc = access.gremlin_has_step(who)
    return f'{_rids(record_ids)}.{acc}.{_record_step(trigger)}.values("id")'


def render_records_linked(
    record_ids: Sequence[str], trigger: InfluencerTrigger, access: AccessFilter, who: Principal
) -> str:
    """For each visible vertex at `record_ids`, the visible records linked to it by a visible
    link."""
    acc = access.gremlin_has_step(who)
    return (
        f'{_rids(record_ids)}.{acc}.project("id","r").by(values("id"))'
        f'.by(bothE().{acc}.otherV().{acc}.{_record_step(trigger)}.values("id").dedup().fold())'
    )


def render_rarity_members(
    record_ids: Sequence[str], exclude_types: Sequence[str], access: AccessFilter, who: Principal
) -> str:
    """Each visible vertex at `record_ids`: its id, stored type, datasets and the ids of the
    visible nodes (of no excluded type) it is linked to by a visible link: its attributes."""
    acc = access.gremlin_has_step(who)
    excluded = (
        f".not(hasLabel({groovy_args_literal([physical_type_name(t) for t in exclude_types])}))"
        if exclude_types
        else ""
    )
    return (
        f'{_rids(record_ids)}.{acc}.project("id","l","ds","nb")'
        '.by(values("id")).by(label()).by(values("datasets").unfold().fold())'
        f'.by(bothE().{acc}.otherV().{acc}{excluded}.values("id").dedup().fold())'
    )


def render_attribute_neighbours(
    record_ids: Sequence[str], access: AccessFilter, who: Principal
) -> str:
    """Each visible attribute vertex at `record_ids`: its id, datasets, and each visible node
    linked to it by a visible link, with that node's type and datasets: what `df` is counted
    from."""
    acc = access.gremlin_has_step(who)
    return (
        f'{_rids(record_ids)}.{acc}.project("id","ds","nb")'
        '.by(values("id")).by(values("datasets").unfold().fold())'
        f'.by(bothE().{acc}.otherV().{acc}.dedup().project("id","l","ds")'
        '.by(values("id")).by(label()).by(values("datasets").unfold().fold()).fold())'
    )


def render_kind_counts(
    physical_label: str, access: AccessFilter, who: Principal
) -> tuple[str, str]:
    """`N_visible` for one stored type: across every readable dataset, and per dataset."""
    acc = access.gremlin_has_step(who)
    start = f"g.V().hasLabel({groovy_string_literal(physical_label)}).{acc}"
    return f"{start}.count()", f'{start}.values("datasets").unfold().groupCount()'


# --- the arithmetic, pure ------------------------------------------------------------------------


@dataclass
class Member:
    id: str
    label: str
    datasets: frozenset[str]
    attributes: frozenset[str]


@dataclass
class Attribute:
    id: str
    datasets: frozenset[str]
    #: Visible neighbours: id -> (stored type, datasets).
    neighbours: dict[str, tuple[str, frozenset[str]]] = field(default_factory=dict)


@dataclass
class Counts:
    """`N_visible` for each stored type: across the case (`None` key) and per dataset."""

    by_kind: dict[str, dict[str | None, int]] = field(default_factory=dict)

    def n(self, kind: str, dataset: str | None) -> int:
        return self.by_kind.get(kind, {}).get(dataset, 0)


def df(attribute: Attribute, kind: str, dataset: str | None) -> int:
    return sum(
        1
        for label, datasets in attribute.neighbours.values()
        if label == kind and (dataset is None or dataset in datasets)
    )


def contribution(attribute: Attribute, kind: str, dataset: str | None, counts: Counts) -> float:
    """`ln(N_visible / df_visible(a))`; 0 when `a` is in no count (cannot happen for a shared
    attribute, whose two holders are counted)."""
    found = df(attribute, kind, dataset)
    total = counts.n(kind, dataset)
    if found <= 0 or total <= 0:
        return 0.0
    return math.log(total / found)


def scope_datasets(
    u_datasets: Iterable[str], v_datasets: Iterable[str], readable: Sequence[str] | None
) -> list[str]:
    """The datasets a per-dataset score is worked out in: both entities', and the reader's."""
    common = set(u_datasets) & set(v_datasets)
    if readable is not None:
        common &= set(readable)
    return sorted(common)


def pair_score(
    u: Member,
    v: Member,
    attributes: Mapping[str, Attribute],
    counts: Counts,
    *,
    per_dataset: bool,
    readable: Sequence[str] | None,
) -> tuple[float | None, str | None, list[tuple[str, float]]]:
    """A pair's score, the dataset it was worked out in, and each shared attribute's contribution,
    highest first. `None` for two of different kinds, or (per dataset) two sharing no dataset."""
    if u.label != v.label or u.id == v.id:
        return None, None, []
    shared = sorted(u.attributes & v.attributes)
    if not per_dataset:
        parts = [(a, contribution(attributes[a], u.label, None, counts)) for a in shared]
        parts.sort(key=lambda p: (-p[1], p[0]))
        return sum(s for _, s in parts), None, parts
    best: tuple[float, str, list[tuple[str, float]]] | None = None
    for dataset in scope_datasets(u.datasets, v.datasets, readable):
        parts = [
            (a, contribution(attributes[a], u.label, dataset, counts))
            for a in shared
            if dataset in attributes[a].datasets
        ]
        parts.sort(key=lambda p: (-p[1], p[0]))
        score = sum(s for _, s in parts)
        if best is None or score > best[0]:
            best = (score, dataset, parts)
    if best is None:
        return None, None, []
    return best


def pair_contributions(
    members: Mapping[str, Member], attributes: Mapping[str, Attribute], *, among: bool
) -> int:
    """How many pair contributions scoring every entity's pairs takes: what the cap is held
    against (rule 2). Among the given entities, an attribute held by `m` of one kind adds
    m·(m − 1)/2; with anyone of the kind, each holder adds the attribute's holders of its kind."""
    work = 0
    holders: dict[tuple[str, str], int] = defaultdict(int)
    for member in members.values():
        for a in member.attributes:
            holders[(a, member.label)] += 1
    for (a, label), held in holders.items():
        attribute = attributes.get(a)
        if attribute is None:
            continue
        if among:
            work += held * (held - 1) // 2
        else:
            work += held * df(attribute, label, None)
    return work


__all__ = [
    "Attribute",
    "Counts",
    "Member",
    "pair_contributions",
    "contribution",
    "df",
    "pair_score",
    "render_attribute_neighbours",
    "render_kind_counts",
    "render_rarity_members",
    "render_records_at_ends",
    "render_records_linked",
    "scope_datasets",
]
