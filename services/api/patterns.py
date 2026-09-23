"""`POST /v1/patterns/preview` and `POST /v1/patterns/run` (`03_CONDUIT_MIDDLEWARE.md` §3.3) —
Phase 7 Stage 4's own query-builder surface, `01_DOMAIN_MODEL.md` §8.1 / `06_DECISIONS.md`
ADR-030's binding proof (`08_ACCEPTANCE_SCENARIOS.md` B19: "the intersection set is returned,
with the estimated count shown before running").

**Not investigation-scoped** — the same reasoning `search.py`/`resolution_trigger.py` already give
for `/v1/search` and `/v1/resolution/{entity_type}/run`: a pattern match is a query over the
whole, principal-filtered graph, not a property of any one working set. Seeding a result into an
investigation is a separate, later `/seed` call, already access-checked on its own terms.

**The estimate is principal-filtered — deliberately not `GraphPort.expand_candidate_count`'s
shape.** That method is the unfiltered half of a comparison only one authorised caller
(`WorkingSetService`) ever sees, never itself shown to an analyst. A pattern's own estimate has
no such reconciling caller and is shown directly, so it must be filtered exactly like `match()`
itself — `GraphPort.match_count`'s own docstring has the full reasoning (access control and the
and 7).

**The cap is a job hand-off, not `working_set.models.LimitExceeded`.** That typed error's three
options (`branch`/`filter`/`promote_to_batch`) are working-set mutations; a pattern result, before
`/seed` ever touches it, isn't one. `03_CONDUIT_MIDDLEWARE.md` §3.3 already specifies the answer:
"large results return a job id" — the same shape `submit_supersede_node` uses for "a request that
takes too long to be a reasonable synchronous operation," picked here from a real signal
(`match_count` against the pattern's own `limit`), not a silent `.limit()` presented as complete.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ports.graph import GraphPort
from schemas.domain import PatternQuery, Principal, SavedPattern, Subgraph, TxId

from .jobs import JobQueue

JOB_TYPE_PATTERN_MATCH = "pattern_match"

#: `GraphPort.match_count`'s own docstring: a real, unavoidable cost bound on the estimate's own
#: traversal, ten times `PatternQuery.limit`'s default so an ordinary pattern is never reported as
#: a floor merely for asking a plausible question. Not `PatternQuery.limit` itself — a caller here
#: needs to see how far past that display cap the true count goes, not the query's own display cap.
PREVIEW_COUNT_CEILING = 10_000

#: `run_pattern_match_job`'s own cap once a match has already been proven (by `run_pattern`'s own
#: `match_count` check) to exceed the request's `pattern.limit` — re-running at that same smaller
#: limit would just move rule 2's silent truncation one layer down instead of fixing it. Not
#: "unbounded": a real Gremlin traversal still needs a cost bound even in the background.
PATTERN_MATCH_JOB_CEILING = 100_000


class PatternPreview(BaseModel):
    """`POST /patterns/preview`'s response. `is_floor` is set exactly when `estimated_count`
    equals `PREVIEW_COUNT_CEILING` — the interface's own "10,000+" rather than a bare "10,000",
    the honest difference `02_GLASS_FRONTEND.md` §7's copy rules ("never use a confidence word
    loosely") draws between an exact count and a floor."""

    estimated_count: int
    is_floor: bool


class SavePatternRequest(BaseModel):
    """`POST /v1/patterns/save`'s body — `06_DECISIONS.md` ADR-032/036/040. `pattern_id=None`
    starts a new pattern at version 1; a given `pattern_id` saves the next version of a pattern
    the caller already owns (`PatternStore.save`'s own `PatternNotFoundError` otherwise)."""

    pattern_id: str | None = None
    name: str
    definition: PatternQuery


class SavedPatternList(BaseModel):
    """`GET /v1/patterns`'s response — the latest version of every pattern the caller owns."""

    patterns: list[SavedPattern]


class PatternRunAccepted(BaseModel):
    """What `/patterns/run` returns either way — `mode` tells the caller whether `subgraph` is
    already final or whether to poll `GET /v1/jobs/{job_id}/events`
    (`03_CONDUIT_MIDDLEWARE.md` §3.3), the same shape `SupersedeNodeAccepted`
    (`services/api/supersede.py`) already uses for the same sync/job split."""

    mode: Literal["sync", "job"]
    subgraph: Subgraph | None = None
    matched_count: int | None = None
    job_id: str | None = None


async def preview_pattern(
    pattern: PatternQuery, *, graph: GraphPort, principal: Principal
) -> PatternPreview:
    count = await graph.match_count(pattern, principal, ceiling=PREVIEW_COUNT_CEILING)
    return PatternPreview(estimated_count=count, is_floor=count >= PREVIEW_COUNT_CEILING)


async def run_pattern(
    pattern: PatternQuery, *, graph: GraphPort, principal: Principal, jobs: JobQueue
) -> PatternRunAccepted:
    """Decides sync vs. job from `match_count` against the pattern's own `limit` — the same
    "measure first, only then choose" shape `submit_supersede_node` uses for degree. Never runs
    `match()` and presents its own `.limit(pattern.limit)` truncation as complete: below the
    limit, the count and the eventual `Subgraph` are proven to agree (`GraphPort.match_count`'s
    docstring — they share the identical compiled traversal up to the tail, so nothing was
    truncated because nothing needed to be); at or above it, this hands off to a job rather than
    ever returning a `Subgraph` silently capped at `pattern.limit` (no exceptions to silent
    truncation)."""
    count = await graph.match_count(pattern, principal, ceiling=pattern.limit)
    if count < pattern.limit:
        subgraph = await graph.match(pattern, principal)
        return PatternRunAccepted(
            mode="sync", subgraph=subgraph, matched_count=len(subgraph.nodes)
        )

    job_id = await jobs.submit(
        JOB_TYPE_PATTERN_MATCH,
        {
            "pattern": pattern.model_dump(mode="json"),
            "principal": principal.model_dump(mode="json"),
        },
    )
    return PatternRunAccepted(mode="job", job_id=job_id)


async def run_pattern_match_job(
    payload: dict[str, Any], *, graph: GraphPort, tx: TxId
) -> dict[str, Any]:
    """The background half `services/api/worker.py`'s `JobWorker` calls — separated from
    `run_pattern` the same way `run_supersede_node_job` is separated from `submit_supersede_node`,
    so a worker test drives this directly rather than reconstructing the payload by hand. `tx` is
    unused, present only to satisfy `JobWorker`'s one fixed dispatch shape — the same disclosed
    shape `run_compute_metric_job` already uses for a job that reads rather than writes. Re-runs
    `match()` at `PATTERN_MATCH_JOB_CEILING`, not the original request's own smaller
    `pattern.limit` — the whole reason this became a job is that the true count is known to exceed
    `pattern.limit`, so re-running at the same cap would only move the truncation, not remove it."""
    pattern = PatternQuery.model_validate(payload["pattern"])
    principal = Principal.model_validate(payload["principal"])
    raised = pattern.model_copy(update={"limit": PATTERN_MATCH_JOB_CEILING})
    subgraph = await graph.match(raised, principal)
    return {"subgraph": subgraph.model_dump(mode="json"), "matched_count": len(subgraph.nodes)}


__all__ = [
    "JOB_TYPE_PATTERN_MATCH",
    "PATTERN_MATCH_JOB_CEILING",
    "PREVIEW_COUNT_CEILING",
    "PatternPreview",
    "PatternRunAccepted",
    "SavePatternRequest",
    "SavedPatternList",
    "preview_pattern",
    "run_pattern",
    "run_pattern_match_job",
]
