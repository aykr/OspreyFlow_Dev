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


def _rendered(profile: str) -> tuple[bool, str]:
    """A profile rendered for real: whether it runs a job worker of its own (a `worker` service in
    compose, a `worker` workload in the chart's values), and what its environment tells the Conduit."""
    import yaml
    from harness.render import render

    from schemas.deployment import OspreyConfig

    if profile in ("local-lite", "small"):
        network = {"public_origin": "https://osprey.example.org"} if profile == "small" else {}
        artefacts = render(OspreyConfig.model_validate({"profile": profile, **({"network": network} if network else {})}),
                           allow_unpinned=True).artefacts  # fmt: skip
        services = yaml.safe_load(artefacts["compose.yaml"])["services"]
        worker = "worker" in services or any("worker_main" in str(s.get("command", "")) for s in services.values())
        env = dict(line.split("=", 1) for line in artefacts["deployment.env"].splitlines() if "=" in line and not line.startswith("#"))
        return worker, env.get("OSPREY_JOB_WORKER", "")
    if profile == "cluster":
        from tests.harness.test_cluster_render import _resolver, cluster_config

        values = yaml.safe_load(render(cluster_config(), resolver=_resolver).artefacts["values.yaml"])
    else:
        from tools.cp_policy_check import FIXTURES, _resolver

        fixture = FIXTURES / "development.yaml"
        values = yaml.safe_load(render(OspreyConfig.model_validate(yaml.safe_load(fixture.read_text())),
                                       resolver=_resolver).artefacts["values.yaml"])  # fmt: skip
    return "worker" in {w["name"] for w in values["workloads"]}, values["environment"].get("OSPREY_JOB_WORKER", "")


@pytest.mark.parametrize("profile", ["local-lite", "small", "cluster", "cloud-platform"])
def test_each_profile_s_rendered_job_loop_agrees_with_whether_it_renders_a_worker(profile: str) -> None:
    """Both ways (the orchestrator's check, 14 Nov): a profile rendering a worker is told `service`, so
    the Conduit never consumes beside it; one rendering none is told `conduit`, so its jobs run. Small
    renders no worker (05 §3: one host, the Conduit beside its stores)."""
    from harness.render import job_worker_place

    has_worker, told = _rendered(profile)
    expected = "service" if has_worker else "conduit"
    assert told == expected and job_worker_place(profile) == expected
    assert has_worker is (profile in ("cluster", "cloud-platform"))


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
