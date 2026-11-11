"""The Athena connector, against a recorded Athena behind the real botocore client (L1.9 part 1;
`athena_fixture.py`; rule 15's second worked example: the fixture refuses what Athena refuses).

What a mistake would do, and the case that catches it:
- the source's file not what the table holds (the header read as a row, a null as text, a value
  with a comma or a quote split) — `test_a_table_lands_as_the_golden_file`;
- pages after the first dropped, or a page asked for over Athena's 1,000 —
  `test_every_page_is_read_at_1000_rows_a_page`;
- Athena's refusals read as no rows, or not refused in words — a query that does not parse, a
  table that does not exist, a principal the workgroup does not grant, a key Athena does not know,
  no results location — `test_athena_s_refusals_are_refused_in_words`;
- a named query that writes (DROP, CTAS, INSERT, UNLOAD, a second statement) run through a
  read-only connector — `test_a_named_query_that_is_not_one_select_is_never_sent`;
- a named query of another workgroup or database, or a table of a database the connection does not
  name, run — `test_a_named_query_or_table_outside_the_connection_is_never_sent`;
- rows, bytes or pages past the cap read and then cut (rule 2) —
  `test_rows_past_the_cap_are_refused_whole_and_paging_stops`, `test_bytes_past_the_cap_…`,
  `test_pages_past_the_cap_…`;
- a query that never finishes left running, or waited on for ever —
  `test_a_query_that_never_finishes_is_stopped_and_refused`;
- a fixture more permissive than Athena (rule 15) — `test_the_fixture_refuses_what_athena_refuses`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from services.ingest.connectors import athena_connector, reads
from services.ingest.connectors.athena_connector import read_athena
from services.ingest.connectors.reads import ConnectorRefused, write_snapshot

from schemas.sources import AthenaConnectionSettings, AthenaRead

from .athena_fixture import REFUSED_KEY, RecordedAthena

GOLDEN = Path(__file__).parent / "golden"
COLUMNS = ["booking_id", "prisoner_ref", "visitor", "booked_for", "notes"]
BOOKINGS: list[list[str | None]] = [
    ["B-0001", "SYN-P-001", "Alex Fictional", "2026-10-01 14:00:00.000", None],
    ["B-0002", "SYN-P-002", "Sam Example, Jr", "2026-10-02 10:30:00.000",
     'first visit; "escorted"'],
    ["B-0003", "SYN-P-001", None, "2026-10-03 09:00:00.000", "visitor withdrawn"],
]  # fmt: skip
MANY = [[f"B-{n:05d}", f"SYN-P-{n % 97:03d}", f"Visitor {n}", "2026-10-01 00:00:00.000", None]
        for n in range(2503)]  # fmt: skip
SELECT_NQ = "0f3c6a7e-1b2d-4c5e-8f90-a1b2c3d4e5f6"


def _athena(**kwargs: Any) -> RecordedAthena:
    return RecordedAthena(
        tables={"visits": {"visit_bookings": (COLUMNS, BOOKINGS), "many": (COLUMNS, MANY),
                           # `SELECT a.id, b.id` gives two columns named `id`, as Athena does.
                           "twice": (["booking_id", "booking_id"], [["B-0001", "B-0002"]]),
                           "surplus": (["booking_id"], [["B-0001", "a value with no column"]])},
                "finance": {"ledger": (["entry"], [["L-1"]])}},
        named_queries={SELECT_NQ: {
            "Name": "recent bookings", "Database": "visits", "WorkGroup": "primary",
            "QueryString": "SELECT booking_id, prisoner_ref FROM visits.visit_bookings "
                           "WHERE booked_for > '2026-10-01'",
        }},
        **kwargs,
    )  # fmt: skip


def _settings(**kwargs: Any) -> AthenaConnectionSettings:
    return AthenaConnectionSettings(region="eu-west-2", databases=["visits"], **kwargs)


def _read(athena: RecordedAthena, read: AthenaRead, key: str | None = None, **kwargs: Any) -> Any:
    client = athena.client() if key is None else athena.client(key)
    return read_athena(client, kwargs.pop("settings", _settings()), read, sleep=lambda _s: None,
                       **kwargs)  # fmt: skip


def test_a_table_lands_as_the_golden_file(tmp_path: Path) -> None:
    athena = _athena()
    rows = _read(athena, AthenaRead(table="visits.visit_bookings"))
    landed = write_snapshot(rows, tmp_path, "bookings").read_text(encoding="utf-8")
    assert landed == (GOLDEN / "athena_visit_bookings.csv").read_text(encoding="utf-8")
    # The statement is made from the checked names alone, quoted: never an expression (rule 8).
    assert athena.sent == ['SELECT * FROM "visits"."visit_bookings"']


def test_every_page_is_read_at_1000_rows_a_page() -> None:
    athena = _athena()
    rows = _read(athena, AthenaRead(table="visits.many"))
    assert [r["booking_id"] for r in rows.rows] == [r[0] for r in MANY]
    assert athena.page_sizes == [1000, 1000, 1000]


def test_a_named_query_lands_as_the_golden_file(tmp_path: Path) -> None:
    athena = _athena()
    athena.named_queries[SELECT_NQ]["QueryString"] = "SELECT * FROM visits.visit_bookings"
    rows = _read(athena, AthenaRead(named_query=SELECT_NQ))
    assert athena.sent == ["SELECT * FROM visits.visit_bookings"]
    landed = write_snapshot(rows, tmp_path, "bookings").read_text(encoding="utf-8")
    assert landed == (GOLDEN / "athena_visit_bookings.csv").read_text(encoding="utf-8")


# The lane review of L1.9, finding 2: the saved query's own Database was checked, but its text could
# name another database or catalog, and read any table the role could reach.
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM finance.ledger",
        'SELECT * FROM "finance"."ledger"',
        'SELECT * FROM "othercatalog"."visits"."many"',
        "SELECT * FROM visits.many m JOIN finance.ledger l ON true",
        "SELECT * FROM visits.many m LEFT OUTER JOIN finance.ledger l ON true",
        "SELECT * FROM visits.many, finance.ledger",
        "SELECT * FROM visits.many AS m, finance.ledger AS l",
        "SELECT * FROM (SELECT * FROM finance.ledger) t",
        "WITH x AS (SELECT * FROM finance.ledger) SELECT * FROM x",
        "SELECT * FROM visits.many WHERE booking_id IN (SELECT entry FROM finance.ledger)",
        "SELECT coalesce((SELECT max(entry) FROM finance.ledger), 'x') FROM visits.many",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM TABLE(system.query(query => 'SELECT 1'))",
        "SELECT * FROM visits.many UNION ALL SELECT * FROM finance.ledger",
        "SELECT * FROM -- a comment\n finance.ledger",
        # The orchestrator's review of L1.9, round 1, item 1: after a subquery, a JOIN, an UNNEST or
        # a TABLESAMPLE the checker went back to looking for FROM or JOIN, so a later `, db.table`
        # in the same FROM list was never checked. Each passed at b29dba44.
        "SELECT * FROM (SELECT 1) t, finance.ledger",
        "SELECT * FROM visits.many CROSS JOIN visits.visit_bookings, finance.ledger",
        "SELECT * FROM visits.many m JOIN visits.visit_bookings b ON true, finance.ledger",
        "SELECT * FROM visits.many CROSS JOIN UNNEST(ARRAY[1]) AS t(n), finance.ledger",
        "SELECT * FROM visits.many TABLESAMPLE BERNOULLI (50), finance.ledger",
        # Their siblings, hunted in the same round.
        "SELECT * FROM visits.many m, LATERAL (SELECT * FROM finance.ledger) l",
        "SELECT * FROM visits.many, LATERAL (SELECT 1) l, finance.ledger",
        "SELECT * FROM visits.many m JOIN LATERAL (SELECT * FROM finance.ledger) l ON true",
        "SELECT * FROM (visits.many m JOIN visits.visit_bookings b ON true), finance.ledger",
        "SELECT * FROM (visits.many m JOIN finance.ledger l ON true)",
        "WITH x AS (SELECT 1), y AS (SELECT * FROM finance.ledger) SELECT * FROM x, y",
        "WITH x AS (SELECT 1) SELECT * FROM x, finance.ledger",
        "SELECT * FROM (WITH z AS (SELECT * FROM finance.ledger) SELECT * FROM z) t",
        "SELECT * FROM (VALUES (1), (2)) AS v(n), finance.ledger",
        "SELECT * FROM visits.many UNION SELECT * FROM visits.many, finance.ledger",
        "SELECT * FROM visits.many INTERSECT SELECT * FROM (SELECT 1) t, finance.ledger",
        "SELECT * FROM visits.many m JOIN visits.visit_bookings b USING (booking_id), finance.ledger",
        "SELECT * FROM visits.many m JOIN visits.visit_bookings b ON (m.notes = b.notes), "
        "finance.ledger",
        "SELECT * FROM visits.many m JOIN visits.visit_bookings b "
        "ON m.booking_id IN (SELECT entry FROM finance.ledger)",
        "SELECT * FROM visits.many m CROSS JOIN UNNEST(ARRAY[1]) WITH ORDINALITY AS t(n, o), "
        "finance.ledger",
        "SELECT * FROM visits.many m, UNNEST((SELECT array_agg(entry) FROM finance.ledger)) AS t(e)",
        "SELECT * FROM visits.many ORDER BY (SELECT max(entry) FROM finance.ledger)",
        "SELECT * FROM visits.many FOR TIMESTAMP AS OF current_timestamp, finance.ledger",
        # A quoted name is a name, never a keyword: `"where"` is an alias, not a WHERE clause.
        'SELECT * FROM visits.many "where", finance.ledger',
        # A comment's marker inside a string value is no comment.
        "SELECT '--', booking_id FROM finance.ledger",
        "SELECT '/*' AS a FROM finance.ledger WHERE '*/' = '*/'",
    ],
)
def test_a_named_query_naming_a_table_outside_the_connection_is_never_sent(statement: str) -> None:
    athena = _athena()
    athena.named_queries[SELECT_NQ]["QueryString"] = statement
    with pytest.raises(ConnectorRefused, match="reads a table outside the databases"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))
    assert athena.sent == []


# Fail closed (the review, round 1, item 1): a shape the checker does not follow is refused, never
# passed over. Each passed at b29dba44, reading a database through the part the checker skipped.
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM visits.many m foo, finance.ledger",
        "SELECT * FROM visits.many MATCH_RECOGNIZE (MEASURES 1 AS x PATTERN (a) DEFINE a AS true), "
        "finance.ledger",
        "SELECT * FROM visits.many m JOIN visits.visit_bookings b, finance.ledger",
        "SELECT * FROM visits.many WHERE true, finance.ledger",
        "SELECT FROM WHERE visits.visit_bookings",
        "SELECT * FROM visits.many, (finance.ledger)",
        "SELECT * FROM visits.many, system.query(query => 'SELECT 1')",
    ],
)
def test_a_named_query_the_checker_cannot_follow_is_refused(statement: str) -> None:
    athena = _athena()
    athena.named_queries[SELECT_NQ]["QueryString"] = statement
    with pytest.raises(ConnectorRefused, match="this check cannot follow|reads a table outside"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))
    assert athena.sent == []


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM visits.visit_bookings",
        "SELECT * FROM visit_bookings",
        'SELECT * FROM "AwsDataCatalog"."visits"."many"',
        "SELECT extract(year FROM b.booked_for) AS y FROM visits.visit_bookings b",
        "SELECT 'FROM finance.ledger' AS words FROM visits.visit_bookings",
        "SELECT * FROM visits.many CROSS JOIN UNNEST(ARRAY[1, 2]) AS t(n)",
        "WITH x AS (SELECT * FROM visits.many) SELECT * FROM x JOIN visits.visit_bookings b ON true",
        # Failing closed must not refuse the plain shapes a client saves (the review, round 1).
        "SELECT * FROM visits.many m JOIN visits.visit_bookings b ON m.booking_id = b.booking_id, "
        "visits.many n",
        "SELECT * FROM visits.many TABLESAMPLE BERNOULLI (50)",
        "SELECT * FROM visits.many AS m TABLESAMPLE SYSTEM (10) JOIN visits.visit_bookings b "
        "USING (booking_id)",
        "SELECT * FROM (SELECT 1) t, visits.many",
        "SELECT * FROM visits.many m, LATERAL (SELECT * FROM visits.visit_bookings) l",
        "SELECT * FROM (VALUES (1), (2)) AS v(n)",
        "SELECT * FROM (visits.many m JOIN visits.visit_bookings b ON true)",
        "SELECT * FROM visits.many m CROSS JOIN UNNEST(ARRAY[1]) WITH ORDINALITY AS t(n, o)",
        "SELECT booking_id IS DISTINCT FROM notes FROM visits.many",
        "SELECT substring(notes FROM 1 FOR 3), trim(BOTH ' ' FROM visitor) FROM visits.many",
        "SELECT count(*) FILTER (WHERE notes IS NULL) FROM visits.many",
        "SELECT row_number() OVER (PARTITION BY prisoner_ref ORDER BY booked_for) FROM visits.many",
        "SELECT * FROM visits.many ORDER BY booking_id LIMIT 10",
        "SELECT * FROM visits.many ORDER BY booking_id FETCH FIRST 5 ROWS WITH TIES",
        "SELECT * FROM visits.many UNION ALL SELECT * FROM visits.visit_bookings",
        "SELECT * FROM visits.many WHERE booking_id IN (SELECT booking_id FROM visits.many) "
        "GROUP BY 1 HAVING count(*) > 1",
        "SELECT * FROM visits.many FOR TIMESTAMP AS OF TIMESTAMP '2026-10-01 00:00:00 UTC'",
        'SELECT * FROM visits.many "from"',
        "SELECT 1 FROM visits.many;",
        "SELECT 1",
    ],
)
def test_a_named_query_reading_only_the_connection_s_databases_is_allowed(statement: str) -> None:
    athena_connector.refuse_relations_outside(statement, _settings())


def test_athena_s_own_words_never_carry_an_arn() -> None:
    """A Lake Formation refusal fails the execution with a reason naming the role it refused."""
    athena = _athena()
    with pytest.raises(ConnectorRefused) as refused:
        _read(athena, AthenaRead(table="visits.lake_formation_locked"))
    words = str(refused.value)
    assert words.startswith("Athena could not run the query: Insufficient Lake Formation")
    assert "arn:" not in words and "synthetic-namespace-role" not in words
    assert "000000000000" not in words


@pytest.mark.parametrize(
    ("case", "words"),
    [
        ("syntax", "Athena could not run the query: line 1:51: mismatched input '<EOF>'"),
        ("missing_table", "Athena could not run the query: TABLE_NOT_FOUND"),
        ("unauthorised", "Athena refused the deployment's cloud role (access denied)"),
        ("unknown_key", "Athena did not recognise the deployment's cloud identity"),
        ("no_results_location", "Athena refused the request: No output location provided"),
        ("results_unwritable", "Athena could not run the query: Access denied when writing"),
    ],
)
def test_athena_s_refusals_are_refused_in_words(case: str, words: str) -> None:
    athena = _athena()
    read, key, settings = AthenaRead(table="visits.visit_bookings"), None, _settings()
    if case == "syntax":
        # One the checker follows (a dangling WHERE) but Athena does not parse: one the checker
        # cannot follow (`SELECT FROM WHERE …`) is refused before it is sent (round 1, item 1).
        athena.named_queries[SELECT_NQ]["QueryString"] = (
            "SELECT booking_id FROM visits.visit_bookings WHERE"
        )
        read = AthenaRead(named_query=SELECT_NQ)
    elif case == "missing_table":
        read = AthenaRead(table="visits.no_such_table")
    elif case == "unauthorised":
        key = REFUSED_KEY
    elif case == "unknown_key":
        key = "AKIDSYNTHETICUNKNOWN"
    elif case == "no_results_location":
        settings = _settings(workgroup="bare")
    elif case == "results_unwritable":
        settings = _settings(results_location="s3://forbidden-results/out/")
    with pytest.raises(ConnectorRefused, match=r"nothing was read") as refused:
        _read(athena, read, key, settings=settings)
    assert str(refused.value).startswith(words)
    assert "synthetic-other-role" not in str(refused.value)  # never the principal's ARN


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE visits.visit_bookings",
        "CREATE TABLE visits.copy AS SELECT * FROM visits.visit_bookings",
        "INSERT INTO visits.visit_bookings SELECT * FROM visits.many",
        "UNLOAD (SELECT * FROM visits.visit_bookings) TO 's3://elsewhere/' WITH (format = 'CSV')",
        "-- a comment first\nDROP TABLE visits.visit_bookings",
        "/* a comment */ DELETE FROM visits.visit_bookings",
        "SELECT 1 FROM visits.many; DROP TABLE visits.visit_bookings",
        "MSCK REPAIR TABLE visits.visit_bookings",
        "WITH x AS (SELECT 1) INSERT INTO visits.visit_bookings SELECT * FROM x",
        # A comment's marker inside a string value hid the second statement from the check (found
        # in the review's sibling hunt, round 1): the string is a string, wherever its markers are.
        "SELECT '--' AS a FROM visits.many; DROP TABLE visits.visit_bookings",
        "SELECT '/*' AS a FROM visits.many; DROP TABLE visits.visit_bookings; SELECT '*/'",
    ],
)
def test_a_named_query_that_is_not_one_select_is_never_sent(statement: str) -> None:
    athena = _athena()
    athena.named_queries[SELECT_NQ]["QueryString"] = statement
    with pytest.raises(ConnectorRefused, match="only a single SELECT"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))
    assert athena.sent == []


def test_a_named_query_or_table_outside_the_connection_is_never_sent() -> None:
    athena = _athena()
    athena.named_queries[SELECT_NQ]["WorkGroup"] = "other"
    with pytest.raises(ConnectorRefused, match="saved in another workgroup"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))
    athena.named_queries[SELECT_NQ].update(WorkGroup="primary", Database="finance")
    with pytest.raises(ConnectorRefused, match="a database this connection does not name"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))
    with pytest.raises(ConnectorRefused, match="a database this connection does not name"):
        _read(athena, AthenaRead(table="finance.ledger"))
    with pytest.raises(ConnectorRefused, match="no named query of that id"):
        _read(athena, AthenaRead(named_query="00000000-0000-4000-8000-000000000000"))
    assert athena.sent == []


def test_rows_past_the_cap_are_refused_whole_and_paging_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reads, "MAX_ROWS", 1500)
    athena = _athena()
    with pytest.raises(ConnectorRefused, match=r"more than 1500 rows.*rule 2"):
        _read(athena, AthenaRead(table="visits.many"))
    assert len(athena.page_sizes) == 2  # stopped at the page that passed the cap


def test_bytes_past_the_cap_are_refused_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reads, "MAX_BYTES", 2_000)
    with pytest.raises(ConnectorRefused, match=r"more than 2000 bytes.*rule 2"):
        _read(_athena(), AthenaRead(table="visits.many"))


def test_pages_past_the_cap_are_refused_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(athena_connector, "MAX_PAGES", 2)
    with pytest.raises(ConnectorRefused, match=r"more than 2 pages.*rule 2"):
        _read(_athena(), AthenaRead(table="visits.many"))


def test_a_query_that_never_finishes_is_stopped_and_refused() -> None:
    athena = _athena(polls=10_000)
    ticks = iter(range(0, 10_000, 30))
    with pytest.raises(ConnectorRefused, match="did not finish within 300 seconds"):
        _read(athena, AthenaRead(table="visits.visit_bookings"), clock=lambda: float(next(ticks)))
    assert athena.asked[-1] == "StopQueryExecution"


def test_a_result_naming_a_column_twice_is_refused_never_one_value_written_in_both() -> None:
    """The review, round 1, item 3 (rule 2): a row kept as a dict by column name kept the second
    `booking_id` only, and the source's file then held it in both cells. Refused, as S3 refuses a
    header naming a column twice, before any row is kept (the route writes only rows it is given)."""
    with pytest.raises(ConnectorRefused, match="names the column 'booking_id' twice"):
        _read(_athena(), AthenaRead(table="visits.twice"))


def test_a_row_with_more_values_than_columns_is_refused_never_cut() -> None:
    """The review, round 1, item 3: `zip(strict=False)` dropped a row's surplus values silently."""
    with pytest.raises(ConnectorRefused, match="row 1 of Athena's table visits.surplus has 2 values"):
        _read(_athena(), AthenaRead(table="visits.surplus"))


