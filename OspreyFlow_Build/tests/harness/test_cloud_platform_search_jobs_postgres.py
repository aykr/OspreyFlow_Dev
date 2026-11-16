"""The search index's Jobs on cloud-platform reach the managed database (ADR-150 decision 4; the
package test's stop, 15 November 2026).

Both Jobs read Postgres: the rebuild and the drift check build their stores with
`services.search_index.resources.feed_resources`, which connects the extraction candidates' store
by `services.api.config.PostgresConfig.from_env()`. That defaults to the developer stack's
`localhost:5433`, so a Job given no database settings fails on a real cluster, as v0.6.0's package
test found: INSTALL's step 5 rolled every workload out and then its rebuild Job stopped with
"Connect call failed ('127.0.0.1', 5433)". Every earlier test passed, because each checked what the
Jobs may read (the policy gate) or ran step 5 against a kubectl that answers the Job as succeeded,
and none ran the Job's own settings through the code that reads them (rule 12).

So this renders the poc's values (the shape that renders the Jobs), templates them with the chart
as Helm does, gives each container the environment Kubernetes would (the ConfigMaps it reads whole,
then its own variables in order, a secret's key by a stand-in value, `$(VAR)` expanded from what is
already set), and asks the rebuild's own configuration path, in a process given that environment
alone, where it would connect. The Conduit is resolved the same way first, as the control: it
reaches the managed database today, so a failure for a Job is the Job's settings, not this
resolution. Helm runs as its pinned image, so this needs Docker, as `test_helm_chart.py` does.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

import pytest
import yaml
from tools.cp_policy_check import FIXTURES, helm_template, render_values

#: The managed database's settings, as the platform's RDS secret would hold them (stand-ins), by the
#: variable the Conduit reads each into: the secret's own key names are the platform's
#: (`platforms/<name>.yaml`), so each is found from the Conduit's own reference to it.
MANAGED = {
    "POSTGRES_HOST": "ospreyflow-poc.cluster-standin.eu-west-2.rds.amazonaws.com",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "standin_user",
    "POSTGRES_PASSWORD": "standin-password",
    "POSTGRES_DB": "standin_db",
}
SEARCH_JOBS = ("ospreyflow-search-rebuild", "ospreyflow-search-drift")
_REFERENCE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)")


@pytest.fixture(scope="module")
def manifests() -> list[dict[str, Any]]:
    values, _registry = render_values(FIXTURES / "poc.yaml")
    assert "searchIndex" in yaml.safe_load(values), "the poc renders no search Jobs"
    return helm_template(values)


def _container(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    doc = next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)
    spec = doc["spec"]
    if kind == "CronJob":
        spec = spec["jobTemplate"]["spec"]["template"]["spec"]
    else:
        spec = spec["template"]["spec"]
    return dict(spec["containers"][0])


def _managed(api: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """The platform's database secret (the one the Conduit's POSTGRES_HOST names) and the stand-in
    value of each of its keys the Conduit reads."""
    refs = {
        v["name"]: v["valueFrom"]["secretKeyRef"]
        for v in api["env"]
        if "secretKeyRef" in (v.get("valueFrom") or {})
    }
    secret = str(refs["POSTGRES_HOST"]["name"])
    return secret, {str(refs[name]["key"]): value for name, value in MANAGED.items()}


def _environment(
    docs: list[dict[str, Any]], container: dict[str, Any], managed: tuple[str, dict[str, str]]
) -> dict[str, str]:
    """The container's environment as Kubernetes gives it: `envFrom` first (a ConfigMap's data; a
    whole Secret's keys cannot be known here and are refused by the policy gate), then `env` in
    order, each value's `$(VAR)` expanded from what is set before it."""
    maps = {d["metadata"]["name"]: d.get("data") or {} for d in docs if d["kind"] == "ConfigMap"}
    env: dict[str, str] = {}
    for source in container.get("envFrom") or []:
        if "configMapRef" in source:
            env.update({k: str(v) for k, v in maps[source["configMapRef"]["name"]].items()})
    for variable in container.get("env") or []:
        if "value" in variable:
            value = str(variable["value"])
            env[variable["name"]] = _REFERENCE.sub(lambda m: env.get(m[1], m[0]), value)
            continue
        ref = (variable.get("valueFrom") or {}).get("secretKeyRef")
        if ref:
            secret, keys = managed
            held = keys.get(ref["key"]) if ref["name"] == secret else None
            env[variable["name"]] = held or f"standin-{ref['name']}-{ref['key']}"
    return env


#: The rebuild's own configuration path, run in a process given the container's environment alone:
#: nothing of this test runner's own (a developer's POSTGRES_* or a CI runner's) can stand in for
#: what the pod would be given. It reads where it would connect and never connects.
_WHERE = """
import json
from services.api.config import PostgresConfig
c = PostgresConfig.from_env()
print(json.dumps({"host": c.host, "port": c.port, "user": c.user, "password": c.password,
                  "database": c.database, "sslmode": c.sslmode}))
"""


def _where(env: dict[str, str]) -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-c", _WHERE],
        env={**env, "PATH": os.environ.get("PATH", ""), "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return dict(json.loads(done.stdout))


def _expected(config: dict[str, Any]) -> None:
    managed = (MANAGED["POSTGRES_HOST"], int(MANAGED["POSTGRES_PORT"]))
    assert (config["host"], config["port"]) == managed, (
        f"connects to {config['host']}:{config['port']}, not the managed database"
    )
    assert (config["user"], config["password"], config["database"]) == (
        MANAGED["POSTGRES_USER"], MANAGED["POSTGRES_PASSWORD"], MANAGED["POSTGRES_DB"],
    )  # fmt: skip
    assert config["sslmode"] == "require"


def test_the_conduit_reaches_the_managed_database(manifests: list[dict[str, Any]]) -> None:
    """The control: the resolution above gives the Conduit the managed database."""
    api = _container(manifests, "Deployment", "api")
    _expected(_where(_environment(manifests, api, _managed(api))))


@pytest.mark.parametrize("job", SEARCH_JOBS)
def test_each_search_job_reaches_the_managed_database(
    manifests: list[dict[str, Any]], job: str
) -> None:
    managed = _managed(_container(manifests, "Deployment", "api"))
    container = _container(manifests, "CronJob", job)
    _expected(_where(_environment(manifests, container, managed)))


@pytest.mark.parametrize("job", SEARCH_JOBS)
def test_each_search_job_is_given_the_database_as_the_conduit_is(
    manifests: list[dict[str, Any]], job: str
) -> None:
    """The same variables from the same secret's keys as the Conduit, and nothing else of the
    platform's database secret: the Jobs read that database as the Conduit does."""
    api = _container(manifests, "Deployment", "api")
    secret, _keys = _managed(api)

    def database(container: dict[str, Any]) -> dict[str, tuple[str, str]]:
        return {
            v["name"]: (ref["name"], ref["key"])
            for v in container.get("env") or []
            if (ref := (v.get("valueFrom") or {}).get("secretKeyRef") or {})
            and ref.get("name") == secret
            and v["name"].startswith(("POSTGRES_", "OSPREY_POSTGRES_"))
        }

    assert database(_container(manifests, "CronJob", job)) == database(api)
