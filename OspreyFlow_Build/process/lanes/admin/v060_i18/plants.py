"""v0.6.0 #18's plants (ADR-148 Amendment 20; rule 15). Each is planted alone, its tests run, and the file restored.
A plant counts as red only when every failing case is one it must fail, and each of those fails.

- The Conduit's plants go in `service_identity.py`, the service identity's Entra tests run, and the file is restored
  from git.
- R1's plants go in platform's `r1_kind.py`, which this branch does not carry. The script applies `r1_proof.diff`
  first, runs R1's driver tests with each plant, restores each from the applied text, and takes the diff off again.

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
TEST = "tests/services/api/test_service_identity_entra.py"
REFUSED = f"{TEST}::test_an_app_only_token_without_the_run_role_is_refused_in_words"
CASES = ("no-roles-claim", "no-role", "another-role", "another-case", "a-string-not-a-list", "nested")

PLANTS = [
    ("no role required (main's shape)",
     [(SI, "        if RUN_APP_ROLE not in held:\n            raise ServiceIdentityRefused(RUN_ROLE_NOT_HELD, status=403)\n", "")],
     [f"{REFUSED}[{i}]" for i in CASES] + [f"{TEST}::test_a_v1_app_only_token_without_the_run_role_is_refused_in_words"]),
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
     [f"{TEST}::test_a_dashboard_identity_holding_its_role_alone_is_told_it_is_a_dashboards"]),
    # The role's name is not planted: renamed, it fails nearly every case of the file (the words name it, every
    # admitted token holds it), so a plant could not tell its own red from the rest. The name's own case guards it.
]

R1 = "OspreyFlow_Build/process/lanes/platform/gates/r1_kind.py"
R1_TESTS = ["tests/test_r1_kind_domain_guard.py", "tests/test_r1_entra_standin.py"]
GUARD = "tests/test_r1_kind_domain_guard.py::"
V060 = f"{GUARD}test_a_v060_release_has_its_run_api_role_checked_with_the_standins_tokens"
UNASSIGNED_REFUSED = "r.status_code == 403 and \"does not hold this API's OspreyFlow.Run app role\" in r.text"
R1_PLANTS = [
    ("R1 asks every release for the role (no gate by release)",
     [(R1, "    if runs_role_release(c, admin):", "    if True:")],
     [f"{GUARD}test_a_release_before_v060_skips_the_run_api_role_in_words"]),
    ("R1 skips the role on every release",
     [(R1, "    if runs_role_release(c, admin):", "    if False:")],
     [f"{V060}[{v}]" for v in ("v0.6.0", "0.7.1", "None", "unreleased")]),
    ("R1 takes an unreadable version for an old release",
     [(R1, "    if len(parts) < 2 or not all(p.isdigit() for p in parts):\n        return True",
       "    if len(parts) < 2 or not all(p.isdigit() for p in parts):\n        return False")],
     [f"{V060}[{v}]" for v in ("None", "unreleased")]),
    ("R1 lets the unassigned application in",
     [(R1, UNASSIGNED_REFUSED, "True")],
     [f"{GUARD}test_a_run_api_letting_an_application_without_the_role_in_fails_the_checks"]),
    # Not planted: a check that takes any refusal of the unassigned application without reading its words. The fake
    # door refuses in the words, so that check still passes. The words themselves are held by the Conduit's own
    # test of RUN_ROLE_NOT_HELD, and on R1 by the live run.
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
    diff = Path(__file__).with_name("r1_proof.diff")
    subprocess.run(["git", "apply", str(diff)], cwd=ROOT, check=True)
    try:
        applied = (ROOT / R1).read_text(encoding="utf-8")
        for name, sites, must in R1_PLANTS:
            missed += not run(name, sites, must, R1_TESTS, env,
                              lambda paths: [(ROOT / p).write_text(applied, encoding="utf-8") for p in paths])
    finally:
        subprocess.run(["git", "apply", "-R", str(diff)], cwd=ROOT, check=True)
    print(f"plants: {len(PLANTS) + len(R1_PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
