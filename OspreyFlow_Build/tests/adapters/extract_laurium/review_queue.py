"""Laurium's findings put through the review queue's real write (rule 5; `06_DECISIONS.md` ADR-135
Amendment 6 decision 6), for `test_findings_inferred.py` (the Conduit's environment, over the fake
service) and `tests/conformance/model_port/test_laurium_findings_pending.py` (Laurium's own
environment, over the real service in-process).

The path is the real one end to end on the Conduit's side: `services/api/review.run_extraction`, given
the Laurium adapter as its `ModelPort`, hands its candidates to the real `ExtractionCandidateStore`,
whose own `store` builds each record and sends its own `INSERT`. Only asyncpg's pool under the store is
stood in for (`CandidateRows`), at the driver: it keeps each row as the store's statement sends it, by
column, so what is checked is the `status` the real store writes. It refuses what Postgres refuses at
that boundary (rule 15's second worked example): values that do not match the statement's columns or
placeholders, a NULL in a column the store's own `CREATE TABLE` declares `NOT NULL`, and a second row
with a table's primary key (a `BIGSERIAL` key it fills itself, as Postgres does); a value of a type
asyncpg's codec does not take for its column (`DataError`), and a column the table does not have;
`ON CONFLICT DO NOTHING` keeps the row there. A transaction keeps all its statements or, on an
exception, none, and after a failed statement it refuses the rest, as Postgres aborts it. What it
does not prove: that Postgres itself accepts the row, which is `tests/services/api/test_review_store.py`'s,
live.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from adapters.extract_laurium.adapter import ExtractLauriumAdapter
from ontology.loader import load_default_ontology
from schemas.domain import Handling, Principal
from services.api import review
from services.api.review import ExtractionCandidateRecord, ExtractionCandidateStore, run_extraction
from services.extract.profile import ExtractionProfile

MODEL = "qwen2.5:0.5b-instruct"
DOCUMENT = "doc-laurium-1"
TEXT = "Statement taken on 3 March. Ada Lovelace met the witness outside the bank."
#: What the model answers: one finding the document states, one it does not (never queued).
ANSWER = json.dumps(
    {
        "Person": [
            {"family_name": "Lovelace", "given_names": "Ada", "confidence": 0.9},
            {"family_name": "Babbage", "given_names": "Charles", "confidence": 0.9},
        ]
    }
)
PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")

#: asyncpg's own refusals, as the stand-in raises them (named here so a test reading them imports no
#: driver: it opens no connection).
REFUSALS = {
    "not_null": asyncpg.exceptions.NotNullViolationError,
    "unique": asyncpg.exceptions.UniqueViolationError,
    "arguments": asyncpg.exceptions.InterfaceError,
    "type": asyncpg.exceptions.DataError,
    "column": asyncpg.exceptions.UndefinedColumnError,
    "aborted": asyncpg.exceptions.InFailedSQLTransactionError,
    "connection": asyncpg.exceptions.ConnectionDoesNotExistError,
}

_INSERT = re.compile(r"INSERT INTO (\w+) \(([^)]*)\) VALUES \(([^)]*)\)", re.S)
_NOT_NULL = re.compile(r"^\s+(\w+) [A-Z ]*?(NOT NULL|PRIMARY KEY)", re.M)
_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", re.S)


_PRIMARY_KEY = re.compile(r"^\s+(\w+) ([A-Z]+)[A-Z ]*?PRIMARY KEY", re.M)
_COLUMN = re.compile(r"^\s+(\w+) (TEXT|DOUBLE PRECISION|TIMESTAMPTZ|BIGSERIAL|BIGINT|INTEGER)\b", re.M)
_ADDED = re.compile(r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+) ([A-Z ]+?);")

#: The Python values asyncpg's codec takes for each column type the store declares; any other is a
#: `DataError` ("invalid input for query argument"), before the statement reaches Postgres.
_ACCEPTS: dict[str, tuple[type, ...]] = {
    "TEXT": (str,),
    "DOUBLE PRECISION": (float, int),
    "TIMESTAMPTZ": (datetime,),
    "BIGSERIAL": (int,),
    "BIGINT": (int,),
    "INTEGER": (int,),
}


@dataclass(frozen=True)
class _Table:
    required: set[str]
    key: str
    serial: bool
    types: dict[str, str]


def _tables() -> dict[str, _Table]:
    """Each table the store's own `CREATE TABLE`s and `ALTER TABLE`s declare: its NOT NULL columns
    a statement must give, its primary key, whether Postgres fills that key itself (a `BIGSERIAL`,
    as the search index's text outbox, ADR-150 decision 3, has: one row per write, the same document
    twice), and each column's type."""
    out: dict[str, _Table] = {}
    for sql in (review._BOOTSTRAP_SQL, review._DOCUMENT_TEXT_BOOTSTRAP_SQL):
        for table, body in _TABLE.findall(sql):
            key, key_type = _PRIMARY_KEY.search(body).groups()  # type: ignore[union-attr]
            serial = key_type.endswith("SERIAL")
            required = {m.group(1) for m in _NOT_NULL.finditer(body)}
            if serial:
                required.discard(key)
            types = {m.group(1): m.group(2) for m in _COLUMN.finditer(body)}
            out[table] = _Table(required, key, serial, types)
        for table, column, kind in _ADDED.findall(sql):
            out[table].types[column] = kind.strip()
    return out


