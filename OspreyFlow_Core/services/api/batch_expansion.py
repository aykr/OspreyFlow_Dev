"""Promote the expansion to a batch job (`06_DECISIONS.md` ADR-151): the working-set cap's third
choice, `promote_to_batch`.

The expansion the cap refused is queued whole, run by the job worker under the requester's own
access, and saved as a private view of the case (ADR-144), or refused with its figures. It is
never cut to fit (rule 2). Nothing joins the case's working set or its delta stream.

**Access (rules 3 and 4).** The payload carries the requester's principal as the route scoped it,
as `pattern_match`'s does. At run time the job asks the case store whether they still hold Editor,
re-scopes them to the case's datasets as they are now (`scope_to_case`, as `scope_a_monitor` does
outside a request), and reads the graph through `GraphPort.expand` with that principal, the read the
synchronous route makes. The filter is the adapter's, in the traversal: a node the requester may not
read is never returned, so it is never in the view. Nothing here filters after retrieval, and no
unscoped principal is ever made.

**The limit is a view's.** `open_view` refuses a view past the working-set cap
(ADR-144 Amendment 2 decision 5), so a result past it is refused here with the figures rather than
saved as a view that never opens. The links counted are those among the result that the requester
may see: what opening the view reads (`edges_among`).

**Its words.** A job is its requester's alone: anyone else asking for it is told it does not exist.
A failure is said in this module's words only (`FAILED_WORDS`), never the exception's (rule 7).

What would fail if this were wrong, each with its plant:
`tests/services/api/test_batch_expansion.py`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field
from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from conduit_common.valkey_compat import reply
from ports.graph import GraphPort
from schemas.batch_expansion import BatchExpansion, BatchExpansionInput, BatchRefusal
from schemas.case_views import CaseViewInput
from schemas.domain import ExpandRequest, NodeId, Principal, TxId

from .case_views import CaseViewStore, ViewNotFound
from .dataset_scope import holds_a_level_in, scope_to_case
from .investigations import AccessLevel, InsufficientAccessError, InvestigationNotFoundError
from .jobs import JOB_TTL_SECONDS, JobQueue, JobRecord
from .working_set.models import MAX_EDGES, MAX_NODES

logger = logging.getLogger(__name__)

JOB_TYPE_BATCH_EXPAND = "batch_expand"

#: ADR-151 decision 5: a job running longer is refused, with the stage it reached.
TIME_LIMIT_SECONDS = 600

#: ADR-151 decision 4: the only words a failed job is told in.
FAILED_WORDS = (
    "The batch expansion could not finish, and nothing was saved. Try again, or narrow the "
    "expansion."
)
QUEUED_WORDS = "Waiting for the batch expansion to start."
STARTING_WORDS = "Starting the batch expansion."
RUNNING_WORDS = (
    "A batch expansion of yours is already running in this case, so another was not started. "
    "Follow that one, or wait for it to finish."
)
GONE_WORDS = "The batch expansion finished, but the view it saved has since been deleted."
_NARROW = "Narrow it by link type, depth or dates and try again."


class BatchRunning(Exception):
    """ADR-151 decision 2: the requester already has one queued or running on this case."""

    def __init__(self, job_id: str) -> None:
        super().__init__(RUNNING_WORDS)
        self.job_id = job_id


class BatchNotFound(Exception):
    """No batch expansion by that id on this case that is this reader's own (ADR-041's
    existence rule, as for a private view)."""


class Audit(Protocol):
    async def record(
        self,
        *,
        principal: Principal,
        action: str,
        resolved_query: dict[str, Any],
        result_cardinality: int,
        investigation_id: str | None = None,
        justification: str | None = None,
    ) -> None: ...


class CaseLevels(Protocol):
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Any: ...


class BatchViewInput(CaseViewInput):
    """The view a batch saves (ADR-151 decision 5): `CaseViewInput` with every one of its
    validators, its selection bounded by the view's cap instead of the 10,000 a client may post.
    The selection is the adapter's answer for the requester, not a request body; a check later
    added to `CaseViewInput` applies here too, by inheritance."""

    node_ids: list[NodeId] | None = Field(default=None, max_length=MAX_NODES)


@dataclass(frozen=True)
class BatchExpandBindings:
    """What `run_batch_expand_job` is given besides its payload, bound once by
    `worker_main.register_all` for the worker image and the Conduit alike: the view store it saves
    into, the case store it re-checks the requester's level with (a getter, as `holds_a_level_in`
    takes one), the dataset store it re-scopes with, the job queue it writes its stage to, and the
    audit it records in."""

    views: CaseViewStore
    investigations: Callable[[], CaseLevels]
    datasets: Any
    jobs: JobQueue
    audit: Audit | None

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "views": self.views,
            "investigations": self.investigations,
            "datasets": self.datasets,
            "jobs": self.jobs,
            "audit": self.audit,
        }


def abandoned(record: JobRecord) -> bool:
    """A job still running a minute past its own limit was left by a worker that stopped: nothing
    reclaims a pending stream entry, so it will never finish. It is said as failed, and its claim
    is taken over, so the requester is not held up for the record's 24 hours."""
    if record.state != "running" or record.started_at is None:
        return False
    return (datetime.now(UTC) - record.started_at).total_seconds() > TIME_LIMIT_SECONDS + 60


