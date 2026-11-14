"""`python -m services.api.worker_main` — the job worker as a process.

`JobWorker`'s own docstring anticipated this exactly: "a real deployment calls it in a loop (not
built here — a `while True` around `run_once` per registered `job_type`, run as this service's own
long-lived process, is deployment wiring, not additional logic to test)." This is that wiring, and
nothing more: no new dispatch logic, no second transaction owner, no handler registry of its own
beyond naming the handlers that already exist.

`06_DECISIONS.md` ADR-049 Stage 2 §3, and the owner's decision of 24 September 2026 that
`05_DEPLOYMENT.md` §3's "three workers" means **three replicas of this one process**.

## The one thing replicas depend on, and why it is not a comment

Each replica must have a **distinct consumer name** within the shared `workers` consumer group.
`JobWorker.run_once` reads with `xreadgroup(CONSUMER_GROUP, consumer_name, {stream: ">"})`, and `>`
means "entries never delivered to any consumer in this group" — so Valkey itself guarantees one
entry reaches exactly one consumer, which is what makes three replicas safe rather than three times
the work. What that guarantee does *not* survive is two processes sharing one consumer name: the
pending-entries list is keyed by consumer, so a crashed replica's unacknowledged entries become
indistinguishable from a live replica's in-flight ones, and recovery cannot tell which to reclaim.

The name is taken from the container hostname, which Compose and Kubernetes both make unique per
replica. `OSPREY_WORKER_NAME` overrides it for anything that does not.

**The test that would fail if this were wrong:**
`tests/services/api/test_worker_replicas.py::test_two_replicas_never_process_the_same_job` — two
real `JobWorker` instances against one real Valkey stream, both reading, asserting the handler ran
exactly once in total. It is a live-service test because the guarantee belongs to Valkey, not to
this code: a fake queue would prove only that the fake hands each entry out once.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable, Collection
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # the import is deferred at runtime — see `main()`'s own comment.
    from .alerts import AlertStore
    from .assessments import JudgementStore
    from .worker import JobWorker

logger = logging.getLogger(__name__)

#: How long a single `run_once` blocks waiting for an entry before returning zero. Short enough
#: that shutdown is prompt, long enough that an idle worker is not a busy loop against Valkey.
BLOCK_MS = 2_000


def consumer_name() -> str:
    """Distinct per replica. The hostname is what Compose and Kubernetes both vary; the override
    exists for anything that does not, and for tests."""
    return os.environ.get("OSPREY_WORKER_NAME") or f"worker-{socket.gethostname()}"


def registered_job_types() -> dict[str, str]:
    """`job_type -> dotted handler path`, resolved lazily so importing this module does not import
    every handler's own dependency tree.

    Both handlers already exist and already match `JobHandler`'s shape — `supersede.py`'s was
    written ahead of its first caller, and `resolve/trigger.py`'s is the longer-running one the
    shape was designed to also carry (ADR-025).
    """
    return {
        "supersede_node": "services.api.supersede:run_supersede_node_job",
        "resolve_entity_type": "services.resolve.trigger:run_resolve_entity_type_job",
        # Enqueued by the compute and pattern routes for a large working set (the orchestrator's
        # fix, 14 November 2026): once registered on the Conduit's own worker alone, whose loop
        # never ran, and not here, so enqueued on every profile and run on none.
        "compute_metric": "services.api.compute_routes:run_compute_metric_job",
        "pattern_match": "services.api.patterns:run_pattern_match_job",
    }


def register_all(
    worker: JobWorker,
    *,
    ontology: Any,
    scheme: Any,
    valkey: Any,
    analyst_layers: Callable[[], Awaitable[Collection[str]]],
    alerts: AlertStore | None,
    judgement_store: JudgementStore | None,
    compute: Any = None,
) -> None:
    """Every handler in `registered_job_types` on `worker`, with what each needs bound, as the
    Conduit's own lifespan binds them (`app.py`): the resolution job its ontology, handling scheme,
    Valkey client and the case layers it must not honour a split from (ADR-025 Amendment 1, ADR-143
    Amendment 1); and both the alerts' repoint journal (`alerts`, ADR-109 Amendment 11), so a link
    either replaces is followed by the alerts citing it. `judgement_store`, the supersede job's
    review-flag hook (`01_DOMAIN_MODEL.md` §5): required, `None` named explicitly where there is
    none, so a registration that forgot it (the deployed worker's did, the L2.8d review's item 6)
    is refused by the type check rather than flagging nothing. `main` calls this, and so does the
    Conduit's lifespan (`app.py`), so the two registrations are one (the L2.8c review's item 13);
    `test_worker_registration.py` proves both. `compute`, the compute job's port: the Conduit passes
    its own; the worker's process, which has none, gets the same in-process one the Conduit builds
    (`ComputeRustworkxAdapter`, `run_resources`)."""
    from importlib import import_module

    bound: dict[str, dict[str, Any]] = {
        "supersede_node": {"alerts": alerts, "judgement_store": judgement_store},
        "resolve_entity_type": {
            "ontology": ontology,
            "scheme": scheme,
            "valkey": valkey,
            "analyst_layers": analyst_layers,
            "alerts": alerts,
        },
        "compute_metric": {"compute": compute if compute is not None else _compute_port()},
    }
    for job_type, dotted in registered_job_types().items():
        module_name, _, attribute = dotted.partition(":")
        handler = getattr(import_module(module_name), attribute)
        kwargs = bound.get(job_type)
        worker.register(job_type, functools.partial(handler, **kwargs) if kwargs else handler)


def _compute_port() -> Any:
    from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter

    return ComputeRustworkxAdapter()


async def run_forever(worker: JobWorker, job_types: list[str], *, stop: asyncio.Event) -> None:
    """One `run_once` per job type, round-robin, until asked to stop.

    Round-robin rather than one task per job type: `run_once` blocks, and two blocking reads from
    one connection would serialise anyway. A job type with nothing pending costs `BLOCK_MS` and
    returns zero, which is the idle case and is meant to be cheap rather than instant.
    """
    while not stop.is_set():
        for job_type in job_types:
            if stop.is_set():
                break
            try:
                processed = await worker.run_once(job_type, block_ms=BLOCK_MS)
            except Exception:  # noqa: BLE001 - a worker must outlive one bad read
                logger.exception("worker: run_once failed for job_type=%s", job_type)
                await asyncio.sleep(1.0)
                continue
            if processed:
                logger.info("worker: processed %d entr(ies) for job_type=%s", processed, job_type)


async def main() -> int:  # pragma: no cover - exercised as a process, not in-process
    logging.basicConfig(level=os.environ.get("OSPREY_LOG_LEVEL", "INFO"))

    # Imported here, not at module scope: this module is imported by tests that assert on
    # `consumer_name()` and the job-type registry without wanting a Valkey connection or an
    # ArcadeDB round trip.
    from valkey.asyncio import Valkey

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology

    from .alerts import AlertStore
    from .assessments import JudgementStore
    from .config import ApiConfig, PostgresConfig
    from .datasets import PostgresDatasetStore
    from .jobs import JobQueue
    from .worker import JobWorker

    # Built the same way `app.py`'s own `lifespan` builds them — deliberately the same
    # construction rather than a second one, so a worker and the Conduit never disagree about the
    # database name, the handling scheme or the ontology a transaction is validated against.
    config = ApiConfig.from_env()
    arcadedb = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await arcadedb.create_database_if_absent()
    graph = GraphArcadeDBAdapter(arcadedb, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())

    client = Valkey(**config.valkey.client_kwargs())
    worker = JobWorker(client, JobQueue(client), graph, consumer_name=consumer_name())
    # The case layers come from the dataset store, read at each run (a layer made since counts).
    datasets = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    # The alerts' repoint journal (ADR-109 Amendment 11): what a job replaces, alerts follow.
    alerts = await AlertStore.connect(PostgresConfig.from_env().dsn)
    # The supersede job flags the judgements citing a corrected node, as the Conduit's does.
    judgements = await JudgementStore.connect(PostgresConfig.from_env().dsn)
    register_all(
        worker,
        ontology=load_default_ontology(),
        scheme=load_uk_le_scheme(),
        valkey=client,
        analyst_layers=datasets.layer_ids,
        alerts=alerts,
        judgement_store=judgements,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    # ADR-150 decision 2: where this shape has an OpenSearch, one replica at a time feeds it.
    indexing: asyncio.Task[None] | None = None
    closing: list[Any] = []
    from services.search_index.run import configured

    if configured():
        from services.search_index.client import SearchIndexConfig, search_client
        from services.search_index.indexer import SearchIndexer
        from services.search_index.run import run_indexer

        from .review import ExtractionCandidateStore

        search_config = SearchIndexConfig.from_env()
        search = search_client(search_config)
        texts = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
        closing += [search.close, texts.close]
        indexer = SearchIndexer(graph, texts, search, search_config.alias, load_default_ontology())
        indexing = asyncio.create_task(run_indexer(indexer, client, consumer_name(), stop))
        logger.info("worker %s: feeding the search index %s", consumer_name(), search_config.alias)

    logger.info("worker %s: started for %s", consumer_name(), sorted(registered_job_types()))
    try:
        await run_forever(worker, sorted(registered_job_types()), stop=stop)
    finally:
        stop.set()
        if indexing is not None:
            await indexing
        for close in closing:
            await close()
        await alerts.close()
        await judgements.close()
        await datasets.close()
    logger.info("worker %s: stopped", consumer_name())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(main()))
