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
with a candidate's primary key. What it does not prove: that Postgres itself accepts the row, which is
`tests/services/api/test_review_store.py`'s, live.
"""

from __future__ import annotations

import json
import re
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
}

_INSERT = re.compile(r"INSERT INTO (\w+) \(([^)]*)\) VALUES \(([^)]*)\)", re.S)
_NOT_NULL = re.compile(r"^\s+(\w+) [A-Z ]*?(NOT NULL|PRIMARY KEY)", re.M)
_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", re.S)


def _not_null() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for sql in (review._BOOTSTRAP_SQL, review._DOCUMENT_TEXT_BOOTSTRAP_SQL):
        for table, body in _TABLE.findall(sql):
            out[table] = {m.group(1) for m in _NOT_NULL.finditer(body)}
    return out


class CandidateRows:
    """asyncpg's pool under `ExtractionCandidateStore`, at the driver: each row kept by column."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self._not_null = _not_null()

    def acquire(self) -> CandidateRows:
        return self

    async def __aenter__(self) -> CandidateRows:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def executemany(self, sql: str, args: list[tuple[Any, ...]]) -> None:
        for values in args:
            self._insert(sql, tuple(values))

    async def execute(self, sql: str, *values: Any) -> str:
        self._insert(sql, values)
        return "INSERT 0 1"

    def _insert(self, sql: str, values: tuple[Any, ...]) -> None:
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
        for column in self._not_null.get(table, set()):
            if row.get(column) is None:
                raise asyncpg.exceptions.NotNullViolationError(
                    f'null value in column "{column}" of relation "{table}"'
                )
        held = self.rows.setdefault(table, [])
        key = "id" if table == "extraction_candidates" else "document_id"
        same = [r for r in held if r[key] == row[key]]
        if same and "ON CONFLICT" not in sql:
            raise asyncpg.exceptions.UniqueViolationError(f"duplicate key in {table}")
        for old in same:
            held.remove(old)
        held.append(row)


async def extract_into_queue(
    adapter: ExtractLauriumAdapter,
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
