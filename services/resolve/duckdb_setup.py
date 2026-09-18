"""DuckDB connection setup for Splink (`docs/06_DECISIONS.md` ADR-021) — registers the `soundex`
scalar UDF DuckDB itself lacks. Confirmed directly, not assumed: `SELECT soundex('MERCER')`
against a bare DuckDB connection raises `Catalog Error: Scalar Function with name soundex does not
exist!`. `phonetics` (MIT) is already a transitive dependency of `splink==3.9.9` itself, so this
adds no new dependency.
"""

from __future__ import annotations

import duckdb
import phonetics


def _soundex(value: str | None) -> str | None:
    if not value:
        return None
    return str(phonetics.soundex(value.lower()))


def new_connection() -> duckdb.DuckDBPyConnection:
    """A fresh, private in-memory connection per resolution run — mirrors
    `adapters/analytics_duckdb/testing.py`'s own per-test-connection pattern. Never shared across
    calls: Splink mutates the connection it's given (temp tables, registered UDFs), so reuse
    across concurrent resolution runs would race."""
    con = duckdb.connect(":memory:")
    con.create_function("soundex", _soundex, ["VARCHAR"], "VARCHAR")
    return con
