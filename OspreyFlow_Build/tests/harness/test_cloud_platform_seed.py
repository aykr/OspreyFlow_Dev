"""The POC seed path's render (ADR-148 Amendment 14): one standing Job, `ospreyflow-seed`, a
CronJob held suspended in the Conduit's image, which the install runbook's optional block starts
with the Conduit and the worker scaled to none. It runs `scripts.seed_poc` (spec 08's three
seeds into one case whose first Author is the first administrator), holding the case store's
address and credentials from the platform's secret, the graph's and ClickHouse's passwords by
name, and nothing else of ours; no service account token (it calls nothing of AWS's); and egress
to ArcadeDB, ClickHouse and the managed networks alone. Rendered for the poc shape alone (the
owner, 13 November 2026: a POC seed path)."""

from __future__ import annotations

import re
from typing import Any

from harness.cloud_platform import SEED_JOB

from tests.harness.test_cloud_platform_render import _artefacts, _config, _values


def _seed(values: dict[str, Any]) -> dict[str, Any]:
    assert "seed" in values, "the poc renders no seed Job"
    return values["seed"]


def test_the_poc_renders_the_seed_job_in_the_conduits_image() -> None:
    values = _values(_config("poc"))
    seed = _seed(values)
    api = next(w for w in values["workloads"] if w["name"] == "api")
    assert seed["image"] == api["image"] and seed["resources"] == api["resources"]
    assert seed["name"] == SEED_JOB == "ospreyflow-seed"
    assert seed["command"] == ["/app/.venv/bin/python", "-m", "scripts.seed_poc"]


def test_the_seed_holds_the_stores_it_writes_and_nothing_else_of_ours() -> None:
    seed = _seed(_values(_config("poc")))
    names = [e["name"] for e in seed["env"]]
    ours = sorted(e["secret"] for e in seed["env"] if "secret" in e)
    assert ours == ["ARCADEDB_ROOT_PASSWORD", "CLICKHOUSE_PASSWORD"]
    platform = {e["secretKeyRef"]["name"] for e in seed["env"] if "secretKeyRef" in e}
    assert platform == {
        "rds-postgresql-instance-output"
    }  # the case store's, no other of the platform's
    for needed in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ):
        assert needed in names
    assert not any(n.startswith(("VALKEY", "LITELLM", "OPENSEARCH", "MINIO")) for n in names)
    # The case's unit: the tenant's own (claims.org_unit), not a default of the seed's.
    assert {"name": "OSPREY_ORG_UNIT", "value": "unit-1"} in seed["env"]


def test_the_seed_reaches_the_graph_clickhouse_and_the_case_store_alone() -> None:
    values = _values(_config("poc"))
    [row] = [w for w in values["egress"]["workloads"] if w["name"] == "seed"]
    assert sorted(p["name"] for p in row["toPods"]) == ["arcadedb", "clickhouse"]
    assert row.get("managed") is True
    assert not row.get("hosts"), "the seed calls nothing outside the cluster (no S3, STS or Entra)"


def test_the_seed_is_the_pocs_alone() -> None:
    assert "seed" not in _values(_config("development"))
    assert "seed" not in _values(_config("production"))


def test_the_chart_renders_it_suspended_with_no_token() -> None:
    chart = _artefacts(
        _config("poc")
    )  # the render's own files; the chart's template is checked by Helm
    from harness.render import REPO_ROOT

    template = (REPO_ROOT / "deploy/helm/ospreyflow/templates/seed.yaml").read_text(
        encoding="utf-8"
    )
    assert "suspend: true" in template and "automountServiceAccountToken: false" in template
    assert re.search(r"backoffLimit: 0", template)
    assert "values.yaml" in chart


# -- the install runbook's optional seed block, run as written against a stub kubectl
# ---------------

