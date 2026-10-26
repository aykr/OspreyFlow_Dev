"""`services/api/resolution_trigger.py` — the manual "resolve now" route's own logic.

Fake `JobQueue` — the thing under test is the validation/submission decision, not `JobQueue`'s own
Valkey mechanics (already proven live in `tests/services/api/test_worker.py`/
`test_valkey_store.py`), the same "fake the decision, not the store" precedent
`test_supersede.py` already established.
"""

from __future__ import annotations

import pytest
from services.api.resolution_trigger import resolve_now, submit_post_ingest_resolution_jobs
from services.resolve.trigger import JOB_TYPE_RESOLVE_ENTITY_TYPE

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from schemas.ingest import LoadReport, RecipeEntity, RowTemplate


class _FakeJobQueue:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, dict[str, object]]] = []

    async def submit(self, job_type: str, payload: dict[str, object]) -> str:
        self.submitted.append((job_type, payload))
        return "job-1"


async def test_resolve_now_submits_a_job_for_a_resolvable_type() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    accepted = await resolve_now("Person", ontology=ontology, jobs=jobs)  # type: ignore[arg-type]

    assert accepted.job_id == "job-1"
    assert jobs.submitted == [(JOB_TYPE_RESOLVE_ENTITY_TYPE, {"entity_type": "Person"})]


async def test_resolve_now_rejects_a_type_with_no_resolution_block() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    with pytest.raises(OntologyError):
        await resolve_now("Endpoint", ontology=ontology, jobs=jobs)  # type: ignore[arg-type]

    assert jobs.submitted == []


async def test_resolve_now_rejects_an_unknown_entity_type() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    with pytest.raises(OntologyError):
        await resolve_now("NotARealType", ontology=ontology, jobs=jobs)  # type: ignore[arg-type]


def _row_template(*types: str) -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(ref=f"e{i}", pole_class="object", type=t) for i, t in enumerate(types)
        ]
    )


def _load_report(nodes_created: int) -> LoadReport:
    return LoadReport(
        load_id="load-1", recipe_id="recipe-1", recipe_version=1, nodes_created=nodes_created
    )


async def test_post_ingest_hook_submits_one_job_per_resolvable_type_the_recipe_declares() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    job_ids = await submit_post_ingest_resolution_jobs(
        _load_report(nodes_created=2),
        _row_template("Person", "Endpoint"),
        ontology=ontology,
        jobs=jobs,  # type: ignore[arg-type]
    )

    # Endpoint declares no `resolution:` block — only Person is submitted.
    assert job_ids == ["job-1"]
    assert jobs.submitted == [(JOB_TYPE_RESOLVE_ENTITY_TYPE, {"entity_type": "Person"})]


async def test_post_ingest_hook_submits_nothing_when_the_load_created_no_nodes() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    job_ids = await submit_post_ingest_resolution_jobs(
        _load_report(nodes_created=0),
        _row_template("Person"),
        ontology=ontology,
        jobs=jobs,  # type: ignore[arg-type]
    )

    assert job_ids == []
    assert jobs.submitted == []


async def test_post_ingest_hook_submits_nothing_for_a_recipe_with_no_row_template() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    job_ids = await submit_post_ingest_resolution_jobs(
        _load_report(nodes_created=2), None, ontology=ontology, jobs=jobs  # type: ignore[arg-type]
    )

    assert job_ids == []
    assert jobs.submitted == []


# --- ADR-127 Amendment 33: automatic resolution can be turned off --------------------------------
# `OSPREY_POST_INGEST_RESOLUTION` (on by default) reaches the hook as `enabled`. Off: nothing is
# enqueued, however many people a load made. An analyst's own "Resolve now" is untouched.


async def test_post_ingest_hook_submits_nothing_when_resolution_is_off() -> None:
    ontology = load_default_ontology()
    jobs = _FakeJobQueue()

    job_ids = await submit_post_ingest_resolution_jobs(
        _load_report(nodes_created=5),
        _row_template("Person", "Endpoint"),
        ontology=ontology,
        jobs=jobs,  # type: ignore[arg-type]
        enabled=False,
    )

    assert job_ids == [] and jobs.submitted == []


async def test_post_ingest_hook_submits_the_same_jobs_as_before_when_resolution_is_on() -> None:
    ontology = load_default_ontology()
    for extra in ({}, {"enabled": True}):
        jobs = _FakeJobQueue()
        job_ids = await submit_post_ingest_resolution_jobs(
            _load_report(nodes_created=2),
            _row_template("Person", "Endpoint"),
            ontology=ontology,
            jobs=jobs,  # type: ignore[arg-type]
            **extra,
        )
        assert job_ids == ["job-1"]
        assert jobs.submitted == [(JOB_TYPE_RESOLVE_ENTITY_TYPE, {"entity_type": "Person"})]


async def test_resolve_now_still_enqueues_whatever_the_setting() -> None:
    jobs = _FakeJobQueue()
    accepted = await resolve_now("Person", ontology=load_default_ontology(), jobs=jobs)  # type: ignore[arg-type]
    assert accepted.job_id == "job-1" and len(jobs.submitted) == 1
