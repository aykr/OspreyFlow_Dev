"""Each workload's own egress, ingress and secrets on the `cloud-platform` profile (ADR-148
Amendment 5 points 21-23, the orchestrator's rulings from case-b's P12 review): the render's rows,
from `profile.yaml`'s `egress` and `secrets`. Helm's own policies, evaluated in Calico's order, are
`tests/cp_policy_check/test_cp_egress_order.py`'s.

What a mistake would do, and the case that catches it (rule 12):
- every pod given every host or the managed stores (the one `all()` Allow this replaces) —
  `test_a_workload_reaches_only_what_its_rows_give_it`;
- a caller left off a path, its calls refused once deployed —
  `test_every_service_a_workload_s_own_environment_names_is_on_its_path`;
- a pod admitting every pod of ours — `test_ingress_is_the_paths_turned_round`;
- the Glass or the recogniser holding the stores' passwords —
  `test_the_glass_and_the_recogniser_hold_no_secret_and_superset_its_own_alone`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from harness.cloud_platform.settings import load_profile
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig


def _values(name: str) -> dict[str, Any]:
    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    rendered = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts
    return yaml.safe_load(rendered["values.yaml"])


@pytest.fixture(scope="module", params=["development", "production", "poc"])
def values(request: pytest.FixtureRequest) -> dict[str, Any]:
    return _values(request.param)


def _rows(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in values["egress"]["workloads"]}


def test_every_rendered_workload_has_its_row(values: dict[str, Any]) -> None:
    others = set(load_profile().egress.others)
    assert others == {"backup", "backup-claims", "restore", "restore-claims"}
    assert set(_rows(values)) == {w["name"] for w in values["workloads"]} | others


def test_a_workload_reaches_only_what_its_rows_give_it(values: dict[str, Any]) -> None:
    rows, egress = _rows(values), load_profile().egress
    hosts = {h["host"] for h in values["egress"]["hosts"]}
    s3 = {h for h in hosts if h.startswith("s3.")}
    sts = {h for h in hosts if h.startswith("sts.")}
    for name, row in rows.items():
        assert row.get("managed", False) == (name in egress.managed), name
        given = set(row.get("hosts", []))
        if name in egress.reach["always"]:
            assert s3 | sts <= given, name
        else:
            # The buckets to the bucket role's pods alone; STS alone to a workload signing in by
            # a role of its own (the gateway, for Bedrock).
            assert not given & s3, name
            assert bool(given & sts) == (name in egress.reach.get("identity", [])), name
        for target in row.get("toPods", []):
            assert target["name"] in egress.paths.get(name, []), (name, target)
    # The Glass and the recogniser reach no store, no host and nothing outside: DNS and the
    # Conduit (the Glass) alone.
    assert rows["ner"].keys() <= {"name", "ports", "fromPods"}
    assert rows["workspace"].get("toPods") == [{"name": "api", "ports": [8000]}]
    assert not rows["workspace"].get("hosts") and not rows["workspace"].get("managed")


def test_a_model_engine_s_host_is_the_gateway_s_alone() -> None:
    rows = _rows(_values("production"))
    assert "api.openai.com" in rows["litellm"]["hosts"]
    assert not [h for h in rows["litellm"]["hosts"] if h.startswith("s3.")]
    assert [n for n, r in rows.items() if "api.openai.com" in r.get("hosts", [])] == ["litellm"]


def test_ingress_is_the_paths_turned_round(values: dict[str, Any]) -> None:
    """A workload admits, in the namespace, exactly the rendered workloads whose paths name it."""
    rows, paths = _rows(values), load_profile().egress.paths
    for name, row in rows.items():
        callers = sorted(n for n in rows if name in paths.get(n, []))
        assert row.get("fromPods", []) == callers, name
    assert rows["worker"].get("fromPods") is None  # nothing calls the workers: they admit none
    assert rows["ner"]["fromPods"] == ["api", "worker"]


def test_every_service_a_workload_s_own_environment_names_is_on_its_path(
    values: dict[str, Any],
) -> None:
    """A workload's own environment (not the shared ConfigMap) names the services it calls; each is
    on its path, so no call it makes is refused once deployed."""
    rows, paths = _rows(values), load_profile().egress.paths
    names = set(rows)
    for workload in values["workloads"]:
        for container in [workload, *workload.get("initContainers", [])]:
            for variable in container.get("env", []):
                value = str(variable.get("value", ""))
                for target in names - {workload["name"]}:
                    if re.search(rf"(^|//|@){re.escape(target)}([:./]|$)", value):
                        assert target in paths.get(workload["name"], []), (workload["name"], value)


def test_the_glass_and_the_recogniser_hold_no_secret_and_superset_its_own_alone(
    values: dict[str, Any],
) -> None:
    workloads = {w["name"]: w for w in values["workloads"]}
    secrets = load_profile().secrets
    for name, workload in workloads.items():
        if not workload.get("envFrom"):
            continue
        named = {e["secret"] for e in workload.get("env", []) if "secret" in e}
        if name in secrets.whole:
            assert not workload.get("noSecret"), name
        else:
            assert workload.get("noSecret"), name
            assert named <= set(secrets.named.get(name, [])), (name, named)
    for name in ("workspace", "ner"):
        assert not [e for e in workloads[name].get("env", []) if "secret" in e], name


# ---- P9's pods, rendered beside the workloads (the orchestrator's rulings from P9 round 2) ----


def test_p9_s_pods_have_rows_by_their_own_names_and_a_restore_reaches_the_api(
    values: dict[str, Any],
) -> None:
    """P9's backup and restore pods render beside the workloads (`values.backups`), so the render
    gives `egress_policy` their names (`egress.others`): each has its row and admits nothing. The
    backup and the restore reach ArcadeDB and ClickHouse, which admit them, and a restore alone the
    cluster's API (`kube-api`); the claims' runs reach none of ours (a claim is a mount). All four
    reach S3 and STS, and nothing reaches KMS: S3 calls it on their behalf (SSE-KMS)."""
    rows = _rows(values)
    hosts = {h["host"] for h in values["egress"]["hosts"]}
    assert not [h for h in hosts if h.startswith("kms.")]
    s3_sts = {h for h in hosts if h.startswith(("s3.", "sts."))}
    stores = {"backup": {"arcadedb", "clickhouse"}, "restore": {"arcadedb", "clickhouse"},
              "backup-claims": set(), "restore-claims": set()}  # fmt: skip
    for name, reached in stores.items():
        assert set(rows[name]["hosts"]) == s3_sts, name
        assert {t["name"] for t in rows[name].get("toPods", [])} == reached, name
        assert "fromPods" not in rows[name] and "ports" not in rows[name], name
        assert not rows[name].get("managed"), name
        assert rows[name].get("toKubeApi", False) == (name == "restore"), name
    for store in ("arcadedb", "clickhouse"):
        callers = set(rows[store]["fromPods"]) & set(stores)
        assert callers == {"backup", "restore"}, store
    assert [n for n, r in rows.items() if r.get("toKubeApi")] == ["restore"]


# ---- the service account's token (Amendment 5 point 24, case-b's P12 part 2) --------------------


@pytest.mark.parametrize("name", ["development", "production", "poc", "production-bedrock"])
def test_only_a_pod_with_an_account_of_its_own_mounts_its_token(name: str) -> None:
    """Every pod and Job says whether its token is mounted (Kubernetes mounts it by default): only
    the IRSA pods and, with Bedrock, the gateway, each by an account of its own; none of the others,
    which call no Kubernetes API."""
    values = _values(name)
    pods = [*values["workloads"], *values["jobs"]]
    for pod in pods:
        assert pod["automountToken"] is bool(pod.get("serviceAccountName")), pod["name"]
    mounted = {p["name"] for p in pods if p["automountToken"]}
    gateway = {"litellm"} if name == "production-bedrock" else set()
    irsa = {"api", "worker", "report-sync"} & {p["name"] for p in pods}  # the poc's has no sync
    assert {"api", "worker"} <= irsa and mounted == irsa | gateway
