"""A minimal job queue — `docs/03_CONDUIT_MIDDLEWARE.md` §2: "Queue is
Valkey Streams in `local-lite`... Job state, progress and failure are
first-class: every job is addressable, has a progress stream, and reports
partial results where partial results are meaningful." `GET /v1/jobs/{id}/
events` (§3.3) is the read side this backs; `PatternQuery`'s "large
results return a job id" is the existing pattern this reuses rather than
inventing a second shape (§3.3, §07_BUILD_PLAN.md Phase 3's supersede_node
bullet).

**Deliberately not a `QueuePort`.** `03_CONDUIT_MIDDLEWARE.md` §2 names a
`QueuePort` behind which Valkey Streams and NATS JetStream (`cluster`)
are interchangeable, but that is a fourth-tier-crossing abstraction on the
same footing as `GraphPort`/`AnalyticsPort`/`ComputePort`/`ModelPort` —
ADR-001 names exactly those four as the ports separating the tiers, and a
`QueuePort` is not one of them. This module is Conduit-internal plumbing
for one worker pool's job shape, not a new Vault-crossing boundary, so it
gets a focused test module (`tests/services/api/test_jobs.py`) rather
than a `tests/conformance/` suite — the distinction Phase 3's own scope
note draws for `expand_candidate_count` applies here too.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from conduit_common.valkey_compat import reply as _reply

JobState = Literal["pending", "running", "done", "failed"]

#: `03_CONDUIT_MIDDLEWARE.md` §4's own idle TTL, reused: a job record is
#: no more entitled to live forever unwatched than a working set is.
JOB_TTL_SECONDS = 24 * 60 * 60


class JobRecord(BaseModel):
    id: str
    job_type: str
    state: JobState
    submitted_at: datetime
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _queue_key(job_type: str) -> str:
    return f"jobs:{job_type}"


class JobQueue:
    """One Valkey Stream per `job_type` (`jobs:{job_type}`) carries the
    work items; `job:{id}` is a JSON hash-of-one carrying status, polled
    by `GET /v1/jobs/{id}/events` rather than pushed — this phase does not
    yet have a caller needing the SSE progress stream `03_CONDUIT_MIDDLEWARE
    .md` §3.3 also names, so `JobRecord` is written whole on each state
    change rather than as an incremental progress log."""

    def __init__(self, client: Valkey) -> None:
        self._client = client

    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        job_id = new_id()
        record = JobRecord(
            id=job_id,
            job_type=job_type,
            state="pending",
            submitted_at=datetime.now(UTC),
            payload=payload,
        )
        await self._save(record)
        await _reply(self._client.xadd(_queue_key(job_type), {"job_id": job_id}))
        return job_id

    async def get_status(self, job_id: str) -> JobRecord | None:
        raw = await _reply(self._client.get(_job_key(job_id)))
        if raw is None:
            return None
        return JobRecord.model_validate_json(raw)

    async def mark_running(self, job_id: str) -> None:
        await self._transition(job_id, state="running")

    async def mark_done(self, job_id: str, result: dict[str, Any]) -> None:
        await self._transition(job_id, state="done", result=result)

    async def mark_failed(self, job_id: str, error: str) -> None:
        await self._transition(job_id, state="failed", error=error)

    async def _transition(
        self,
        job_id: str,
        *,
        state: JobState,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        existing = await self.get_status(job_id)
        if existing is None:
            raise KeyError(f"no job record for {job_id!r}")
        updated = existing.model_copy(update={"state": state, "result": result, "error": error})
        await self._save(updated)

    async def _save(self, record: JobRecord) -> None:
        await _reply(
            self._client.set(_job_key(record.id), record.model_dump_json(), ex=JOB_TTL_SECONDS)
        )