_KUBECTL = r"""#!/bin/bash
# kubectl for the seed block: each call logged; the pods, the Jobs and their outcomes as $SCENARIO
# says (ok | seed-fails | pods-stay).
echo "$*" >> "$CALLS"
case "$*" in
  *"get deployment/api"*"replicas"*) echo 2 ;;
  *"get deployment/worker"*"replicas"*) echo 1 ;;
  *"wait --for=delete pod"*) [ "$SCENARIO" != pods-stay ] ;;
  *"create job"*) echo created ;;
  *"get pod"*"phase"*) echo Succeeded ;;
  *"wait --for=jsonpath={.status.conditions[0].status}=True"*) true ;;
  *"get job seed-"*"succeeded"*) [ "$SCENARIO" = seed-fails ] || echo 1 ;;
  *"get job search-"*"succeeded"*) echo 1 ;;
  *"logs job/seed-"*) printf 'seed: c1\nseed: done, hmp, fixture-corp, scenarios in case c1\n' ;;
  *logs*) echo "search index rebuilt" ;;
  *) true ;;
esac
"""


def _seed_block(config: str = "poc") -> str | None:
    text = _artefacts(_config(config)).get("INSTALL.md", "")
    if "## 9. Optional: spec 08's acceptance data" not in text:
        return None
    section = text[text.index("## 9. Optional: spec 08's acceptance data") :]
    return re.search(r"^```bash later\n(.*?)^```\n", section, re.S | re.M).group(1)  # type: ignore[union-attr]


def _run_seed(tmp_path, scenario: str) -> tuple[int, str, list[str]]:  # type: ignore[no-untyped-def]
    import subprocess

    block = _seed_block()
    assert block is not None
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kubectl").write_text(_KUBECTL)
    (bin_ / "sleep").write_text("#!/bin/bash\n")
    for tool in ("kubectl", "sleep"):
        (bin_ / tool).chmod(0o755)
    calls = tmp_path / "calls"
    env = {
        "PATH": f"{bin_}:/usr/bin:/bin",
        "CALLS": str(calls),
        "SCENARIO": scenario,
        "NS": "ospreyflow-poc",
    }
    done = subprocess.run(
        ["bash", "-c", "set -e\n" + block], capture_output=True, text=True, timeout=60, env=env
    )
    return done.returncode, done.stdout + done.stderr, calls.read_text().splitlines()


def test_the_seed_block_is_the_pocs_alone_and_not_part_of_the_order() -> None:
    assert _seed_block("poc") is not None
    assert _seed_block("development") is None and _seed_block("production") is None


def test_the_seed_runs_with_the_conduit_and_worker_at_none_then_puts_them_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _run_seed(tmp_path, "ok")
    assert code == 0, said
    order = [c for c in calls if "scale" in c or "create job" in c]
    assert (
        "--replicas=0" in order[0]
        and "deployment/api" in order[0]
        and "deployment/worker" in order[0]
    )
    assert "cronjob/ospreyflow-seed" in order[1]
    assert any("deployment/api" in c and "--replicas=2" in c for c in order[2:])
    assert any("deployment/worker" in c and "--replicas=1" in c for c in order[2:])
    assert "seed: done, hmp, fixture-corp, scenarios" in said  # every line of the seed's, printed
    # The poc searches with OpenSearch: the index rebuilt from the seeded graph, last.
    assert "cronjob/ospreyflow-search-rebuild" in [c for c in calls if "create job" in c][-1]


def test_a_failed_seed_puts_the_conduit_back_then_stops_by_name(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _run_seed(tmp_path, "seed-fails")
    assert code != 0 and "seed-" in said and "failed" in said
    assert any("deployment/api" in c and "--replicas=2" in c for c in calls), (
        "left the Conduit at none"
    )
    assert not any("search-rebuild" in c for c in calls if "create job" in c)


def test_the_seed_is_refused_while_the_conduits_pods_are_still_there(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _run_seed(tmp_path, "pods-stay")
    assert code != 0 and "still running" in said
    assert not any("create job" in c for c in calls), "seeded beside a running Conduit"
    assert any("deployment/api" in c and "--replicas=2" in c for c in calls), (
        "left the Conduit at none"
    )
