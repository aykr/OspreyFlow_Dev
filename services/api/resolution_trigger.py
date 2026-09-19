"""`POST /v1/resolution/{entity_type}/run` — the manual "resolve now" half of `06_DECISIONS.md`
ADR-025's corpus-wide resolution trigger, `services/resolve/trigger.py`.

**Not investigation-scoped**, the same reasoning `search.py`'s own docstring already gives for
`/v1/search`: resolution is corpus-wide and cross-investigation, not a property of any one working
set, so there is no `owning_unit`/`AuthorizedInvestigationDep` check here — any authenticated
principal may ask the corpus-wide trigger to run. `services/api/resolution.py`'s own routes
(threshold, manual link/split, `explain`) are the *investigation-scoped* half of resolution and
correctly stay nested under `/v1/investigations/{id}/...`; this is deliberately a sibling module,
not an addition to that one, matching that file's own "per-investigation working-set concept" test.

**Always submits a job, never runs synchronously.** `submit_supersede_node`'s own sync/job split
picks its branch from a cheap, already-available signal — `neighbourhood_stats`' degree. Nothing
comparably cheap exists for `resolve_entity_type`: learning a type's population size means paging
`list_nodes` to exhaustion, which costs as much as simply running the resolution — there is no
free peek. Given the same absence of a real measurement this module's own trigger docstring already
discloses for sizing the overlap-guard TTL, inventing an arbitrary population threshold here would
have the identical problem. Always job-mode is the honest simplification, not a deferred decision.
"""

from __future__ import annotations

from pydantic import BaseModel
from services.resolve.trigger import JOB_TYPE_RESOLVE_ENTITY_TYPE

from ontology.errors import OntologyError
from schemas.domain import OntologySchema
from schemas.ingest import LoadReport, RowTemplate

from .jobs import JobQueue


class ResolveNowAccepted(BaseModel):
    job_id: str


def _require_resolvable(entity_type_name: str, ontology: OntologySchema) -> None:
    entity_type = ontology.entity_type(entity_type_name)
    if entity_type is None:
        raise OntologyError(f"{entity_type_name!r} is not a type in the active ontology")
    if entity_type.resolution is None:
        raise OntologyError(
            f"{entity_type_name!r} declares no resolution: block — the corpus-wide trigger only "
            "runs against a type the ontology configures for resolution"
        )


async def resolve_now(
    entity_type_name: str, *, ontology: OntologySchema, jobs: JobQueue
) -> ResolveNowAccepted:
    _require_resolvable(entity_type_name, ontology)
    job_id = await jobs.submit(JOB_TYPE_RESOLVE_ENTITY_TYPE, {"entity_type": entity_type_name})
    return ResolveNowAccepted(job_id=job_id)


async def submit_post_ingest_resolution_jobs(
    report: LoadReport,
    row_template: RowTemplate | None,
    *,
    ontology: OntologySchema,
    jobs: JobQueue,
) -> list[str]:
    """`06_DECISIONS.md` ADR-025's post-ingest hook — the real caller
    `resolve_entity_type`/`write_same_as_edges`/`detect_conflicts`/
    `record_conflicts` never had (`07_BUILD_PLAN.md`'s Phase 6 gaps list).
    Called from `POST .../ingest/recipes/{recipe_id}/run` once a load
    actually creates something. Takes the recipe's own `row_template`
    directly, not a whole `Recipe`/`StudioRecipeDraft` — the caller's own
    representation (a published `Recipe` has one shape, a Studio draft
    another) is not this function's concern, only the entity types it
    declares.

    **Scoped to the recipe's own declared entity types, not a fresh read
    of what it created.** `LoadReport.created_node_ids` names individual
    nodes, not their types; re-fetching each one just to learn its `type`
    when the recipe's own `row_template.entities` already declares every
    type it can possibly produce would be a second, redundant read for
    information already available for free. This is a disclosed upper
    bound (a recipe declaring `Person` and `Endpoint` submits a `Person`
    job even on a run that happened to create only `Endpoint`s this time),
    not an exact "what did this specific run touch" — `run_resolution_for_
    entity_type`'s own `list_nodes` pass is what actually does the precise
    work; this only decides which types are worth asking it about."""
    if report.nodes_created == 0 or row_template is None:
        return []
    touched_types = {entity.type for entity in row_template.entities}
    job_ids: list[str] = []
    for entity_type_name in sorted(touched_types):
        entity_type = ontology.entity_type(entity_type_name)
        if entity_type is None or entity_type.resolution is None:
            continue
        job_ids.append(
            await jobs.submit(JOB_TYPE_RESOLVE_ENTITY_TYPE, {"entity_type": entity_type_name})
        )
    return job_ids


__all__ = ["ResolveNowAccepted", "resolve_now", "submit_post_ingest_resolution_jobs"]
