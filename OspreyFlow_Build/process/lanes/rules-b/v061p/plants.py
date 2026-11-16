"""ADR-150 Amendment 4's plants (rule 15): each removes or reverses one sentence at its real call
site, runs the tests that claim to catch it, expects them red, and puts the file back (in a
`finally`). Live: under rules-b's lease (`stack_lease.sh live rules-b -- …`, from OspreyFlow_Core);
`--offline` runs the plants whose tests need no store.

Prints each plant's raw pytest summary and RED, GREEN or BROKEN (a collection error, an error in a
set-up, or nothing run: never read as red); exits 1 if any was not RED or the built tree is not
green before and after. Shape and runner as `process/lanes/rules/v052-index/plants.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
B = "../OspreyFlow_Build/tests/services/search_index"
LIVE_FILE = f"{B}/test_conduit_feed_live.py"
FEEDS = f"{LIVE_FILE}::test_a_conduit_with_no_worker_feeds_the_index_and_its_outbox_falls"
LEAVES = f"{LIVE_FILE}::test_a_rebuild_leaves_the_outbox_it_covered_and_the_feed_drains_it"
OFFLINE = f"{B}/test_conduit_feed.py"
REACH = f"{B}/test_index_feed_reach.py"
APP = "OspreyFlow_Core/services/api/app.py"
WORKER = "OspreyFlow_Core/services/api/worker_main.py"
REBUILD = "OspreyFlow_Core/services/search_index/rebuild.py"
LIVE = (LIVE_FILE,)

PLANTS: list[tuple[str, str, str, str, list[str]]] = [
    # decision 1: the Conduit starts the feed where it runs the job loop
    (
        "F1 the Conduit never starts the feed (236e31e's behaviour)",
        APP,
        "        if index_feed_in_conduit()\n        else None\n    )\n",
        "        if False\n        else None\n    )\n",
        [FEEDS],
    ),
    (
        "F2 the Conduit feeds without an OpenSearch to feed",
        APP,
        "    return job_loop_in_conduit(environ) and search_index_configured(environ)\n",
        "    return job_loop_in_conduit(environ)\n",
        [
            f"{OFFLINE}::test_the_conduit_feeds_the_index_only_where_it_runs_the_job_loop_and_there_is_one"
        ],
    ),
    (
        "F3 the Conduit feeds beside a worker",
        APP,
        "    return job_loop_in_conduit(environ) and search_index_configured(environ)\n",
        "    return search_index_configured(environ)\n",
        [f"{OFFLINE}::test_cluster_s_conduit_never_feeds_beside_its_worker"],
    ),
    (
        "F4 the worker runs an indexer of its own beside the helper",
        WORKER,
        "        if feed is not None:\n            logger.info(",
        "        if feed is None:\n            run_indexer(None, None, None, None)\n"
        "        if feed is not None:\n            logger.info(",
        [f"{OFFLINE}::test_the_worker_and_the_conduit_start_the_feed_one_way"],
    ),
    # decision 4 (rule 4): app.py naming a feed read is caught by the reach test
    (
        "F5 the Conduit reads the feed's unfiltered read itself",
        APP,
        "        if index_feed_in_conduit()\n        else None\n    )\n",
        "        if index_feed_in_conduit()\n        else None\n    )\n"
        '    _feed_read = getattr(graph, "nodes_for_index", None)\n',
        [f"{REACH}::test_no_route_or_other_module_reaches_the_indexers_reads"],
    ),
    # decision 3: a rebuild leaves the outbox it covered
    (
        "F6 a rebuild clears the outbox rows it covered",
        REBUILD,
        '        await client.indices.update_aliases(body={"actions": actions})\n',
        '        await client.indices.update_aliases(body={"actions": actions})\n'
        "        _rows = await source.pending_index(100_000)\n"
        "        await source.clear_pending_index([r.ref for r in _rows])\n",
        [LEAVES],
    ),
    # decision 1's third bullet: stopped at shutdown, before the stores, beside the job loop
    (
        "F7 the lifespan never closes the feed",
        APP,
        "            await index_feed.close(timeout=JOB_LOOP_STOP_SECONDS)\n",
        "",
        [
            f"{OFFLINE}::test_the_lifespan_stops_the_feed_with_the_job_loop_and_closes_it_before_the_stores"
        ],
    ),
    (
        "F8 the feed's stop waits for the job loop",
        APP,
        "        if index_feed is not None:\n            index_feed.stop.set()\n",
        "",
        [
            f"{OFFLINE}::test_the_lifespan_stops_the_feed_with_the_job_loop_and_closes_it_before_the_stores"
        ],
    ),
    (
        "F9 a refused search setting stops the Conduit's start",
        APP,
        "    except Exception:  # noqa: BLE001 - said, and the Conduit starts without a feed\n",
        "    except ImportError:\n",
        [f"{OFFLINE}::test_refused_search_settings_start_the_conduit_without_a_feed"],
    ),
    (
        "F10 a feed's close leaves its client open",
        "OspreyFlow_Core/services/search_index/run.py",
        "        for close in self.closing:\n            await close()\n",
        "",
        [
            f"{OFFLINE}::test_a_feed_s_close_stops_it_and_closes_what_it_opened",
            f"{OFFLINE}::test_a_feed_past_its_bound_is_cancelled_and_still_closes_its_client",
        ],
    ),
]


def _run(tests: list[str]) -> tuple[str, str]:
    """RED only where pytest ran the tests and some failed (exit 1, "failed" in its summary, no
    error); a collection error, an error in a set-up or nothing run is BROKEN."""
    with tempfile.TemporaryDirectory() as cache:
        done = subprocess.run(
            [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
             "-p", "no:randomly", "-q", *tests],
            cwd=CORE, capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPYCACHEPREFIX": cache, "PYTHONDONTWRITEBYTECODE": "1"},
        )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    failed = [line for line in lines if line.startswith(("FAILED ", "ERROR ../"))]
    summary = lines[-1] if lines else done.stderr.strip()
    said = " | ".join([*failed, summary])
    if done.returncode == 0:
        return "GREEN", said
    if done.returncode == 1 and " failed" in summary and " error" not in summary:
        return "RED", said
    return "BROKEN", said


def main() -> int:
    offline = "--offline" in sys.argv[1:]
    every = [LIVE_FILE, OFFLINE, REACH]
    plants = PLANTS
    if offline:
        every = [t for t in every if t not in LIVE]
        plants = [p for p in PLANTS if not any(t.startswith(LIVE) for t in p[4])]
        print(f"offline: {len(plants)} of {len(PLANTS)} plants, the live file left out")
    state, line = _run(every)
    print(f"built: {state} - {line}")
    if state != "GREEN":
        return 1
    left = 0
    root = CORE.parent
    for name, rel, built, planted, tests in plants:
        path = root / rel
        source = path.read_text(encoding="utf-8")
        if source.count(built) != 1:
            print(f"{name}: the built text is not in {rel} exactly once; plant not applied")
            left += 1
            continue
        try:
            path.write_text(source.replace(built, planted), encoding="utf-8")
            state, line = _run(tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}]: {state} - {line}")
        left += 0 if state == "RED" else 1
    state, line = _run(every)
    print(f"restored: {state} - {line}")
    return 1 if left or state != "GREEN" else 0


if __name__ == "__main__":
    sys.exit(main())
