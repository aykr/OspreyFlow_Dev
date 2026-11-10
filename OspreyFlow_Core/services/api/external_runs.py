"""External orchestration's run API (`06_DECISIONS.md` ADR-141 decisions 9–12 and 14; R11, R14):
the orchestrator orchestrates, OspreyFlow executes.

**Who acts.** A thin client (an Airflow task, the CLI) signs in as a **service identity** through
the deployment's OIDC client-credentials grant (`service_identity.py`). The identity authorises the
trigger and nothing more: it may trigger only a pipeline marked *owned externally* by that very
client (`StudioRecipeDraft.owned_externally_by`; ADR-141 open question 1, taken per pipeline, the
strict option). **The run acts as the pipeline's owner**, the person who marked it, resolved afresh
through token exchange with every refusal a scheduled slot gets (`ScheduleExecutor.
owner_for_external`), and the loader's studio role besides. A refusal is recorded *refused*, in
words, with the trigger `external`, the external run id and the identity.

**Once.** The external run id is the idempotency key (decision 12): the ledger's partial unique
index lets one run that started hold it. The same id again answers that run's status, marked
`already_recorded`, and loads nothing. A refused trigger loaded nothing, so a retry of it is judged
again.

**What the identity reads back** (`status_for`): the run's outcome and, only where the owner may
view every marking the run's rows were written at, its counts and held rows; otherwise *withheld*
(ADR-110 decision 8, rule 3: "one with the grant cannot read anything through the run API it could
not read as the owner"). An owner who cannot be resolved now withholds them too.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply
from ontology.handling import HandlingScheme, principal_may_view
from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft
from schemas.operations import ExternalRunStatus

from .recipe_run import RecipeRunDeps, begin_run, continue_run
from .recipe_runs import Counted, External, ExternalRunRecorded, RecipeRun
from .run_quotas import QuotaRefused
from .scheduler import ScheduleExecutor, ScheduleRunRefused
from .studio_map import resolve_source_handling

log = logging.getLogger(__name__)

#: The recipe's own run lock, the scheduler's (`ScheduleExecutor`): one run of a pipeline at a time.
_LOCK_SECONDS = 6 * 60 * 60
_STILL_GOING = "the previous run of this pipeline is still going"

Spawn = Callable[[Coroutine[Any, Any, None]], object]


FAILED_WORDS = "the run failed; the pipeline's owner can read why on the Studio's Runs tab"


def served_words(outcome: str, words: str | None, owner_id: str) -> str | None:
    """What the service identity is told of a run that did not succeed (rule 7; the lane review of
    L1.7, item 12): a refusal's own words with the owner's account id put as "the pipeline's
    owner", since the ledger writes it into them; a failure only as fixed words, since its text is
    the Conduit's own and may name what the identity may not read."""
    if outcome == "succeeded" or outcome == "running":
        return None
    if outcome == "failed":
        return FAILED_WORDS
    text = words or "no reason was recorded"
    return text.replace(owner_id, "the pipeline's owner") if owner_id else text


def _outcome(run: RecipeRun) -> str:
    if run.outcome in ("running", "succeeded", "failed", "refused"):
        return run.outcome
    return "refused"


async def status_for(
    run: RecipeRun,
    *,
    owner: Principal | None,
    scheme: HandlingScheme,
    already_recorded: bool = False,
) -> ExternalRunStatus:
    """The run as the service identity reads it: counts only where the owner may view every
    marking the run wrote at (`owner` `None`: the owner could not be resolved, so withheld)."""
    may = owner is not None and all(principal_may_view(m, owner, scheme) for m in run.markings)
    graph_writes = run.metering.graph_writes if run.metering is not None else None
    return ExternalRunStatus(
        run_id=run.run_id,
        pipeline_id=run.recipe_id,
        version=run.recipe_version,
        external_run_id=run.external_run_id or "",
        outcome=_outcome(run),  # type: ignore[arg-type]
        started_at=run.started_at,
        finished_at=run.finished_at,
        words=served_words(_outcome(run), run.failure, run.run_as),
        already_recorded=already_recorded,
        rows_read=run.rows_read if may else None,
        rows_rejected=run.rows_rejected if may else None,
        rows_held=run.rows_held if may else None,
        graph_writes=graph_writes if may else None,
        withheld=not may and run.outcome == "succeeded",
    )


