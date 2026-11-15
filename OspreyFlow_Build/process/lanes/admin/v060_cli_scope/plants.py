"""v0.6.0's CLI scope (the owner's word beside #18; rule 15): `service_token` on Entra ID. Each plant goes alone in
`cli/ospreyflow/conduit_client.py`, the client's tests run, and the file is restored from git. A plant counts as red
only when every failing case is one it must fail, and each of those fails.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/v060_cli_scope/plants.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CC = "OspreyFlow_Core/cli/ospreyflow/conduit_client.py"
TEST = "tests/cli/test_conduit_client.py"
BARE = f"{TEST}::test_on_entra_a_missing_or_bare_scope_is_refused_in_words_naming_the_setting"
GRANTED = f"{TEST}::test_on_entra_the_service_identity_asks_for_the_apis_default_scope"
OTHER = f"{TEST}::test_on_entra_another_apis_scope_is_refused_in_words_naming_the_setting"
KEYCLOAK = f"{TEST}::test_keycloak_is_asked_as_before_with_no_scope"

PLANTS = [
    ("no scope sent (main's shape)",
     [(CC, '    if scope:\n        form["scope"] = scope\n', "")],
     [GRANTED, OTHER]),
    ("a scope always sent, empty with none set",
     [(CC, '    if scope:\n        form["scope"] = scope\n', '    form["scope"] = scope\n')],
     [KEYCLOAK]),
    ("Entra's missing-scope refusal in the generic words",
     [(CC, "        if 1002012 in codes:", "        if False:")],
     [f"{BARE}[{i}]" for i in ("unset", "empty", "no-default-suffix", "a-delegated-scope")]),
    ("Entra's unknown-resource refusal in the generic words",
     [(CC, "        if 500011 in codes:", "        if False:")],
     [OTHER]),
]


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# v0.6.0 CLI scope plants at {head}")
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
            out = subprocess.run([str(ROOT / "OspreyFlow_Core/.venv/bin/python"), "-m", "pytest", "-q", "-p",
                                  "no:cacheprovider", TEST, "-rf", "--tb=no"], cwd=ROOT / "OspreyFlow_Build",
                                 capture_output=True, text=True,
                                 env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}).stdout
        finally:
            subprocess.run(["git", "checkout", "--", *{p for p, _, _ in sites}], cwd=ROOT, check=True)
        failed = re.findall(r"^FAILED (\S+)", out, re.M)
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
