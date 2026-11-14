"""OpenSearch on the cloud-platform poc shape (v0.5.2, ROUTE_052 step 3a; the owner's ruling of 13 November
2026): the namespace's own OpenSearch domain, two data nodes in two zones, reached inside the VPC on 443 and
answering only requests signed with the namespace's IAM role (IRSA with SigV4), with no fine-grained access
control; no index backup of our own (a restore ends with the rebuild from the graph, ADR-150); the domain
deleted with the namespace's Terraform at decommission.

What a mistake would do, and the case that catches it (rule 12):
- the poc still refused, or rendered with one node, or in one zone, or with fine-grained access control's
  users and master password — `test_the_poc_renders_its_domain_two_nodes_two_zones_iam_alone`;
- a principal other than the namespace's own role admitted by the domain's policy —
  the same case;
- the Conduit or the worker given no address, or no signing, or a pod that does not search given the
  address — `test_the_conduit_and_the_worker_read_the_address_and_sign`;
- a platform whose module fronts the domain with a signing proxy still told to sign —
  `test_a_platform_that_signs_for_us_says_none`;
- the index's rebuild and drift check with no pod to run in, or one without the role —
  `test_the_rebuild_and_the_drift_check_are_standing_job_templates_under_the_role`;
- the runbooks silent on what the client provides, on the index's backup, or on the rebuild after a
  restore — `test_the_runbooks_say_what_the_client_provides_and_what_is_not_backed_up`.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from harness.cloud_platform import opensearch_settings
from harness.cloud_platform.settings import load_platform

from tests.harness.test_cloud_platform_render import _artefacts, _config, _values


def _poc() -> dict[str, str]:
    return _artefacts(_config("poc"))


def _block(text: str, header: str) -> str:
    found = re.search(rf'{re.escape(header)} \{{(.*?)\n\}}', text, re.DOTALL)
    assert found, header
    return found.group(1)


def test_the_poc_renders_its_domain_two_nodes_two_zones_iam_alone() -> None:
    files = _poc()
    assert _config("poc").components.search.value == "opensearch"
    tf = files["terraform/opensearch.tf"]
    domain = _block(tf, 'resource "aws_opensearch_domain" "search"')
    assert re.search(r"instance_count\s*=\s*2\b", domain)
    assert re.search(r"zone_awareness_enabled\s*=\s*true", domain)
    assert re.search(r"availability_zone_count\s*=\s*2\b", domain)
    assert re.search(r"subnet_ids\s*=\s*\[var\.subnet_ids\[0\], var\.subnet_ids\[1\]\]", domain)
    assert re.search(r'tls_security_policy\s*=\s*"Policy-Min-TLS-1-2-2019-07"', domain)
    assert "enforce_https" in domain and "encrypt_at_rest" in domain and "node_to_node_encryption" in domain
    # No fine-grained access control: no internal users, no master user or password.
    assert "advanced_security_options" not in tf and "master_user" not in tf
    policy = _block(tf, 'data "aws_iam_policy_document" "search"')
    assert re.findall(r"identifiers\s*=\s*(\[.*?\])", policy) == ["[aws_iam_role.service.arn]"]
    assert '"es:ESHttp*"' in policy
    # The development shape too: two nodes in every shape.
    assert re.search(r"instance_count\s*=\s*2\b", _artefacts(_config("development"))["terraform/opensearch.tf"])


def _containers(values: dict[str, Any], name: str) -> list[dict[str, Any]]:
    for pod in [*values["workloads"], *values.get("jobs", [])]:
        if pod["name"] == name:
            return [pod, *(pod.get("initContainers") or [])]
    raise AssertionError(name)


def _env(container: dict[str, Any]) -> dict[str, Any]:
    return {e["name"]: e for e in container.get("env", [])}


def test_the_conduit_and_the_worker_read_the_address_and_sign() -> None:
    values = _values(_config("poc"))
    for name in ("api", "worker"):
        url = _env(_containers(values, name)[0])["OPENSEARCH_URL"]
        assert url["secretKeyRef"] == {"name": "opensearch-output", "key": "proxy_url"}, name
    for name in ("workspace", "ner", "litellm", "arcadedb", "clickhouse", "laurium"):
        assert "OPENSEARCH_URL" not in _env(_containers(values, name)[0]), name
    environment = values["environment"]
    assert environment["OPENSEARCH_SIGNING"] == "sigv4"
    assert environment["OPENSEARCH_REGION"] == "eu-west-2"
    # Reached inside the VPC on 443, by the pods that read the stores.
    assert 443 in values["egress"]["managedPorts"]
    managed = {w["name"] for w in values["egress"]["workloads"] if w.get("managed")}
    assert {"api", "worker"} <= managed


def test_a_platform_that_signs_for_us_says_none() -> None:
    """MoJ's module names its secret key `proxy_url`: if the platform's proxy signs, we must not."""
    platform = load_platform("client")
    assert opensearch_settings(_config("poc"), platform)["OPENSEARCH_SIGNING"] == "sigv4"
    proxied = platform.model_copy(update={"opensearch_signing": "none"})
    assert opensearch_settings(_config("poc"), proxied)["OPENSEARCH_SIGNING"] == "none"
    # A deployment that does not search with OpenSearch is given none of it.
    plain = _config("poc", components={"search": "postgres-fulltext"})
    assert opensearch_settings(plain, platform) == {}


def test_the_rebuild_and_the_drift_check_are_standing_job_templates_under_the_role() -> None:
    """ADR-150's two commands (rules' 3c), each a CronJob held suspended: never run on a schedule,
    started by the runbooks with `kubectl create job --from=cronjob/<name>`, in the Conduit's image,
    under the namespace's `ospreyflow` service account (the IRSA role the domain admits)."""
    values = _values(_config("poc"))
    search = values["searchIndex"]
    assert search["serviceAccountName"] == "ospreyflow"
    assert search["image"] == next(w["image"] for w in values["workloads"] if w["name"] == "api")
    assert {j["name"]: j["command"] for j in search["jobs"]} == {
        "ospreyflow-search-rebuild": ["/app/.venv/bin/python", "-m", "scripts.rebuild_search_index"],
        "ospreyflow-search-drift": ["/app/.venv/bin/python", "-m", "scripts.search_index_drift"],
    }
    from harness.render import REPO_ROOT

    chart = (REPO_ROOT / "deploy/helm/ospreyflow/templates/searchindex.yaml").read_text(encoding="utf-8")
    assert "kind: CronJob" in chart and "suspend: true" in chart
    assert "serviceAccountName" in chart and "ospreyflow.container" in chart
    # Not rendered where the deployment does not search with OpenSearch.
    assert "searchIndex" not in _values(_config("poc", components={"search": "postgres-fulltext"}))


