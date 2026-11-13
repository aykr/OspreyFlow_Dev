"""ADR-146 Amendment 7 (the orchestrator's review, item 6; its verification of e911b90, item 3): a
DuckDB analytics file made before an alert's facts were kept per set of its citations has
`alert_facts` and `alert_fact_handlings` without `fact_id` and `grp`, and `CREATE TABLE IF NOT
EXISTS` would leave them so. `create_events_table`, run at every start, brings such a file forward:
each old row its own set (`fact_id` its alert's, group 0), so a trend still counts it, and a
second start changes nothing. As `test_load_id_migration.py` does for `load_id`."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import (
    CREATE_ALERT_FACT_HANDLINGS_TABLE,
    CREATE_ALERT_FACTS_TABLE,
    create_events_table,
)
from ontology.handling import load_uk_le_scheme
from schemas.analytics import AlertTrendRequest
from schemas.domain import Interval, Principal

READER = Principal(id="analyst", clearance="OFFICIAL", org_unit="unit-1")
WINDOW = Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 6, 30, tzinfo=UTC))


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info('{table}')").fetchall()]


def _old_file() -> duckdb.DuckDBPyConnection:
    """A file as the Conduit left it before the sets: one alert's fact and its marking."""
    con = duckdb.connect(":memory:")
    con.execute(CREATE_ALERT_FACTS_TABLE)
    con.execute(CREATE_ALERT_FACT_HANDLINGS_TABLE)
    assert "fact_id" not in _columns(con, "alert_facts")
    assert not {"fact_id", "grp"} & set(_columns(con, "alert_fact_handlings"))
    con.execute(
        "INSERT INTO alert_facts VALUES ('old', 'case-1', 'typology', 'typology:r1', 'structuring', "
        "'medium', 'open', '2026-03-02 12:00:00', 'analyst', 'case', NULL, NULL, 1)"
    )
    con.execute("INSERT INTO alert_fact_handlings VALUES ('old', 'OFFICIAL', 'P', 'unit-1', 'unit-1')")
    return con


async def test_an_old_file_gains_the_sets_and_its_alert_is_still_counted() -> None:
    """Red with the sets not added: the trend failed on the missing `grp` ("Binder Error:
    Referenced column \"grp\" not found"); with the old rows' `fact_id` left empty: the trend still
    counted the alert (it reads an old row by its alert) and the check of `fact_id` failed."""
    con = _old_file()
    create_events_table(con)
    adapter = AnalyticsDuckDBAdapter(con, load_uk_le_scheme())
    trend = await adapter.alert_trend(AlertTrendRequest(investigation_scope="case-1", window=WINDOW), READER)
    assert trend.total == 1.0
    assert con.execute("SELECT fact_id FROM alert_facts").fetchall() == [("old",)]
    assert con.execute("SELECT fact_id, grp FROM alert_fact_handlings").fetchall() == [("old", 0)]


def test_running_it_again_on_a_file_that_has_the_sets_changes_nothing() -> None:
    con = _old_file()
    create_events_table(con)
    create_events_table(con)
    assert _columns(con, "alert_facts").count("fact_id") == 1
    assert [_columns(con, "alert_fact_handlings").count(c) for c in ("fact_id", "grp")] == [1, 1]
    assert con.execute("SELECT count(*) FROM alert_fact_handlings").fetchall() == [(1,)]
