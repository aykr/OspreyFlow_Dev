"""Connection strength and shared-attribute rarity in the ArcadeDB adapter (`06_DECISIONS.md`
ADR-139 decisions 2 and 4; `GraphPort.connection_strengths` and `shared_attribute_rarity`).

Every query here carries the access step on every vertex and every link it steps over (rule 3), so
a record, entity or link the principal may not see is in no count and evidences nothing: the result
is the result in a world without it. Nothing is stored. The arithmetic is pure and lives elsewhere:
`ontology/influencers.py` for strength, and `pair_score` below for rarity.

**The client's measure** (ADR-139 Amendment 2, `share`) needs, beside what the pair holds, the
pair links through every value of the same kind in scope (`Σ_b C(k_b, 2)`): `render_kind_holders`
reads each visible value of a kind with its visible holders, and `ShareTotals` sums them, per
dataset and across the case. **Client parity** needs, for a stored link, how many links of its
type the reader may see in each dataset (`render_link_type_counts`).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ontology.influencers import pair_links, share_rarity
from schemas.domain import Principal
from schemas.strength import InfluencerTrigger, RarityMeasure

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
    """Each visible attribute vertex at `record_ids`: its id, stored type, datasets, and each
    visible node linked to it by a visible link, with that node's type and datasets: what `df`
    (and the client's `k`) is counted from."""
    acc = access.gremlin_has_step(who)
    return (
        f'{_rids(record_ids)}.{acc}.project("id","l","ds","nb")'
        '.by(values("id")).by(label()).by(values("datasets").unfold().fold())'
        f'.by(bothE().{acc}.otherV().{acc}.dedup().project("id","l","ds")'
        '.by(values("id")).by(label()).by(values("datasets").unfold().fold()).fold())'
    )


def render_kind_holders(
    attribute_label: str, holder_label: str, access: AccessFilter, who: Principal
) -> tuple[str, str]:
    """For the client's sum: how many (value, holder) steps there are to read, for the cap, and
    then each visible value of `attribute_label` (a stored type) with its datasets and the
    datasets of each visible holder of `holder_label` linked to it by a visible link."""
    acc = access.gremlin_has_step(who)
    start = f"g.V().hasLabel({groovy_string_literal(attribute_label)}).{acc}"
    holders = f"bothE().{acc}.otherV().{acc}.hasLabel({groovy_string_literal(holder_label)})"
    return (
        f"{start}.{holders}.count()",
        f'{start}.project("ds","h").by(values("datasets").unfold().fold())'
        f'.by({holders}.dedup().project("ds").by(values("datasets").unfold().fold()).fold())',
    )


def render_link_type_counts(
    physical_labels: Sequence[str], access: AccessFilter, who: Principal
) -> tuple[str, str]:
    """Client parity's `n`: the links of one type (its stored labels) the reader may see, the
    link and both its ends, across the case and per dataset."""
    acc = access.gremlin_has_step(who)
    start = (
        f"g.E().hasLabel({groovy_args_literal(list(physical_labels))}).{acc}"
        f".where(outV().{acc}).where(inV().{acc})"
    )
    return f"{start}.count()", f'{start}.values("datasets").unfold().groupCount()'


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
    #: The attribute's own stored type: its kind, for the client's sum.
    label: str = ""


@dataclass
class ShareTotals:
    """The client's `ΣN`: `Σ_b C(k_b, 2)` over the visible values `b` of one kind, by
    (value kind, holder kind), across the case (`None` key) and per dataset."""

    by_kinds: dict[tuple[str, str], dict[str | None, int]] = field(default_factory=dict)

    def total(self, attribute_kind: str, holder_kind: str, dataset: str | None) -> int:
        return self.by_kinds.get((attribute_kind, holder_kind), {}).get(dataset, 0)

    def add_value(
        self,
        attribute_kind: str,
        holder_kind: str,
        value_datasets: Iterable[str],
        holder_datasets: Sequence[Iterable[str]],
    ) -> None:
        """One visible value and its visible holders' datasets: `C(k, 2)` across the case, and in
        each dataset the value belongs to, `C(k_d, 2)` for its holders in that dataset."""
        sums = self.by_kinds.setdefault((attribute_kind, holder_kind), {})
        sums[None] = sums.get(None, 0) + pair_links(len(holder_datasets))
        held = [set(d) for d in holder_datasets]
        for dataset in set(value_datasets):
            k = sum(1 for d in held if dataset in d)
            sums[dataset] = sums.get(dataset, 0) + pair_links(k)


def share_value(
    attribute: Attribute, kind: str, dataset: str | None, totals: ShareTotals
) -> float:
    """The client's `1 − N/ΣN` for one value, in one dataset (or across the case)."""
    return share_rarity(
        pair_links(df(attribute, kind, dataset)), totals.total(attribute.label, kind, dataset)
    )


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
    measure: RarityMeasure = "idf",
    totals: ShareTotals | None = None,
    add_for: Callable[[str | None], float] | None = None,
) -> tuple[float | None, str | None, list[tuple[str, float]]]:
    """A pair's score, the dataset it was worked out in, and each shared attribute's score,
    highest first. `None` for two of different kinds, or (per dataset) two sharing no dataset.

    `idf`: the sum of `ln(N/df)` over what they share. `share` (the client's): the highest of each
    shared value's `1 − C(k, 2)/ΣC(k_b, 2)` (`totals`). Per dataset, the dataset whose score (plus
    `add_for(dataset)`, for client parity's adds) is highest is kept."""
    if u.label != v.label or u.id == v.id:
        return None, None, []
    shared = sorted(u.attributes & v.attributes)

    def scored(dataset: str | None) -> tuple[float, list[tuple[str, float]]]:
        held = [a for a in shared if dataset is None or dataset in attributes[a].datasets]
        if measure == "share":
            assert totals is not None
            parts = [(a, share_value(attributes[a], u.label, dataset, totals)) for a in held]
        else:
            parts = [(a, contribution(attributes[a], u.label, dataset, counts)) for a in held]
        parts.sort(key=lambda p: (-p[1], p[0]))
        if measure == "share":
            return (parts[0][1] if parts else 0.0), parts
        return sum(s for _, s in parts), parts

    if not per_dataset:
        score, parts = scored(None)
        return score, None, parts
    best: tuple[float, float, str, list[tuple[str, float]]] | None = None
    for dataset in scope_datasets(u.datasets, v.datasets, readable):
        score, parts = scored(dataset)
        ranked = score + (add_for(dataset) if add_for else 0.0)
        if best is None or ranked > best[0]:
            best = (ranked, score, dataset, parts)
    if best is None:
        return None, None, []
    return best[1], best[2], best[3]


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
    "ShareTotals",
    "render_kind_holders",
    "render_link_type_counts",
    "share_value",
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
