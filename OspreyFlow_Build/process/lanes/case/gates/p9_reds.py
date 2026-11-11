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
     '    clickhouse["serviceAccountName"] = CLICKHOUSE_SERVICE_ACCOUNT\n', "",
     [TR + "test_clickhouse_writes_its_backup_as_the_backup_role_by_its_own_pod"]),
    ("ClickHouse's STS region not given (it asked sts.us-east-1 on kind)", RENDER,
     '        {"name": "AWS_DEFAULT_REGION", "value": region},\n', "",
     [TR + "test_clickhouse_writes_its_backup_as_the_backup_role_by_its_own_pod"]),
    # ---- the role and the bucket ---------------------------------------------------------------------------------
    ("a second delete in the role (a set's data)", RENDER,
     'CLICKHOUSE_LOCK = "sets/*/clickhouse/.lock"',
     'CLICKHOUSE_LOCK = "sets/*/clickhouse/.lock"\nOBJECT_ACTIONS = [*OBJECT_ACTIONS, "s3:DeleteObject"]',
     [TR + "test_the_backup_roles_only_delete_is_clickhouses_own_lock_file",
      TS + "test_each_backup_role_is_refused_every_delete_but_clickhouses_lock"]),
    ("the lock's delete on a wider pattern", RENDER,
     'CLICKHOUSE_LOCK = "sets/*/clickhouse/.lock"', 'CLICKHOUSE_LOCK = "sets/*"',
     [TR + "test_the_backup_roles_only_delete_is_clickhouses_own_lock_file",
      TS + "test_each_backup_role_is_refused_every_delete_but_clickhouses_lock"]),
    ("DeleteObjectVersion beside the lock's delete", RENDER,
     '[{"Effect": "Allow", "Action": ["s3:DeleteObject"],\n              "Resource": [f"{bucket_arn}/{CLICKHOUSE_LOCK}"]}],',
     '[{"Effect": "Allow", "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],\n              "Resource": [f"{bucket_arn}/{CLICKHOUSE_LOCK}"]}],',
     [TR + "test_the_backup_roles_only_delete_is_clickhouses_own_lock_file"]),
    ("the lock's delete taken away (ClickHouse's BACKUP then fails at its end, as on kind)", RENDER,
     '[{"Effect": "Allow", "Action": ["s3:DeleteObject"],\n              "Resource": [f"{bucket_arn}/{CLICKHOUSE_LOCK}"]}],',
     '[{"Effect": "Allow", "Action": ["s3:GetObject"],\n              "Resource": [f"{bucket_arn}/{CLICKHOUSE_LOCK}"]}],',
     [TP + "test_a_backup_writes_a_set_encrypted_by_the_deployments_key_its_manifest_last",
      TS + "test_clickhouses_role_may_remove_its_lock_and_nothing_else"]),
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
    ("the file system's lost+found backed up", RUN, "        if top.name == LOST_FOUND:\n            continue\n", "",
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
    # ---- round 2: who may reach the sets, the bucket's and key's policies, the trust --------------------------
    ("the deployment's ClickHouse user keeps the S3 and URL sources and BACKUP", RENDER,
     "        <query>REVOKE S3, URL, BACKUP ON *.*</query>\n", "",
     [TR + "test_clickhouses_own_user_is_refused_the_buckets_and_the_backup_user_holds_them"]),
    ("ClickHouse's role reaches the whole set, not its own prefix", RENDER,
     'CLICKHOUSE_OBJECTS = ("sets/*/clickhouse/*",)', 'CLICKHOUSE_OBJECTS = ("sets/*",)',
     [TR + "test_each_role_reaches_its_own_prefix_alone", TS + "test_each_role_is_refused_the_other_roles_prefix"]),
    ("the key used by any service, not through S3 alone", RENDER,
     '    return {"StringEquals": {"kms:ViaService": f"s3.{region}.amazonaws.com"}}',
     '    return {"StringEquals": {"kms:ViaService": [f"s3.{region}.amazonaws.com", "ec2.amazonaws.com"]}}',
     [TR + "test_each_role_reaches_its_own_prefix_alone",
      TR + "test_the_keys_own_policy_lets_the_account_administer_the_roles_use_and_nobody_delete"]),
    ("the key's deletion allowed", RENDER, '"Sid": "NeverScheduledForDeletion", "Effect": "Deny"',
     '"Sid": "NeverScheduledForDeletion", "Effect": "Allow"',
     [TR + "test_the_keys_own_policy_lets_the_account_administer_the_roles_use_and_nobody_delete"]),
    ("the bucket not versioned", RENDER, '("versioning_configuration", [("status", _q("Enabled"))]),',
     '("versioning_configuration", [("status", _q("Suspended"))]),',
     [TR + "test_the_bucket_is_versioned_so_an_overwrite_erases_nothing"]),
    ("TLSOnly no longer a deny", RENDER, '"Sid": "TLSOnly", "Effect": "Deny"', '"Sid": "TLSOnly", "Effect": "Allow"',
     [TS + "test_plain_http_is_refused_by_the_bucket_policy"]),
    ("KMSOnly no longer a deny", RENDER, '"Sid": "KMSOnly", "Effect": "Deny"', '"Sid": "KMSOnly", "Effect": "Allow"',
     [TS + "test_another_encryption_or_another_key_is_refused_by_the_bucket_policy"]),
    ("ItsOwnKey no longer a deny", RENDER, '"Sid": "ItsOwnKey", "Effect": "Deny"', '"Sid": "ItsOwnKey", "Effect": "Allow"',
     [TS + "test_another_key_the_role_may_use_is_refused_by_the_bucket_policy_alone"]),
    ("NoKeyNamed no longer a deny", RENDER, '"Sid": "NoKeyNamed", "Effect": "Deny"', '"Sid": "NoKeyNamed", "Effect": "Allow"',
     [TS + "test_aws_kms_named_without_a_key_is_refused_by_the_bucket_policy"]),
    ("BackupRolesOnly no longer a deny", RENDER, '"Sid": "BackupRolesOnly", "Effect": "Deny"',
     '"Sid": "BackupRolesOnly", "Effect": "Allow"', [TS + "test_the_conduits_role_is_refused_the_backups_bucket"]),
    ("the trust without its :sub", RENDER,
     '{"StringEquals": {f"{issuer}:sub": subject,\n                                            f"{issuer}:aud": "sts.amazonaws.com"}}',
     '{"StringEquals": {f"{issuer}:aud": "sts.amazonaws.com"}}',
     [TS + "test_a_token_for_another_service_account_is_refused_by_sts"]),
    ("the trust without its :aud", RENDER,
     '{"StringEquals": {f"{issuer}:sub": subject,\n                                            f"{issuer}:aud": "sts.amazonaws.com"}}',
     '{"StringEquals": {f"{issuer}:sub": subject}}',
     [TS + "test_a_token_for_another_audience_is_refused_by_sts"]),
    # ---- the stand-in's own checks --------------------------------------------------------------------------------
    ("the stand-in takes any signature", STANDIN, "        if not hmac.compare_digest(expected, signature):",
     "        if False:", [TS + "test_a_wrong_secret_is_refused_by_its_signature"]),
    ("the stand-in takes plain HTTP as TLS", STANDIN, '"aws:SecureTransport": "true" if self.secure else "false"',
     '"aws:SecureTransport": "true"', [TS + "test_plain_http_is_refused_by_the_bucket_policy"]),
    ("the stand-in's KMS allows what the role is not given", STANDIN,
     '        verdict = evaluate(principal.policies, action, key_arn, context)\n        if verdict != "allow":',
     '        verdict = "allow"\n        if verdict != "allow":',
     [TS + "test_without_kms_generate_data_key_a_write_is_refused_naming_the_key"]),
    # ---- the restore's guards ---------------------------------------------------------------------------------------
    ("the restore runs beside a writer", RUN, "    writers_stopped(settings, pods)\n    manifest = verify_set(bucket, set_id)",
     "    manifest = verify_set(bucket, set_id)",
     [TP + "test_a_restore_refuses_while_a_writer_runs_and_touches_nothing"]),
    ("a ClickHouse file missing from the set let through", RUN, "            if there is None:", "            if False:",
     [TP + "test_a_missing_clickhouse_part_leaves_arcadedb_and_clickhouse_untouched"]),
    ("the graph's zip fetched unchecked (neither the set's verify nor its own)", RUN,
     ['    """The set\'s ArcadeDB zip into `folder`, checked against its manifest before it is used; the\n    whole set verified first."""\n    manifest = verify_set(bucket, set_id)',
      '    if (size, digest) != (graph["bytes"], graph["sha256"]):'],
     ['    """The set\'s ArcadeDB zip into `folder`, checked against its manifest before it is used; the\n    whole set verified first."""\n    manifest = manifest_of(bucket, set_id)',
      '    if False:'],
     [TP + "test_a_zip_that_does_not_match_its_manifest_is_never_restored"]),
    ("a backup file's name reaching outside the claim taken", RUN, '        if "/" in name or name.startswith("."):',
     "        if False:", [TP + "test_arcadedb_reporting_no_file_is_refused_in_words"]),
    ("an unfinished set counted as finished", RUN, "        if parts[2] == MANIFEST:", "        if True:",
     [TP + "test_an_unfinished_set_is_never_restored"]),
    ("a slot run again over its finished set", RUN, '        raise BackupRefused("backup", f"take set {set_id}", "that set is already finished")',
     "        pass", [TP + "test_a_finished_slot_is_never_taken_again"]),
    # ---- the chart, round 2 (Helm, on the server) --------------------------------------------------------------------
    ("the restore's API policy ordered after the deny", CHART, "  order: 150\n", "  order: 250\n",
     [TH + "test_the_restore_alone_may_reach_the_clusters_api_before_the_egress_deny"]),
    ("the backups' Role given more than get and list", CHART, '    verbs: ["get", "list"]', '    verbs: ["get", "list", "delete"]',
     [TH + "test_the_backups_account_may_see_pods_and_nothing_else"]),
]

if __name__ == "__main__":
    sys.exit(runner.main())
