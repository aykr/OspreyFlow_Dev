"""Where a search page's time goes (the owner's question from step 4's table, the orchestrator, 14
November 2026): names (p50 856 ms), full text (885 ms) and exact (857 ms) take nearly the same,
while suggestions on the same index take 57 ms, which looks like a fixed cost of some 0.8 s on every
search page rather than the search itself. This times one query of each kind, several times, two
ways:

- **Over the wire**, as m10-measure through the Conduit the step 4 runner starts (the same request
  `measure_search` sends for M3 to M5: `_request`, `_send`), with a suggestion and the Conduit's
  `/healthz` beside it for the floor every request pays.
- **In process**, through the real `search_service.search_page` against d's own stores, each
  collaborator timed where it is called: the reader's access filter (`index_access_filter`); the
  index's query body (`build_search_body`); the OpenSearch call, its round trip beside OpenSearch's
  own `took` (the by-type counts, the mentions and the dataset counts are aggregations of that one
  request, `query.py`, not queries of their own); reading the reply (`read_search_response`); every
  graph read by port method (`get_nodes`, the hits' hydration, and `edges_among`, the merge's links
  among the shown nodes), each with how many SQL and Gremlin calls it sent and their time (the
  store's list of types, `SELECT … FROM schema:types`, read by each, apart); building
  the results (`_result`); the merge (`_merged`); and the answer's serialisation
  (`model_dump_json`).

Over the wire less in process is what the route adds: the token, the case, the case's datasets
(`datasets.list_for`), its threshold, the pending ids, the audit row and the response's own
serialisation by FastAPI. The case's threshold is read once over its own route
(`/resolution/threshold`) and used in process, so the merge runs as the page runs it; each query
runs in process also without it (`tau none`), so the merge's own share shows.

**Read-only**: every graph call is a read and every index call a search; over the wire it sends
only the searches, suggestions and the threshold read step 4 already sends (each route writes its
own audit row, as M1 to M6 did). Run on d under rules' lease, with rules' agreement, inside the
step 4 runner, from `OspreyFlow_Core` (it needs `OSPREY_MEASURE_BASE`, `OSPREY_MEASURE_CASE` and
`OSPREY_MEASURE_TOKEN` from the runner, and the lease's `ARCADEDB_*` and `OPENSEARCH_*`):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/v052-measure/step4_stack.py \\
        --case <the case> -- .venv/bin/python \\
        ../OspreyFlow_Build/process/lanes/platform/v052-measure/profile_page.py \\
        --database <B's database> --queries ~/osprey-load/step4/queries.jsonl --repeat 10

It prints, for each kind, the median ms of every stage and its call counts, and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
sys.path[:0] = [str(CORE), str(CORE / "packages")]

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter  # noqa: E402
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from ontology.handling import load_uk_le_scheme  # noqa: E402
from ontology.packs import load_deployment_ontology  # noqa: E402
from scripts import measure_search  # noqa: E402
from services.api import search_service  # noqa: E402
from services.api.search_access import index_access_filter  # noqa: E402
from services.search_index.client import SearchIndexConfig, search_client  # noqa: E402
from services.search_index.document import phonetic_codes  # noqa: E402

from schemas.domain import Principal  # noqa: E402
from schemas.search import SearchPageRequest  # noqa: E402

#: The kinds step 4 timed on the page (M3, M4, M5) and the suggestion beside them (M1).
KINDS = ("names", "fulltext", "exact")
#: m10-measure as rules granted it on d (step4_stack.SUBJECTS), M1 to M6's own subject.
MEASURE = Principal(
    id="m10-measure",
    clearance="OFFICIAL-SENSITIVE",
    org_unit="unit-intel",
    receivable_handling_codes=["P", "C"],
    datasets=["cs-intel"],
)

_stage: contextvars.ContextVar[str] = contextvars.ContextVar("stage", default="other")


class _Ledger:
    """One run's times: each stage's wall ms, and the store calls sent inside it."""

    def __init__(self) -> None:
        self.ms: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)

    def add(self, stage: str, ms: float, calls: int = 1) -> None:
        self.ms[stage] += ms
        self.calls[stage] += calls


LEDGER = _Ledger()


async def _timed(stage: str, run: Awaitable[Any]) -> Any:
    token = _stage.set(stage)
    started = time.perf_counter()
    try:
        return await run
    finally:
        LEDGER.add(stage, (time.perf_counter() - started) * 1000)
        _stage.reset(token)


class _TimedClient:
    """The adapter's ArcadeDB client, each SQL and Gremlin call counted under the graph read that
    sent it (the calls of one read may overlap, so their sum can pass the read's wall time)."""

    def __init__(self, inner: ArcadeDBClient) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        found = getattr(self._inner, name)
        if name not in ("sql", "gremlin"):
            return found

        async def call(*args: Any, **kwargs: Any) -> Any:
            # The store's list of types (`lookup.unique_id_types`, read on every read by id, all
            # types with all their indexes) apart from the per-type lookups it leads to.
            what = "sql schema:types" if args and "schema:types" in str(args[0]) else name
            started = time.perf_counter()
            try:
                return await found(*args, **kwargs)
            finally:
                LEDGER.add(f"{_stage.get()} · {what}", (time.perf_counter() - started) * 1000)

        return call


class _TimedGraph:
    """The graph port, each method's wall time under `graph.<method>`."""

    def __init__(self, inner: GraphArcadeDBAdapter) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        found = getattr(self._inner, name)
        if not asyncio.iscoroutinefunction(found):
            return found

        async def call(*args: Any, **kwargs: Any) -> Any:
            return await _timed(f"graph.{name}", found(*args, **kwargs))

        return call


def _wrap_sync(stage: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    def call(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            LEDGER.add(stage, (time.perf_counter() - started) * 1000)

    return call


def _instrument() -> None:
    """The search service's own steps, timed where `search_page` calls them."""
    q = search_service.q
    q.build_search_body = _wrap_sync("build_search_body", q.build_search_body)
    q.read_search_response = _wrap_sync("read_search_response", q.read_search_response)
    search_service._result = _wrap_sync("_result (each hit)", search_service._result)
    merged = search_service._merged

    async def timed_merged(*args: Any, **kwargs: Any) -> Any:
        return await _timed("_merged", merged(*args, **kwargs))

    search_service._merged = timed_merged


def _timed_searcher(searcher: search_service.Searcher) -> search_service.Searcher:
    async def ask(body: dict[str, Any], timeout: float) -> dict[str, Any]:
        started = time.perf_counter()
        reply = await searcher(body, timeout)
        LEDGER.add("opensearch (round trip)", (time.perf_counter() - started) * 1000)
        LEDGER.add("opensearch (its own took)", float(reply.get("took", 0)))
        return reply

    return ask


def _get(base: str, path: str, token: str | None) -> tuple[float, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(base.rstrip("/") + path, headers=headers)
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=30) as answer:
        data = answer.read()
    return (time.perf_counter() - started) * 1000, data


def _first_of_each(path: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    chosen: dict[str, dict[str, Any]] = {}
    for row in rows:
        chosen.setdefault(row["class"], row)
    missing = [k for k in (*KINDS, "suggest") if k not in chosen]
    if missing:
        raise SystemExit(f"profile_page: {path} has no {', '.join(missing)} row")
    return chosen


def _median(values: list[float]) -> str:
    return f"{statistics.median(values):.1f}" if values else "-"


def _wire(base: str, case: str, token: str, row: dict[str, Any], repeat: int) -> list[float]:
    path, body = measure_search._request(case, row)
    times = []
    for _ in range(repeat):
        ms, answer, error = measure_search._send(base, path, body, token)
        if answer is None:
            raise SystemExit(f"profile_page: {path} answered {error}")
        times.append(ms)
    return times


async def _in_process(
    args: argparse.Namespace, rows: dict[str, dict[str, Any]], tau: float | None
) -> None:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database=args.database))
    adapter = GraphArcadeDBAdapter(_TimedClient(client), load_uk_le_scheme())  # type: ignore[arg-type]
    schema = load_deployment_ontology()
    adapter.use_schema(schema)
    graph = _TimedGraph(adapter)
    config = SearchIndexConfig.from_env()
    searcher = _timed_searcher(
        search_service.opensearch_searcher(search_client(config, max_retries=0), config.alias)
    )
    scheme = load_uk_le_scheme()
    _instrument()
    names = {d: d for d in MEASURE.datasets or ()}
    for kind in KINDS:
        row = rows[kind]
        _path, body = measure_search._request("case", row)
        request = SearchPageRequest.model_validate(body)
        for label, page_tau in ((f"tau {tau}", tau), ("tau none", None)):
            runs: list[_Ledger] = []
            totals: list[float] = []
            for i in range(args.warm + args.repeat):
                global LEDGER
                LEDGER = _Ledger()
                started = time.perf_counter()
                access = await _timed(
                    "index_access_filter", _sync(index_access_filter, scheme, MEASURE)
                )
                answer = await search_service.search_page(
                    request, MEASURE, graph,  # type: ignore[arg-type]
                    searcher=searcher, access_filter=access, phonetic_codes=phonetic_codes,
                    types=[t.name for t in schema.entity_types], case_datasets=names,
                    tau=page_tau, schema=schema,
                )  # fmt: skip
                await _timed("model_dump_json", _sync(answer.model_dump_json))
                if i >= args.warm:
                    totals.append((time.perf_counter() - started) * 1000)
                    runs.append(LEDGER)
            stages = sorted({s for r in runs for s in r.ms}, key=lambda s: -statistics.median(
                [r.ms.get(s, 0.0) for r in runs]))  # fmt: skip
            print(f"\n{kind} ({row['query']!r}), in process, {label}: total median "
                  f"{_median(totals)} ms over {len(totals)} runs; {len(answer.results)} results, "
                  f"source {answer.source}")  # fmt: skip
            for stage in stages:
                ms = [r.ms.get(stage, 0.0) for r in runs]
                calls = statistics.median([r.calls.get(stage, 0) for r in runs])
                print(f"  {stage}: median {_median(ms)} ms ({calls:g} calls)")


async def _sync(fn: Callable[..., Any], *args: Any) -> Any:
    return fn(*args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", default="ospreyflow")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--warm", type=int, default=2)
    args = parser.parse_args(argv)
    if os.environ.get("STEP4_SEARCH_INDEX_ALIAS"):  # as the runner gives its Conduit the alias
        os.environ.setdefault("OSPREY_SEARCH_INDEX_ALIAS", os.environ["STEP4_SEARCH_INDEX_ALIAS"])
    base, case = os.environ["OSPREY_MEASURE_BASE"], os.environ["OSPREY_MEASURE_CASE"]
    token = os.environ["OSPREY_MEASURE_TOKEN"]
    rows = _first_of_each(args.queries)
    _ms, raw = _get(base, f"/v1/investigations/{case}/resolution/threshold", token)
    tau = float(json.loads(raw)["threshold"])
    print(f"the case's threshold: {tau}")
    floor = [_get(base, "/healthz", None)[0] for _ in range(args.warm + args.repeat)][args.warm :]
    print(f"over the wire, /healthz: median {_median(floor)} ms")
    for kind in (*KINDS, "suggest"):
        times = _wire(base, case, token, rows[kind], args.warm + args.repeat)[args.warm :]
        print(f"over the wire, {kind} ({rows[kind]['query']!r}): median {_median(times)} ms, "
              f"min {min(times):.1f}, max {max(times):.1f}")  # fmt: skip
    asyncio.run(_in_process(args, rows, tau))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
