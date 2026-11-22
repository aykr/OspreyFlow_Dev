"""SE9 (ADR-144 Amendment 7), without a store: how the adapter counts a view's deletions and
records them. What it returns for a hidden, live, superseded or absent id is the conformance suite's
to prove against ArcadeDB (`test_count_deleted_visible_*` in
`conformance/graph_port/test_suite.py`); here the text of the query, the reader reaching it, the
chunks, what is refused, and what each deleting write sends are checked, so a plant that lifts one
of them fails by name.

- the count's query carries the reader's own access step with the reverted test turned round, and
  never the live step (`test_the_count_query_...`, red with the access step left out:
  `test_the_count_check_fails_without_the_access_step`);
- a superseded node is not a deletion (`hasNot("superseded_by")` stays in the step);
- an id nobody holds costs the round trips a hidden one does (`test_an_absent_id_...`);
- every write that sets `reverted` sets `reverted_at` and `reverted_by` in the same statement
  (`test_revert_withdraw_and_layer_...`), and a restore clears them with the flag.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from adapters.graph_arcadedb import adapter as adapter_module
from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.builders import (
    render_count_deleted_visible_gremlin,
    render_count_visible_gremlin,
)
from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

from .test_get_by_id_reads import _adapter as _reader_adapter
from .test_get_by_id_reads import _Client
from .test_revert_elements_by_type import TypedStore
from .test_revert_elements_by_type import _adapter as _typed_adapter

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"])
AT = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


# --- the query ----------------------------------------------------------------------------------


def test_the_count_query_carries_the_readers_access_step_with_the_reverted_test_turned_round() -> (
    None
):
    access = AccessFilter(load_uk_le_scheme())
    secret = READER.model_copy(update={"clearance": "SECRET"})
    query = render_count_deleted_visible_gremlin(["#9:1", "#9:2"], access, READER)
    assert query.startswith("g.V(['#9:1','#9:2']).") and query.endswith(
        ".values('id').dedup().count()"
    )
    # Deleted, and not live: the one structural test turned round; a supersession is still out.
    assert 'has("reverted",true)' in query and 'has("reverted",false)' not in query
    assert 'hasNot("superseded_by")' in query
    # Everything else is the reader's own step: their clearance, handling codes and datasets.
    live_step = access.gremlin_has_step(READER)
    assert live_step.replace('has("reverted",false)', 'has("reverted",true)') in query
    assert render_count_deleted_visible_gremlin(["#9:1", "#9:2"], access, secret) != query
    assert render_count_deleted_visible_gremlin(["#9:1"], access, READER) != (
        render_count_visible_gremlin(["#9:1"], access, READER)
    )
    empty = render_count_deleted_visible_gremlin([], access, READER)
    assert empty.startswith("g.V().limit(0).") and empty.endswith(".values('id').dedup().count()")


def test_the_count_check_fails_without_the_access_step() -> None:
    """Rule 15, at the shape the adapter calls the builder in: a filter whose step is empty renders
    a count of every vertex at the ids, and the reader's step is not in it."""

    class Open(AccessFilter):
        def gremlin_has_step(self, principal: Principal, **_: Any) -> str:
            return "identity()"

        def gremlin_structural_step(self, **_: Any) -> str:
            return "identity()"

    real = AccessFilter(load_uk_le_scheme())
    opened = Open(load_uk_le_scheme())
    planted = render_count_deleted_visible_gremlin(["#9:1"], opened, READER)
    assert planted != render_count_deleted_visible_gremlin(["#9:1"], real, READER)
    assert 'has("handling_classification"' not in planted
    assert 'has("handling_classification"' in render_count_deleted_visible_gremlin(
        ["#9:1"], real, READER
    )


def test_the_deleted_step_leaves_the_live_step_as_it_was() -> None:
    """Every other read still excludes a reverted element: `gremlin_has_step` and the structural
    step, asked as before, say `has("reverted",false)` and nothing about a deletion."""
    access = AccessFilter(load_uk_le_scheme())
    assert 'has("reverted",false)' in access.gremlin_has_step(READER)
    assert 'has("reverted",true)' not in access.gremlin_has_step(READER)
    assert access.gremlin_structural_step() == 'has("reverted",false).hasNot("superseded_by")'


# --- what the adapter does with it --------------------------------------------------------------


class _CountingClient(_Client):
    def __init__(self, counts: list[int], **kw: Any) -> None:
        super().__init__(**kw)
        self.counts = list(counts)

    async def gremlin(self, query: str, **_: Any) -> list[dict[str, Any]]:
        self.gremlin_sent.append(query)
        return [{"result": self.counts.pop(0)}]


async def test_the_adapter_sums_the_counts_of_each_chunk_and_sends_the_deleted_query() -> None:
    client = _CountingClient([1000, 1000, 400])
    adapter, _ = _reader_adapter(client)
    ids = [f"n{i:05d}" for i in range(2501)]
    assert await adapter.count_deleted_visible([*ids, *ids[:50]], READER) == 2400
    assert len(client.gremlin_sent) == 3
    assert all('has("reverted",true)' in q for q in client.gremlin_sent)
    assert all(q.endswith(".values('id').dedup().count()") for q in client.gremlin_sent)


