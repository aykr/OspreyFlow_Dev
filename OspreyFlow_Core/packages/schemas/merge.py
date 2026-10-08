"""The one merge rule for a repeated edge pair, used by every write path (ADR-058 D5).

`01_DOMAIN_MODEL.md` §3: one summarised edge per (type, source, target). A second write for the
same pair merges into the stored edge instead of adding another: the occurrences add, every
provenance source is kept (de-duplicated by document and locator, §7), the interval widens, the
latest write's own properties win, the handling is never lowered (ADR-102: the most restrictive
of each part, `ontology.handling.merge_handling`), and the revision counts the writes.
`GraphArcadeDBAdapter.upsert_edges` applies the rule one write at a time against the store; a bulk
load receives all of a pair's writes together and applies it here before anything is written.
Keeping the rule in one place is the point: two copies would drift, and the test that compares the
two paths (`tests/adapters/graph_arcadedb/test_merge_rules_shared_by_both_paths.py`) would be the
only thing to notice.

Pure functions over the domain models; nothing here touches a store.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from schemas.domain import EdgeWrite, Handling, Interval, Provenance


def merge_provenance(existing: Provenance | None, incoming: Provenance) -> Provenance:
    """Every source row reference is retained (`01_DOMAIN_MODEL.md` §7), de-duplicated by
    `(document_id, locator)` so writing the same row twice does not grow the list. The other
    provenance fields are the incoming write's own."""
    if existing is None:
        return incoming
    seen = {(s.document_id, s.locator) for s in existing.sources}
    merged_sources = list(existing.sources)
    for source in incoming.sources:
        if (source.document_id, source.locator) not in seen:
            merged_sources.append(source)
            seen.add((source.document_id, source.locator))
    return incoming.model_copy(update={"sources": merged_sources})


def merge_datasets(existing: Sequence[str] | None, incoming: Sequence[str]) -> list[str]:
    """ADR-099: an element belongs to every dataset that wrote it, so a second write adds its
    datasets and never drops one. Sorted, so the stored list is the same whatever the order."""
    return sorted(set(existing or ()) | set(incoming))


def merge_interval(existing: Interval | None, incoming: Interval | None) -> Interval | None:
    """The union of the two: the earliest start and the latest end. A missing interval never
    erases a present one."""
    if existing is None:
        return incoming
    if incoming is None:
        return existing
    valid_from = min(existing.valid_from, incoming.valid_from)
    existing_to = existing.valid_to or existing.valid_from
    incoming_to = incoming.valid_to or incoming.valid_from
    return Interval(valid_from=valid_from, valid_to=max(existing_to, incoming_to))


@dataclass(frozen=True)
class AggregatedEdge:
    """One edge per pair, and how many writes it summarises (the stored revision)."""

    write: EdgeWrite
    writes: int


def _pair_key(write: EdgeWrite, *, directed: bool) -> tuple[str, str, str]:
    """An undirected type's pair is the same either way round, as `upsert_edges` finds it."""
    low, high = write.source, write.target
    if not directed and high < low:
        low, high = high, low
    return (write.type, low, high)


def aggregate_edge_writes(
    writes: Sequence[EdgeWrite],
    *,
    directed: Callable[[str], bool],
    handling: Callable[[Handling, Handling], Handling],
) -> list[AggregatedEdge]:
    """Collapse repeated pairs by the rule above, in order of each pair's first appearance.

    What the aggregate keeps of which write mirrors what `upsert_edges` leaves in the store: the
    first write's id, endpoints (and so orientation), `created_at` and `created_by`, because the
    stored edge keeps them; every write's datasets (ADR-099); the latest write's properties,
    `load_id` and recipe, because a merge takes those from the incoming write; the handling merged
    by `handling(existing, incoming)` (ADR-102, never lowered); occurrences summed; provenance and
    interval merged. `directed(type_name)` says whether a type is directed. `handling` is required,
    so no caller can leave a later write free to lower a link."""
    order: list[tuple[str, str, str]] = []
    grouped: dict[tuple[str, str, str], tuple[EdgeWrite, int]] = {}
    for write in writes:
        key = _pair_key(write, directed=directed(write.type))
        held = grouped.get(key)
        if held is None:
            order.append(key)
            grouped[key] = (write, 1)
            continue
        accumulated, count = held
        grouped[key] = (
            write.model_copy(
                update={
                    "id": accumulated.id,
                    "source": accumulated.source,
                    "target": accumulated.target,
                    "created_at": accumulated.created_at,
                    "created_by": accumulated.created_by,
                    "occurrences": accumulated.occurrences + write.occurrences,
                    "interval": merge_interval(accumulated.interval, write.interval),
                    "provenance": merge_provenance(accumulated.provenance, write.provenance),
                    "datasets": merge_datasets(accumulated.datasets, write.datasets),
                    "handling": handling(accumulated.handling, write.handling),
                }
            ),
            count + 1,
        )
    return [AggregatedEdge(write=grouped[key][0], writes=grouped[key][1]) for key in order]
