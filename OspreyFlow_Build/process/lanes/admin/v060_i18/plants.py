"""v0.6.0 #18's plants (ADR-148 Amendment 20; rule 15). Each is planted alone, its tests run, and the file restored.
A plant counts as red only when every failing case is one it must fail, and each of those fails.

- The Conduit's plants go in `service_identity.py`, the service identity's Entra tests run, and the file is restored
  from git.
- R1's plants go in platform's `r1_kind.py`, and the guide's in the guide, the poc manifest and the runbook. This
  branch carries none of them, so the script applies `r1_proof.diff` (then `registration_and_guide.diff`) first,
  runs their tests with each plant, restores each from the applied text, and takes the diff off again.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/v060_i18/plants.py
"""
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SI = "OspreyFlow_Core/services/api/service_identity.py"
APP = "OspreyFlow_Core/services/api/app.py"
TEST = "tests/services/api/test_service_identity_entra.py"
REFUSED = f"{TEST}::test_an_app_only_token_without_the_run_role_is_refused_in_words"
DOOR = f"{TEST}::test_the_run_api_refuses_a_client_registered_as_a_dashboard_identity"
CASES = ("no-roles-claim", "no-role", "another-role", "another-case", "a-string-not-a-list", "nested")

PLANTS = [
    ("no role required (main's shape)",
     [(SI, "        if RUN_APP_ROLE not in held:\n            raise ServiceIdentityRefused(RUN_ROLE_NOT_HELD, status=403, client=client)\n", "")],
     [f"{REFUSED}[{i}]" for i in CASES] + [f"{TEST}::test_a_v1_app_only_token_without_the_run_role_is_refused_in_words",
                                           f"{DOOR}[no-role-not-a-dashboard]"]
     + [f"{TEST}::test_the_run_api_door_with_a_store_answering_none_or_too_slowly[no-role-store-{w}]"
        for w in ("answers-none", "too-slow")]),
    ("the role compared without its case",
     [(SI, "        if RUN_APP_ROLE not in held:", "        if RUN_APP_ROLE.lower() not in [r.lower() for r in held]:")],
     [f"{REFUSED}[another-case]"]),
    ("a roles string taken for a list",
     [(SI, "if isinstance(roles, list) else []", "if isinstance(roles, list) else [roles] if isinstance(roles, str) else []")],
     [f"{REFUSED}[a-string-not-a-list]"]),
    ("the run role asked before the dashboards' role",
     [(SI, '        roles = claims.get("roles")\n',
       '        roles = claims.get("roles")\n'
       "        if RUN_APP_ROLE not in (roles if isinstance(roles, list) else []):\n"
       "            raise ServiceIdentityRefused(RUN_ROLE_NOT_HELD, status=403)\n")],
     # the planted refusal names no client, so a registered dashboard holding no role is not told it is one either
     [f"{TEST}::test_a_dashboard_identity_holding_its_role_alone_is_told_it_is_a_dashboards",
      f"{DOOR}[no-role-registered-dashboard]"]),
    ("a registered dashboard holding no role told to grant itself the run role",
     [(APP, "        if refused.client is not None:\n            try:", "        if False:\n            try:")],
     [f"{DOOR}[no-role-registered-dashboard]"]),
    ("a run-role refusal turned into a 503 when the registrations cannot be read",
     [(APP, "            except HTTPException as answer:\n                if answer.status_code != 503:\n                    raise\n",
       "            except HTTPException:\n                raise\n")],
     [f"{TEST}::test_the_run_api_door_with_a_store_answering_none_or_too_slowly[no-role-store-too-slow]"]),
    # The role's name is not planted: renamed, it fails nearly every case of the file (the words name it, every
    # admitted token holds it), so a plant could not tell its own red from the rest. The name's own case guards it.
]

