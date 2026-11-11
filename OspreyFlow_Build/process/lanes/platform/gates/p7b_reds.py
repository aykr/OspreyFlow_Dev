"""P7b's refusals and promises (ADR-148 Amendment 5), each shown red first (rule 15), by the runner of
`p7_round1_reds.py`: each plant undoes one branch **in the file it lives in**, alone, runs the tests that
hold it (every one must fail), and writes the file back byte for byte (hash-checked). Run from
OspreyFlow_Core, on the closed offline ports, with nothing else writing the tree (the chart's plants need
Docker, for Helm):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/gates/p7b_reds.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("p7_round1_reds", HERE / "p7_round1_reds.py")
assert _spec and _spec.loader
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

B, C = "OspreyFlow_Build/", "OspreyFlow_Core/"
T_D = "../OspreyFlow_Build/tests/cp_policy_check/test_cp_decommission_check.py::"
T_CP = "../OspreyFlow_Build/tests/cp_policy_check/test_cp_policy_check.py::"
T_POC = "../OspreyFlow_Build/tests/harness/test_cloud_platform_poc.py::"
T_R = "../OspreyFlow_Build/tests/harness/test_cloud_platform_render.py::"
T_IMG = "../OspreyFlow_Build/tests/cli/test_images_verb.py::"
CHECK = C + "harness/cloud_platform/decommission_check.py"
INIT = C + "harness/cloud_platform/__init__.py"

runner.PLANTS = [
    # ---- the decommission check, each branch alone -----------------------------------------------------
    ("decommission: an object labelled ours passes", CHECK,
     "    if labels.get(PART_OF) == RELEASE or what in names:\n", "    if what in names:\n",
     [T_D + "test_a_leftover_in_the_namespace_is_named[labelled]"]),
    ("decommission: our Secret, by its name, passes", CHECK,
     "    if labels.get(PART_OF) == RELEASE or what in names:\n", "    if labels.get(PART_OF) == RELEASE:\n",
     [T_D + "test_a_leftover_in_the_namespace_is_named[our-secret]"]),
    ("decommission: a StatefulSet's claim (the selector's labels alone) passes", CHECK,
     '        return any(p.match(str(metadata.get("name"))) for p in _claim_patterns(values))\n',
     "        return False\n",
     [T_D + "test_a_leftover_in_the_namespace_is_named[statefulset-claim]"]),
    ("decommission: a volume kept after our claim passes", CHECK,
     "        if claim_is_ours:\n", "        if False:\n",
     [T_D + "test_a_volume_kept_after_its_claim_is_named"]),
    ("decommission: the Terraform state not read", CHECK,
     "        if address:\n", "        if False:\n",
     [T_D + "test_anything_left_in_the_terraform_state_is_named"]),
    ("decommission: an IAM role or policy not named as such", CHECK,
     '    if resource.startswith("aws_iam"):\n', "    if False:\n",
     [T_D + "test_anything_left_in_the_terraform_state_is_named[aws_iam_role.service]",
      T_D + "test_anything_left_in_the_terraform_state_is_named[aws_iam_policy.buckets]"]),
    ("decommission: a KMS key alias not named as such", CHECK,
     '    if resource.startswith("aws_kms_alias"):\n', "    if False:\n",
     [T_D + "test_anything_left_in_the_terraform_state_is_named[aws_kms_alias.store]"]),
    ("decommission: a bucket of ours passes", CHECK,
     "        if bucket and bucket.startswith(bucket_prefix):\n", "        if False:\n",
     [T_D + "test_a_bucket_of_this_deployment_s_is_named"]),
    ("decommission: main exits 0 with a leftover", CHECK,
     "    return 1 if found.items else 0\n", "    return 0\n",
     [T_D + "test_main_exits_1_on_a_leftover_and_0_on_none"]),
    # ---- the poc shape ----------------------------------------------------------------------------------
    ("poc: the Keeper StatefulSet still rendered", INIT,
     '        and not (poc and w["name"] == "clickhouse-keeper")\n', "",
     [T_POC + "test_one_arcadedb_one_clickhouse_and_no_keeper_of_its_own"]),
    ("poc: the server's own Keeper not configured", INIT,
     '        files["clickhouse.xml"] = embedded_keeper_clickhouse_config()\n', "",
     [T_POC + "test_the_clickhouse_server_runs_its_own_keeper"]),
    ("poc: disruption budgets rendered", INIT,
     '        if pod.get("kind") == "StatefulSet" and not poc:\n',
     '        if pod.get("kind") == "StatefulSet":\n',
     [T_POC + "test_no_disruption_budgets"]),
    ("poc: the Ingest root left on the shared claim", INIT,
     "            _onto_own_claims(pod, profile)\n", "            pass\n",
     [T_POC + "test_the_ingest_root_is_on_a_claim_of_its_own"]),
    ("schema: poc accepted in production", C + "packages/schemas/deployment.py",
     '        if self.shape == "poc" and self.environment != "development":\n', "        if False:\n",
     [T_POC + "test_the_poc_shape_is_refused_in_production"]),
    ("chart: a claim's mount named the shared volume", C + "deploy/helm/ospreyflow/templates/_helpers.tpl",
     '    - name: {{ if .claim }}{{ printf "claim-%s" .claim }}{{ else }}shared{{ end }}\n',
     "    - name: shared\n",
     [T_CP + "test_the_poc_shape_s_own_claim_is_rendered_and_mounted"]),
    ("chart: the own claims not rendered", C + "deploy/helm/ospreyflow/templates/storage.yaml",
     "{{- range .Values.storage.claims }}\n", "{{- range list }}\n",
     [T_CP + "test_the_poc_shape_s_own_claim_is_rendered_and_mounted"]),
    # ---- the orchestrator's findings of 11 November, folded in --------------------------------------------
    ("ceiling: the scheme's highest kept on the profile", INIT,
     '        environment["OSPREY_HIGHEST_MARKING"] = DEFAULT_CEILING\n', "        pass\n",
     [T_R + "test_the_ceiling_is_official_sensitive_unless_the_deployment_names_its_own"]),
    ("images: the refusal names a render command missing the packages", C + "cli/ospreyflow/images.py",
     '"OspreyFlow_Core: PYTHONPATH=.:packages .venv/bin/python -m harness.render"',
     '"OspreyFlow_Core: PYTHONPATH=. .venv/bin/python -m harness.render"',
     [T_IMG + "test_no_plan_is_refused_with_a_command_that_renders_it"]),
    ("poc: no CPU limit named", INIT,
     '    container["resources"]["limits"]["cpu"] = limit\n', "    return\n",
     [T_POC + "test_every_poc_container_names_a_cpu_limit_at_or_above_its_request"]),
    ("poc: a CPU limit below its request accepted", INIT,
     "    if _millicores(limit) < _millicores(request):\n", "    if False:\n",
     [T_POC + "test_a_cpu_limit_below_its_request_is_refused_in_words"]),
    ("poc: the OpenSearch domain still made", C + "harness/cloud_platform/terraform.py",
     '    if config.components.search is SearchBackend.OPENSEARCH and cp.shape != "poc":\n',
     "    if config.components.search is SearchBackend.OPENSEARCH:\n",
     [T_POC + "test_the_poc_shape_makes_no_opensearch_domain"]),
    ("render: an artefact's own folder not made (terraform/)", C + "harness/render.py",
     "        make_shared_folder(target.parent, under=out_dir)\n", "",
     [T_R + "test_a_first_render_into_an_empty_folder_writes_every_artefact"]),
    ("render: the plan's digests not carried forward (each tag resolved afresh)",
     C + "harness/cloud_platform/carry.py",
     "        return copied.get(image) or fallback(image)\n", "        return fallback(image)\n",
     [T_R + "test_a_tag_that_moves_between_the_two_renders_keeps_the_digest_that_was_copied"]),
    ("images: a third-party image copied by its tag alone", C + "cli/ospreyflow/images.py",
     "    if by_tag:\n", "    if False:\n",
     [T_IMG + "test_a_third_party_image_named_by_tag_alone_is_never_copied"]),
]

if __name__ == "__main__":
    sys.exit(runner.main())