def _running_key(case_id: str, requester: str) -> str:
    return f"batch_expand:running:{case_id}:{requester}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def default_name(seeds: int, at: datetime) -> str:
    """ADR-151 decision 5: "Expanded from 12 nodes, 14 Nov 2026 14:05"."""
    return f"Expanded from {_plural(seeds, 'node', 'nodes')}, {at.day} {at:%b %Y %H:%M}"


def refusal_words(refusal: BatchRefusal, *, stage: str | None = None) -> str:
    """Each refusal's sentence, with its figures where it has them."""
    if refusal.code == "too_many_nodes":
        return (
            f"The expansion found {refusal.would_be:,} nodes, more than the {refusal.cap:,} a view "
            f"can show, so nothing was saved. {_NARROW}"
        )
    if refusal.code == "too_many_links":
        return (
            f"The expansion found {refusal.would_be:,} links among its nodes, more than the "
            f"{refusal.cap:,} a view can show, so nothing was saved. {_NARROW}"
        )
    if refusal.code == "found_nothing":
        return "The expansion found nothing you may see, so nothing was saved."
    if refusal.code == "no_longer_an_editor":
        return (
            "You can no longer edit this case, so the expansion was not run and nothing was saved."
        )
    reached = f" It had reached: {stage[0].lower()}{stage[1:]}." if stage else ""
    return f"The expansion took longer than ten minutes, so nothing was saved.{reached} {_NARROW}"


# --- submission (the route's half) -------------------------------------------------------------


async def submit(
    jobs: JobQueue,
    valkey: Valkey,
    case_id: str,
    principal: Principal,
    body: BatchExpansionInput,
) -> BatchExpansion:
    """Queues one `batch_expand` job for `principal` on `case_id`, or raises `BatchRunning` naming
    the one they already have. The claim is one Valkey key per requester and case, set only if
    absent; a claim left by a job that has finished is taken over atomically (`SET … GET`), so two
    submissions racing past a finished job do not both start one. Nothing is read from the graph."""
    job_id = new_id()
    key = _running_key(case_id, principal.id)
    while not await reply(valkey.set(key, job_id, nx=True, ex=JOB_TTL_SECONDS)):
        held = await reply(valkey.get(key))
        if held is None:
            continue  # cleared since: try the claim again
        held_id = held.decode() if isinstance(held, bytes) else str(held)
        record = await jobs.get_status(held_id)
        # No record yet is a claim whose job is being queued now: running, as far as anyone asks.
        if record is None or (record.state in ("pending", "running") and not abandoned(record)):
            raise BatchRunning(held_id)
        replaced = await reply(valkey.set(key, job_id, ex=JOB_TTL_SECONDS, get=True))
        replaced_id = replaced.decode() if isinstance(replaced, bytes) else replaced
        if replaced_id not in (None, held_id):
            # Another submission took the claim between the read and the write: it is theirs.
            await reply(valkey.set(key, replaced_id, ex=JOB_TTL_SECONDS))
            raise BatchRunning(str(replaced_id))
        break
    payload = {
        "job_id": job_id,
        "case_id": case_id,
        "principal": principal.model_dump(mode="json"),
        "request": body.request.model_dump(mode="json"),
        "justification": body.justification,
        "name": body.name,
        "submitted_at": datetime.now(UTC).isoformat(),
    }
    await jobs.submit(JOB_TYPE_BATCH_EXPAND, payload, job_id=job_id)
    return BatchExpansion(id=job_id, state="queued", words=QUEUED_WORDS)


