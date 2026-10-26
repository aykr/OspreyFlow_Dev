"""ADR-127 Amendment 19, the cost: R5's full file, about 100,000 rows, sends exactly one `EdgeWrite` for
each of its 3,547 links across all its `upsert_edges` calls (Amendment 18 counts the links), where a
write for each row's two links is about two hundred thousand.

Slow, and outside `make ci` (`tests/ingest` is not in `make test`; `make conformance` selects the
folder, and this case skips there unless asked): it reads, resolves, stages and loads about 100,000 rows
against the graph stand-in, which holds every event in memory. Run it with
`OSPREYFLOW_RUN_SLOW=1`; the combine time (the time spent folding writes into the held ones,
`aggregate_edge_writes`) is printed apart from the whole run's, for `INGEST_ACTUALS.md`.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from services.ingest import engine

from tests.ingest.combined_run_support import CountingMerging
from tests.ingest.loop_monitor import LoopMonitor
from tests.ingest.pid_golden_support import CALLS, CASE, ONTOLOGY, keys_in, load, rows_of
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import KeyStore, Sink

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("OSPREYFLOW_RUN_SLOW"),
        reason="R5's whole file: set OSPREYFLOW_RUN_SLOW=1 to run it",
    ),
]

BEFORE = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_number_owners.csv",
)
LINKS = 3547


async def test_r5s_full_file_sends_exactly_one_write_for_each_of_its_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = CountingMerging(ONTOLOGY)
    store = KeyStore()
    for file in BEFORE:
        report, _ = await load(graph, file, Sink(store, CASE))
        assert report.rejections == [], (file, report.rejections[:3])

    spent = {"combine": 0.0}
    real = engine.aggregate_edge_writes

    def timed(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return real(*args, **kwargs)
        finally:
            spent["combine"] += time.perf_counter() - started

    monkeypatch.setattr(engine, "aggregate_edge_writes", timed)
    sent_before = graph.edges_sent
    started = time.perf_counter()
    report, events = await load(graph, CALLS, Sink(store, CASE))
    whole = time.perf_counter() - started

    assert report.rejections == [], report.rejections[:3]
    _, link_keys = keys_in(CALLS)
    rows = len(rows_of(CALLS))
    sent = graph.edges_sent - sent_before
    print(
        f"\nR5 full file: {rows:,} rows, {len(events):,} events, {sent:,} EdgeWrites sent, "
        f"whole load {whole:.1f} s, of which combining {spent['combine']:.1f} s"
    )
    assert report.rows_read == rows
    assert sent == len(link_keys) == LINKS, (
        "one write for each link: the file's links are the plan's, 3,547 (ADR-127 Amendment 18)"
    )
    assert len(report.touched_edge_ids) == sent, "the record names each link once"


async def test_r5s_run_never_holds_the_event_loop_for_two_seconds() -> None:
    """ADR-127 Amendment 29: the keep-alive of the run's open transaction is an asyncio task, so a
    run that holds the loop for longer than the session's life loses its transaction (the first real
    seed's R5 did, after about four minutes). A task sampling the loop every 100 ms records the
    longest stall across the whole run, and none may exceed two seconds."""
    graph = CountingMerging(ONTOLOGY)
    store = KeyStore()
    for file in BEFORE:
        report, _ = await load(graph, file, Sink(store, CASE))
        assert report.rejections == [], (file, report.rejections[:3])
    rows_of(CALLS)  # read once, here: the test's own file read is not the run's
    started = time.perf_counter()
    async with LoopMonitor() as monitor:
        report, _events = await load(graph, CALLS, Sink(store, CASE))
    whole = time.perf_counter() - started
    print(
        f"\nR5 full file: whole load {whole:.1f} s, "
        f"longest event-loop stall {monitor.longest:.2f} s"
    )
    assert report.rejections == [], report.rejections[:3]
    print(monitor.report())
    assert monitor.longest <= 2.0, monitor.report()
