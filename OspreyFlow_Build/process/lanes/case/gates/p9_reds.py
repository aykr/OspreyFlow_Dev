"""P9's refusals and promises (ADR-148 Amendment 7), each shown red first (rule 15), by the plant runner of
`process/lanes/platform/gates/p7_round1_reds.py`: each plant undoes one branch **in the file it lives in**, alone,
in the shape the code really had or would have, runs the tests that hold it (every one must fail), and writes
the file back byte for byte (hash-checked). Run from OspreyFlow_Core on the closed offline ports; the chart's
plants need Docker for Helm (the test server):

    stack_lease.sh offline case -- .venv/bin/python ../OspreyFlow_Build/process/lanes/case/gates/p9_reds.py

The kind run's refusals (the bucket's policy, kms:GenerateDataKey, ClickHouse's expired session, a missing
claims part) are the live half: `p9_kind.sh reds`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "p7_round1_reds", HERE.parents[1] / "platform" / "gates" / "p7_round1_reds.py"
)
assert _spec and _spec.loader
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

T = "../OspreyFlow_Build/tests/cloud_platform_backup/"
TP, TC, TR = T + "test_platform_backup.py::", T + "test_platform_backup_claims.py::", T + "test_backups_render.py::"
TS, TH = T + "test_s3_standin.py::", T + "test_backups_chart.py::"
RUN = "OspreyFlow_Core/services/api/platform_backup.py"
RENDER = "OspreyFlow_Core/harness/cloud_platform_backups.py"
CHART = "OspreyFlow_Core/deploy/helm/ospreyflow/templates/backups.yaml"
STANDIN = "OspreyFlow_Build/tests/fixtures/cloud_platform/s3_standin.py"
SLOT_LINE = "    set_id = set_of(settings.job_name)\n"

runner.PLANTS = [
    # ---- ClickHouse, as kind found it ------------------------------------------------------------------------------
    ("ClickHouse handed the role's session in the statement (the shape sent until kind refused it, Code 42)", RUN,
     '    return f"S3({_quoted(url)})"', "    return f\"S3({_quoted(url)}, 'ASIAPLANTED', 'secret', 'session-token')\"",
     [TP + "test_a_backup_writes_a_set_encrypted_by_the_deployments_key_its_manifest_last",
      TP + "test_a_restore_fetches_the_zip_checked_and_restores_clickhouse_from_the_set"]),
    ("ClickHouse's pod not the backup role's", RENDER,
     '    clickhouse["serviceAccountName"] = SERVICE_ACCOUNT\n', "",
     [TR + "test_clickhouse_writes_its_backup_as_the_backup_role_by_its_own_pod"]),
    ("ClickHouse's STS region not given (it asked sts.us-east-1 on kind)", RENDER,
     '        {"name": "AWS_DEFAULT_REGION", "value": region},\n', "",
     [TR + "test_clickhouse_writes_its_backup_as_the_backup_role_by_its_own_pod"]),
    # ---- the role and the bucket ---------------------------------------------------------------------------------
    ("the backup role given delete back", RENDER,
     'OBJECT_ACTIONS = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]',
     'OBJECT_ACTIONS = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]',
     [TR + "test_the_backup_role_can_never_delete_a_set", TS + "test_the_backup_role_is_refused_a_delete"]),
    ("no lifecycle rule expiring the sets", RENDER,
     '                    ("expiration", [("days", str(EXPIRE_DAYS))]),\n', "",
     [TR + "test_the_sets_expire_by_the_buckets_lifecycle_rule"]),
    ("the key and the bucket not kept from a destroy (spec 05 §6.1)", RENDER,
     '                ("lifecycle", [("prevent_destroy", "true")]),\n', "",
     [TR + "test_the_key_and_the_bucket_outlive_a_destroy_of_the_namespace"]),
    # ---- the claims part ------------------------------------------------------------------------------------------
    ("the claims run names its set by the clock, not the slot", RUN, SLOT_LINE, "    set_id = stamp()\n",
     [TC + "test_a_set_with_claims_holds_them_and_is_finished_only_with_them",
      TC + "test_an_overlapping_second_run_never_joins_the_first_runs_set"]),
    ("the claims run joins the newest open set (the design ruled out)", RUN, SLOT_LINE,
     "    set_id = max((s.set_id for s in sets(bucket) if not s.complete), default=set_of(settings.job_name))\n",
     [TC + "test_an_overlapping_second_run_never_joins_the_first_runs_set"]),
    ("a missing claims part let through at the end of the wait", RUN,
     "        if left <= 0:\n            raise BackupRefused(", "        if left <= 0:\n            return {}\n            raise BackupRefused(",
     [TC + "test_a_missing_claims_part_leaves_the_set_unfinished_and_unrestorable",
      TC + "test_main_runs_each_part_and_fails_the_job_on_a_missing_claims_part"]),
    ("a claims part added to a finished set", RUN,
     '    if finished:\n        raise BackupRefused(\n            "claims", f"add to set',
     '    if False:\n        raise BackupRefused(\n            "claims", f"add to set',
     [TC + "test_a_claims_run_never_adds_to_a_finished_set"]),
    ("the file system's lost+found backed up", RUN, "if entry.name != LOST_FOUND:", "if True:",
     [TC + "test_a_set_with_claims_holds_them_and_is_finished_only_with_them"]),
    ("a part unpacked without tarfile's data filter", RUN, 'filter="data"', 'filter="fully_trusted"',
     [TC + "test_a_part_reaching_outside_its_claim_is_refused"]),
    ("files written after the set left in the claim by its restore", RUN,
     "                    shutil.rmtree(entry)\n                else:\n                    entry.unlink()",
     "                    pass\n                else:\n                    pass",
     [TC + "test_a_restore_puts_each_claim_back_as_it_was"]),
    # ---- the stand-in -----------------------------------------------------------------------------------------------
    ("the stand-in ends a session at a policy change (AWS does not)", STANDIN,
     "                    session.policies = role.policies", "                    del self.sessions[key]",
     [TS + "test_a_policy_changed_by_the_lever_judges_the_sessions_already_running"]),
    # ---- the chart (Helm, on the server) ----------------------------------------------------------------------------
    ("the backup pod given the whole Secret (envFrom)", CHART,
     '"env" $env "resources" $b.resources\n                  "claims" (list (dict "name" "arcadedb-backups"',
     '"env" $env "envFrom" true "resources" $b.resources\n                  "claims" (list (dict "name" "arcadedb-backups"',
     [TH + "test_the_cronjob_runs_on_arcadedbs_node_with_its_claim_one_run_at_a_time"]),
    ("the claims mounted writable by the claims run", CHART, "                readOnly: true\n", "",
     [TH + "test_the_claims_run_is_beside_the_shared_pods_on_the_same_schedule_read_only"]),
    ("the claims run placed anywhere, not beside the shared pods", CHART,
     'ospreyflow.io/shared: "true"', 'ospreyflow.io/shared: "false"',
     [TH + "test_the_claims_run_is_beside_the_shared_pods_on_the_same_schedule_read_only"]),
    ("each run's set named by its pod's name (a random suffix), not its Job's", CHART,
     "metadata.labels['batch.kubernetes.io/job-name']", "metadata.name",
     [TH + "test_the_standard_shape_has_no_claims_run"]),
]

if __name__ == "__main__":
    sys.exit(runner.main())