# --- reading a job (the status route's half) ---------------------------------------------------


async def read(
    jobs: JobQueue, views: CaseViewStore, case_id: str, job_id: str, reader: Principal
) -> BatchExpansion:
    """The job as its requester is told it. Any job that is not a batch expansion on this case
    made by `reader` is `BatchNotFound`, alike."""
    record = await jobs.get_status(job_id)
    if record is None or not _is_readers(record, case_id, reader):
        raise BatchNotFound(job_id)
    if record.state == "pending":
        return BatchExpansion(id=job_id, state="queued", words=QUEUED_WORDS)
    if abandoned(record):
        return BatchExpansion(id=job_id, state="failed", words=FAILED_WORDS)
    if record.state == "running":
        stage = record.progress or STARTING_WORDS.rstrip(".")
        return BatchExpansion(id=job_id, state="running", words=f"{stage}.")
    if record.state == "failed" or record.result is None:
        return BatchExpansion(id=job_id, state="failed", words=FAILED_WORDS)
    result = record.result
    if result.get("outcome") == "refused":
        refusal = BatchRefusal.model_validate(result["refusal"])
        return BatchExpansion(
            id=job_id, state="refused", words=str(result["words"]), refusal=refusal
        )
    nodes, links = int(result["nodes"]), int(result["links"])
    try:
        view = await views.get(case_id, str(result["view_id"]), reader.id)
    except ViewNotFound:
        return BatchExpansion(id=job_id, state="done", words=GONE_WORDS, nodes=nodes, links=links)
    words = (
        f"Saved {_plural(nodes, 'node', 'nodes')} and {_plural(links, 'link', 'links')} as your "
        f"private view “{view.name}”."
    )
    return BatchExpansion(
        id=job_id, state="done", words=words, view=view.wire(), nodes=nodes, links=links
    )


def _is_readers(record: JobRecord, case_id: str, reader: Principal) -> bool:
    payload = record.payload
    return (
        record.job_type == JOB_TYPE_BATCH_EXPAND
        and payload.get("case_id") == case_id
        and (payload.get("principal") or {}).get("id") == reader.id
    )


# --- the job (the worker's half) ---------------------------------------------------------------


class _Refused(BaseModel):
    refusal: BatchRefusal


async def run_batch_expand_job(
    payload: dict[str, Any],
    *,
    graph: GraphPort,
    tx: TxId,
    views: CaseViewStore,
    investigations: Callable[[], CaseLevels],
    datasets: Any,
    jobs: JobQueue,
    valkey: Valkey,
    audit: Audit | None,
    time_limit: float | None = None,
) -> dict[str, Any]:
    """`JobWorker`'s handler for `batch_expand`. `tx` is unused: the job writes no graph element,
    only a view, as `run_pattern_match_job` reads without writing. Runs in a task of its own, so
    the case scope `scope_to_case` sets lives and dies with this job and never reaches the next
    job the worker takes. Returns the outcome the status route reads: done, or refused with its
    words; an exception is the worker's `failed`, said only in `FAILED_WORDS`."""
    job_id = str(payload["job_id"])
    case_id = str(payload["case_id"])
    principal = Principal.model_validate(payload["principal"])
    stage: list[str] = []

    async def say(words: str) -> None:
        stage[:] = [words]
        await jobs.mark_progress(job_id, words)

    work = asyncio.create_task(
        _expand_and_save(payload, principal, say, graph, views, investigations, datasets, audit)
    )
    try:
        try:
            outcome = await asyncio.wait_for(work, time_limit or TIME_LIMIT_SECONDS)
        except TimeoutError:
            outcome = _Refused(refusal=BatchRefusal(code="took_too_long"))
        if isinstance(outcome, _Refused):
            if audit is not None:
                await audit.record(
                    principal=principal,
                    action="batch_expand_refused",
                    investigation_id=case_id,
                    resolved_query={"job_id": job_id, "code": outcome.refusal.code},
                    result_cardinality=0,
                )
            words = refusal_words(outcome.refusal, stage=stage[0] if stage else None)
            return {
                "outcome": "refused",
                "refusal": outcome.refusal.model_dump(mode="json"),
                "words": words,
            }
        return outcome
    finally:
        await _release(valkey, case_id, principal.id, job_id)


