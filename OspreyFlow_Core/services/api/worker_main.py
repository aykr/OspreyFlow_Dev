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
import logging
import os
import signal
import socket
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the import is deferred at runtime — see `main()`'s own comment.
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
    }


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
    from importlib import import_module

    from valkey.asyncio import Valkey

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology

    from .config import ApiConfig
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

    for job_type, dotted in registered_job_types().items():
        module_name, _, attribute = dotted.partition(":")
        worker.register(job_type, getattr(import_module(module_name), attribute))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    logger.info("worker %s: started for %s", consumer_name(), sorted(registered_job_types()))
    await run_forever(worker, sorted(registered_job_types()), stop=stop)
    logger.info("worker %s: stopped", consumer_name())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(main()))