def test_a_catalog_athena_does_not_hold_is_refused_in_words() -> None:
    """The review, round 1, item 7: the fixture ignored QueryExecutionContext.Catalog."""
    athena = _athena()
    with pytest.raises(ConnectorRefused, match="Athena could not run the query: CATALOG_NOT_FOUND"):
        _read(athena, AthenaRead(table="visits.visit_bookings"),
              settings=_settings(catalog="synthetic_nowhere"))  # fmt: skip
    athena.named_queries[SELECT_NQ]["QueryString"] = (
        'SELECT * FROM "synthetic_nowhere"."visits"."many"'
    )
    with pytest.raises(ConnectorRefused, match="CATALOG_NOT_FOUND"):
        _read(athena, AthenaRead(named_query=SELECT_NQ),
              settings=_settings(catalog="synthetic_nowhere"))  # fmt: skip


def test_a_join_to_a_table_athena_does_not_hold_is_refused_in_words() -> None:
    """The review, round 1, item 7: the fixture found a missing table only at the first FROM."""
    athena = _athena()
    athena.named_queries[SELECT_NQ]["QueryString"] = (
        "SELECT * FROM visits.many m JOIN visits.no_such_table n ON true"
    )
    with pytest.raises(ConnectorRefused, match="TABLE_NOT_FOUND.*visits.no_such_table"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))


