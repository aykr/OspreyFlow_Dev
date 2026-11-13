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

import pytest
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
    # The case's unit is not rendered: the first administrator's own, from the people store.
    assert "OSPREY_ORG_UNIT" not in names


def test_the_seed_reaches_the_graph_clickhouse_and_the_case_store_alone() -> None:
    values = _values(_config("poc"))
    [row] = [w for w in values["egress"]["workloads"] if w["name"] == "seed"]
    assert sorted(p["name"] for p in row["toPods"]) == ["arcadedb", "clickhouse"]
    assert row.get("managed") is True
    assert not row.get("hosts"), "the seed calls nothing outside the cluster (no S3, STS or Entra)"


def test_the_seed_is_the_pocs_alone() -> None:
    for shape in ("development", "production"):
        values = _values(_config(shape))
        assert "seed" not in values
        # No row either: no store admits a pod of that name where no seed is rendered.
        assert "seed" not in [w["name"] for w in values["egress"]["workloads"]]


def test_a_restore_refuses_to_run_beside_the_seed() -> None:
    """ADR-148 Amendment 13 point 4: a restore refuses to run beside any pod that writes the stores
    it replaces. The seed writes the graph and ClickHouse, so it is one of the restore's writers."""
    values = _values(_config("poc"))
    assert "seed" in values["backups"]["writers"]


# -- the install runbook's optional seed block, run as written against a stub kubectl
# ---------------

_KUBECTL = r"""#!/bin/bash
# kubectl for the seed block: each call logged; the pods, the Jobs and their outcomes as $SCENARIO
# says (ok | seed-fails | pods-stay | never-starts | overruns | create-fails | at-none |
# rebuild-fails).
echo "$*" >> "$CALLS"
case "$*" in
  *"get deployment/api"*"replicas"*) [ "$SCENARIO" = at-none ] && echo 0 || echo 2 ;;
  *"get deployment/worker"*"replicas"*) echo 1 ;;
  *"wait --for=delete pod"*) [ "$SCENARIO" != pods-stay ] ;;
  *"create job"*"ospreyflow-seed"*) [ "$SCENARIO" != create-fails ] ;;
  *"create job"*) true ;;
  *"get pod"*"seed-"*"phase"*) [ "$SCENARIO" = never-starts ] && echo Pending || echo Succeeded ;;
  *"get pod"*"phase"*) echo Succeeded ;;
  *"wait --for=jsonpath"*"job/seed-"*) [ "$SCENARIO" != overruns ] ;;
  *"wait --for=jsonpath"*) true ;;
  *"get job seed-"*"succeeded"*) [ "$SCENARIO" = seed-fails ] || echo 1 ;;
  *"get job search-"*"succeeded"*) [ "$SCENARIO" = rebuild-fails ] || echo 1 ;;
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
    assert _back(calls), "left the Conduit at none"
    assert not any("search-rebuild" in c for c in calls if "create job" in c)


def _back(calls: list[str]) -> bool:
    """The Conduit and the worker put back at their noted copies, and the backups resumed."""
    api = any("deployment/api" in c and "--replicas=2" in c for c in calls)
    worker = any("deployment/worker" in c and "--replicas=1" in c for c in calls)
    backups = any("ospreyflow-backup" in c and '"suspend":false' in c for c in calls)
    return api and worker and backups


@pytest.mark.parametrize(
    ("scenario", "says"),
    [
        ("never-starts", "did not start"),
        ("overruns", "ran past"),
        ("seed-fails", "failed"),
        ("create-fails", "could not be started"),
    ],
)
def test_a_seed_that_does_not_succeed_is_deleted_before_the_conduit_is_back(
    tmp_path: Any, scenario: str, says: str
) -> None:
    """A Job that did not start, ran past its bound or failed is deleted before the Conduit and
    the worker are put back, so it can never write beside them; then the failure is named."""
    code, said, calls = _run_seed(tmp_path, scenario)
    assert code != 0 and says in said, said
    assert _back(calls), "left the Conduit, the worker or the backups stopped"
    if scenario != "create-fails":
        deleted = next(
            i for i, c in enumerate(calls) if c.startswith("-n ospreyflow-poc delete job seed-")
        )
        put_back = next(
            i for i, c in enumerate(calls) if "deployment/api" in c and "--replicas=2" in c
        )
        assert deleted < put_back
    assert not any("search-rebuild" in c for c in calls if "create job" in c)


def test_the_backups_are_held_for_the_seeds_length(tmp_path: Any) -> None:
    """The daily backup must not catch the seed halfway: suspended before the Conduit stops,
    resumed when it is back."""
    code, said, calls = _run_seed(tmp_path, "ok")
    assert code == 0, said
    held = next(
        i for i, c in enumerate(calls) if "ospreyflow-backup" in c and '"suspend":true' in c
    )
    stopped = next(i for i, c in enumerate(calls) if "--replicas=0" in c)
    assert held < stopped and _back(calls)


def test_a_conduit_already_at_none_is_refused_before_anything_changes(tmp_path: Any) -> None:
    """Copies noted as none (a run cut short before) would be put back as none and called back."""
    code, said, calls = _run_seed(tmp_path, "at-none")
    assert code != 0 and "at none" in said
    assert not any("scale" in c or "create job" in c or "patch" in c for c in calls)


def test_a_failed_rebuild_is_deleted_and_named(tmp_path: Any) -> None:
    code, said, calls = _run_seed(tmp_path, "rebuild-fails")
    assert code != 0 and "search-rebuild-" in said and "failed" in said
    assert any(c.startswith("-n ospreyflow-poc delete job search-rebuild-") for c in calls)


def test_the_seed_is_refused_while_the_conduits_pods_are_still_there(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code, said, calls = _run_seed(tmp_path, "pods-stay")
    assert code != 0 and "still running" in said
    assert not any("create job" in c for c in calls), "seeded beside a running Conduit"
    assert _back(calls), "left the Conduit at none"
