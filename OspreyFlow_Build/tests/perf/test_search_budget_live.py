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

M10, the leak test at scale, is pass or fail, asked as m10-part (`OSPREY_MEASURE_PART_TOKEN`): it
needs that, `OSPREY_MEASURE_CONTROLS` (a JSON
object, each control subject's token by its name, one per R-owning unit; in the environment, never
a file) and `OSPREY_MEASURE_LEAKS` (a JSON-lines file of leak cases derived from B's truth, each
naming its `control`, `measure_search.measure_leaks`), and is skipped with that reason where either
is unset.

M9, the fallback, stops OpenSearch mid-session: it runs only where `OSPREY_MEASURE_STOP_OPENSEARCH`
names the container to stop (on the day, stack d's, under rules' lease with its agreement), and is
skipped with that reason otherwise, so no other run stops a store. The container is started again
whatever happens, and the index must answer again before the case ends."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from scripts import measure_search

_NAMED = (
    "OSPREY_MEASURE_BASE",
    "OSPREY_MEASURE_CASE",
    "OSPREY_MEASURE_TOKEN",
    "OSPREY_MEASURE_QUERIES",
)


def _void_on_401(measure: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """The first refused token ends the whole run, saying so: a run whose figures are void must not
    report as finished, and no later case measures on (step 4's rerun on d, 14 November 2026)."""

    def guarded(**kwargs: Any) -> dict[str, Any]:
        try:
            return measure(**kwargs)
        except measure_search.TokenRefused as refused:
            pytest.exit(f"step 4: {refused}", returncode=3)

    return guarded


def _record(measure: str, result: dict[str, Any]) -> None:
    """Each case's result, as JSON in the folder OSPREY_MEASURE_RESULTS names (the record's table
    is made from them: `process/lanes/platform/v052-measure/results_table.py`), written before
    its verdict is asserted, so a figure that fails is recorded too. Nothing where none is named."""
    folder = os.environ.get("OSPREY_MEASURE_RESULTS", "").strip()
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / f"{measure}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
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
    result = _void_on_401(measure_search.measure)(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=stack["OSPREY_MEASURE_TOKEN"],
        queries=queries,
        n=int(os.environ.get("OSPREY_MEASURE_N", "200")),
        warmup=int(os.environ.get("OSPREY_MEASURE_WARMUP", "20")),
    )
    found = result["classes"][query_class]
    _record(found["measure"], {**found, "class": query_class})
    assert found["verdict"] == "met", f"{found['measure']} {query_class}: {found['why']}"


def test_m6_a_drawn_node_reaches_the_index_within_its_failure_figure() -> None:
    stack = _stack()
    found = _void_on_401(measure_search.measure_lag)(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=stack["OSPREY_MEASURE_TOKEN"],
        n=int(os.environ.get("OSPREY_MEASURE_LAG_N", "50")),
        warmup=5,
    )
    _record("M6", found)
    assert found["verdict"] == "met", f"M6 lag: {found['why']}"


def test_m10_nothing_hidden_is_seen_or_counted_by_the_part_cleared_principal() -> None:
    stack = _stack()
    missing = [
        n
        for n in ("OSPREY_MEASURE_PART_TOKEN", "OSPREY_MEASURE_CONTROLS", "OSPREY_MEASURE_LEAKS")
        if not os.environ.get(n)
    ]
    if missing:
        pytest.skip(
            f"no leak cases named ({', '.join(missing)} unset): M10 needs the part-cleared "
            "principal and the controls"
        )
    lines = Path(os.environ["OSPREY_MEASURE_LEAKS"]).read_text(encoding="utf-8").splitlines()
    found = _void_on_401(measure_search.measure_leaks)(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=os.environ["OSPREY_MEASURE_PART_TOKEN"],
        controls=json.loads(os.environ["OSPREY_MEASURE_CONTROLS"]),
        cases=[json.loads(line) for line in lines if line.strip()],
    )
    _record("M10", found)
    assert found["verdict"] == "met", "M10: " + "; ".join(found["failures"][:20])


def test_m9_opensearch_stopped_mid_session_the_bar_falls_back_and_says_so() -> None:
    import subprocess

    stack = _stack()
    container = os.environ.get("OSPREY_MEASURE_STOP_OPENSEARCH", "").strip()
    if not container:
        pytest.skip(
            "OSPREY_MEASURE_STOP_OPENSEARCH unset: M9 stops OpenSearch, and runs only where the "
            "container to stop is named (stack d's, under rules' lease, with its agreement)"
        )
    lines = Path(stack["OSPREY_MEASURE_QUERIES"]).read_text(encoding="utf-8").splitlines()
    every = [json.loads(line) for line in lines if line.strip()]
    names = [q for q in every if q["class"] == "names"][:5]
    prefixes = [q for q in every if q["class"] == "suggest"][:5]
    assert names and prefixes, "M9 needs name and suggestion queries in the queries file"
    queries = [{"route": "search", **q} for q in names] + [
        {"route": "suggest", **q} for q in prefixes
    ]

    def docker(verb: str) -> None:
        subprocess.run(["docker", verb, container], check=True, capture_output=True)

    found = _void_on_401(measure_search.measure_fallback)(
        base=stack["OSPREY_MEASURE_BASE"],
        case=stack["OSPREY_MEASURE_CASE"],
        token=stack["OSPREY_MEASURE_TOKEN"],
        queries=queries,
        stop=lambda: docker("stop"),
        start=lambda: docker("start"),
    )
    _record("M9", found)
    assert found["verdict"] == "met", "M9: " + "; ".join(found["failures"])
