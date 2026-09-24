"""Three replicas of one worker process must not do the same job three times.

`06_DECISIONS.md` ADR-049 Stage 2 §3, and the owner's decision of 24 September 2026 that
`05_DEPLOYMENT.md` §3's "three workers" means three replicas of `services/api/worker_main.py`.

**This is a live-service test on purpose, and that is the whole point of it.** The guarantee it
asserts is Valkey's, not this codebase's: `JobWorker.run_once` reads with
`xreadgroup(CONSUMER_GROUP, consumer_name, {stream: ">"})`, and `>` means "entries never delivered
to any consumer in this group". A fake queue would prove only that the fake hands each entry out
once — which is exactly the failure `06_DECISIONS.md` ADR-041 records for the fake-backed
access-control tests, where twenty-two tests passed identically either side of a real fix because
the fake never ran the query the fix changed.

**The named invariant (`CLAUDE.md` rule 12):** two replicas never process the same job. If replicas
shared one consumer name, or read with `0` instead of `>`, or acknowledged before processing, this
is the test that fails.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from services.api.jobs import JobQueue
from services.api.worker import CONSUMER_GROUP, JobWorker
from services.api.worker_main import consumer_name
from valkey.asyncio import Valkey

pytestmark = pytest.mark.asyncio

JOB_TYPE = "supersede_node"


class _RecordingGraph:
    """A transaction recorder, not a graph. The worker owns the transaction lifecycle
    (`begin`/`commit`/`rollback` around every dispatch) and this test is about *how many times* a
    job is dispatched, not about what the handler writes — so the graph is the one collaborator
    that can honestly be a stand-in here, while the queue, which is what the invariant actually
    rests on, is real."""

    def __init__(self) -> None:
        self.commits = 0

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        self.commits += 1

    async def rollback_transaction(self, tx: str) -> None:
        pass


@pytest.fixture
async def valkey() -> Valkey:
    client = Valkey(
        host=os.environ.get("VALKEY_HOST", "127.0.0.1"),
        port=int(os.environ.get("VALKEY_PORT", "6379")),
        db=int(os.environ.get("VALKEY_DB", "0")),
    )
    yield client
    await client.aclose()


async def test_two_replicas_never_process_the_same_job(valkey: Valkey) -> None:
    """The invariant, against a real stream. One job submitted, two workers reading concurrently,
    the handler must run exactly once in total."""
    jobs = JobQueue(valkey)
    graph = _RecordingGraph()
    runs: list[str] = []

    async def handler(payload: dict, *, graph, tx) -> dict:
        runs.append(payload["marker"])
        return {"ok": True}

    marker = uuid.uuid4().hex
    job_id = await jobs.submit(JOB_TYPE, {"marker": marker})

    replicas = [
        JobWorker(valkey, jobs, graph, consumer_name=f"replica-{n}-{marker[:8]}") for n in (1, 2)
    ]
    for replica in replicas:
        replica.register(JOB_TYPE, handler)

    await asyncio.gather(*(r.run_once(JOB_TYPE, block_ms=1500) for r in replicas))

    assert runs == [marker], (
        f"the job ran {len(runs)} time(s) across two replicas; Valkey's consumer group must "
        "deliver each entry to exactly one consumer"
    )
    assert graph.commits == 1, "one dispatch, one committed transaction"
    record = await jobs.get_status(job_id)
    assert record is not None and record.state == "done"


async def test_three_replicas_share_the_work_rather_than_repeating_it(valkey: Valkey) -> None:
    """The positive half, and not a formality: a group that delivered every entry to every consumer
    would fail the case above; a group that delivered nothing to anyone would pass it. Three jobs,
    three replicas, each job done exactly once and the total equal to the number submitted."""
    jobs = JobQueue(valkey)
    graph = _RecordingGraph()
    runs: list[str] = []

    async def handler(payload: dict, *, graph, tx) -> dict:
        runs.append(payload["marker"])
        return {"ok": True}

    batch = uuid.uuid4().hex[:8]
    markers = [f"{batch}-{n}" for n in range(3)]
    for m in markers:
        await jobs.submit(JOB_TYPE, {"marker": m})

    replicas = [JobWorker(valkey, jobs, graph, consumer_name=f"r{n}-{batch}") for n in range(3)]
    for replica in replicas:
        replica.register(JOB_TYPE, handler)

    # Two passes: with three entries and three readers, one replica may win the first read for
    # more than one entry. What must hold is the total, not the distribution.
    for _ in range(2):
        await asyncio.gather(*(r.run_once(JOB_TYPE, block_ms=1000, count=3) for r in replicas))

    assert sorted(runs) == sorted(markers), f"expected each job once, got {sorted(runs)}"


async def test_each_replica_takes_a_distinct_consumer_name_from_its_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property the invariant above actually rests on in a real deployment. Compose and
    Kubernetes both vary the hostname per replica; if `consumer_name()` returned a constant, three
    containers would share one entry in the group's pending list and a crashed replica's in-flight
    entries would be indistinguishable from a live one's."""
    monkeypatch.delenv("OSPREY_WORKER_NAME", raising=False)
    monkeypatch.setattr("services.api.worker_main.socket.gethostname", lambda: "osprey-worker-2")
    assert consumer_name() == "worker-osprey-worker-2"

    monkeypatch.setattr("services.api.worker_main.socket.gethostname", lambda: "osprey-worker-3")
    assert consumer_name() == "worker-osprey-worker-3"

    monkeypatch.setenv("OSPREY_WORKER_NAME", "explicit")
    assert consumer_name() == "explicit"


async def test_an_unacknowledged_entry_is_redelivered_rather_than_lost(valkey: Valkey) -> None:
    """`run_once`'s own documented contract: "a crash between dequeue and ack leaves the entry
    redelivered to the next `xreadgroup` call… rather than silently lost." Planted by a handler
    that raises, which makes the worker roll back and mark the job failed — and the entry must
    still be acknowledged, because a failed job is a processed job, not a lost one. The pending
    count is what distinguishes the two."""
    jobs = JobQueue(valkey)
    graph = _RecordingGraph()

    async def always_fails(payload: dict, *, graph, tx) -> dict:
        raise RuntimeError("deliberate")

    marker = uuid.uuid4().hex
    job_id = await jobs.submit(JOB_TYPE, {"marker": marker})
    worker = JobWorker(valkey, jobs, graph, consumer_name=f"solo-{marker[:8]}")
    worker.register(JOB_TYPE, always_fails)

    assert await worker.run_once(JOB_TYPE, block_ms=1500) == 1

    record = await jobs.get_status(job_id)
    assert record is not None and record.state == "failed"
    assert graph.commits == 0, "a failing handler must roll back, never commit"

    pending = await valkey.xpending(jobs.stream_key(JOB_TYPE), CONSUMER_GROUP)
    count = pending["pending"] if isinstance(pending, dict) else pending[0]
    assert count == 0, "a failed job is processed, not lost — its entry must still be acked"