#: test_a_run_api_answering_wrongly_fails_the_checks's ids: what the fake run API gets wrong.
WRONG_IDS = ["unassigned-in", "orchestrator-out", "dashboard-in", "ingress-404"]
R1 = "OspreyFlow_Build/process/lanes/platform/gates/r1_kind.py"
R1_TESTS = ["tests/test_r1_kind_domain_guard.py", "tests/test_r1_entra_standin.py"]
GUARD = "tests/test_r1_kind_domain_guard.py::"
V060 = f"{GUARD}test_a_v060_release_has_its_run_api_role_checked_with_the_standins_tokens"
WRONG = f"{GUARD}test_a_run_api_answering_wrongly_fails_the_checks"
UNISSUED = f"{GUARD}test_a_token_the_standin_will_not_issue_is_a_fail_in_the_record"
INPOD = "tests/test_r1_entra_standin.py::test_r1s_in_pod_token_fetch_gets_a_token_and_says_a_refusal_whole"
R1_PLANTS = [
    ("R1 asks every release for the role (no gate by release)",
     [(R1, "    if runs_role_release(c, admin):", "    if True:")],
     [f"{GUARD}test_a_release_before_v060_skips_the_run_api_role_in_words"]),
    ("R1 skips the role on every release",
     [(R1, "    if runs_role_release(c, admin):", "    if False:")],
     # skipped, nothing asks the run API, so no wrong answer and no unissued token can fail the checks either
     [f"{V060}[{v}]" for v in ("v0.6.0", "0.7.1", "None", "unreleased")]
     + [f"{WRONG}[{w}]" for w in WRONG_IDS] + [UNISSUED]),
    ("R1 takes an unreadable version for an old release",
     [(R1, "    if len(parts) < 2 or not all(p.isdigit() for p in parts):\n        return True",
       "    if len(parts) < 2 or not all(p.isdigit() for p in parts):\n        return False")],
     [f"{V060}[{v}]" for v in ("None", "unreleased")]),
    ("R1 lets the unassigned application in",
     [(R1, "r.status_code == 403 and RUN_ROLE_WORDS in r.text", "True")],
     [f"{WRONG}[unassigned-in]"]),
    ("R1 takes any answer for the granted orchestrator",
     [(R1, "r.status_code == 404 and RUN_NOT_FOUND in r.text", "True")],
     [f"{WRONG}[orchestrator-out]", f"{WRONG}[ingress-404]"]),
    ("R1 takes any 404 for the granted orchestrator",
     [(R1, "r.status_code == 404 and RUN_NOT_FOUND in r.text", "r.status_code == 404")],
     [f"{WRONG}[ingress-404]"]),
    ("R1 lets the dashboard identity in",
     [(R1, "r.status_code == 403 and DASHBOARD_WORDS in r.text", "True")],
     [f"{WRONG}[dashboard-in]"]),
    ("R1 lets a token the stand-in will not issue exit unrecorded",
     [(R1, '            ok(f"the Entra stand-in issues {name} its token", False, refusal_words(refused))', "            raise")],
     [UNISSUED]),
    ("R1 records the head of sh()'s message (the command), not the refusal",
     [(R1, '    return (output.splitlines() or [""])[0][:300]', '    return said[:300]')],
     [UNISSUED, INPOD]),
    ("R1's record takes every line kubectl adds",
     [(R1, '    return (output.splitlines() or [""])[0][:300]', '    return output[:300]')],
     [UNISSUED]),
    ("the in-pod fetch lets a refusal out as a traceback",
     [(R1, "except urllib.error.HTTPError as refused:", "except KeyError as refused:")],
     [INPOD]),
    # Not planted: R1's words drifting from the Conduit's. `test_the_checks_words_are_the_conduits_own` reads both,
    # and the plants above already change what the checks read.
]

GUIDE = "OspreyFlow_Core/docs/administration-guide.md"
MANIFEST = "OspreyFlow_Core/harness/cloud_platform/poc_manifest.yaml"
RUNBOOKS = "OspreyFlow_Core/harness/cloud_platform/runbooks.py"
GUIDE_TESTS = ["tests/test_admin_guide_run_app_role.py", "tests/harness/test_cloud_platform_poc.py",
               "tests/test_guide_poc_manifest.py", "tests/test_admin_guide_copies.py"]