def test_the_runbooks_say_what_the_client_provides_and_what_is_not_backed_up() -> None:
    files = _poc()
    needs = files["INSTALL.md"]
    needs = needs[needs.index("**What it needs.**") : needs.index("## 1.")]
    assert "OpenSearch" in needs and "two private subnets" in needs and "two availability zones" in needs
    assert "SigV4" in needs and "fine-grained access control" in needs
    decommission = files["DECOMMISSION.md"]
    assert "OpenSearch domain" in decommission and "not kept" in decommission
    from harness.render import REPO_ROOT

    recovery = (REPO_ROOT / "deploy/RUNBOOK.md").read_text(encoding="utf-8")
    assert "cronjob/ospreyflow-search-rebuild" in recovery and "cronjob/ospreyflow-search-drift" in recovery
    assert "search index rebuilt:" in recovery and "search index drift: none" in recovery
    assert "not backed up" in recovery


def test_the_manifest_lists_the_domain_as_rendered() -> None:
    from harness.cloud_platform import manifest

    listed = manifest.load()
    assert "pending" not in listed["managed"]["opensearch"]
    assert listed["managed"]["opensearch"]["data_nodes"] == 2
    assert listed["managed"]["opensearch"]["signing"] == "sigv4"
    assert yaml.safe_dump(listed).count("v052-opensearch") == 0


