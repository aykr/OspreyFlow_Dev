"""The ADR-148 audit's ruling 3, data safety (the owner, 13 November 2026; in v0.5.2):

1. **The shared claim joins the backup set and its restore**: the published pipelines (the recipes
   repository, `data/recipes`), the model settings and the map settings (with the map key file), each
   a part of the set's claims part beside the Ingest root;
2. **RDS's point-in-time restore reaches every set**: `backup_retention_period` is the sets' own 35 days
   (`cloud_platform_backups.EXPIRE_DAYS`), so a set's finish time is always within RDS's window;
3. **The decommission has no default**: the operator chooses `keep` or `destroy` for the backups bucket
   and its KMS key, and the record (the leftover check's output) states which.

What a mistake would do, and the case that catches it (rule 12):
- a restore that brings back the stores but not the pipelines or the settings that make sense of them
  — `test_the_shared_claim_s_three_folders_are_parts_of_the_set`;
- a set older than RDS's window, so the stores and PostgreSQL cannot be brought to one time —
  `test_rds_keeps_point_in_time_for_as_long_as_the_sets_are_kept`;
- a decommission that keeps (or destroys) the backups because nobody said otherwise —
  `test_step_7_refuses_until_keep_or_destroy_is_chosen` and the two cases after it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
import pytest
from harness.cloud_platform.runbooks import command_blocks
from harness.cloud_platform_backups import BUCKET_SUFFIX, EXPIRE_DAYS

from tests.harness.test_cloud_platform_render import _artefacts, _config, _values


# ---- 1. the shared claim -----------------------------------------------------------------------


def test_the_shared_claim_s_three_folders_are_parts_of_the_set() -> None:
    backups = _values(_config("poc"))["backups"]
    assert backups["shared"] == [
        {"name": "shared-recipes", "subPath": "data/recipes"},
        {"name": "shared-model-settings", "subPath": "model-settings"},
        {"name": "shared-map-settings", "subPath": "map-settings"},
    ]
    # Every pod that mounts one of them is a writer a restore refuses to run beside.
    assert {"api", "worker"} <= set(backups["writers"])


def test_the_shared_folders_are_the_conduit_s_own_paths() -> None:
    """The parts name the subpaths the Conduit itself mounts: a renamed mount would back up an empty
    folder and restore nothing, silently."""
    values = _values(_config("poc"))
    api = next(w for w in values["workloads"] if w["name"] == "api")
    mounted = {m["subPath"] for m in api["shared"] if "claim" not in m}
    assert {"model-settings", "map-settings", "data"} <= mounted
    recipes = values["environment"].get("OSPREY_RECIPE_REPO_ROOT") or next(
        e["value"] for e in api.get("env", []) if e["name"] == "OSPREY_RECIPE_REPO_ROOT"
    )
    data = next(m["mountPath"] for m in api["shared"] if m["subPath"] == "data")
    assert recipes == f"{data}/recipes"


# ---- 2. RDS's point-in-time window -------------------------------------------------------------


@pytest.mark.parametrize("fixture", ["poc", "development", "production"])
def test_rds_keeps_point_in_time_for_as_long_as_the_sets_are_kept(fixture: str) -> None:
    rds = _artefacts(_config(fixture))["terraform/rds.tf"]
    found = re.search(r"backup_retention_period\s*=\s*(\d+)", rds)
    assert found and int(found.group(1)) == EXPIRE_DAYS == 35


def test_the_recovery_runbook_says_the_window_is_the_sets_own() -> None:
    from harness.render import REPO_ROOT

    text = (REPO_ROOT / "deploy/RUNBOOK.md").read_text(encoding="utf-8")
    assert "35 days" in text and "point in time" in text


# ---- 3. the decommission's choice --------------------------------------------------------------


def _step_7(tmp_path: Path) -> str:
    text = _artefacts(_config("poc"))["DECOMMISSION.md"]
    step = text[text.index("## 7.") : text.index("## 8.")]
    [block] = command_blocks(step, on_the_platform=True)
    return block


def _run_step_7(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    (bin_dir / "aws").write_text(
        "#!/bin/sh\n"
        f'echo "aws $*" >> {calls}\n'
        'case "$*" in\n'
        '  *get-bucket-lifecycle-configuration*) echo \'{"Rules": [{"ID": "retained-sets"}]}\' ;;\n'
        "  *list-object-versions*) echo '{}' ;;\n"
        "  *describe-key*) echo arn:aws:kms:eu-west-2:123456789012:key/k ;;\n"
        "  *get-caller-identity*) echo 123456789012 ;;\n"
        "esac\n"
    )
    (bin_dir / "tofu").write_text(f'#!/bin/sh\necho "tofu $*" >> {calls}\nexit 0\n')
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    done = subprocess.run(
        ["bash", "-c", f"set -e\n{_step_7(tmp_path)}"], capture_output=True, text=True, check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "REGION": "eu-west-2", "WORK": str(work),
             "PREFIX": "ospreyflow-poc-1a2b3c4d-", "FOLDER": str(tmp_path), **env},
    )  # fmt: skip
    return done, calls.read_text().splitlines()


@pytest.mark.parametrize("choice", [None, "", "maybe", "Keep"])
def test_step_7_refuses_until_keep_or_destroy_is_chosen(tmp_path: Path, choice: str | None) -> None:
    env = {} if choice is None else {"BACKUPS": choice}
    done, calls = _run_step_7(tmp_path, BACKUP_RETENTION_DAYS="365", **env)
    assert done.returncode != 0
    assert "keep or destroy" in done.stdout + done.stderr
    assert calls == []  # nothing touched before the choice
    assert not (tmp_path / "work" / "backups").exists()


def test_step_7_keep_sets_the_retention_and_takes_them_out_of_the_state(tmp_path: Path) -> None:
    done, calls = _run_step_7(tmp_path, BACKUPS="keep", BACKUP_RETENTION_DAYS="365")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (tmp_path / "work" / "backups").read_text().strip() == "keep"
    assert any("put-bucket-lifecycle-configuration" in c for c in calls)
    assert any(c.startswith("tofu state rm") for c in calls)
    assert not any("delete-bucket " in c or c.endswith("delete-bucket") for c in calls)
    assert not any("schedule-key-deletion" in c for c in calls)
    # Keep needs its retention.
    done, _ = _run_step_7(tmp_path, BACKUPS="keep")
    assert done.returncode != 0 and "BACKUP_RETENTION_DAYS" in done.stdout + done.stderr


def test_step_7_destroy_empties_and_removes_the_bucket_then_schedules_the_key(tmp_path: Path) -> None:
    done, calls = _run_step_7(tmp_path, BACKUPS="destroy")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (tmp_path / "work" / "backups").read_text().strip() == "destroy"
    order = [c.split()[2] for c in calls if c.startswith("aws ") and len(c.split()) > 2]
    assert order.index("delete-bucket-policy") < order.index("delete-bucket")
    assert order.index("delete-bucket") < order.index("schedule-key-deletion")
    assert any(f"ospreyflow-poc-1a2b3c4d-{BUCKET_SUFFIX}" in c for c in calls if "delete-bucket" in c)
    assert not any("put-bucket-lifecycle-configuration" in c for c in calls)


def test_step_8_s_check_is_told_the_choice() -> None:
    text = _artefacts(_config("poc"))["DECOMMISSION.md"]
    step = text[text.index("## 8.") : text.index("## 9.")]
    assert '--backups "$(cat "$WORK/backups")"' in step
    assert "keep or destroy" in text[text.index("## 7.") : text.index("## 8.")]