GT = "tests/test_admin_guide_run_app_role.py::"
POC = "tests/harness/test_cloud_platform_poc.py::test_the_install_says_how_an_orchestrator_is_granted_the_run_role"
GUIDE_PLANTS = [
    ("the guide's first-draft words, the wrong blade",
     [(GUIDE, "add it to the orchestrator's own registration (API\n  permissions, this API, Application permissions) and grant admin consent, then ask for a new\n  token\".",
       "assign it to the application (the API's registration,\n  App roles), then sign in again\".")],
     [f"{GT}test_the_guide_quotes_the_run_apis_own_refusal", f"{GT}test_the_first_drafts_wrong_blade_is_gone",
      # spec/10 is the guide's copy, so a guide changed alone is no longer level with it
      "tests/test_admin_guide_copies.py::test_the_specification_s_copy_is_the_shipped_guide_from_section_1"]),
    ("the manifest's API registration without the run role",
     [(MANIFEST, "app_roles: [Dashboard.Read, OspreyFlow.Run]", "app_roles: [Dashboard.Read]")],
     [f"{GT}test_the_guide_and_the_manifest_name_principal_auths_role",
      "tests/test_guide_poc_manifest.py::test_section_6a2_s_poc_tables_are_the_manifest_s"]),
    ("the runbook's paragraph said only with reporting on",
     [(RUNBOOKS, "    parts.append(\n        \"**For an orchestrator that runs pipelines**",
       "    if config.reporting.sync:\n      parts.append(\n        \"**For an orchestrator that runs pipelines**")],
     [f"{POC}[reporting-off-id-uri-default]", f"{POC}[reporting-off-id-uri-set]"]),
    # The CLI's scope (the owner's word beside #18), said in the same diff.
    ("the guide's run row without the CLI's scope",
     [(GUIDE, "by client credentials, and on Entra ID `OSPREY_TOKEN_SCOPE`, the API's application ID URI followed by `/.default`)",
       "by client credentials)")],
     [f"{GT}test_the_guide_says_the_cli_sends_the_apis_scope_on_entra",
      "tests/test_admin_guide_copies.py::test_the_specification_s_copy_is_the_shipped_guide_from_section_1"]),
    ("the install without the orchestrator's token scope",
     [(RUNBOOKS, "`OSPREY_TOKEN_SCOPE` to\\n\"\n        f\"`{claims.id_uri}/.default`",
       "`OSPREY_TOKEN_SCOPE` to\\n\"\n        f\"`the API's scope`")],
     [f"{POC}[{r}-id-uri-{u}]" for r in ("reporting-on", "reporting-off") for u in ("default", "set")]),
    ("the install's scope always api://<id>, whatever the ID URI",
     [(RUNBOOKS, "f\"`{claims.id_uri}/.default`", "f\"`api://{claims.api_client_id}/.default`")],
     [f"{POC}[reporting-on-id-uri-set]", f"{POC}[reporting-off-id-uri-set]"]),
]

Restore = Callable[[set[str]], object]


def run(name: str, sites: list[tuple[str, str, str]], must: list[str], tests: list[str], env: dict[str, str],
        restore: Restore) -> bool:
    for path, old, new in sites:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert text.count(old) == 1, f"{name}: {old!r} is not there exactly once"
        (ROOT / path).write_text(text.replace(old, new), encoding="utf-8")
    try:
        out = subprocess.run([str(ROOT / "OspreyFlow_Core/.venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                              *tests, "-rf", "--tb=no"], cwd=ROOT / "OspreyFlow_Build", capture_output=True, text=True,
                             env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}).stdout
    finally:
        restore({p for p, _, _ in sites})
    failed = re.findall(r"^FAILED (\S+)", out, re.M)
    if not failed and "passed" not in out:
        sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
    missing = [m for m in must if m not in failed]
    stray = [f for f in failed if f not in must]
    red = not missing and not stray
    print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed: {failed}"
          + (f"; not failed: {missing}" if missing else "") + (f"; also failed: {stray}" if stray else ""))
    return red


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# v0.6.0 #18 plants at {head}")
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | {
        "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
        "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
    missed = 0
    for name, sites, must in PLANTS:
        missed += not run(name, sites, must, [TEST], env,
                          lambda paths: subprocess.run(["git", "checkout", "--", *paths], cwd=ROOT, check=True))
    for diff_name, plants, tests in (("r1_proof.diff", R1_PLANTS, R1_TESTS),
                                     ("registration_and_guide.diff", GUIDE_PLANTS, GUIDE_TESTS)):
        diff = Path(__file__).with_name(diff_name)
        subprocess.run(["git", "apply", str(diff)], cwd=ROOT, check=True)
        try:
            applied = {p: (ROOT / p).read_text(encoding="utf-8") for _, sites, _ in plants for p, _, _ in sites}
            for name, sites, must in plants:
                missed += not run(name, sites, must, tests, env,
                                  lambda paths: [(ROOT / p).write_text(applied[p], encoding="utf-8") for p in paths])
        finally:
            subprocess.run(["git", "apply", "-R", str(diff)], cwd=ROOT, check=True)
    print(f"plants: {len(PLANTS) + len(R1_PLANTS) + len(GUIDE_PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
