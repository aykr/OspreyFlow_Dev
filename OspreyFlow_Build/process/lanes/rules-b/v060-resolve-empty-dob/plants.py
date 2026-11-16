"""Plants for the empty date-of-birth fix (rule 15): each plant is a wrong version of the fix, put
in place of the real one, and the three new tests in tests/resolve/test_resolver.py are run against
it. A plant is caught when at least one of them fails. Run from OspreyFlow_Core with the venv and
the pinned dead ports (no stack is touched: Splink on DuckDB is in-process):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/rules-b/v060-resolve-empty-dob/plants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
CORE = HERE.parents[5] / "OspreyFlow_Core"
BUILD = HERE.parents[4]
sys.path[:0] = [str(CORE), str(CORE / "packages"), str(CORE / "cli"), str(BUILD)]

import pandas as pd  # noqa: E402

from schemas.domain import PropertyType  # noqa: E402
from services.resolve import resolver  # noqa: E402
from tests.resolve import test_resolver as t  # noqa: E402

TESTS = [
    "test_a_population_with_no_date_of_birth_at_all_resolves_without_raising",
    "test_the_same_name_with_no_date_of_birth_still_becomes_a_candidate",
    "test_a_population_with_dates_of_birth_resolves_exactly_as_before",
]
REAL_FRAME = resolver._nodes_to_dataframe
REAL_RESOLVE = resolver.resolve_entity_type
TEMPORAL = (PropertyType.DATE, PropertyType.DATETIME)


def _rows(nodes, columns, property_types):
    rows = []
    for node in nodes:
        row = {"unique_id": node.id}
        for column in columns:
            row[column] = resolver._cast(node.properties.get(column), property_types.get(column))
        rows.append(row)
    return pd.DataFrame(rows)


def no_fix(nodes, columns, property_types):
    """The code before the fix."""
    return _rows(nodes, columns, property_types)


def every_date_column_emptied(nodes, columns, property_types):
    """The dtype forced on every date column, empty or not: the dates are lost."""
    frame = _rows(nodes, columns, property_types)
    for c in columns:
        if property_types.get(c) in TEMPORAL:
            frame[c] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return frame


def any_instead_of_all(nodes, columns, property_types):
    """A column with any empty row treated as empty: a mixed population loses its dates."""
    frame = _rows(nodes, columns, property_types)
    for c in columns:
        if property_types.get(c) in TEMPORAL and frame[c].isna().any():
            frame[c] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return frame


def empty_column_as_text(nodes, columns, property_types):
    """The empty column given a type, but a string one: DuckDB reads VARCHAR, year() still fails."""
    frame = _rows(nodes, columns, property_types)
    for c in columns:
        if property_types.get(c) in TEMPORAL and frame[c].isna().all():
            frame[c] = frame[c].astype("string")
    return frame


def swallow_the_failure(nodes, entity_type):
    """No dtype fix; the failure caught and an empty answer returned (silently resolving nothing)."""
    try:
        return REAL_RESOLVE(nodes, entity_type)
    except Exception:  # noqa: BLE001 - the plant itself
        return []


PLANTS = [
    ("no fix (main before it)", "frame", no_fix),
    ("every date column emptied, not only an empty one", "frame", every_date_column_emptied),
    ("any() for all(): a mixed column emptied", "frame", any_instead_of_all),
    ("the empty column typed as text", "frame", empty_column_as_text),
    ("the failure swallowed, returning no candidates", "resolve", swallow_the_failure),
]


def run_tests() -> list[str]:
    failed = []
    for name in TESTS:
        try:
            getattr(t, name)()
        except Exception as exc:  # noqa: BLE001 - a test's failure is the result
            failed.append(f"{name}: {type(exc).__name__}")
    return failed


def main() -> int:
    import logging

    logging.disable(logging.CRITICAL)
    import warnings

    warnings.filterwarnings("ignore")
    baseline = run_tests()
    print(f"the real fix: {len(TESTS) - len(baseline)} of {len(TESTS)} pass {baseline or ''}")
    caught = 0
    for label, where, plant in PLANTS:
        if where == "frame":
            resolver._nodes_to_dataframe = plant
        else:
            resolver._nodes_to_dataframe = no_fix
            t.resolve_entity_type = plant
        try:
            failed = run_tests()
        finally:
            resolver._nodes_to_dataframe = REAL_FRAME
            t.resolve_entity_type = REAL_RESOLVE
        caught += bool(failed)
        print(f"{'RED  ' if failed else 'GREEN'} {label}: {failed or 'every test passed - NOT caught'}")
    print(f"{caught} of {len(PLANTS)} plants caught")
    return 0 if caught == len(PLANTS) and not baseline else 1


if __name__ == "__main__":
    sys.exit(main())
