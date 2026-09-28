"""The first job-queue worker this system has — `spec/06_DECISIONS.md` ADR-025: a single,
generic dispatcher by `job_type`, not resolution-specific, closing `services/api/supersede.py`'s
own long-disclosed gap in the same stroke — its own module docstring already named the eventual
worker as one of `supersede_node`'s two intended callers, written ahead of it the same way
`GraphPort.find_node` landed ahead of its own first caller in Phase 2.

`JobQueue.submit` (`jobs.py`) already writes each job onto a Valkey Stream
(`jobs:{job_type}`), but nothing before this drains it — no consumer group, no `xreadgroup`,
nothing. A submitted job sat in its stream forever. This module is that consumer: one Valkey
Streams consumer group (`workers`) per `job_type`, `xreadgroup`-ing pending entries and
dispatching each to a registered handler of one fixed shape:

    async def handler(payload: dict[str, Any], *, graph: GraphPort, tx: TxId) -> dict[str, Any]

The worker itself owns the transaction lifecycle — `begin_transaction`/`commit_transaction`/
`rollback_transaction` wrap every dispatched call — so a handler that fails partway through rolls
back cleanly rather than leaving a partially-applied write; no handler manages its own
transaction. `services/api/supersede.py::run_supersede_node_job` already matches this shape
exactly (nothing called it before, so nothing to adapt); `services/resolve/trigger.py::
run_resolve_entity_type_job` is the second, longer-running caller this shape was designed to also
serve (`06_DECISIONS.md` ADR-025's own "both callers fit a single dispatch shape" finding).

**What this does not build, disclosed rather than assumed.** `03_CONDUIT_MIDDLEWARE.md` §3.3
names a real SSE progress stream (`GET /v1/jobs/{id}/events`); `JobRecord` is still written whole
on state change (`pending`/`running`/`done`/`failed`), no incremental log. Neither
`run_supersede_node_job` (one atomic operation) nor `run_resolve_entity_type_job` (long, but with
no caller yet needing to watch it mid-run) needs incremental progress badly enough to justify
building it speculatively — the next caller that genuinely does is the one to add it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply
from ports.graph import GraphPort

from .jobs import JobQueue

logger = logging.getLogger(__name__)

JobHandler = Callable[..., Awaitable[dict[str, Any]]]

#: One consumer group for every `job_type`'s stream — a single logical worker
#: pool, not one group per job type, so a deployment can run N worker
#: processes against the same group and Valkey load-balances entries across
#: them (TinkerPop-unrelated, ordinary Streams semantics).
CONSUMER_GROUP = "workers"


class JobWorker:
    """One process (or one of several sharing `CONSUMER_GROUP`), N registered
    handlers. `run_once` is the directly-testable unit; a real deployment
    calls it in a loop (not built here — a `while True` around `run_once`
    per registered `job_type`, run as this service's own long-lived
    process, is deployment wiring, not additional logic to test)."""

    def __init__(
        self, client: Valkey, jobs: JobQueue, graph: GraphPort, *, consumer_name: str = "worker-1"
    ) -> None:
        self._client = client
        self._jobs = jobs
        self._graph = graph
        self._consumer_name = consumer_name
        self._handlers: dict[str, JobHandler] = {}
        self._groups_ready: set[str] = set()

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def _ensure_group(self, job_type: str) -> None:
        if job_type in self._groups_ready:
            return
        stream_key = self._jobs.stream_key(job_type)
        try:
            await reply(
                self._client.xgroup_create(stream_key, CONSUMER_GROUP, id="0", mkstream=True)
            )
        except Exception as exc:
            # BUSYGROUP: the group already exists — the expected steady
            # state after the first call ever made for this job_type, on
            # this or a prior process. Any other failure is real.
            if "BUSYGROUP" not in str(exc):
                raise
        self._groups_ready.add(job_type)

    async def run_once(self, job_type: str, *, block_ms: int = 1000, count: int = 1) -> int:
        """Reads and processes up to `count` pending entries for `job_type`,
        returns how many it actually processed (0 if none were pending
        within `block_ms`). Each entry is `xack`'d only after its handler's
        transaction has committed or been rolled back and the job record
        updated — a crash between dequeue and ack leaves the entry
        redelivered to the next `xreadgroup` call, per ordinary Streams
        consumer-group semantics, rather than silently lost."""
        handler = self._handlers.get(job_type)
        if handler is None:
            raise KeyError(f"no handler registered for job_type {job_type!r}")
        await self._ensure_group(job_type)
        stream_key = self._jobs.stream_key(job_type)

        response = await reply(
            self._client.xreadgroup(
                CONSUMER_GROUP,
                self._consumer_name,
                {stream_key: ">"},
                count=count,
                block=block_ms,
            )
        )
        if not response:
            return 0

        processed = 0
        for _stream_key, entries in response:
            for entry_id, fields in entries:
                job_id = _decode(fields[b"job_id"] if b"job_id" in fields else fields["job_id"])
                await self._process(job_type, job_id, handler)
                await reply(self._client.xack(stream_key, CONSUMER_GROUP, entry_id))
                processed += 1
        return processed

    async def _process(self, job_type: str, job_id: str, handler: JobHandler) -> None:
        record = await self._jobs.get_status(job_id)
        if record is None:
            logger.warning(
                "worker: no job record for %s (job_type=%s) — skipping", job_id, job_type
            )
            return
        await self._jobs.mark_running(job_id)
        tx = await self._graph.begin_transaction()
        try:
            result = await handler(record.payload, graph=self._graph, tx=tx)
        except Exception as exc:  # noqa: BLE001 - a job's own failure must not crash the worker
            await self._graph.rollback_transaction(tx)
            await self._jobs.mark_failed(job_id, str(exc))
            logger.exception("worker: job %s (job_type=%s) failed", job_id, job_type)
            return
        await self._graph.commit_transaction(tx)
        await self._jobs.mark_done(job_id, result)


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
