"""Search's live budget gate (ADR-149 Amendment 2): M1, M3, M4, M5 and M6 judged on a B-sized stack
at their failure figures, by `scripts.measure_search` and its `BUDGETS` (held to the amendment's
table both ways by `tests/test_measure_search.py`). Step 6 (`v052-r1`) and each release run it
under a lease, against the load.

The stack is named by the environment, never an argument:
- `OSPREY_MEASURE_BASE`: the Conduit's door;
- `OSPREY_MEASURE_CASE`: the case holding the load;
- `OSPREY_MEASURE_TOKEN`: the measuring principal's bearer token, with edit and draw rights on the
  case (M6 draws on a board of its own);
- `OSPREY_MEASURE_QUERIES`: a JSON-lines file made from B's plants (the `truth` column), with
  every query class.

`OSPREY_MEASURE_N` and `OSPREY_MEASURE_WARMUP` default to the amendment's 200 sends after 20
discarded; M6 takes `OSPREY_MEASURE_LAG_N` (default 50) draws after 5, each waiting on the
indexer. Where no stack is named, each case is skipped and says why: there is nothing B-sized to
measure. A class with no queries in a named stack's file fails rather than passing unmeasured.

M10, the leak test at scale, is pass or fail: it needs two more, `OSPREY_MEASURE_CLEARED_TOKEN` (the
fully cleared principal's, for each case's control) and `OSPREY_MEASURE_LEAKS` (a JSON-lines file of
leak cases derived from B's truth, `measure_search.measure_leaks`), and is skipped with that reason
where either is unset. M9 (the fallback) is not in this file yet: a case to be written for step 6's
live run."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from scripts import measure_search

_NAMED = (
    "OSPREY_MEASURE_BASE",
    "OSPREY_MEASURE_CASE",
    "OSPREY_MEASURE_TOKEN",
    "OSPREY_MEASURE_QUERIES",
)


def _stack() -> dict[str, str]:
    missing = [name for name in _NAMED if not os.environ.get(name)]
    if missing:
        pytest.skip(
            f"no B-sized stack named ({', '.join(missing)} unset): step 6 and each release run "
            "this under a lease, against the load"
        )
    return {name: os.environ[name] for name in _NAMED}


@pytest.mark.parametrize(
    "query_class",
    measure_search.QUERY_CLASSES,
    ids=[f"{measure_search.BUDGETS[c]['measure']}-{c}" for c in measure_search.QUERY_CLASSES],
)
def test_the_class_is_within_its_failure_figure_on_the_load(query_class: str) -> None:
    stack = _stack()
    lines = Path(stack["OSPREY_MEASURE_QUERIES"]).read_text(encoding="utf-8").splitlines()
    queries = [
        q for q in (json.loads(line) for line in lines if line.strip()) if q["class"] == query_class
    ]
    assert queries, (
        f"the queries file holds no {query_class!r} query: the class would pass unmeasured"
    )
    result = measure_search.measure(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=stack["OSPREY_MEASURE_TOKEN"],
        queries=queries,
        n=int(os.environ.get("OSPREY_MEASURE_N", "200")),
        warmup=int(os.environ.get("OSPREY_MEASURE_WARMUP", "20")),
    )
    found = result["classes"][query_class]
    assert found["verdict"] == "met", f"{found['measure']} {query_class}: {found['why']}"


def test_m6_a_drawn_node_reaches_the_index_within_its_failure_figure() -> None:
    stack = _stack()
    found = measure_search.measure_lag(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=stack["OSPREY_MEASURE_TOKEN"],
        n=int(os.environ.get("OSPREY_MEASURE_LAG_N", "50")),
        warmup=5,
    )
    assert found["verdict"] == "met", f"M6 lag: {found['why']}"


def test_m10_nothing_hidden_is_seen_or_counted_by_the_part_cleared_principal() -> None:
    stack = _stack()
    missing = [
        n for n in ("OSPREY_MEASURE_CLEARED_TOKEN", "OSPREY_MEASURE_LEAKS") if not os.environ.get(n)
    ]
    if missing:
        pytest.skip(f"no leak cases named ({', '.join(missing)} unset): M10 needs both principals")
    lines = Path(os.environ["OSPREY_MEASURE_LEAKS"]).read_text(encoding="utf-8").splitlines()
    found = measure_search.measure_leaks(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=stack["OSPREY_MEASURE_TOKEN"],
        cleared_token=os.environ["OSPREY_MEASURE_CLEARED_TOKEN"],
        cases=[json.loads(line) for line in lines if line.strip()],
    )
    assert found["verdict"] == "met", "M10: " + "; ".join(found["failures"][:20])