class CandidateRows:
    """asyncpg's pool under `ExtractionCandidateStore`, at the driver: each row kept by column."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self._tables = _tables()
        self._serial = 0
        self._in_transaction = False
        self._aborted = False
        #: Tables whose inserts fail as a lost connection would, to show a transaction kept whole.
        self.fail_on: set[str] = set()

    def acquire(self) -> CandidateRows:
        return self

    async def __aenter__(self) -> CandidateRows:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """asyncpg's `conn.transaction()`: every statement in it kept, or, on any exception, none
        (the text and its search outbox row are one transaction, ADR-150 decision 3)."""
        before = {table: list(held) for table, held in self.rows.items()}
        self._in_transaction, self._aborted = True, False
        try:
            yield
            if self._aborted:
                # A statement failed and the caller went on: Postgres rolls back at commit.
                self.rows = before
                raise asyncpg.exceptions.InFailedSQLTransactionError(
                    "current transaction is aborted, commands ignored until end of transaction block"
                )
        except BaseException:
            self.rows = before
            raise
        finally:
            self._in_transaction = self._aborted = False

    async def executemany(self, sql: str, args: list[tuple[Any, ...]]) -> None:
        for values in args:
            self._insert(sql, tuple(values))

    async def execute(self, sql: str, *values: Any) -> str:
        self._insert(sql, values)
        return "INSERT 0 1"

    def _insert(self, sql: str, values: tuple[Any, ...]) -> None:
        if self._aborted:
            raise asyncpg.exceptions.InFailedSQLTransactionError(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        try:
            self._insert_one(sql, values)
        except Exception:
            self._aborted = self._in_transaction
            raise

    def _insert_one(self, sql: str, values: tuple[Any, ...]) -> None:
        found = _INSERT.search(sql)
        if found is None:
            raise AssertionError(f"not a statement this stand-in knows: {sql[:60]!r}")
        table, columns, marks = found.groups()
        names = [c.strip() for c in columns.split(",")]
        if len(marks.split(",")) != len(values) or len(names) != len(values):
            raise asyncpg.exceptions.InterfaceError(
                f"the server expects {len(marks.split(','))} arguments for this query, "
                f"{len(values)} were passed"
            )
        row = dict(zip(names, values, strict=True))
        if table not in self._tables:
            raise AssertionError(f"not a table the store creates: {table!r}")
        shape = self._tables[table]
        required, key, serial = shape.required, shape.key, shape.serial
        for n, (column, value) in enumerate(row.items(), start=1):
            if column not in shape.types:
                raise asyncpg.exceptions.UndefinedColumnError(
                    f'column "{column}" of relation "{table}" does not exist'
                )
            accepts = _ACCEPTS[shape.types[column]]
            if value is not None and (isinstance(value, bool) or not isinstance(value, accepts)):
                raise asyncpg.exceptions.DataError(
                    f"invalid input for query argument ${n}: {value!r} "
                    f"({shape.types[column]} takes {', '.join(t.__name__ for t in accepts)})"
                )
        for column in required:
            if row.get(column) is None:
                raise asyncpg.exceptions.NotNullViolationError(
                    f'null value in column "{column}" of relation "{table}"'
                )
        if table in self.fail_on:
            raise asyncpg.exceptions.ConnectionDoesNotExistError(
                "connection was closed in the middle of operation"
            )
        held = self.rows.setdefault(table, [])
        if serial and key not in row:
            self._serial += 1
            row[key] = self._serial
        same = [r for r in held if r[key] == row[key]]
        if same and "ON CONFLICT" not in sql:
            raise asyncpg.exceptions.UniqueViolationError(f"duplicate key in {table}")
        if same and "DO NOTHING" in sql:
            return
        for old in same:
            held.remove(old)
        held.append(row)


async def extract_into_queue(
    adapter: ExtractLauriumAdapter, *, laurium_may_read: bool = False
) -> tuple[list[ExtractionCandidateRecord], CandidateRows]:
    """The one path an extraction takes to the review queue, with the real store over `CandidateRows`."""
    rows = CandidateRows()
    store = ExtractionCandidateStore(rows)  # type: ignore[arg-type]
    stored = await run_extraction(
        adapter,
        load_default_ontology(),
        store,
        document_id=DOCUMENT,
        text=TEXT,
        profile=ExtractionProfile(["Person"]),
        handling=HANDLING,
        principal=PRINCIPAL,
        extraction_model=MODEL,
        laurium_may_read=laurium_may_read,
    )
    return stored, rows


def assert_queued_pending(stored: list[ExtractionCandidateRecord], rows: CandidateRows) -> None:
    """Rule 5: the one finding the document states is written `pending`, traced to its document and
    to the span that says it, by and for the analyst's unit; nothing is reviewed or put in the
    graph; the finding the document does not state is not written at all."""
    [row] = rows.rows["extraction_candidates"]
    assert row["status"] == "pending"
    assert [r.status.value for r in stored] == ["pending"]
    assert [r.reviewed_by for r in stored] == [None] and [r.node_id for r in stored] == [None]
    assert row["document_id"] == DOCUMENT
    assert row["entity_type"] == "Person"
    start, end = (int(n) for n in row["locator"].removeprefix("char span ").split("-"))
    assert TEXT[start:end] == "Lovelace"
    assert row["model"] == MODEL
    assert (row["owning_unit"], row["created_by"]) == (PRINCIPAL.org_unit, PRINCIPAL.id)
    assert rows.rows["document_texts"] == [
        {**rows.rows["document_texts"][0], "document_id": DOCUMENT, "text": TEXT}
    ]
