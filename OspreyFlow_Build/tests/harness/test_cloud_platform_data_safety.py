"""The ADR-148 audit's ruling 3, data safety (the owner, 13 November 2026; in v0.5.2):

1. **The shared claim joins the backup set and its restore**: the published pipelines (the recipes
   repository, `data/recipes`), the model settings and the map settings (with the map key file), each
   a part of the set's claims part beside the Ingest root;
2. **RDS's point-in-time restore reaches every set**: `backup_retention_period` is 35 days, AWS's
   maximum (`cloud_platform_backups.POINT_IN_TIME_DAYS`), and the sets expire a day sooner, at 34
   (`EXPIRE_DAYS`; MORNING item 5, (a)), so a set's finish time is always within RDS's window;
3. **The decommission has no default**: the operator chooses `keep` or `destroy` for the backups bucket
   and its KMS key, and the record (the leftover check's output) states which.

What a mistake would do, and the case that catches it (rule 12):
- a restore that brings back the stores but not the pipelines or the settings that make sense of them
  — `test_the_shared_claim_s_three_folders_are_parts_of_the_set`;
- a set older than RDS's window, so the stores and PostgreSQL cannot be brought to one time —
  `test_rds_keeps_point_in_time_a_day_longer_than_the_sets_are_kept`;
- a decommission that keeps (or destroys) the backups because nobody said otherwise —
  `test_step_7_refuses_until_keep_or_destroy_is_chosen` and the two cases after it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from harness.cloud_platform.runbooks import command_blocks
from harness.cloud_platform_backups import BUCKET_SUFFIX, EXPIRE_DAYS, POINT_IN_TIME_DAYS
from tools.cp_policy_check import _resolver

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


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_the_ingest_root_joins_the_set_wherever_it_is_not_a_claim_of_its_own(fixture: str) -> None:
    """MORNING item 6, (a): outside poc the Ingest root (the uploads and the drop folder) is a
    folder of the shared claim, so it is the set's fourth shared part, read-only to the backup and
    put back by restore-claims. Without it a restore brings back loads citing uploads that are not there."""
    values = _values(_config(fixture))
    api = next(w for w in values["workloads"] if w["name"] == "api")
    assert not any(m.get("claim") for m in api["shared"]), "the Ingest root has no claim here"
    assert values["backups"]["shared"] == [
        {"name": "shared-recipes", "subPath": "data/recipes"},
        {"name": "shared-model-settings", "subPath": "model-settings"},
        {"name": "shared-map-settings", "subPath": "map-settings"},
        {"name": "shared-ingest", "subPath": "ingest"},
    ]


def test_the_poc_s_ingest_root_is_its_own_claim_and_not_a_shared_part_too() -> None:
    values = _values(_config("poc"))
    assert {"name": "ingest", "size": values["storage"]["claims"][0]["size"]} in values["storage"][
        "claims"
    ]
    assert "shared-ingest" not in [part["name"] for part in values["backups"]["shared"]]


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_every_pod_writing_the_shared_ingest_folder_is_a_writer(fixture: str) -> None:
    """A restore refuses to run beside a pod that writes the part it puts back: every workload or
    Job mounting the shared `ingest` folder, or a folder inside it (`ingest/uploaded`), by the
    render's own mounts."""
    from harness.cloud_platform_backups import shared_parts, writers

    values = _values(_config(fixture))
    pods = [*values["workloads"], *values.get("jobs", [])]
    def mounts(w: dict[str, Any]) -> list[dict[str, Any]]:
        inits = [m for c in w.get("initContainers", []) for m in c.get("shared") or []]
        return [*(w.get("shared") or []), *inits]

    mounting = {
        str(w["name"])
        for w in pods
        for m in mounts(w)
        if str(m.get("subPath", "")).split("/")[0] == "ingest"
    }
    assert mounting and mounting <= set(values["backups"]["writers"])
    # A pod mounting only a folder inside the part (the uploads) is one too.
    dropper = {"name": "dropper", "shared": [{"subPath": "ingest/uploaded", "mountPath": "/u"}]}
    assert "dropper" in writers([*pods, dropper], {}, parts=shared_parts(pods))


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
def test_rds_keeps_point_in_time_a_day_longer_than_the_sets_are_kept(fixture: str) -> None:
    """MORNING item 5, (a): RDS's earliest restorable point lags its retention by up to a day, and
    S3's expiry rounds up to midnight UTC, so a set kept as long as RDS's window may fall outside it
    in its last day. RDS cannot keep more than 35 days (AWS's maximum), so the sets expire at 34:
    read from the rendered Terraform both ways, never from the constants alone."""
    artefacts = _artefacts(_config(fixture))
    rds = re.search(r"backup_retention_period\s*=\s*(\d+)", artefacts["terraform/rds.tf"])
    sets = re.findall(r"^\s*days\s*=\s*(\d+)\s*$", artefacts["terraform/backups.tf"], re.MULTILINE)
    assert rds and int(rds.group(1)) == POINT_IN_TIME_DAYS == 35
    assert sets == [str(EXPIRE_DAYS)] and EXPIRE_DAYS == 34
    assert int(sets[0]) + 1 <= int(rds.group(1)), "a set's last day outside RDS's window"


