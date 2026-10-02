"""The lookup-cost probe finds one account four ways, refuses to time a lookup that found the wrong
thing, stays on its scratch database, and says what it found (ADR-058 Amendment 5).

No store is needed. The store here answers only the shapes the probe sends and refuses any other
(rule 15), and returns what the real one returns: an element map for Gremlin, a record for SQL.
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

import pytest
from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal
from scripts import probe_lookup_cost as probe
from scripts import spike_bulk_transport as spike

LABEL = "mx_Endpoint"


class _Store:
    def __init__(self, ids: list[str], refuse: set[str] = frozenset()) -> None:  # type: ignore[assignment]
        self.ids, self.refuse, self.seen = set(ids), refuse, []

    async def command(
        self, language: str, command: str, *, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.seen.append((language, command))
        if language == "sql":
            if (
                not command.startswith(f"SELECT FROM {LABEL} WHERE id = :id")
                or not params
            ):
                raise RuntimeError(f"unexpected sql: {command}")
            wanted = params["id"]
            return [{"id": wanted}] if wanted in self.ids else []
        if language == "gremlin":
            if not command.startswith("g.V()") or not command.endswith(".elementMap()"):
                raise RuntimeError(f"unexpected gremlin: {command}")
            for shape in self.refuse:
                if shape == "label_first" and command.startswith("g.V().hasLabel("):
                    raise RuntimeError("store refuses hasLabel here")
            found = [i for i in self.ids if groovy_string_literal(i) in command]
            return [{"id": found[0], "~label": LABEL}] if found else []
        raise RuntimeError(f"unexpected language: {language}")


def test_the_first_shape_is_what_the_adapter_sends_today() -> None:
    """Catches a probe that times a lookup the adapter never makes: shape one must match, and the
    adapter's own source must still contain that shape, or the result says nothing about it."""
    shapes = probe.lookup_shapes(LABEL, "A1")
    assert shapes["gremlin_has_id"].command == "g.V().has(\"id\",'A1').elementMap()"
    adapter = (
        pathlib.Path(spike.__file__).parent.parent / "packages/adapters/graph_arcadedb"
    )
    assert (
        'g.V().has("id",{node_lit}).elementMap()'
        in (adapter / "adapter.py").read_text()
    )
    assert set(shapes) == set(probe.SHAPES)


def test_a_lookup_that_found_nothing_or_the_wrong_account_is_not_a_timing() -> None:
    """Catches a fast lookup that is fast because it found nothing."""
    store = _Store(["A1"])
    lookup = probe.lookup_shapes(LABEL, "A2")["sql_where_id"]
    with pytest.raises(probe.WrongAnswer):
        asyncio.run(probe.time_lookup(store, lookup, "A2"))
    other = probe.lookup_shapes(LABEL, "A1")["sql_where_id"]
    with pytest.raises(probe.WrongAnswer):
        asyncio.run(probe.time_lookup(store, other, "A9"))
    assert asyncio.run(probe.time_lookup(store, other, "A1")) >= 0


def test_the_sample_is_spread_across_the_whole_set() -> None:
    """Catches timing only the first accounts written, which would hide a cost that grows with
    how many accounts come before."""
    ids = [f"A{i}" for i in range(1000)]
    sample = probe.spread(ids, 30)
    assert len(sample) == 30 and sample[0] == "A0" and int(sample[-1][1:]) > 900
    assert probe.spread(ids[:5], 30) == ids[:5]


def test_a_shape_the_store_refuses_is_reported_and_the_others_still_run() -> None:
    store = _Store([f"A{i}" for i in range(50)], refuse={"label_first"})
    result = asyncio.run(probe.measure_size(store, LABEL, [f"A{i}" for i in range(50)]))
    assert "gremlin_label_has_id" in result.failed
    assert set(result.times) == set(probe.SHAPES) - {"gremlin_label_has_id"}
    assert all(len(v) == probe.LOOKUPS for v in result.times.values())


def test_the_table_says_how_each_shape_grew() -> None:
    small = probe.SizeResult(1000, times={s: [1.0, 1.0] for s in probe.SHAPES})
    large = probe.SizeResult(
        15000,
        times={
            "gremlin_has_id": [20.0, 20.0],
            "gremlin_label_has_id": [1.0, 1.0],
            "gremlin_has_label_id": [1.0, 1.0],
            "sql_where_id": [0.5, 0.5],
        },
    )
    text = "\n".join(probe.table([small, large]))
    assert "gremlin_has_id: 20.0 times as slow at 15,000 accounts as at 1,000" in text
    assert "sql_where_id: 0.5 times as slow" in text
    large.failed["sql_where_id"] = "RuntimeError: x"
    large.times.pop("sql_where_id")
    assert "sql_where_id at 15,000: FAILED" in "\n".join(probe.table([small, large]))


class _Indexes:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def sql(self, command: str) -> list[dict[str, Any]]:
        if command != "SELECT FROM schema:indexes":
            raise RuntimeError(f"unexpected sql: {command}")
        return self.rows


def test_indexes_on_the_account_type_are_listed_and_their_absence_is_said() -> None:
    held = [
        {
            "name": "mx_Endpoint[id]",
            "typeName": LABEL,
            "properties": ["id"],
            "unique": True,
        },
        {"name": "other", "typeName": "mx_Other", "properties": ["id"], "unique": True},
    ]
    lines = asyncio.run(probe.index_lines(_Indexes(held), LABEL))
    assert len(lines) == 1 and "unique True" in lines[0] and "other" not in lines[0]
    none = asyncio.run(probe.index_lines(_Indexes(held[1:]), LABEL))
    assert "no index on mx_Endpoint" in none[0]


def test_the_run_refuses_a_name_off_the_scratch_prefix_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a probe that creates or drops a database that is not its own."""
    monkeypatch.setattr(probe, "SCRATCH_PREFIX", "vault_")
    with pytest.raises(spike.NotScratchError):
        asyncio.run(probe.run([100], say=lambda _: None))
    assert probe.SCRATCH_PREFIX == "vault_"
    monkeypatch.undo()
    assert spike.refuse_unless_scratch(f"{probe.SCRATCH_PREFIX}lookup_120000")
