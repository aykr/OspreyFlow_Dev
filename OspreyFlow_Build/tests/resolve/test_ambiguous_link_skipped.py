"""ADR-110 Amendment 18 in a resolution run: recording conflicts supersedes each split link it
annotates, one per conflict. A link whose id two edge types hold is skipped, and the run goes on
with the rest: one bad link never silences the whole run (the shape L2.8 found twice). The skip is
recorded in the run's own result (`ResolutionRunResult.links_skipped`, the job's stored result a
person sees) by the link's id, never its type. Red with the catch removed: the batch stops at the
ambiguous link (`process/lanes/studio/L1.2a_RED_RECORD.md`)."""

from __future__ import annotations

from typing import Any

from ports.graph import AmbiguousLinkId
from schemas.domain import EdgeWrite
from services.resolve.conflicts import ResolutionConflict
from services.resolve.resolver import MODEL_VERSION
from services.resolve.same_as_writer import record_conflicts
from services.resolve.trigger import ResolutionRunResult

from tests.resolve.test_same_as_writer import _split_edge


class _Graph:
    def __init__(self, ambiguous: str) -> None:
        self.ambiguous = ambiguous
        self.superseded: list[str] = []

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: Any) -> str:
        if edge_id == self.ambiguous:
            raise AmbiguousLinkId(edge_id, ["NOT_SAME_AS", "OTHER"])
        self.superseded.append(edge_id)
        return replacement.id


def _conflict(split_id: str) -> ResolutionConflict:
    return ResolutionConflict(
        node_a="n1", node_b="n2", not_same_as_edge_id=split_id, would_be_score=0.97,
        would_be_model_version=MODEL_VERSION, would_be_comparison_vector={"match_weight": 5.1},
    )  # fmt: skip


async def test_an_ambiguous_link_is_skipped_and_the_rest_are_recorded() -> None:
    first = _split_edge().model_copy(update={"id": "split-1"})
    second = _split_edge().model_copy(update={"id": "split-2"})
    graph = _Graph(ambiguous="split-1")
    skipped: list[str] = []

    recorded = await record_conflicts(
        graph,  # type: ignore[arg-type]
        [_conflict("split-1"), _conflict("split-2")],
        {"split-1": first, "split-2": second},
        created_by="resolve-service",
        tx="tx-1",
        skipped=skipped,
    )

    assert graph.superseded == ["split-2"] and len(recorded) == 1, "the other is still written"
    assert skipped == ["split-1"]
    result = ResolutionRunResult(skipped=False, conflicts_recorded=len(recorded), links_skipped=skipped)
    assert result.to_dict()["links_skipped"] == ["split-1"], "in the run's own result"
    assert "OTHER" not in str(result.to_dict())
