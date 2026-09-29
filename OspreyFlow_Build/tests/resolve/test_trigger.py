"""`services/resolve/trigger.py` — `06_DECISIONS.md` ADR-025's corpus-wide resolution trigger.

Four layers, each proven at the level that actually needs it:
- `service_principal`'s clearance/receivable-codes choice — pure, unit-tested directly.
- That choice actually holds against the real adapter: a restricted-`handling_code` record is
  invisible to the service principal specifically, not to every principal
  (`01_DOMAIN_MODEL.md` §2.2's own decision) — real ArcadeDB, no fake, per the four-instances
  finding below.
- `_fetch_population`'s "page until `next_cursor is None`" loop — the caller-side half of rule 2's
  "never truncate silently" (`list_nodes`'s own conformance suite already proves the port side of
  that contract), proven against a small recording fake since nothing security-relevant depends on
  the fake's own behaviour here — the same precedent `tests/services/api/test_supersede.py`
  already established for a routing decision, not an access-control claim.
- The overlap guard and the full orchestration — real Valkey and real ArcadeDB
  (`adapters.graph_arcadedb.testing.arcadedb_adapter`), no fakes, since this is exactly the kind
  of security/concurrency-relevant path the four-instances finding
  says a fake cannot stand in for.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.resolve.trigger import (
    LOCK_TTL_SECONDS,
    ResolutionRunResult,
    _fetch_population,
    run_resolution_for_entity_type,
    service_principal,
    try_run_resolution_with_overlap_guard,
)
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Handling,
    ListNodesPage,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


def _person_write(family_name: str, given_names: str, date_of_birth: str) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=now,
        ),
        handling=_handling(),
        created_by=CLEARED.id,
        created_at=now,
    )


def test_service_principal_carries_the_schemes_top_clearance_and_no_restricted_codes() -> None:
    scheme = load_uk_le_scheme()
    principal = service_principal(scheme)
    assert principal.clearance == "SECRET"  # uk-le.yaml's own most-restrictive classification
    assert principal.receivable_handling_codes == []


# --- _fetch_population's pagination loop (fake — a routing/looping decision, not access control) -


def _node(node_id: str) -> Node:
    from schemas.domain import AuditStub

    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="a" * 64)],
            first_seen=datetime.now(UTC),
        ),
        handling=_handling(),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="loader-1"),
    )


class _PagingFakeGraph:
    """Three nodes, forced over three one-node pages — proves the loop keeps calling `list_nodes`
    until `next_cursor is None`, never stopping on a short page early (`ListNodesPage`'s own
    docstring, the exact defect a caller that guessed from page length rather than checking the
    field would reproduce)."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self._pages = {
            None: ListNodesPage(nodes=[_node("n1")], next_cursor="n1"),
            "n1": ListNodesPage(nodes=[_node("n2")], next_cursor="n2"),
            "n2": ListNodesPage(nodes=[_node("n3")], next_cursor=None),
        }

    async def list_nodes(
        self, entity_type: str, principal: Principal, *, cursor: str | None = None, limit: int = 500
    ) -> ListNodesPage:
        self.calls.append(cursor)
        return self._pages[cursor]


async def test_fetch_population_pages_until_next_cursor_is_none() -> None:
    graph = _PagingFakeGraph()
    nodes = await _fetch_population(graph, "Person", CLEARED)  # type: ignore[arg-type]
    assert [n.id for n in nodes] == ["n1", "n2", "n3"]
    assert graph.calls == [None, "n1", "n2"]


# --- the overlap guard, real Valkey --------------------------------------------------------


async def test_overlap_guard_skips_a_second_run_while_the_first_holds_the_lock() -> None:
    client = Valkey(host="localhost", port=6379, db=0)
    entity_type = f"test-Person-{datetime.now(UTC).timestamp()}"
    lock_key = f"resolve:running:{entity_type}"
    held_lock = client.lock(lock_key, timeout=LOCK_TTL_SECONDS, blocking=False)
    assert await held_lock.acquire()

    called = False

    async def _should_not_run(*args: object, **kwargs: object) -> ResolutionRunResult:
        nonlocal called
        called = True
        raise AssertionError("must not run while the lock is held")

    import services.resolve.trigger as trigger_module

    original = trigger_module.run_resolution_for_entity_type
    trigger_module.run_resolution_for_entity_type = _should_not_run
    try:
        result = await try_run_resolution_with_overlap_guard(
            entity_type,
            graph=None,  # type: ignore[arg-type]
            tx="tx-1",
            ontology=None,  # type: ignore[arg-type]
            scheme=None,  # type: ignore[arg-type]
            valkey=client,
        )
    finally:
        trigger_module.run_resolution_for_entity_type = original

    assert called is False
    assert result.skipped is True
    assert result.reason == "a resolution run is already in progress"

    await held_lock.release()
    await client.delete(lock_key)
    await client.aclose()


