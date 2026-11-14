"""Where the job loop runs (the orchestrator's fix, 14 November 2026, from rules-b's finding): a profile
whose render has no worker service runs it inside the Conduit (`harness/service_inventory.py`: "Lite runs
the same loop inside the Conduit"); a profile with one never does, so the two never both consume. Every
job type the Conduit enqueues is one the loop (wherever it runs) registers.

Offline: the render's word, the registry and the Conduit's rule. The loop itself, a job enqueued and run
by a lite Conduit, is `test_scheduler_lifespan.py`'s live case.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"


def _submitted_job_types() -> set[str]:
    """Every `JOB_TYPE_*` the Conduit's code passes to `JobQueue.submit`, read from the source."""
    constants: dict[str, str] = {}
    submitted: set[str] = set()
    for path in (CORE / "services").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("JOB_TYPE_"):
                        constants[target.id] = str(node.value.value)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "submit" and node.args and isinstance(node.args[0], ast.Name)
                    and node.args[0].id.startswith("JOB_TYPE_")):  # fmt: skip
                submitted.add(node.args[0].id)
    return {constants[name] for name in submitted}


def test_every_job_type_the_conduit_enqueues_is_one_the_loop_registers() -> None:
    """compute_metric and pattern_match were registered on the Conduit's own worker alone, which never
    ran its loop, and not in the worker image: enqueued on every profile, run on none."""
    from services.api.worker_main import registered_job_types

    submitted = _submitted_job_types()
    assert {"compute_metric", "pattern_match", "resolve_entity_type", "supersede_node"} <= submitted
    assert submitted - set(registered_job_types()) == set()


def test_register_all_registers_exactly_the_registry() -> None:
    from services.api.worker import JobWorker
    from services.api.worker_main import register_all, registered_job_types

    worker = JobWorker(None, None, None)  # type: ignore[arg-type]
    register_all(worker, ontology=None, scheme=None, valkey=None, analyst_layers=None, alerts=None,  # type: ignore[arg-type]
                 judgement_store=None)  # fmt: skip
    assert set(worker._handlers) == set(registered_job_types())


def _rendered_worker(profile: str) -> bool:
    from harness.cloud_platform import DEVELOPMENT_REPLICAS as CLOUD_REPLICAS
    from harness.cluster import REPLICAS as CLUSTER_REPLICAS

    return (profile == "cluster" and "worker" in CLUSTER_REPLICAS) or (
        profile == "cloud-platform" and "worker" in CLOUD_REPLICAS
    )


@pytest.mark.parametrize("profile", ["local-lite", "small", "cluster", "cloud-platform"])
def test_the_render_says_the_conduit_runs_the_jobs_exactly_where_it_renders_no_worker(profile: str) -> None:
    from harness.render import job_worker_place

    assert job_worker_place(profile) == ("service" if _rendered_worker(profile) else "conduit")


def test_lite_s_deployment_env_names_the_conduit_as_the_job_loop() -> None:
    from harness.render import _render_env

    from schemas.deployment import OspreyConfig

    env = _render_env(OspreyConfig.model_validate({"profile": "local-lite"}))
    assert "OSPREY_JOB_WORKER=conduit" in env.splitlines()


@pytest.mark.parametrize(("value", "runs"), [("conduit", True), ("service", False), ("", False), (None, False)],
                         ids=["conduit", "service", "empty", "unset"])  # fmt: skip
def test_the_conduit_runs_the_job_loop_only_where_the_render_says_so(value: str | None, runs: bool) -> None:
    """Unset (a test app, or a deployment rendered before this): no loop, as before, so a worker that
    exists is never joined by a Conduit consuming beside it."""
    from services.api.app import job_loop_in_conduit

    environ = {} if value is None else {"OSPREY_JOB_WORKER": value}
    assert job_loop_in_conduit(environ) is runs


def test_the_service_inventory_s_lite_note_is_what_the_code_does() -> None:
    from harness.service_inventory import INVENTORY

    (worker,) = [e for e in INVENTORY if e.directory == "services/worker"]
    assert "Lite runs the same loop inside the Conduit" in worker.note