# -- the restore's search step, run as written (the reviews of searchkind 6998234) -----------------

_KUBECTL = r'''#!/bin/bash
# A kubectl for the recovery runbook's step 5: each call logged; the Job's pod and outcome as
# $SCENARIO says (starts: never | fails | succeeds).
echo "$*" >> "$CALLS"
case "$*" in
  *"create job"*) echo "job created" ;;
  *"get pod"*"phase"*) case "$SCENARIO" in never) echo Pending ;; fails) echo Failed ;; *) echo Succeeded ;; esac ;;
  *"wait --for=jsonpath={.status.conditions[0].status}=True"*) [ "$SCENARIO" != never ] ;;
  *"get job"*"succeeded"*) [ "$SCENARIO" = succeeds ] && echo 1 || true ;;
  *logs*) echo "the Job's last line" ;;
  *) true ;;
esac
'''


def _search_step(tmp_path, scenario: str) -> tuple[int, str, list[str]]:  # type: ignore[no-untyped-def]
    import subprocess

    from harness.render import REPO_ROOT

    recovery = (REPO_ROOT / "deploy/RUNBOOK.md").read_text(encoding="utf-8")
    step = recovery[recovery.index("# 5. Where the deployment searches with OpenSearch") :]
    step = step[: step.index("```")].replace("<namespace>", "ospreyflow-poc")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kubectl").write_text(_KUBECTL)
    (bin_ / "sleep").write_text("#!/bin/bash\n")  # the poll's waits, not slept in a test
    for tool in ("kubectl", "sleep"):
        (bin_ / tool).chmod(0o755)
    calls = tmp_path / "calls"
    done = subprocess.run(["bash", "-c", "set -e\n" + step], capture_output=True, text=True, timeout=60,
                          env={"PATH": f"{bin_}:/usr/bin:/bin", "CALLS": str(calls), "SCENARIO": scenario})  # fmt: skip
    return done.returncode, done.stdout + done.stderr, calls.read_text().splitlines()


def test_the_restores_search_jobs_are_bounded_in_minutes() -> None:
    from harness.render import REPO_ROOT

    recovery = (REPO_ROOT / "deploy/RUNBOOK.md").read_text(encoding="utf-8")
    step = recovery[recovery.index("# 5. Where the deployment searches with OpenSearch") :]
    step = step[: step.index("```")]
    bounds = re.findall(r"--timeout=\"?\$?\{?(\w+)", step) + re.findall(r":(\d+m)\b", step)
    assert "6h" not in step and "1h" not in step
    assert bounds and all(re.fullmatch(r"\d+m", b) and int(b[:-1]) <= 30 for b in bounds if b[0].isdigit())


def test_a_search_job_that_never_starts_stops_the_restore_by_name(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _search_step(tmp_path, "never")
    assert code != 0
    assert "search-rebuild-" in said and "did not start" in said and "describe pod" in said
    assert not any("search-drift" in c for c in calls), "the drift check started after a rebuild that never ran"


def test_a_search_job_that_fails_stops_the_restore_by_name_at_once(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _search_step(tmp_path, "fails")
    assert code != 0
    assert "search-rebuild-" in said and "failed" in said
    # It ended at once: no wait on a condition that a failed Job never reaches.
    assert not any("condition=complete" in c for c in calls)
    assert not any("search-drift" in c for c in calls)


def test_both_search_jobs_run_when_each_succeeds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _search_step(tmp_path, "succeeds")
    assert code == 0, said
    created = [c for c in calls if "create job" in c]
    assert [("search-rebuild" in c, "search-drift" in c) for c in created] == [(True, False), (False, True)]
    assert said.count("the Job's last line") == 2
