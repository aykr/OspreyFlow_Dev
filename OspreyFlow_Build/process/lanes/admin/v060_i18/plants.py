"""v0.6.0 #18's plants (ADR-148 Amendment 20; rule 15). Each is planted alone in the Conduit, the service identity's
Entra tests run, and the file restored from git. A plant counts as red only when every failing case is one it must
fail, and each of those fails.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/v060_i18/plants.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SI = "OspreyFlow_Core/services/api/service_identity.py"
PA = "OspreyFlow_Core/packages/principal_auth/__init__.py"
TEST = "tests/services/api/test_service_identity_entra.py"
REFUSED = "test_an_app_only_token_without_the_run_role_is_refused_in_words"

PLANTS = [
    ("no role required (main's shape)",
     [(SI, "        if RUN_APP_ROLE not in held:\n            raise ServiceIdentityRefused(RUN_ROLE_NOT_HELD, status=403)\n", "")],
     [f"{REFUSED}[{i}]" for i in ("no-roles-claim", "no-role", "another-role", "another-case", "a-string-not-a-list", "nested")]),
    ("the role compared without its case", [(SI, "        if RUN_APP_ROLE not in held:", "        if RUN_APP_ROLE.lower() not in [r.lower() for r in held]:")],
     [f"{REFUSED}[another-case]"]),
    ("a roles string taken for a list", [(SI, "if isinstance(roles, list) else []", "if isinstance(roles, list) else [roles] if isinstance(roles, str) else []")],
     [f"{REFUSED}[a-string-not-a-list]"]),
    ("the role named otherwise", [(PA, 'RUN_APP_ROLE = "OspreyFlow.Run"', 'RUN_APP_ROLE = "Runs.Trigger"')],
     ["test_the_run_app_role_is_principal_auths_own_name", f"{REFUSED}[another-role]",
      "test_an_app_only_token_holding_the_run_role_names_its_client", "test_an_entra_app_only_token_names_its_client",
      "test_a_v1_app_only_token_names_its_client_by_appid"]),
]


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
        for path, old, new in sites:
            text = (ROOT / path).read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{name}: {old!r} is not there exactly once"
            (ROOT / path).write_text(text.replace(old, new), encoding="utf-8")
        try:
            out = subprocess.run([str(ROOT / "OspreyFlow_Core/.venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                  TEST, "-rf", "--tb=no"], cwd=ROOT / "OspreyFlow_Build", capture_output=True, text=True,
                                 env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}).stdout
        finally:
            subprocess.run(["git", "checkout", "--", *{p for p, _, _ in sites}], cwd=ROOT, check=True)
        failed = [f.split("::", 1)[1] for f in re.findall(r"^FAILED (\S+)", out, re.M)]
        if not failed and "passed" not in out:
            sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
        missing = [m for m in must if m not in failed]
        stray = [f for f in failed if f not in must]
        red = not missing and not stray
        missed += not red
        print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed: {failed}"
              + (f"; not failed: {missing}" if missing else "") + (f"; also failed: {stray}" if stray else ""))
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