async def _refuse(
    deps: RecipeRunDeps,
    recipe: StudioRecipeDraft,
    external: External,
    words: str,
    *,
    owner_id: str,
    case: str,
) -> ExternalRunStatus:
    now = datetime.now(UTC)
    run_id = await deps.recipe_runs.record_not_run(
        recipe_id=recipe.recipe_id,
        recipe_version=recipe.version,
        investigation_id=case,
        trigger="external",
        slot=None,
        run_as=owner_id,
        source=resolve_source_handling(recipe),
        outcome="refused",
        failure=words,
        now=now,
        counts_toward_pause=False,
        counted=Counted(recipe.dataset_id, recipe.owning_unit),
        external=external,
    )
    return ExternalRunStatus(
        run_id=run_id,
        pipeline_id=recipe.recipe_id,
        version=recipe.version,
        external_run_id=external.run_id,
        outcome="refused",
        started_at=now,
        finished_at=now,
        words=served_words("refused", words, owner_id),
    )


async def start_external_run(
    *,
    deps: RecipeRunDeps,
    executor: ScheduleExecutor,
    valkey: Valkey,
    recipe: StudioRecipeDraft,
    external: External,
    spawn: Spawn,
    resolve_owner: Callable[[str], Awaitable[Principal | None]],
) -> ExternalRunStatus:
    """Judges and starts one external run (the route's caller has already matched the identity to
    the pipeline's grant). Answers at once: refused, already recorded, or running; the run itself
    goes on in the background (`spawn`) and is read back by `GET /v1/runs/{run_id}`."""
    held = await deps.recipe_runs.by_external(recipe.recipe_id, external.run_id)
    if held is not None and held.outcome != "refused":
        owner = await resolve_owner(held.run_as)
        return await status_for(
            held, owner=owner, scheme=deps.handling_scheme, already_recorded=True
        )
    owner_id = recipe.schedule_owner or ""
    try:
        owner, case = await executor.owner_for_external(recipe)
    except ScheduleRunRefused as refused:
        return await _refuse(
            deps, recipe, external, str(refused), owner_id=owner_id, case=recipe.schedule_case or ""
        )
    lock = f"schedule:lock:{recipe.recipe_id}"
    token = uuid4().hex
    if not await reply(valkey.set(lock, token, nx=True, ex=_LOCK_SECONDS)):
        return await _refuse(deps, recipe, external, _STILL_GOING, owner_id=owner.id, case=case)
    try:
        run_id, started_at = await begin_run(
            deps,
            principal=owner,
            recipe=recipe,
            investigation_id=case,
            trigger="external",
            external=external,
        )
    except QuotaRefused:
        await _release(valkey, lock, token)
        recorded = await deps.recipe_runs.by_external(recipe.recipe_id, external.run_id)
        if recorded is None:  # pragma: no cover - begin_run records it before raising
            raise
        return await status_for(recorded, owner=owner, scheme=deps.handling_scheme)
    except ExternalRunRecorded as recorded:
        await _release(valkey, lock, token)
        run = await deps.recipe_runs.get(recorded.run_id)
        if run is None:  # pragma: no cover - the index names a row that exists
            raise
        return await status_for(
            run, owner=owner, scheme=deps.handling_scheme, already_recorded=True
        )
    except BaseException:
        await _release(valkey, lock, token)
        raise

    async def _go() -> None:
        try:
            await continue_run(
                deps,
                run_id=run_id,
                started_at=started_at,
                principal=owner,
                recipe=recipe,
                investigation_id=case,
                source_location=None,
                trigger="external",
            )
        except Exception:  # noqa: BLE001 - the ledger has it as failed, in words
            log.exception("external run %s of pipeline %s failed", run_id, recipe.recipe_id)
        finally:
            await _release(valkey, lock, token)

    spawn(_go())
    run = await deps.recipe_runs.get(run_id)
    assert run is not None
    return await status_for(run, owner=owner, scheme=deps.handling_scheme)


async def _release(valkey: Valkey, lock: str, token: str) -> None:
    held = await reply(valkey.get(lock))
    if held in (token, token.encode()):
        await reply(valkey.delete(lock))
