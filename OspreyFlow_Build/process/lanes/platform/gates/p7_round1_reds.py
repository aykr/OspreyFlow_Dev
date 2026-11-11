"""P7's round-1 fixes (the orchestrator's two independent reviews of 1a63953d) and the two branches round 2 found
unproven, each shown red first (rule 15).

Each plant undoes one fix, or plants one fault, **in the file the fix lives in**, in the shape that code really
had or emits, then runs the tests that hold it, which must fail; the file is then written back byte for byte
(checked by hash). The green for every test is the full run after it (`make test` at the head). Run from
OspreyFlow_Core, on the closed offline ports, with nothing else writing the tree:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/gates/p7_round1_reds.py

Prints one line per plant: RED (its tests failed, as they must) or NOT RED (a test that cannot fail for its
reason), and exits 1 if any plant was not red.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
B, C = "OspreyFlow_Build/", "OspreyFlow_Core/"
T_CP = "../OspreyFlow_Build/tests/cp_policy_check/test_cp_policy_check.py::"
T_TF = "../OspreyFlow_Build/tests/cp_policy_check/test_rendered_terraform.py::"
T_R = "../OspreyFlow_Build/tests/harness/test_cloud_platform_render.py::"
T_HELM = "../OspreyFlow_Build/tests/harness/test_helm_chart.py::"
T_JAVA = "../OspreyFlow_Build/tests/test_conduit_image_java_licence.py::"
T_MAP = "../OspreyFlow_Build/tests/services/api/test_map_admin.py::"
CHECK, INIT = B + "tools/cp_policy_check.py", C + "harness/cloud_platform/__init__.py"
TF, HELPERS = C + "harness/cloud_platform/terraform.py", C + "deploy/helm/ospreyflow/templates/_helpers.tpl"

#: (what is planted, file, old text, new text, the tests that must go red); a plant of two edits gives
#: each of old and new as a list, applied in pairs.
PLANTS: list[tuple[str, str, str | list[str], str | list[str], list[str]]] = [
    # ---- item 3: egress opened by one setting -------------------------------------------------------------
    ("open-egress: a too-wide or default-route network passes", CHECK,
     '    return too_wide_for_egress(net) or ""\n', '    return ""\n',
     [T_CP + "test_a_host_s_network_that_opens_egress_is_refused",
      T_CP + "test_managed_networks_that_open_egress_are_refused"]),
    ("open-egress: an Allow with no destination passes", CHECK,
     "            if not CALICO_DESTINATIONS & set(destination):\n", "            if False:\n",
     [T_CP + "test_an_allow_rule_with_no_destination_is_refused"]),
    ("open-egress: a Kubernetes egress rule to everywhere passes", CHECK,
     '            if not rule.get("to"):\n', "            if False:\n",
     [T_CP + "test_the_open_egress_policy_is_refused"]),
    ("schema: egress_nets of any width accepted", C + "packages/schemas/deployment.py",
     "                if why := too_wide_for_egress(net):\n", "                if why := None:\n",
     [T_R + "test_a_network_that_would_open_egress_is_refused"]),
    ("platform settings: managed/service nets of any width accepted", C + "harness/cloud_platform/settings.py",
     "        if why := too_wide_for_egress(net):\n", "        if why := None:\n",
     [T_R + "test_a_platform_s_networks_that_would_open_egress_are_refused"]),
    ("open-egress: a Kubernetes egress ipBlock of any width passes (round 2)", CHECK,
     "                if cidr and (why := _too_wide(cidr)):\n", "                if False:\n",
     [T_CP + "test_a_kubernetes_egress_address_block_that_opens_egress_is_refused"]),
    # ---- item 4: other tenants ----------------------------------------------------------------------------
    ("ingress-isolation: a pod no policy selects passes", CHECK,
     "        if not any(_matches(selector, labels) for selector in selectors):\n",
     "        if False:\n",
     [T_CP + "test_a_dropped_internal_policy_leaves_pods_open_and_is_refused"]),
    ("ingress-isolation: any namespace selector passes", CHECK,
     '                    if selector != {"matchLabels": controller}:\n', "                    if False:\n",
     [T_CP + "test_a_widened_ingress_policy_is_refused",
      T_CP + "test_an_ingress_controller_namespace_not_the_platform_s_is_refused"]),
    ("ingress-isolation: an address block passes", CHECK,
     '                if "ipBlock" in peer:\n                    yield Violation("ingress-isolation", where, '
     "f\"admits {peer['ipBlock']}\")\n",
     "                if False:\n                    pass\n",
     [T_CP + "test_a_widened_ingress_policy_is_refused"]),
    ("ingress-isolation: a rule from every source passes", CHECK,
     '            if not rule.get("from"):\n', "            if False:\n",
     [T_CP + "test_the_public_policy_admitting_every_address_is_refused"]),
    ("ingress-isolation: a Calico ingress Allow beyond a selector passes (round 2)", CHECK,
     '            if rule.get("action") == "Allow" and set(source) != {"selector"}:\n', "            if False:\n",
     [T_CP + "test_a_calico_ingress_allow_beyond_a_selector_is_refused"]),
    ("chart: ospreyflow-public rendered behind the platform's Ingress", C + "deploy/helm/ospreyflow/templates/networkpolicies.yaml",
     '{{- if not (dig "enabled" false (.Values.ingress | default dict)) }}\n', "{{- if true }}\n",
     [T_CP + "test_the_render_passes"]),
    # ---- item 6: the checksum annotations -----------------------------------------------------------------
    ("chart: the checksums unquoted (as at 1a63953d)", C + "deploy/helm/ospreyflow/templates/workloads.yaml",
     "| trunc 16 | quote }}", "| trunc 16 }}",
     [T_HELM + "test_a_checksum_of_digits_alone_is_still_text"]),
    # ---- item 7: the Ingress for the WebSocket and uploads --------------------------------------------------
    ("ingress: no timeouts rendered", INIT,
     '        annotations[nginx + directive.replace("_", "-")] = str(seconds)\n', "        pass\n",
     [T_R + "test_the_ingress_keeps_the_glass_s_websocket_open_and_takes_its_uploads"]),
    ("ingress: no body size rendered", INIT,
     '    annotations[nginx + "proxy-body-size"] = _nginx_size(upload_cap_bytes(environment))\n', "",
     [T_R + "test_the_ingress_keeps_the_glass_s_websocket_open_and_takes_its_uploads"]),
    ("ingress: the deployment's upload cap read as a bare int (round 2: 0 became 0m, no limit)", INIT,
     "    if given > 0:\n        return given\n",
     "    if UPLOAD_CAP_VARIABLE in environment:\n        return int(environment[UPLOAD_CAP_VARIABLE])\n",
     [T_R + "test_the_ingress_reads_the_upload_cap_as_the_conduit_does"]),
    ("ingress: the upload cap's source bound at import (the defect the test found)", INIT,
     "def upload_cap_bytes(environment: dict[str, Any], path: Path | None = None) -> int:\n",
     "def upload_cap_bytes(environment: dict[str, Any], path: Path | None = CONDUIT_UPLOADS) -> int:\n",
     [T_R + "test_the_ingress_s_settings_follow_their_sources"]),
    # ---- item 8: fsGroupChangePolicy --------------------------------------------------------------------
    ("chart: no fsGroupChangePolicy (as at 1a63953d)", HELPERS,
     "  fsGroupChangePolicy: OnRootMismatch\n", "",
     [T_CP + "test_the_render_passes"]),
    ("fs-group-walk: an fsGroup walked at every start passes", CHECK,
     '    if "fsGroup" in pod and pod.get("fsGroupChangePolicy") != "OnRootMismatch":\n', "    if False:\n",
     [T_CP + "test_a_volume_walk_at_every_start_is_refused"]),
    # ---- item 11: resources -------------------------------------------------------------------------------
    ("chart: resources not rendered", HELPERS,
     "  resources: {{ toJson . }}\n", "",
     [T_CP + "test_the_render_passes"]),
    ("no-resources: a container without them passes", CHECK,
     "        if missing:\n", "        if False:\n",
     [T_CP + "test_a_container_without_resources_is_refused"]),
    ("render: no resources on a container", INIT,
     '            container["resources"] = _resources(\n'
     '                profile, pod["name"] if container is pod else container["name"]\n            )\n',
     "",
     [T_R + "test_every_container_asks_for_what_it_needs_and_is_limited"]),
    ("render: ArcadeDB's heap not from its limit", INIT,
     '        if pod["name"] == "arcadedb":\n            _heap_from_the_limit(pod, profile)\n', "",
     [T_R + "test_arcadedb_s_heap_follows_its_memory_limit"]),
    # ---- the ownership rulings: extension points as data --------------------------------------------------
    ("render: an image of ours with no row is a bare KeyError", INIT,
     "            if built is None:\n", "            if False:\n",
     [T_R + "test_an_image_of_ours_with_no_build_row_is_refused_in_words"]),
    ("render: group 0 a constant, not the row", INIT,
     '        if pod["name"] in profile.group_zero:\n', '        if pod["name"] == "keycloak":\n',
     [T_R + "test_a_door_group_zero_and_an_always_host_are_rows"]),
    ("render: the always-hosts constants, not the rows", INIT,
     "    hosts = [host.format(region=platform.aws_region) for host in profile.egress.always]\n",
     '    hosts = [f"s3.{platform.aws_region}.amazonaws.com", f"sts.{platform.aws_region}.amazonaws.com"]\n',
     [T_R + "test_a_door_group_zero_and_an_always_host_are_rows"]),
    # ---- minors: another profile's config ------------------------------------------------------------------
    ("cp_policy_check: another profile's config is a bare AttributeError", CHECK,
     "    if cloud is None:\n", "    if False:\n",
     [T_CP + "test_a_configuration_of_another_profile_is_refused_in_words"]),
    # ---- item 9: the Conduit without Java -----------------------------------------------------------------
    ("Dockerfile: the upgrade after the code, as root (round 2, item 5: the shape at dd0233e1)", C + "services/api/Dockerfile",
     ["RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*\n\n",
      'ENTRYPOINT ["uvicorn", "services.api.app:app", "--host", "0.0.0.0", "--port", "8000"]\n'],
     ["\n",
      'ENTRYPOINT ["uvicorn", "services.api.app:app", "--host", "0.0.0.0", "--port", "8000"]\n'
      "USER root\nRUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*\nUSER 10001:10001\n"],
     [T_JAVA + "test_the_final_stage_upgrades_before_the_code_and_as_root"]),
    ("Dockerfile: the omitted image given JAVA_HOME", C + "services/api/Dockerfile",
     'FROM python:3.12-slim AS runtime-omitted\nLABEL org.ospreyflow.runtime.java.included="omitted"\n',
     'FROM python:3.12-slim AS runtime-omitted\nLABEL org.ospreyflow.runtime.java.included="omitted"\nENV JAVA_HOME="/opt/java"\n',
     [T_JAVA + "test_the_omitted_image_does_not_declare_java"]),
    ("Dockerfile: the omission's stage Java's (a red record for an older test)", C + "services/api/Dockerfile",
     "FROM python:3.12-slim AS runtime-omitted\n", "FROM runtime-included AS runtime-omitted\n",
     [T_JAVA + "test_the_cloud_platform_s_build_carries_no_java"]),
    ("profile.yaml: the Conduit planned with Java (a red record for an older test)",
     C + "harness/cloud_platform/profile.yaml",
     "build_args: {CONDUIT_JAVA: omitted}", "build_args: {}",
     [T_R + "test_the_conduit_is_planned_without_java"]),
    # ---- item 10: Admin › Maps' words --------------------------------------------------------------------
    ("map_admin: a route that does not exist offered again", C + "services/api/map_admin.py",
     '"can, the map uses its providers alone."',
     '"can, the map uses its providers alone. Or run `ospreyflow map build` and copy the tiles into the '
     'tiles bucket."',
     [T_MAP + "test_on_a_cloud_platform_the_build_says_there_is_no_basemap_route_yet"]),
    # ---- the Terraform minors ----------------------------------------------------------------------------
    ("terraform: a provider block rendered", TF,
     '    files["variables.tf"] = _file(\n',
     '    files["main.tf"] = \'provider "aws" {\\n  region = "eu-west-2"\\n}\\n\'\n    files["variables.tf"] = _file(\n',
     [T_TF + "test_the_providers_and_backend_are_the_namespace_folder_s"]),
    ("terraform: no :aud condition", TF,
     "(\"variable\", '\"${var.eks_oidc_issuer}:aud\"'),", "(\"variable\", '\"${var.eks_oidc_issuer}:sub\"'),",
     [T_TF + "test_the_bucket_role_trusts_the_service_account_s_tokens_for_sts_alone"]),
    ("terraform: OpenSearch with no security group", TF,
     '                                ("security_group_ids", "[aws_security_group.search.id]"),\n', "",
     [T_TF + "test_opensearch_is_reached_from_the_namespace_s_networks_by_the_bucket_role_alone"]),
    ("terraform: a secret key the values read and the Terraform does not write (an older test)", TF,
     '                    pg["host"]: "aws_db_instance.postgres.address",\n',
     '                    "rds_host": "aws_db_instance.postgres.address",\n',
     [T_R + "test_every_secret_the_values_read_is_one_the_terraform_writes"]),
]

PORTS = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
         "CLICKHOUSE_HTTP_PORT": "59994"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    not_red = 0
    for what, relative, old, new, tests in PLANTS:
        path = ROOT / relative
        original = path.read_bytes()
        before = _digest(path)
        text = original.decode("utf-8")
        olds, news = ([old], [new]) if isinstance(old, str) else (old, new)
        if missing := [o for o in olds if text.count(o) != 1]:
            print(f"NOT PLANTED  {what}: its text is not once in {relative}: {missing[0][:80]!r}")
            not_red += 1
            continue
        for o, n in zip(olds, news, strict=True):
            text = text.replace(o, n)
        try:
            path.write_text(text, encoding="utf-8")
            done = subprocess.run(
                [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:cacheprovider",
                 "--no-header", "-rf", "--tb=short", *tests],
                capture_output=True, text=True, env={**os.environ, **PORTS}, check=False,
            )  # fmt: skip
        finally:
            path.write_bytes(original)
        assert _digest(path) == before, f"{relative} was not restored"
        failed = [line for line in done.stdout.splitlines() if line.startswith("FAILED")]
        # Each failure's own text (its assertion or error lines), in full: the record shows why it failed.
        reasons = [line for line in done.stdout.splitlines() if line.startswith("E ")]
        summary = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else done.stderr[-200:]
        if done.returncode == 0 or not failed:
            not_red += 1
            print(f"NOT RED  {what}\n    {summary}")
        else:
            print(f"RED      {what}  [{relative}]\n    {summary}")
            for line in failed:
                print(f"    {line}")
            for line in reasons:
                print(f"      {line}")
    print(f"\n{len(PLANTS)} plants, {len(PLANTS) - not_red} red, {not_red} not red")
    return 1 if not_red else 0


if __name__ == "__main__":
    sys.exit(main())
