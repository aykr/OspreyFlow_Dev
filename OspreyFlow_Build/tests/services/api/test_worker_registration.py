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
        worker, ontology=ontology, scheme=scheme, valkey=valkey, analyst_layers=_layers, alerts=None
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
        alerts=None,
    )
    with pytest.raises(TypeError, match="analyst_layers"):
        await worker._handlers["resolve_entity_type"](  # noqa: SLF001
            {"entity_type": "Person"}, graph=object(), tx="tx"
        )


async def test_the_deployed_worker_gives_both_jobs_the_alerts_repoint_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-109 Amendment 11 (L2.8c): the standalone worker is where both jobs run in a deployment,
    so the alert store `main` connects is bound to the supersede job (each cloned link recorded)
    and to the resolution job (each split's annotation recorded). Red with `alerts` left out of
    either job's bindings: that job ran with `alerts=None`, recording nothing."""
    from services.api import supersede

    seen: dict[str, Any] = {}

    async def supersede_job(payload: Any, **kwargs: Any) -> dict[str, Any]:
        seen["supersede_node"] = kwargs.get("alerts")
        return {}

    async def guarded(entity_type_name: str, **kwargs: Any) -> ResolutionRunResult:
        seen["resolve_entity_type"] = kwargs.get("alerts")
        return ResolutionRunResult(skipped=True, reason="test")

    monkeypatch.setattr(supersede, "run_supersede_node_job", supersede_job)
    monkeypatch.setattr(trigger, "try_run_resolution_with_overlap_guard", guarded)
    alerts, valkey = object(), object()
    worker = JobWorker(valkey, JobQueue(valkey), object(), consumer_name="test")  # type: ignore[arg-type]
    worker_main.register_all(worker, ontology=load_default_ontology(), scheme=load_uk_le_scheme(),
                             valkey=valkey, analyst_layers=_layers, alerts=alerts)  # fmt: skip
    await worker._handlers["supersede_node"]({}, graph=object(), tx="tx")  # noqa: SLF001
    await worker._handlers["resolve_entity_type"]({"entity_type": "Person"}, graph=object(), tx="tx")  # noqa: SLF001
    assert seen == {"supersede_node": alerts, "resolve_entity_type": alerts}


async def test_a_supersede_job_registered_without_the_alert_store_is_refused_at_its_first_job() -> None:
    """The review's round 2, item 3(c): every registration of the supersede job (the Conduit's in
    `app.py`, the worker's in `worker_main.register_all`) must bind the alerts' journal. `alerts`
    is a required keyword, so one that forgot it is refused at its first job, naming it, rather
    than recording nothing and leaving every alert citing a cloned link withheld. Red with
    `alerts` given a default again: the job ran."""
    from services.api.supersede import run_supersede_node_job

    valkey = object()
    worker = JobWorker(valkey, JobQueue(valkey), object(), consumer_name="test")  # type: ignore[arg-type]
    worker.register("supersede_node", run_supersede_node_job)
    with pytest.raises(TypeError, match="alerts"):
        await worker._handlers["supersede_node"]({"node_id": "n", "replacement": {}}, graph=object(), tx="tx")  # noqa: SLF001
