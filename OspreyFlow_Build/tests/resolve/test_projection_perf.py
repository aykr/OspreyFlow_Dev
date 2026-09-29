"""Phase 6a Stage 2, Question 3's own commitment: "if it debounces, say so explicitly rather than
leaving it to be discovered under a demo" applies to cost too, not just the commit-on-release
decision. `compute_clusters`/`diff_clusters` had no measurement at the working set's own 50,000-
node cap (`services/api/working_set/models.py::MAX_NODES`) before this — this gives "what does it
cost at the top of the range" a real, reported number instead of an assumption.

Not a CI performance gate — `02_GLASS_FRONTEND.md` §5 names Sigma/canvas frame budgets, not this
server-side path, and no figure for it exists to gate against. The assertion below is a generous
regression tripwire (a real quadratic blowup would blow through it by orders of magnitude), not a
tuned budget; the printed timing is the number this stage's own write-up records.

Worst case, not an average one: every one of the 50,000 nodes forms a single chain of `SAME_AS`
edges scored between `THRESHOLD_BROAD` and `THRESHOLD_BALANCED`, so moving from Balanced to Broad
collapses all 50,000 singletons into one cluster in a single call — the largest `merged`/`affected`
event this path can produce, and therefore the largest `diff_clusters` output
(`affected_cluster_ids`) a `DeltaReproject` could ever carry.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from services.api.working_set.models import MAX_NODES
from services.resolve.projection import (
    THRESHOLD_BALANCED,
    THRESHOLD_BROAD,
    compute_clusters,
    diff_clusters,
)

from schemas.domain import AuditStub, Edge, Handling, Provenance, ProvenanceState, SourceRef

# A single shared instance reused across all 50k edges — `compute_clusters`/`diff_clusters` never
# mutate an `Edge`, and constructing a fresh `Provenance`/`Handling`/`AuditStub` per edge would
# measure Pydantic construction cost, not the union-find this test is actually about.
_PROVENANCE = Provenance(
    state=ProvenanceState.INFERRED,
    sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
)
_HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")
_AUDIT = AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1")

# Generous enough that ordinary machine variance never trips it, tight enough that a real
# quadratic blowup in the union-find (e.g. a future change losing path compression) would.
_CEILING_SECONDS = 5.0


def test_compute_clusters_and_diff_clusters_at_the_50k_working_set_cap() -> None:
    node_ids = [f"n{i}" for i in range(MAX_NODES)]
    same_as_edges = [
        Edge(
            id=f"e{i}",
            type="SAME_AS",
            source=f"n{i}",
            target=f"n{i + 1}",
            properties={"score": 0.90},  # below Balanced (0.95), above Broad (0.80)
            provenance=_PROVENANCE,
            handling=_HANDLING,
            audit=_AUDIT,
        )
        for i in range(MAX_NODES - 1)
    ]

    started = time.perf_counter()
    before = compute_clusters(node_ids, same_as_edges, [], THRESHOLD_BALANCED)
    after = compute_clusters(node_ids, same_as_edges, [], THRESHOLD_BROAD)
    delta = diff_clusters(before, after)
    elapsed = time.perf_counter() - started

    # Worst case, checked: every node was its own singleton at Balanced, all 50,000 collapse into
    # one cluster at Broad — the largest single `merged`/`affected`/`affected_cluster_ids` event
    # this path can produce.
    assert delta.merged == 1
    assert delta.split == 0
    assert delta.nodes_affected == MAX_NODES
    assert len(delta.affected_cluster_ids) == MAX_NODES

    print(
        f"\ncompute_clusters x2 + diff_clusters @ {MAX_NODES} nodes / "
        f"{len(same_as_edges)} edges: {elapsed:.3f}s"
    )
    assert elapsed < _CEILING_SECONDS, (
        f"compute_clusters/diff_clusters took {elapsed:.3f}s at the {MAX_NODES}-node cap, "
        f"over the {_CEILING_SECONDS}s tripwire"
    )