# --- full orchestration, real ArcadeDB -------------------------------------------------------


async def test_run_resolution_for_entity_type_writes_same_as_and_records_a_conflict() -> None:
    """One live pass proving the wiring itself — `list_nodes` (paged) feeding
    `resolve_entity_type`, its candidates feeding `write_same_as_edges` *and* `detect_conflicts`,
    a manually-split pair's conflict correctly recorded via `record_conflicts` — the composition
    `tests/resolve/*`'s own unit tests each prove one link of in isolation."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (dup_a_id, dup_b_id, split_c_id, split_d_id) = await graph.upsert_nodes(
            [
                _person_write("Mercer", "Dana", "1980-01-01"),
                _person_write("Mercer", "Dana", "1980-01-01"),
                _person_write("Ahmed", "Zayn", "1975-06-01"),
                _person_write("Ahmed", "Zayn", "1975-06-01"),
            ],
            tx,
        )
        from schemas.domain import EdgeWrite

        await graph.upsert_edges(
            [
                EdgeWrite(
                    id=new_id(),
                    type="NOT_SAME_AS",
                    source=split_c_id,
                    target=split_d_id,
                    properties={},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[
                            SourceRef(document_id="analyst", locator="manual", excerpt_hash="")
                        ],
                        first_seen=datetime.now(UTC),
                    ),
                    handling=_handling(),
                    created_by=CLEARED.id,
                    created_at=datetime.now(UTC),
                )
            ],
            tx,
        )
        await graph.commit_transaction(tx)

        tx = await graph.begin_transaction()
        result = await run_resolution_for_entity_type(
            "Person", graph=graph, tx=tx, ontology=ontology, scheme=scheme
        )
        await graph.commit_transaction(tx)

        assert result.nodes_processed == 4
        assert result.same_as_written >= 1
        assert result.conflicts_recorded == 1

        dup_a = await graph.get_node(dup_a_id, CLEARED)
        dup_b = await graph.get_node(dup_b_id, CLEARED)
        assert dup_a is not None and dup_b is not None


async def test_service_principal_cannot_see_a_restricted_handling_code_record() -> None:
    """`01_DOMAIN_MODEL.md` §2.2's own decision, proven against the real adapter rather than left
    asserted only in `service_principal`'s docstring: the service principal carries the scheme's
    top *clearance* but no *receivable restricted codes*, so a `Person` marked with a restricted
    `handling_code` (`R`, `uk-le.yaml`) is invisible to it regardless of classification — the same
    two-axis check `AccessFilter.gremlin_has_step` already applies to every other principal. A
    second, ordinarily-cleared-and-entitled principal proves the record exists and would be visible
    to a principal that *does* carry the code, so this isn't merely an unreachable fixture."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    entitled = Principal(
        id="reviewer-1",
        clearance="SECRET",
        org_unit="restricted-unit",
        receivable_handling_codes=["R"],
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (restricted_id,) = await graph.upsert_nodes(
            [
                NodeWrite(
                    id=new_id(),
                    type="Person",
                    properties={"family_name": "Classified", "given_names": "R."},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[SourceRef(document_id="d", locator="l", excerpt_hash="a" * 64)],
                        first_seen=datetime.now(UTC),
                    ),
                    handling=Handling(
                        classification="SECRET",
                        handling_code="R",
                        originator="restricted-unit",
                        owning_unit="restricted-unit",
                    ),
                    created_by="analyst-1",
                    created_at=datetime.now(UTC),
                )
            ],
            tx,
        )
        await graph.commit_transaction(tx)

        service = service_principal(scheme)
        page = await graph.list_nodes("Person", service, limit=500)
        assert restricted_id not in {n.id for n in page.nodes}

        entitled_page = await graph.list_nodes("Person", entitled, limit=500)
        assert restricted_id in {n.id for n in entitled_page.nodes}