def test_the_recovery_runbook_says_the_sets_expire_a_day_inside_the_window() -> None:
    from harness.render import REPO_ROOT

    text = re.sub(r"\s+", " ", (REPO_ROOT / "deploy/RUNBOOK.md").read_text(encoding="utf-8"))
    assert f"lifecycle rule {EXPIRE_DAYS} days after they were written" in text
    assert f"RDS keeps point in time for {POINT_IN_TIME_DAYS} days" in text
    assert "35 days after they were written" not in text and "the total, 35 days" not in text


def test_the_decommission_names_the_sets_own_expiry() -> None:
    text = re.sub(r"\s+", " ", _artefacts(_config("poc"))["DECOMMISSION.md"])
    assert f"own {EXPIRE_DAYS}-day rule" in text and "own 35-day rule" not in text


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


# -- the claims run in every shape, as the chart renders it (docs' review of 6a8, 13 Nov) ------


def _recovery_cloud_section() -> str:
    from harness.render import REPO_ROOT

    text = (REPO_ROOT / "deploy/RUNBOOK.md").read_text(encoding="utf-8")
    section = text[text.index("## The `cloud-platform` profile") :]
    intro = section[: section.index("**The restore below")]
    found = intro + section[section.index("**The schedule.**") :][:900]
    return " ".join(found.split())  # the prose as read, its line breaks aside


def test_the_recovery_runbook_says_the_claims_run_is_every_shapes_and_what_it_holds() -> None:
    """The chart renders `ospreyflow-backup-claims` wherever the set has a claims part
    (backups.yaml's `if $parts`): every shape, holding the shared claim's parts (Amendment 13
    decision 4) and, in the poc shape, the Ingest root's claim beside them. The recovery runbook
    says so, naming each part as
    the render names it (`cloud_platform_backups.SHARED_PARTS`), never 'in the poc shape' alone."""
    from harness.cloud_platform_backups import INGEST_PART, SHARED_PARTS

    section = _recovery_cloud_section()
    schedule = section[section.index("**The schedule.**") :]
    assert "proof-of-concept shape, `ospreyflow-backup-claims`" not in schedule
    assert "in every shape" in schedule
    for part in SHARED_PARTS:
        assert f"`{part['subPath']}`" in section, part["subPath"]
    assert "`ospreyflow-ingest`" in section  # the poc shape's own claim, beside them
    # MORNING item 6, (a): elsewhere the Ingest root is a shared folder, and a part of its own.
    words = re.sub(r"\s+", " ", section)
    assert f"`{INGEST_PART['subPath']}` folder" in words and f"`{INGEST_PART['name']}`" in words


def test_the_manifest_lists_the_claims_jobs_whenever_the_chart_renders_them() -> None:
    """The manifest's builder lists the claims run and its restore on the chart's own condition (a
    claim of the shape's own or the shared parts), not on `storage.claims` alone."""
    from harness.cloud_platform import manifest

    for shape in ("poc", "development"):
        config = _config(shape)
        values = _values(config)
        own = (values.get("storage") or {}).get("claims")
        has_parts = bool(own or values["backups"].get("shared"))
        jobs = manifest.rendered(config, resolver=_resolver)["jobs"]
        assert has_parts and "ospreyflow-backup-claims" in jobs, shape
        assert "ospreyflow-restore-claims-<set>" in jobs, shape


def test_step_8_names_the_step_that_writes_each_listing_it_lacks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Step 8's check needs three listings: the state and the buckets from its own first block, the
    backups choice from step 7's. A missing one is named with the step that writes it, so an
    operator resuming in a new shell goes back to the right block (searchkind's reviews)."""
    import subprocess

    from tests.harness.test_cloud_platform_render import _artefacts, _config

    text = _artefacts(_config("poc"))["DECOMMISSION.md"]
    loop = re.search(r"^for listing in .*?^done\n.*?\n", text, re.DOTALL | re.MULTILINE)
    assert loop, "step 8's listing check"
    (tmp_path / "state.txt").write_text("")
    (tmp_path / "buckets.txt").write_text("")
    run = ["bash", "-c", "set -e\n" + loop.group(0)]
    env = {"PATH": "/usr/bin:/bin", "WORK": str(tmp_path)}
    done = subprocess.run(run, capture_output=True, text=True, env=env, check=False)
    assert done.returncode != 0
    assert f"no {tmp_path}/backups: step 7's platform block writes it" in done.stdout
    (tmp_path / "backups").write_text("keep\n")
    (tmp_path / "state.txt").unlink()
    run = ["bash", "-c", "set -e\n" + loop.group(0)]
    env = {"PATH": "/usr/bin:/bin", "WORK": str(tmp_path)}
    done = subprocess.run(run, capture_output=True, text=True, env=env, check=False)
    said = f"no {tmp_path}/state.txt: step 8's first block (the platform's) writes it"
    assert said in done.stdout
