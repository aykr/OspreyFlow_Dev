"""Detects when a fresh resolution run's candidates would have merged a pair an analyst already
split — `01_DOMAIN_MODEL.md` §4: "a manual split is a `NOT_SAME_AS` edge that the projection
always honours and no future resolution run may override", and
`03_CONDUIT_MIDDLEWARE.md` §5.3: "a later run that would have merged the pair records the
conflict for review rather than acting on it."

**The record's shape is this build's own design, not spec text.** Both citations above name the
*behaviour* ("record the conflict for review") but neither specifies what a recorded conflict
must contain — unlike `SAME_AS`'s `model_version`/`comparison_vector`, which `01_DOMAIN_MODEL.md`
§4 names explicitly (`06_DECISIONS.md`'s ADR-021 citation confirms that one is spec-derived; this
one is a Stage 5 judgement call, flagged as such per `CLAUDE.md`'s "before you write code" rule
rather than folded in as if the spec already said so).

**Why annotate the existing `NOT_SAME_AS` edge rather than invent a new edge type or a
side-channel record.** `GraphPort.supersede_edge` already exists for exactly "a correction to
the evidence itself" (its own docstring) and gives the conflict a real, permanent, queryable home
— on the one edge a reviewing analyst would already look at — without a new port method, a new
system edge type, or a store outside the Vault the working set's own 24-hour TTL would eventually
drop. `packages/ontology/loader.py`'s `_SYSTEM_EDGE_PROPERTIES[NOT_SAME_AS]` carries the four
`conflict_*` fields this produces.

**Why this stops at detection+recording, not a review surface.** No endpoint here or elsewhere
lists "all pending conflicts" for an investigation or the corpus — an analyst who already knows
which pair to check can query `explain`/the graph directly for `conflict_pending = true`, but
nothing proactively surfaces it. `07_BUILD_PLAN.md`'s Phase 6 known-gaps list records this as a
deliberate gap, not an oversight.

**What "would have merged" means with no session-specific τ available here.** This module runs
against the whole corpus, outside any one investigation's session — there is no per-investigation
τ to test against. `services/resolve/projection.THRESHOLD_BROAD` (0.80) is the bar, not
`DEFAULT_THRESHOLD` (Balanced, 0.95): merging is monotonic in score, so a candidate that clears
Strict or Balanced also clears Broad, which makes Broad the one single value that catches every
candidate that could merge under *any* of the three officially offered detents — an investigation
actually running at Broad would otherwise have a real, silent gap, since a candidate scoring
(say) 0.85 clears Broad but not the Balanced bar this module used to check against. A candidate
that does not even clear Broad could not merge under any of the three supported settings, so it
genuinely is not a conflict. This substitution (Broad, not the session default) was flagged to
and confirmed by the user rather than decided silently — `06_DECISIONS.md`'s ADR-021 addendum
records the decision and the "why Broad, not Balanced" reasoning above."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from schemas.domain import Edge, EdgeId, NodeId

from .projection import THRESHOLD_BROAD
from .resolver import MODEL_VERSION, SameAsCandidate


@dataclass(frozen=True)
class ResolutionConflict:
    node_a: NodeId
    node_b: NodeId
    not_same_as_edge_id: EdgeId
    would_be_score: float
    would_be_model_version: str
    would_be_comparison_vector: dict[str, Any]


def detect_conflicts(
    candidates: Sequence[SameAsCandidate],
    not_same_as_edges: Sequence[Edge],
    *,
    threshold: float = THRESHOLD_BROAD,
) -> list[ResolutionConflict]:
    """Pure — the same "one pure function over a bounded working set" shape `projection.py`
    already established, so this is unit-testable without a graph or a transaction. A candidate
    conflicts with a split pair only if its score meets `threshold`; a candidate that scores below
    it was never going to merge anything and recording it would just be noise a reviewing analyst
    has to filter back out."""
    split_by_pair: dict[frozenset[NodeId], Edge] = {
        frozenset((edge.source, edge.target)): edge for edge in not_same_as_edges
    }
    conflicts: list[ResolutionConflict] = []
    for candidate in candidates:
        if candidate.score < threshold:
            continue
        edge = split_by_pair.get(frozenset((candidate.node_a, candidate.node_b)))
        if edge is None:
            continue
        conflicts.append(
            ResolutionConflict(
                node_a=candidate.node_a,
                node_b=candidate.node_b,
                not_same_as_edge_id=edge.id,
                would_be_score=candidate.score,
                would_be_model_version=MODEL_VERSION,
                would_be_comparison_vector=candidate.comparison_vector,
            )
        )
    return conflicts


def conflict_properties(conflict: ResolutionConflict) -> dict[str, Any]:
    """The `conflict_*` property values to merge onto the `NOT_SAME_AS` edge's existing
    properties before calling `supersede_edge` — kept separate from the writer
    (`same_as_writer.record_conflicts`) so this stays a pure mapping, no `GraphPort`/`TxId`
    involved."""
    return {
        "conflict_pending": True,
        "conflict_score": conflict.would_be_score,
        "conflict_model_version": conflict.would_be_model_version,
        "conflict_comparison_vector": json.dumps(
            conflict.would_be_comparison_vector, sort_keys=True
        ),
    }
