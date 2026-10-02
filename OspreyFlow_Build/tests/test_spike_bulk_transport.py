"""The transport spike touches only its own scratch databases and reports what it finds
(ADR-058 D10).

No store is needed: the refusal that keeps it off the working database fires before any
connection is made, the comparison is a pure function, and the shape checks are run against a
store that refuses what it does not recognise (rule 15).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from scripts import spike_bulk_transport as spike


def test_the_working_database_is_refused_before_any_connection() -> None:
    """Catches the spike creating, dropping or loading into a database that is not its own: the
    name is checked before a client is built, so a wrong name cannot reach the server."""
    for name in ("ospreyflow", "vault_paysim", "spike_bulk", "xspike_bulk_1"):
        with pytest.raises(spike.NotScratchError):
            asyncio.run(spike._fresh(name, []))
        with pytest.raises(spike.NotScratchError):
            spike.refuse_unless_scratch(name)
    assert spike.refuse_unless_scratch("spike_bulk_up_120000") == "spike_bulk_up_120000"


def test_every_scratch_name_the_run_builds_passes_the_guard() -> None:
    """Catches a candidate name drifting off the prefix, which would make the run refuse itself
    only when it reaches the store."""
    for template in ("up_{}", "g{}_{}", "sql_{}", "shapes_{}"):
        assert (spike.SCRATCH_PREFIX + template.format(100, "120000")).startswith(
            "spike_bulk_"
        )


def test_synthetic_writes_have_shared_accounts_and_repeated_pairs() -> None:
    """Catches a data set that exercises neither path's hard cases: accounts shared between
    edges (so degrees matter) and repeated pairs (so the merge runs)."""
    nodes, edges = spike.synthetic_writes(200)
    assert len(edges) == 200 and len({e.id for e in edges}) == 200
    assert len(nodes) < 2 * len(edges)
    pairs = [(e.source, e.target) for e in edges]
    assert len(set(pairs)) < len(pairs)
    assert {n.id for n in nodes} >= {p for pair in pairs for p in pair}
    assert [e.id for e in edges] == [e.id for e in spike.synthetic_writes(200)[1]]


def test_the_comparison_reports_a_missing_an_extra_and_a_wrong_count() -> None:
    """Catches a comparison that says 'identical' when the methods left different edges."""
    reference = {"a": 1, "b": 2, "c": 3}
    assert spike.differences(reference, dict(reference)) == []
    found = spike.differences(reference, {"a": 1, "b": 5, "d": 1})
    assert "only in the reference: c" in found
    assert "only in the other: d" in found
    assert "b: occurrences 2 against 5" in found
    assert len(found) == 3


class _Client:
    """Answers the shapes the loader sends; `refuse` names a fragment it fails on."""

    def __init__(self, refuse: str | None = None) -> None:
        self.refuse = refuse
        self.queries: list[str] = []

    async def gremlin(
        self,
        query: str,
        *,
        params: dict[str, Any] | None = None,
        session_id: Any = None,
    ) -> list[Any]:
        self.queries.append(query)
        if self.refuse and self.refuse in query:
            raise RuntimeError("cannot parse")
        if "project(" in query and "label()" in query:
            return []
        if "limit(1).count()" in query:
            return [{"result": 0}]
        if "project(" in query:  # stored pairs, degrees: rows of projections, none here
            return []
        if ".sum()" in query:  # the corpus total
            return [{"result": 0}]
        raise AssertionError(f"unexpected query: {query}")


def test_a_failing_shape_is_reported_as_a_line_not_a_crash() -> None:
    """Catches a shape that the store refuses being swallowed (reported ok) or aborting the
    whole run before the other shapes are tried."""
    nodes, edges = spike.synthetic_writes(20)
    lines = asyncio.run(spike._shape_checks(_Client(refuse="coalesce"), nodes, edges))  # type: ignore[arg-type]
    assert len(lines) == 6
    failed = [line for line in lines if "FAILED" in line]
    assert len(failed) == 1 and "degrees" in failed[0] and "cannot parse" in failed[0]
    assert all("ok" in line for line in lines if "FAILED" not in line)


def test_a_failed_candidate_says_so_instead_of_a_rate() -> None:
    """Catches a failed load printing a speed."""
    failed = spike.Outcome("bulk", note="RuntimeError: boom")
    assert "FAILED" in failed.line(100) and "edges/s" not in failed.line(100)
    done = spike.Outcome("bulk", seconds=2.0, edges={"a": 1}, strays=1)
    assert "50 edges/s" in done.line(100) and "1 id(s) stored twice" in done.line(100)
