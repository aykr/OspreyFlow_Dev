"""The visual query builder's own preview and sync/job routing decisions —
`spec/02_GLASS_FRONTEND.md` §3.3, `spec/08_ACCEPTANCE_SCENARIOS.md` B19, `spec/06_DECISIONS.md`
ADR-030. Exercised against a minimal fake `GraphPort`, the same shape `test_supersede.py` uses for
`submit_supersede_node`'s own sync/job decision: the thing under test is `preview_pattern`/
`run_pattern`'s own logic, not `GraphPort.match`/`match_count` themselves (those are proven
against a live adapter in `tests/conformance/graph_port`).
"""

from __future__ import annotations

from services.api.patterns import (
    JOB_TYPE_PATTERN_MATCH,
    PREVIEW_COUNT_CEILING,
    preview_pattern,
    run_pattern,
    run_pattern_match_job,
)

from schemas.domain import Node, PatternEdge, PatternNode, PatternQuery, Principal, Subgraph

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _pattern(limit: int = 1000) -> PatternQuery:
    return PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person"),
            PatternNode(var="e", entity_type="Endpoint"),
        ],
        edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        limit=limit,
    )


def _node(node_id: str) -> Node:
    from datetime import UTC, datetime

    from schemas.domain import AuditStub, Handling, Provenance, ProvenanceState, SourceRef

    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="analyst-1"),
    )


class _FakeGraph:
    def __init__(self, *, true_count: int) -> None:
        self._true_count = true_count
        self.match_count_calls: list[int] = []
        self.match_calls: list[int] = []

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        self.match_count_calls.append(ceiling)
        return min(self._true_count, ceiling)

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        self.match_calls.append(pattern.limit)
        materialised = min(self._true_count, pattern.limit)
        return Subgraph(nodes=[_node(f"n{i}") for i in range(materialised)], edges=[])


class _FakeJobQueue:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, dict[str, object]]] = []

    async def submit(self, job_type: str, payload: dict[str, object]) -> str:
        self.submitted.append((job_type, payload))
        return "job-1"


async def test_preview_reports_an_exact_count_under_the_ceiling() -> None:
    graph = _FakeGraph(true_count=42)
    preview = await preview_pattern(_pattern(), graph=graph, principal=PRINCIPAL)  # type: ignore[arg-type]
    assert preview.estimated_count == 42
    assert preview.is_floor is False
    assert graph.match_count_calls == [PREVIEW_COUNT_CEILING]


async def test_preview_reports_a_floor_at_the_ceiling_never_a_falsely_precise_number() -> None:
    graph = _FakeGraph(true_count=50_000)
    preview = await preview_pattern(_pattern(), graph=graph, principal=PRINCIPAL)  # type: ignore[arg-type]
    assert preview.estimated_count == PREVIEW_COUNT_CEILING
    assert preview.is_floor is True


async def test_run_below_the_limit_executes_synchronously_with_an_exact_count() -> None:
    graph = _FakeGraph(true_count=200)
    jobs = _FakeJobQueue()
    accepted = await run_pattern(
        _pattern(limit=1000), graph=graph, principal=PRINCIPAL, jobs=jobs  # type: ignore[arg-type]
    )
    assert accepted.mode == "sync"
    assert accepted.matched_count == 200
    assert accepted.subgraph is not None and len(accepted.subgraph.nodes) == 200
    assert jobs.submitted == []


async def test_run_at_or_above_the_limit_never_returns_a_silently_capped_subgraph() -> None:
    graph = _FakeGraph(true_count=5_000)
    jobs = _FakeJobQueue()
    accepted = await run_pattern(
        _pattern(limit=1000), graph=graph, principal=PRINCIPAL, jobs=jobs  # type: ignore[arg-type]
    )
    assert accepted.mode == "job"
    assert accepted.job_id == "job-1"
    assert accepted.subgraph is None
    assert accepted.matched_count is None
    # `match()` is never called synchronously once the count check has already shown the true
    # population exceeds `pattern.limit` — the defect this test guards is a caller that runs the
    # capped query anyway and reports it as if it were the whole answer.
    assert graph.match_calls == []
    (job_type, payload) = jobs.submitted[0]
    assert job_type == JOB_TYPE_PATTERN_MATCH


async def test_pattern_match_job_raises_the_ceiling_rather_than_reusing_the_original_limit() -> (
    None
):
    graph = _FakeGraph(true_count=5_000)
    result = await run_pattern_match_job(
        {
            "pattern": _pattern(limit=1000).model_dump(mode="json"),
            "principal": PRINCIPAL.model_dump(mode="json"),
        },
        graph=graph,  # type: ignore[arg-type]
        tx="tx-1",
    )
    assert result["matched_count"] == 5_000
    # Proves the job re-ran at a raised cap, not the original request's own smaller `limit=1000` —
    # the exact "moved the truncation one layer down instead of fixing it" regression named in
    # `run_pattern_match_job`'s own docstring.
    assert graph.match_calls == [100_000]
