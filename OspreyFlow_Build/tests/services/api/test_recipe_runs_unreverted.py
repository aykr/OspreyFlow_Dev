"""`RecipeRunStore.unreverted_loads` (ADR-127 Amendment 23, "The runs" and "The reset"): the one
question the Prison Intelligence seed asks of the run ledger, twice. "Does this case hold an
unreverted load of this recipe, at this version, from this source?" (a file is not run again) and
"which unreverted loads of these recipes does the case hold, newest first?" (what the rehearsal
reset reverts).

Pure: a connection stand-in records the statement and its arguments and answers with rows shaped as
the ledger's own `jsonb_array_elements` gives them. What the statement selects is proved live, in
`test_recipe_runs.py`. What would fail if the invariant broke:

- a query that returned a reverted record would make the seed skip a file whose load was reverted
  (`test_the_statement_leaves_out_a_reverted_record`);
- a query not scoped to the case would let another case's load stop this case's seed
  (`test_the_statement_is_asked_of_one_case_and_the_recipes_named`);
- a query that returned the record's id lists would pull a million-row file's ids into memory for a
  yes or no (`test_the_statement_drops_the_id_lists`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.api.recipe_runs import RecipeRunStore

from schemas.ingest import LoadRecord

T0 = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


class _Conn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.asked: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.asked.append((sql, args))
        return self.rows


class _Acquired:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _Conn:
        return self.conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def acquire(self) -> _Acquired:
        return _Acquired(self.conn)


def _record(load_id: str, recipe: str, source: str) -> LoadRecord:
    return LoadRecord(
        load_id=load_id, recipe_id=recipe, recipe_version=1, source=source, started_at=T0,
        created_by="w", investigation_id="case-1",
    )  # fmt: skip


def _store(rows: list[dict[str, Any]]) -> tuple[RecipeRunStore, _Conn]:
    conn = _Conn(rows)
    return RecipeRunStore(_Pool(conn), "dsn"), conn  # type: ignore[arg-type]


async def test_the_records_come_back_as_load_records_in_the_statements_order() -> None:
    rows = [
        {"rec": _record("02", "r-a", "x/a.csv").model_dump_json()},
        {"rec": _record("01", "r-a", "x/b.csv").model_dump_json()},
    ]
    store, _ = _store(rows)
    found = await store.unreverted_loads("case-1", ["r-a"])
    assert [(r.load_id, r.source) for r in found] == [("02", "x/a.csv"), ("01", "x/b.csv")]
    assert all(isinstance(r, LoadRecord) for r in found)


async def test_the_statement_is_asked_of_one_case_and_the_recipes_named() -> None:
    store, conn = _store([])
    await store.unreverted_loads("case-1", ["r-a", "r-b"])
    ((sql, args),) = conn.asked
    assert args[:2] == ("case-1", ["r-a", "r-b"])
    assert "investigation_id = $1" in sql and "recipe_id = ANY($2" in sql
    assert "ORDER BY" in sql and "DESC" in sql, "newest first"


async def test_the_statement_leaves_out_a_reverted_record() -> None:
    store, conn = _store([])
    await store.unreverted_loads("case-1", ["r-a"])
    ((sql, _),) = conn.asked
    assert "rec->>'reverted_at' IS NULL" in sql


async def test_the_statement_drops_the_id_lists() -> None:
    """Every list a `LoadRecord` holds that is a list of ids is dropped, derived from the model so a
    list added to it later is caught here."""
    store, conn = _store([])
    await store.unreverted_loads("case-1", ["r-a"])
    ((sql, args),) = conn.asked
    assert "rec - $3::text[]" in sql
    id_lists = {
        name
        for name, field in LoadRecord.model_fields.items()
        if str(field.annotation).startswith("list[")
    }
    assert id_lists, "the model holds lists"
    assert set(args[2]) == id_lists


async def test_no_recipe_asks_the_ledger_nothing() -> None:
    store, conn = _store([{"rec": "{}"}])
    assert await store.unreverted_loads("case-1", []) == []
    assert conn.asked == []