async def test_count_deleted_visible_of_no_ids_is_zero_and_sends_nothing() -> None:
    client = _CountingClient([])
    adapter, _ = _reader_adapter(client)
    assert await adapter.count_deleted_visible([], READER) == 0
    assert client.sql_sent == [] and client.gremlin_sent == [] and client.schema_sent == 0


async def test_count_deleted_visible_refuses_a_bare_string_for_the_ids() -> None:
    client = _CountingClient([])
    adapter, _ = _reader_adapter(client)
    with pytest.raises(TypeError):
        await adapter.count_deleted_visible("n00001", READER)
    assert client.sql_sent == [] and client.gremlin_sent == []


async def test_an_absent_id_is_counted_by_the_same_round_trips_as_a_hidden_one() -> None:
    """A guessed id the store does not hold sends the Gremlin count anyway (the `limit(0)` form), so
    the requests made tell nothing of what exists or what was deleted."""
    absent = _CountingClient([0], known=lambda _id: False)
    hidden = _CountingClient([0], known=lambda _id: True)
    for client in (absent, hidden):
        adapter, _ = _reader_adapter(client)
        assert await adapter.count_deleted_visible(["n00007"], READER) == 0
    assert len(absent.gremlin_sent) == len(hidden.gremlin_sent) == 1
    assert len(absent.sql_sent) == len(hidden.sql_sent)
    assert "limit(0)" in absent.gremlin_sent[0] and "limit(0)" not in hidden.gremlin_sent[0]


# --- what the deleting writes record -------------------------------------------------------------


async def test_a_revert_sets_when_and_by_whom_in_the_statement_that_sets_the_flag() -> None:
    store = TypedStore()
    store.vertex("Person", "p1")
    store.edge("ASSOCIATE_OF", "e1", "p1", "p1")
    graph = _typed_adapter(store)
    await graph.revert_elements(["p1"], ["e1"], "tx", by="analyst-1", at=AT)
    for row in (store.vertices["Person"]["p1"], store.edges["ASSOCIATE_OF"]["e1"]):
        assert row["reverted"] is True
        assert (row["reverted_at"], row["reverted_by"]) == (AT.isoformat(), "analyst-1")
    # The flag and the record are one statement: no UPDATE sets one without the other.
    updates = [c for c in store.sql_sent if c.startswith("UPDATE ")]
    assert updates and all("reverted_at = :at, reverted_by = :by" in c for c in updates)


async def test_a_revert_that_names_no_one_still_records_the_time() -> None:
    store = TypedStore()
    store.vertex("Person", "p1")
    graph = _typed_adapter(store)
    before = datetime.now(UTC)
    await graph.revert_elements(["p1"], [], "tx")
    row = store.vertices["Person"]["p1"]
    assert row["reverted_by"] is None
    assert before <= datetime.fromisoformat(row["reverted_at"]) <= datetime.now(UTC)


class _WithdrawStore(TypedStore):
    """`TypedStore`, answering the withdraw, layer and restore statements too and keeping the
    parameters each was sent."""

    def __init__(self) -> None:
        super().__init__()
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        if command.startswith("UPDATE ") and "withdrawn_by_load" in command:
            if "reverted = true, withdrawn_by_load = null" not in command:
                self.statements.append((command, dict(params or {})))
                return []
        if command.startswith("SELECT id, datasets FROM"):
            self.statements.append((command, dict(params or {})))
            return [{"id": "p1", "datasets": ["layer-1"]}]
        if command.startswith("SELECT id, source, target FROM"):
            return []  # no withdrawn link: the restore's link half has nothing to bring back
        if command.startswith("SELECT id FROM") and "withdrawn_by_load = :load" in command:
            self.statements.append((command, dict(params or {})))
            return [{"id": "p1"}]
        return await super().sql(command, params=params, session_id=session_id)


async def test_withdraw_and_layer_withdrawal_set_when_and_by_whom_with_the_flag() -> None:
    store = _WithdrawStore()
    store.vertex("Person", "p1")
    graph = _typed_adapter(store)
    await graph.withdraw_elements(["p1"], [], "refresh-2", "tx", by="analyst-2", at=AT)
    await graph.withdraw_layer("layer-1", "layer-delete:case-a", "tx", by="analyst-3", at=AT)
    sets = [(c, p) for c, p in store.statements if c.startswith("UPDATE ")]
    assert len(sets) >= 2
    for command, params in sets:
        assert re.search(
            r"SET reverted = true, reverted_at = :at, reverted_by = :by, withdrawn_by_load = :\w+ ",
            command,
        ), command
        assert params["at"] == AT.isoformat() and params["by"] in ("analyst-2", "analyst-3")


async def test_a_restore_clears_when_and_by_whom_with_the_flag() -> None:
    store = _WithdrawStore()
    store.vertex("Person", "p1")
    graph = _typed_adapter(store)
    await graph.restore_withdrawn("refresh-2", "tx")
    restores = [c for c, _ in store.statements if c.startswith("UPDATE ")]
    assert restores, "the restore sent no update"
    assert all(
        "SET reverted = false, reverted_at = null, reverted_by = null, withdrawn_by_load = null"
        in c
        for c in restores
    ), restores


def test_the_adapter_module_names_the_new_read() -> None:
    assert hasattr(adapter_module.GraphArcadeDBAdapter, "count_deleted_visible")