async def _expand_and_save(
    payload: dict[str, Any],
    principal: Principal,
    say: Callable[[str], Awaitable[None]],
    graph: GraphPort,
    views: CaseViewStore,
    investigations: Callable[[], CaseLevels],
    datasets: Any,
    audit: Audit | None,
) -> dict[str, Any] | _Refused:
    case_id = str(payload["case_id"])
    request = ExpandRequest.model_validate(payload["request"])
    try:
        await investigations().get_authorized(case_id, principal, need=AccessLevel.EDITOR)
    except (InvestigationNotFoundError, InsufficientAccessError):
        return _Refused(refusal=BatchRefusal(code="no_longer_an_editor"))
    scoped = await scope_to_case(
        principal, case_id, datasets, holds_a_level=holds_a_level_in(investigations)
    )
    seeds = len(set(request.node_ids))
    await say(f"Expanding from {_plural(seeds, 'node', 'nodes')}")
    found = await graph.expand(request, scoped)
    node_ids = list(dict.fromkeys(n.id for n in found.nodes))
    if not node_ids:
        return _Refused(refusal=BatchRefusal(code="found_nothing"))
    if len(node_ids) > MAX_NODES:
        return _Refused(
            refusal=BatchRefusal(
                code="too_many_nodes", cap_kind="nodes", cap=MAX_NODES, would_be=len(node_ids)
            )
        )
    await say(f"Counting the links among {_plural(len(node_ids), 'node', 'nodes')}")
    links = await graph.edges_among(node_ids, scoped) if len(node_ids) > 1 else []
    if len(links) > MAX_EDGES:
        return _Refused(
            refusal=BatchRefusal(
                code="too_many_links", cap_kind="edges", cap=MAX_EDGES, would_be=len(links)
            )
        )
    await say("Saving the view")
    submitted = datetime.fromisoformat(str(payload["submitted_at"]))
    # Validated as a client's view is, bar the 10,000-id bound on a posted body (`BatchViewInput`).
    lens = BatchViewInput(
        name=payload.get("name") or default_name(seeds, submitted),
        node_ids=node_ids,
        filter=None,
        layout={},
        window=request.temporal_window,
        threshold=None,
    )
    view = await views.save(case_id, lens, principal.id)
    try:
        if audit is not None:
            await audit.record(
                principal=principal,
                action="save_case_view",
                investigation_id=case_id,
                resolved_query={"view_id": view.id, "from_batch": str(payload["job_id"])},
                result_cardinality=len(node_ids),
                justification=payload.get("justification"),
            )
    except BaseException:
        # A view saved and not audited is taken away again, so `FAILED_WORDS`' "nothing was saved"
        # stays true (and a cancellation at the ten minutes does the same).
        await views.delete(case_id, view.id, principal.id)
        raise
    return {"outcome": "done", "view_id": view.id, "nodes": len(node_ids), "links": len(links)}


async def _release(valkey: Valkey, case_id: str, requester: str, job_id: str) -> None:
    """Lets the requester start another: the claim is cleared only if it is still this job's."""
    key = _running_key(case_id, requester)
    try:
        held = await reply(valkey.get(key))
        if held is not None and (held.decode() if isinstance(held, bytes) else held) == job_id:
            await reply(valkey.delete(key))
    except Exception:  # noqa: BLE001 - the claim expires on its own; the outcome stands
        logger.warning("batch expansion %s: its claim was not cleared", job_id)


__all__ = [
    "FAILED_WORDS",
    "JOB_TYPE_BATCH_EXPAND",
    "TIME_LIMIT_SECONDS",
    "BatchExpandBindings",
    "BatchNotFound",
    "BatchRunning",
    "default_name",
    "read",
    "refusal_words",
    "run_batch_expand_job",
    "submit",
]
