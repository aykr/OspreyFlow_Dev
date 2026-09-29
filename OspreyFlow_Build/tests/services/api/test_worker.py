"""`JobWorker` against a live Valkey (`make dev-up`) — the queue-mechanics half.

The dispatch decision (which handler a `job_type` maps to) and the transaction wrapper's
commit/rollback behaviour are simple enough to prove with a recording fake `GraphPort`,
consistent with `tests/services/api/test_supersede.py`'s own precedent of faking the *decision*
under test, not a security-relevant read path — nothing here exercises access control, so a fake
is the right tool, not a shortcut around the four-instances lesson. The Valkey Streams
consumer-group mechanics themselves (`xgroup_create`,
`xreadgroup`, `xack`) run against the real client, the same discipline `test_valkey_store.py`
already established for `ValkeyWorkingSetStore`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.jobs import JobQueue
from services.api.worker import JobWorker
from valkey.asyncio import Valkey

from schemas.domain import TxId


class _FakeGraph:
    def __init__(self) -> None:
        self.began = 0
        self.committed: list[TxId] = []
        self.rolled_back: list[TxId] = []

    async def begin_transaction(self) -> TxId:
        self.began += 1
        return f"tx-{self.began}"

    async def commit_transaction(self, tx: TxId) -> None:
        self.committed.append(tx)

    async def rollback_transaction(self, tx: TxId) -> None:
        self.rolled_back.append(tx)


@pytest.fixture
async def client() -> Valkey:
    conn = Valkey(host="localhost", port=6379, db=0)
    yield conn
    await conn.aclose()


def _job_type() -> str:
    return f"test-job-{datetime.now(UTC).timestamp()}"


async def test_run_once_dispatches_a_submitted_job_to_its_registered_handler(
    client: Valkey,
) -> None:
    job_type = _job_type()
    jobs = JobQueue(client)
    graph = _FakeGraph()
    worker = JobWorker(client, jobs, graph)  # type: ignore[arg-type]

    seen_payloads: list[dict[str, object]] = []

    async def handler(payload: dict[str, object], *, graph: object, tx: TxId) -> dict[str, object]:
        seen_payloads.append(payload)
        return {"ok": True}

    worker.register(job_type, handler)
    job_id = await jobs.submit(job_type, {"n": 1})

    processed = await worker.run_once(job_type, block_ms=1000)

    assert processed == 1
    assert seen_payloads == [{"n": 1}]
    assert graph.committed == ["tx-1"]
    assert graph.rolled_back == []
    record = await jobs.get_status(job_id)
    assert record is not None
    assert record.state == "done"
    assert record.result == {"ok": True}

    await client.delete(jobs.stream_key(job_type))


async def test_run_once_with_nothing_pending_returns_zero(client: Valkey) -> None:
    job_type = _job_type()
    jobs = JobQueue(client)
    graph = _FakeGraph()
    worker = JobWorker(client, jobs, graph)  # type: ignore[arg-type]

    async def handler(payload: dict[str, object], *, graph: object, tx: TxId) -> dict[str, object]:
        raise AssertionError("must not be called — nothing was submitted")

    worker.register(job_type, handler)

    processed = await worker.run_once(job_type, block_ms=100)

    assert processed == 0
    await client.delete(jobs.stream_key(job_type))


async def test_a_failing_handler_rolls_back_and_marks_the_job_failed(client: Valkey) -> None:
    job_type = _job_type()
    jobs = JobQueue(client)
    graph = _FakeGraph()
    worker = JobWorker(client, jobs, graph)  # type: ignore[arg-type]

    async def handler(payload: dict[str, object], *, graph: object, tx: TxId) -> dict[str, object]:
        raise ValueError("boom")

    worker.register(job_type, handler)
    job_id = await jobs.submit(job_type, {})

    processed = await worker.run_once(job_type, block_ms=1000)

    assert processed == 1
    assert graph.committed == []
    assert graph.rolled_back == ["tx-1"]
    record = await jobs.get_status(job_id)
    assert record is not None
    assert record.state == "failed"
    assert record.error == "boom"

    await client.delete(jobs.stream_key(job_type))


async def test_run_once_raises_for_an_unregistered_job_type(client: Valkey) -> None:
    job_type = _job_type()
    jobs = JobQueue(client)
    graph = _FakeGraph()
    worker = JobWorker(client, jobs, graph)  # type: ignore[arg-type]

    with pytest.raises(KeyError):
        await worker.run_once(job_type, block_ms=100)