def test_an_unqualified_table_is_read_from_the_query_s_own_database(tmp_path: Path) -> None:
    """The review, round 1, item 7: an unqualified table hit the fixture's assert; Athena resolves
    it against the execution's database, and so does the fixture."""
    athena = _athena()
    athena.named_queries[SELECT_NQ]["QueryString"] = "SELECT * FROM visit_bookings"
    rows = _read(athena, AthenaRead(named_query=SELECT_NQ))
    landed = write_snapshot(rows, tmp_path, "bookings").read_text(encoding="utf-8")
    assert landed == (GOLDEN / "athena_visit_bookings.csv").read_text(encoding="utf-8")
    athena.named_queries[SELECT_NQ]["QueryString"] = "SELECT * FROM ledger"
    with pytest.raises(ConnectorRefused, match="TABLE_NOT_FOUND.*visits.ledger"):
        _read(athena, AthenaRead(named_query=SELECT_NQ))


def test_the_fixture_refuses_what_athena_refuses() -> None:
    """Rule 15: each refusal the reader's tests rely on is one the fixture really makes."""
    athena = _athena(polls=0)
    client = athena.client()
    started = client.start_query_execution(QueryString='SELECT * FROM "visits"."many"',
                                           WorkGroup="primary")  # fmt: skip
    with pytest.raises(ClientError, match="less than or equal to 1000"):
        client.get_query_results(QueryExecutionId=started["QueryExecutionId"], MaxResults=1001)
    with pytest.raises(ClientError, match="Invalid NextToken"):
        client.get_query_results(QueryExecutionId=started["QueryExecutionId"], NextToken="forged")
    with pytest.raises(ClientError, match="AccessDeniedException"):
        athena.client(REFUSED_KEY).start_query_execution(QueryString="SELECT 1 FROM visits.many")
    with pytest.raises(ClientError, match="No output location"):
        client.start_query_execution(QueryString="SELECT 1 FROM visits.many", WorkGroup="bare")
    with pytest.raises(ClientError, match="WorkGroup nowhere is not found"):
        client.start_query_execution(QueryString="SELECT 1 FROM visits.many", WorkGroup="nowhere")
    slow = _athena(polls=1).client()
    running = slow.start_query_execution(QueryString='SELECT * FROM "visits"."many"')
    with pytest.raises(ClientError, match="not yet finished"):
        slow.get_query_results(QueryExecutionId=running["QueryExecutionId"])
