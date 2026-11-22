"""C249: a `Person.date_of_birth` that is not an ISO date no longer fails the whole type's run.

On main `resolver._cast` called `date.fromisoformat` on every value, so one record whose date of
birth read `12/03/1980` (a day-first date a source carried through unconverted) raised `ValueError`
out of `resolve_entity_type`, the worker rolled the transaction back and marked the job failed, and
every other record of the type went unresolved with nobody told.

The invariants and the test that fails if each is broken:

- **A bad date does not fail the type's run**:
  `test_a_bad_date_among_good_ones_resolves_the_good_ones` (the resolver) and
  `test_the_run_completes_over_the_good_records` (the production path,
  `run_resolution_for_entity_type`, over a graph that answers as the adapter does). Plant: the
  `ValueError` put back (`_cast` raising for the value as it did) fails both.
- **A skipped record is named, never silently dropped (rule 2)**: the run's own result counts the
  records left out and names each by id, property and a typed reason, never by the value (a date of
  birth is `sensitivity: high`): `test_the_skipped_record_is_named_by_reason_not_by_value`. Plant:
  the skip with no note.
- **Access control is unchanged (rules 3, 4)**: the population is what the service principal's
  `list_nodes` returns, and a record it may not read is never fetched, so it is neither resolved
  nor named as skipped:
  `test_a_record_the_service_principal_may_not_read_is_neither_resolved_nor_named`.
  The graph stand-in refuses as the adapter does, by `principal_may_view` over each node's handling.
- **A date is still cast, not read as text**: `test_good_dates_still_reach_the_comparison_as_dates`
  (the earlier defect that `year(VARCHAR)` fails to bind).
- **A worker's failure is recorded and readable**:
  `tests/services/api/test_resolution_job_status.py`.

The shapes planted are the ones a source really carries: a day-first date, a free-text date, an
impossible calendar date, and an empty string (which `date.fromisoformat` also refuses).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from services.resolve import resolver as resolver_module
from services.resolve.resolver import resolve_entity_type
from services.resolve.trigger import (
    ResolutionRunResult,
    run_resolution_for_entity_type,
    service_principal,
)

from ontology.handling import load_uk_le_scheme, principal_may_view
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    EdgeWrite,
    EntityTypeDef,
    Handling,
    ListNodesPage,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
PERSON_TYPE: EntityTypeDef = next(e for e in ONTOLOGY.entity_types if e.name == "Person")

#: What a source really carries: day-first, free text, impossible, and an empty cell.
BAD_DATES = ["12/03/1980", "March 1980", "1980-02-31", ""]


def _handling(code: str = "P", classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification,
        handling_code=code,
        originator="unit-1",
        owning_unit="unit-1",
    )


def _person(
    node_id: str, family: str, given: str, dob: str, *, handling: Handling | None = None
) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={"family_name": family, "given_names": given, "date_of_birth": dob},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")],
            first_seen=datetime.now(UTC),
        ),
        handling=handling or _handling(),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )


def _good_pair_and_one_other() -> list[Node]:
    return [
        _person("good-1", "Mercer", "Dana", "1980-01-01"),
        _person("good-2", "Mercer", "Dana", "1980-01-01"),
        _person("other", "Okafor", "Susan", "1975-03-03"),
    ]


def _pairs(candidates: Sequence[Any]) -> set[frozenset[str]]:
    return {frozenset((c.node_a, c.node_b)) for c in candidates}


# --- the resolver ---------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", BAD_DATES)
def test_a_bad_date_among_good_ones_resolves_the_good_ones(bad: str) -> None:
    nodes = [*_good_pair_and_one_other(), _person("bad", "Mercer", "Dana", bad)]
    # The function the defect was in, as every caller calls it: it must not raise.
    candidates = resolve_entity_type(nodes, PERSON_TYPE)
    assert frozenset({"good-1", "good-2"}) in _pairs(candidates)
    assert all("bad" not in pair for pair in _pairs(candidates)), (
        "a record whose date is not a date is left out of the comparison, never compared"
    )


@pytest.mark.parametrize("bad", BAD_DATES)
def test_the_skipped_record_is_named_by_reason_not_by_value(bad: str) -> None:
    nodes = [*_good_pair_and_one_other(), _person("bad", "Mercer", "Dana", bad)]
    outcome = resolver_module.resolve_entity_type_with_skips(nodes, PERSON_TYPE)
    assert frozenset({"good-1", "good-2"}) in _pairs(outcome.candidates)
    assert [(s.node_id, s.property, s.reason) for s in outcome.skipped] == [
        ("bad", "date_of_birth", "not_an_iso_date")
    ]
    # Rule 7 and the property's own sensitivity: the note says what was wrong, never the value.
    assert not bad or bad not in repr(outcome.skipped)


def test_every_bad_record_is_named_and_a_type_left_with_one_record_is_not_compared() -> None:
    nodes = [
        _person("good", "Mercer", "Dana", "1980-01-01"),
        _person("bad-1", "Mercer", "Dana", "12/03/1980"),
        _person("bad-2", "Mercer", "Dana", "March 1980"),
    ]
    outcome = resolver_module.resolve_entity_type_with_skips(nodes, PERSON_TYPE)
    assert outcome.candidates == []
    assert [s.node_id for s in outcome.skipped] == ["bad-1", "bad-2"]


def test_a_type_with_no_bad_date_has_nothing_skipped() -> None:
    outcome = resolver_module.resolve_entity_type_with_skips(
        _good_pair_and_one_other(), PERSON_TYPE
    )
    assert outcome.skipped == []
    assert frozenset({"good-1", "good-2"}) in _pairs(outcome.candidates)


def test_a_date_missing_altogether_is_not_a_bad_date() -> None:
    """No `date_of_birth` at all is a record with no date, which the comparison already treats as
    unknown: it is compared and not named as skipped."""
    without = _person("no-date", "Mercer", "Dana", "1980-01-01")
    del without.properties["date_of_birth"]
    outcome = resolver_module.resolve_entity_type_with_skips(
        [*_good_pair_and_one_other(), without], PERSON_TYPE
    )
    assert outcome.skipped == []


def test_good_dates_still_reach_the_comparison_as_dates() -> None:
    """The earlier defect (`year(VARCHAR)` does not bind): a good date is cast, not left as text,
    so the pair on the same date of birth still scores as a match."""
    outcome = resolver_module.resolve_entity_type_with_skips(
        _good_pair_and_one_other(), PERSON_TYPE
    )
    top = max(outcome.candidates, key=lambda c: c.score)
    assert {top.node_a, top.node_b} == {"good-1", "good-2"}
    assert top.score > 0.9


def test_the_plant_the_value_error_put_back_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15: the planted fault at the shape the code sees. `_cast` as it was on main raised
    `ValueError` for the string it was given; with that back, the type's run fails, so the tests
    above are not passing by another route."""
    real = resolver_module._cast_or_skip

    def raising(value: Any, prop_type: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(value, str) and prop_type is not None and prop_type.value == "date":
            import datetime as dt

            return dt.date.fromisoformat(value)
        return real(value, prop_type, *args, **kwargs)

    monkeypatch.setattr(resolver_module, "_cast_or_skip", raising)
    nodes = [*_good_pair_and_one_other(), _person("bad", "Mercer", "Dana", "12/03/1980")]
    with pytest.raises(ValueError):
        resolver_module.resolve_entity_type_with_skips(nodes, PERSON_TYPE)


# --- the production path -------------------------------------------------------------------------


class _VisibleGraph:
    """The graph as the resolution run reads and writes it, refusing as the adapter does: a node is
    listed only to a principal who may view its handling (`principal_may_view`, the same two axes
    the adapter injects into the traversal). It answers no link between the nodes, and keeps what
    is written."""

    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = nodes
        self.written: list[EdgeWrite] = []
        self.listed_for: list[str] = []

    async def list_nodes(
        self, entity_type: str, principal: Principal, *, cursor: str | None = None, limit: int = 500
    ) -> ListNodesPage:
        self.listed_for.append(principal.id)
        seen = [
            n
            for n in self._nodes
            if n.type == entity_type and principal_may_view(n.handling, principal, SCHEME)
        ]
        return ListNodesPage(nodes=seen, next_cursor=None)

    async def expand(self, request: Any, principal: Principal) -> Subgraph:
        return Subgraph(nodes=[], edges=[])

    async def upsert_edges(self, writes: list[EdgeWrite], tx: str) -> list[str]:
        self.written.extend(writes)
        return [w.id for w in writes]


async def _no_layers() -> set[str]:
    return set()


async def _run(nodes: list[Node]) -> tuple[ResolutionRunResult, _VisibleGraph]:
    graph = _VisibleGraph(nodes)
    result = await run_resolution_for_entity_type(
        "Person",
        graph=graph,  # type: ignore[arg-type]
        tx="tx-1",
        ontology=ONTOLOGY,
        scheme=SCHEME,
        analyst_layers=_no_layers,
    )
    return result, graph


async def test_the_run_completes_over_the_good_records() -> None:
    nodes = [*_good_pair_and_one_other(), _person("bad", "Mercer", "Dana", "12/03/1980")]
    result, graph = await _run(nodes)
    assert result.skipped is False, "`skipped` is the overlap guard's word; this run ran"
    assert result.same_as_written == 1
    assert [frozenset((w.source, w.target)) for w in graph.written] == [
        frozenset({"good-1", "good-2"})
    ]


async def test_the_runs_own_result_counts_and_names_what_it_left_out() -> None:
    nodes = [
        *_good_pair_and_one_other(),
        _person("bad-a", "Mercer", "Dana", "12/03/1980"),
        _person("bad-b", "Okafor", "Susan", "yesterday"),
    ]
    result, _ = await _run(nodes)
    assert result.records_left_out == 2
    said = result.to_dict()
    assert said["records_left_out"] == 2
    assert said["left_out"] == [
        {"node_id": "bad-a", "property": "date_of_birth", "reason": "not_an_iso_date"},
        {"node_id": "bad-b", "property": "date_of_birth", "reason": "not_an_iso_date"},
    ]
    assert "12/03/1980" not in repr(said) and "yesterday" not in repr(said)
    assert result.nodes_processed == len(nodes), "the population read, as before"


async def test_a_run_with_nothing_left_out_says_so_in_its_result() -> None:
    result, _ = await _run(_good_pair_and_one_other())
    assert result.records_left_out == 0
    assert result.to_dict()["left_out"] == []


async def test_a_record_the_service_principal_may_not_read_is_neither_resolved_nor_named() -> None:
    """Rules 3 and 4: the run sees what its principal may see and no more. A restricted record
    (`handling_code` R, which the service principal carries no code for) with a bad date is never
    fetched, so it is not compared, and it is not named among the records left out either: naming
    it would tell whoever reads the run's result that a record exists that they may not see."""
    restricted = _person(
        "hidden", "Mercer", "Dana", "12/03/1980", handling=_handling("R", "SECRET")
    )
    nodes = [*_good_pair_and_one_other(), restricted]
    result, graph = await _run(nodes)
    assert graph.listed_for == [service_principal(SCHEME).id]
    assert result.records_left_out == 0
    assert "hidden" not in repr(result.to_dict())
    assert result.nodes_processed == 3
