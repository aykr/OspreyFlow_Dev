"""What became of a matching job, in words a person can read (C249 and L06).

A post-ingest run queues one `resolve_entity_type` job per resolvable type its recipe writes, and
"Resolve now" queues one. The worker records how each ended on the job's own record
(`jobs.JobQueue`: pending, running, done or failed, kept for a day), and until this module **nothing
read it**: the batch expansion's route reads its own jobs and no other, and a run threw the ids
away. A job that failed, or whose worker stopped, left the run looking as it had when it began.

**The words are this module's, never the worker's** (rule 7). A failed job's `error` is the
exception's text, which can name a Gremlin step, a node or a value; it stays on the job's record for
the operator, and is not said to a reader. Nor is any count or node id of the corpus's records said.

**Records a run left out are not said at all, not even as a yes or no** (rule 3). A matching run
reads the whole corpus as the service principal (`resolve.trigger`), not as the reader who asks, so
"some records were left out" is a fact about records the reader may not see, and a yes or no about
them is a one-bit count of the same. A finished job is said finished, left out or not. The run's own
result counts the records it left out and names them (`ResolutionRunResult.left_out`, kept on the
job's record) for an operator.

**No oracle for which ids exist.** An id with no record, a record past its day, and the id of a job
of another kind answer in exactly the same words: a reader cannot find out from this which job ids
the server holds.

**A worker that stopped cannot be told from a long run, so it is not claimed.** Nothing reclaims a
stream entry, so a job whose worker was lost stays `running` on its record until the record expires
(ADR-151 Cost). But a run does not stop when its overlap lock expires: `resolve.trigger` says a run
may outlive `LOCK_TTL_SECONDS` and handles the lock's release failing for that case, and the worker
sets no time limit on a job (the batch expansion has its own, enforced, which is why it can say
abandoned). So a job still running a minute past the lock's life is said **overdue**: longer than a
matching run is expected to take, it may still be working or its worker may have been lost, and the
reader is not told to run it again, which once the lock has expired is not refused and would overlap
a live run. A verdict of "lost" needs a signal that a worker is alive (a heartbeat the worker writes
without racing the job's own record), which is a change to the worker and not made here. A job that
was queued and never taken (no worker at all) is indistinguishable from a long queue, and is still
said to be waiting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from services.resolve.trigger import JOB_TYPE_RESOLVE_ENTITY_TYPE, LOCK_TTL_SECONDS

from .jobs import JobRecord

ResolutionJobState = Literal["queued", "running", "overdue", "done", "not_run", "failed", "gone"]

#: The matching lock's own life, and a minute past it, as ADR-151's limit has a minute past its own.
#: Past this a run is overdue; it is not thereby lost (see the module's docstring).
OVERDUE_AFTER_SECONDS = LOCK_TTL_SECONDS + 60

GONE_WORDS = (
    "There is no record of this matching job. A job's record is kept for a day, so it may have "
    "ended longer ago than that, or the reference may not be one this server issued."
)


class ResolutionJobStatus(BaseModel):
    job_id: str
    state: ResolutionJobState
    words: str


class JobSource(Protocol):
    """What this reads of the job queue: a job's record, or nothing where there is none (an id never
    issued, or one past its day)."""

    async def get_status(self, job_id: str) -> JobRecord | None: ...


def overdue(record: JobRecord, now: datetime) -> bool:
    if record.state != "running" or record.started_at is None:
        return False
    return (now - record.started_at).total_seconds() > OVERDUE_AFTER_SECONDS


def _is_a_resolution_job(record: JobRecord) -> bool:
    return record.job_type == JOB_TYPE_RESOLVE_ENTITY_TYPE


async def resolution_job_status(
    jobs: JobSource, job_id: str, *, now: datetime | None = None
) -> ResolutionJobStatus:
    """The job as a reader is told it. A record that cannot be read as a job is raised, not said to
    be gone: that is a fault of the store, and "no record" would hide it."""
    now = now or datetime.now(UTC)
    record = await jobs.get_status(job_id)
    if record is None or not _is_a_resolution_job(record):
        return ResolutionJobStatus(job_id=job_id, state="gone", words=GONE_WORDS)
    kind = str(record.payload.get("entity_type") or "records")
    matching = f"Matching for {kind}"
    if record.state == "pending":
        return ResolutionJobStatus(
            job_id=job_id, state="queued", words=f"{matching} is waiting for a worker to take it."
        )
    if overdue(record, now):
        stage = f" Its stage: {record.progress}." if record.progress else ""
        return ResolutionJobStatus(
            job_id=job_id,
            state="overdue",
            words=(
                f"{matching} has been running for longer than a matching run is expected to "
                f"take.{stage} It may still be working, or the worker that took it may have been "
                "lost. Do not start it again yet; if it does not finish, tell an administrator, "
                "who can read the worker's log."
            ),
        )
    if record.state == "running":
        stage = f" Its stage: {record.progress}." if record.progress else ""
        return ResolutionJobStatus(
            job_id=job_id, state="running", words=f"{matching} is running.{stage}"
        )
    if record.state == "failed":
        return ResolutionJobStatus(
            job_id=job_id,
            state="failed",
            words=(
                f"{matching} failed, so none of its results were saved. Run it again; if it "
                "fails again, tell an administrator, who can read why in the worker's log."
            ),
        )
    return _done(job_id, matching, record.result or {})


def _done(job_id: str, matching: str, result: dict[str, Any]) -> ResolutionJobStatus:
    if result.get("skipped"):
        return ResolutionJobStatus(
            job_id=job_id,
            state="not_run",
            words=f"{matching} did not run: another matching run for it was already in progress.",
        )
    return ResolutionJobStatus(job_id=job_id, state="done", words=f"{matching} finished.")
