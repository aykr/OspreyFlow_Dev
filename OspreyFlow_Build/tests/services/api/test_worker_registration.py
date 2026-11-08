"""The deployed worker's registration (`worker_main.register_all`, what `worker_main.main` calls):
a resolution job it runs is given the case layers (ADR-025 Amendment 1, ADR-143 Amendment 1), and
the ontology, scheme and Valkey client the job also needs. The orchestrator's request 3 on L3.1:
before this, `main` registered the handler bare, so a standalone worker could not run a resolution
job at all, and nothing tested it.

Red first: with the handlers registered bare, as `main` did, the job is refused for want of its
arguments.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import worker_main
from services.api.jobs import JobQueue
from services.api.worker import JobWorker
from services.resolve import trigger
from services.resolve.trigger import ResolutionRunResult

from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology


async def _layers() -> set[str]:
    return {"layer-of-case-a"}


async def test_the_deployed_worker_runs_a_resolution_job_with_the_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: dict[str, Any] = {}

    async def guarded(entity_type_name: str, **kwargs: Any) -> ResolutionRunResult:
        asked.update(kwargs, entity_type=entity_type_name)
        return ResolutionRunResult(skipped=True, reason="test")

    monkeypatch.setattr(trigger, "try_run_resolution_with_overlap_guard", guarded)
    ontology, scheme, valkey = load_default_ontology(), load_uk_le_scheme(), object()
    worker = JobWorker(valkey, JobQueue(valkey), object(), consumer_name="test")  # type: ignore[arg-type]
    worker_main.register_all(
        worker, ontology=ontology, scheme=scheme, valkey=valkey, analyst_layers=_layers
    )
    handler = worker._handlers["resolve_entity_type"]  # noqa: SLF001
    result = await handler({"entity_type": "Person"}, graph=object(), tx="tx")
    assert result["skipped"] is True
    assert asked["entity_type"] == "Person"
    assert asked["analyst_layers"] is _layers
    assert (asked["ontology"], asked["scheme"], asked["valkey"]) == (ontology, scheme, valkey)
    assert set(worker._handlers) == set(worker_main.registered_job_types())  # noqa: SLF001


async def test_the_registration_check_fails_with_the_bindings_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15: the handlers registered bare, as `main` registered them before this fix, and the
    same call is refused for want of the job's arguments."""

    def bare(handler: Any, **_bound: Any) -> Any:
        return handler

    monkeypatch.setattr(worker_main.functools, "partial", bare)
    valkey = object()
    worker = JobWorker(valkey, JobQueue(valkey), object(), consumer_name="test")  # type: ignore[arg-type]
    worker_main.register_all(
        worker,
        ontology=load_default_ontology(),
        scheme=load_uk_le_scheme(),
        valkey=valkey,
        analyst_layers=_layers,
    )
    with pytest.raises(TypeError, match="analyst_layers"):
        await worker._handlers["resolve_entity_type"](  # noqa: SLF001
            {"entity_type": "Person"}, graph=object(), tx="tx"
        )
