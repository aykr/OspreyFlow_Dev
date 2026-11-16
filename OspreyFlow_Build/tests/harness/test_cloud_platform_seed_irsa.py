"""The POC seed's Job reaches the staging bucket as the Conduit does (ADR-148 Amendment 14; v0.6.0's
package test, INSTALL step 9 on cloud-platform, 16 November 2026): the HMP seed stages its files
through `conduit_common.s3`, whose bucket is `<MINIO_BUCKET_PREFIX>staging` signed by the pod's own
web identity. The seed's Job had no service account (so no IRSA role) and no prefix (so the bucket
was the default `ospreyflow-staging`): HeadBucket was refused, and on cloud-platform the seed could
never succeed. And step 9's block then ran the search index's rebuild after the failed seed, so the
block ended 0.

What a mistake would do, and the case that catches it (rule 12):
- the seed's Job without the IRSA account, its token or the platform's bucket prefix (the bucket
  refused) — `test_the_seed_runs_as_the_conduit_s_account_with_its_bucket_prefix`,
  `test_the_chart_mounts_the_seed_s_token_under_its_account`;
- the seed unable to reach S3 or STS (its web identity exchanged at STS) —
  `test_the_seed_reaches_s3_and_sts`;
- the policy gate refusing the seed under IRSA's account, or admitting it under another or with the
  namespace's default account's token — `test_the_policy_gate_admits_the_seed_as_an_irsa_pod`;
- a failed seed followed by a rebuild that ends 0, so the block reports success, run as a person
  runs it (no `set -e`: the runbook says run each block in one bash shell) —
  `test_a_failed_seed_ends_the_block_failed_without_set_e`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tools.cp_policy_check import _token

from tests.harness.test_cloud_platform_render import _config, _values
from tests.harness.test_cloud_platform_seed import _back, _run_seed

CHART = Path(__file__).resolve().parents[3] / "OspreyFlow_Core" / "deploy" / "helm" / "ospreyflow"


def _api_env(values: dict[str, Any], name: str) -> dict[str, Any]:
    api = next(w for w in values["workloads"] if w["name"] == "api")
    return next(e for e in api["env"] if e["name"] == name)


def test_the_seed_runs_as_the_conduit_s_account_with_its_bucket_prefix() -> None:
    values = _values(_config("poc"))
    seed = values["seed"]
    api = next(w for w in values["workloads"] if w["name"] == "api")
    assert seed.get("serviceAccountName") == api["serviceAccountName"]
    assert seed["serviceAccountName"]  # the platform's `secrets.irsa.service_account`
    prefix = [e for e in seed["env"] if e["name"] == "MINIO_BUCKET_PREFIX"]
    assert prefix == [_api_env(values, "MINIO_BUCKET_PREFIX")], seed["env"]


def test_the_chart_mounts_the_seed_s_token_under_its_account() -> None:
    """The chart's own words (Helm's output is `test_cp_egress_order`'s, where helm runs): the
    seed's pod takes the values' account and mounts its token, never `false` beside it."""
    text = (CHART / "templates" / "seed.yaml").read_text(encoding="utf-8")
    body = text.split("*/ -}}", 1)[1]
    assert "serviceAccountName: {{ $s.serviceAccountName }}" in body
    assert "automountServiceAccountToken: true" in body
    assert "automountServiceAccountToken: false" not in body


def test_the_seed_reaches_s3_and_sts() -> None:
    values = _values(_config("poc"))
    [row] = [w for w in values["egress"]["workloads"] if w["name"] == "seed"]
    [api] = [w for w in values["egress"]["workloads"] if w["name"] == "api"]
    s3 = [h for h in api["hosts"] if h.startswith("s3.")]
    sts = [h for h in api["hosts"] if h.startswith("sts.")]
    assert s3 and sts
    assert sorted(row.get("hosts") or []) == sorted(s3 + sts), row


def _cronjob(
    pod: str, account: str | None, *, token: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A CronJob as the chart renders the seed's: the pod's name in its template's labels."""
    spec: dict[str, Any] = {"automountServiceAccountToken": token, "containers": [{"name": pod}]}
    if account is not None:
        spec["serviceAccountName"] = account
    doc = {
        "kind": "CronJob",
        "metadata": {"name": f"ospreyflow-{pod}"},
        "spec": {"jobTemplate": {"spec": {"template": {
            "metadata": {"labels": {"app.kubernetes.io/name": pod}}, "spec": spec}}}},
    }  # fmt: skip
    return doc, spec


@pytest.mark.parametrize(
    ("account", "token", "said"),
    [
        ("IRSA", True, []),
        (None, True, ["mounts the namespace's default account's token"]),
        ("someone-else", True, ["mounts someone-else's token, not IRSA's"]),
        ("GATEWAY", True, ["runs as GATEWAY, the gateway's account",
                           "mounts GATEWAY's token, not IRSA's"]),
    ],
)  # fmt: skip
def test_the_policy_gate_admits_the_seed_as_an_irsa_pod(
    account: str | None, token: bool, said: list[str]
) -> None:
    values = _values(_config("poc"))
    irsa = next(w for w in values["workloads"] if w["name"] == "api")["serviceAccountName"]
    gateway = "ospreyflow-gateway"
    named = {"IRSA": irsa, "GATEWAY": gateway}.get(account or "", account)
    doc, spec = _cronjob("seed", named, token=token)
    found = [v.detail for v in _token(doc, spec, irsa, gateway)]
    assert found == [s.replace("IRSA", irsa).replace("GATEWAY", gateway) for s in said]


@pytest.mark.parametrize("scenario", ["seed-fails", "never-starts", "overruns", "create-fails"])
def test_a_failed_seed_ends_the_block_failed_without_set_e(tmp_path: Any, scenario: str) -> None:
    """As a person runs it, in a bash shell without `set -e`: the failure is the block's last word
    and its status, the rebuild never started, and everything put back."""
    code, said, calls = _run_seed(tmp_path, scenario, set_e=False)
    assert code != 0, said
    assert not any("search-rebuild" in c for c in calls if "create job" in c), calls
    assert _back(calls)


def test_a_seed_that_succeeds_still_ends_with_the_rebuild_s_status(tmp_path: Any) -> None:
    code, said, calls = _run_seed(tmp_path, "ok", set_e=False)
    assert code == 0, said
    assert "cronjob/ospreyflow-search-rebuild" in [c for c in calls if "create job" in c][-1]
    code, said, _ = _run_seed(tmp_path / "again", "rebuild-fails", set_e=False)
    assert code != 0 and "search-rebuild-" in said and "failed" in said
